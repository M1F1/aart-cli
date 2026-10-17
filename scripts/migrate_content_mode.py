#!/usr/bin/env python3
"""Rewrite an aart-cli 0.9.x Registry checkout so aart-cli 0.10.0 can read it.

aart-cli 0.10.0 renamed the content mode (CP-31 step 13, D-376):

  key   promotion_mode -> content_mode       (registry/versions, registry/promotions, index, snapshot)
  value vendored       -> self-contained
  value referenced     -> pinned-reference   (also `source_mode` in references/**)

Rewriting references/** changes the Registry content digest (it covers artifacts/ and
references/), so every record that binds the old digest is rebound to the new one.

Usage (from anywhere; stdlib only, Python 3.10+):

  python3 migrate_content_mode.py REGISTRY_CHECKOUT           dry run: says what would change
  python3 migrate_content_mode.py REGISTRY_CHECKOUT --write   rewrites the files in place

The checkout must be clean (`git status` empty). Nothing is committed or pushed. Afterwards run
`aart-cli registry validate --source .`, review `git diff`, and commit/push through your normal
review flow.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

_VALUES = {"vendored": "self-contained", "referenced": "pinned-reference"}
_MODE_KEYS = ("content_mode", "source_mode")
_DIGEST_KEYS = ("registry_snapshot", "registry_snapshot_after", "registry_snapshot_before")


def _canonical(value: object) -> str:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _migrate(value: object, digests: dict[str, str]) -> object:
    if isinstance(value, list):
        return [_migrate(item, digests) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, object] = {}
    for key, item in value.items():
        if key == "promotion_mode":
            if "content_mode" in value:
                raise ValueError("record has both promotion_mode and content_mode")
            key = "content_mode"
        if key in _MODE_KEYS and isinstance(item, str):
            item = _VALUES.get(item, item)
        if key in _DIGEST_KEYS and isinstance(item, str):
            item = digests.get(item, item)
        result[key] = _migrate(item, digests)
    return result


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(("git", "-C", str(root), *args), check=True, capture_output=True).stdout


def _frame(data: bytes) -> bytes:
    return len(data).to_bytes(8, "big") + data


def _content_digest(root: Path, contents: dict[str, bytes]) -> str:
    """AART-TREE-V1 over the tracked files under artifacts/ and references/ (registry_state_digest)."""

    modes = {}
    for line in _git(root, "ls-files", "-s", "-z", "--", "artifacts", "references").split(b"\0"):
        if line:
            meta, path = line.split(b"\t", 1)
            modes[path.decode("utf-8")] = meta.split(b" ")[0]
    records = []
    for path in sorted(modes):
        if modes[path] not in (b"100644", b"100755"):
            continue
        content = contents.get(path)
        if content is None:
            content = (root / path).read_bytes()
        records.append(
            b"F"
            + _frame(path.encode("utf-8"))
            + (b"\x01" if modes[path] == b"100755" else b"\x00")
            + len(content).to_bytes(8, "big")
            + hashlib.sha256(content).digest()
        )
    payload = b"AART-TREE-V1\x00" + b"".join(_frame(record) for record in records)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _rewrite(root: Path, top: str, digests: dict[str, str]) -> dict[str, bytes]:
    """New bytes for every JSON file under `top` that changes; refuses non-canonical input."""

    changed: dict[str, bytes] = {}
    base = root / top
    if not base.is_dir():
        return changed
    for path in sorted(base.rglob("*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        value = json.loads(text)
        body = text.rstrip("\n")
        if body != _canonical(value):
            raise ValueError(f"{relative} is not canonical JSON; it was not written by aart-cli")
        new = _canonical(_migrate(value, digests))
        if new != body:
            changed[relative] = (new + text[len(body) :]).encode("utf-8")
    return changed


def _recorded_snapshots(root: Path) -> set[str]:
    found = set()
    for path in (root / "registry" / "versions").rglob("*.json"):
        found.add(json.loads(path.read_text(encoding="utf-8"))["registry_snapshot"])
    return found


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2) or (len(argv) == 2 and argv[1] != "--write"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    root = Path(argv[0]).resolve()
    write = len(argv) == 2
    if not (root / "aart-cli-registry.json").is_file():
        print(
            f"error: {root} is not a Registry checkout (no aart-cli-registry.json)", file=sys.stderr
        )
        return 2
    if _git(root, "status", "--porcelain"):
        print(
            "error: the checkout has uncommitted changes; commit or stash them first",
            file=sys.stderr,
        )
        return 2
    try:
        references = _rewrite(root, "references", {})
        old = _content_digest(root, {})
        recorded = _recorded_snapshots(root)
        if recorded and recorded != {old}:
            print(
                "error: the version records do not bind this checkout's content digest "
                f"(records: {sorted(recorded)}, computed: {old}); run `registry validate` "
                "with aart-cli 0.9.x first",
                file=sys.stderr,
            )
            return 1
        new = _content_digest(root, references)
        records = _rewrite(root, "registry", {old: new} if old != new else {})
    except (ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    changes = {**references, **records}
    for relative in sorted(changes):
        print(("rewrote " if write else "would rewrite ") + relative)
        if write:
            (root / relative).write_bytes(changes[relative])
    if old != new:
        print(f"content digest {old} -> {new}")
    print(f"{len(changes)} file(s) {'rewritten' if write else 'to rewrite (dry run; add --write)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
