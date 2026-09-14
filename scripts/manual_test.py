#!/usr/bin/env python3
"""Create, open and safely discard an isolated AART manual-test ecosystem."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from agent_artifacts.application.maintainer import reconcile_source_scan
from agent_artifacts.application.promotion import (
    PromotionEvidence,
    load_registry_versions,
    plan_bulk_promotion,
    project_promotion,
)
from agent_artifacts.domain.candidates import assess_candidate
from agent_artifacts.domain.identifiers import ObjectDigest, SourceAlias
from agent_artifacts.domain.registry import PromotionMode
from agent_artifacts.domain.result import Ok
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.protocol.native_tree import (
    SnapshotEntry,
    SnapshotEntryKind,
    SnapshotOrigin,
    SourceSnapshot,
)
from agent_artifacts.protocol.paths import parse_relative_path

MARKER = ".aart-manual-lab.json"
SCHEMA = 1
CHECKOUT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path("/tmp/aart-cli-manual-lab")


@dataclass(frozen=True, slots=True)
class ManualLab:
    root: Path
    run_id: str
    branch: str


def _run(argv: tuple[str, ...], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{' '.join(argv[:3])} failed in {cwd}: {detail}")
    return completed.stdout.strip()


def _git(repo: Path, *args: str) -> str:
    return _run(("git", *args), cwd=repo)


def _safe_root(raw: Path) -> Path:
    root = raw.expanduser().resolve()
    if root in {Path("/"), Path.home().resolve(), CHECKOUT} or len(root.parts) < 3:
        raise ValueError(f"manual-test root is too broad: {root}")
    return root


def _marker(root: Path) -> dict[str, object]:
    marker = root / MARKER
    if not marker.is_file() or marker.is_symlink():
        # The way out has to be in the message, and it has to be a way out that works.  An
        # installed payload is delivered read-only, directories included, so a bare `rm -rf` stops
        # at the first artifact root with "Permission denied" -- after it has already removed the
        # marker, which is how a lab arrives here in the first place.  `reset_lab` restores the
        # write bit as it goes; a human doing this by hand has to be told to do the same.
        raise ValueError(
            f"refusing to touch unmarked directory: {root}\n"
            f"Nothing here is owned by a manual-test lab, so it is not this tool's to remove. "
            f"If it is a leftover lab, look at it and then remove it yourself -- installed "
            f"payloads are read-only, so the write bit has to come back first:\n"
            f"  chmod -R u+w {root} && rm -rf {root}"
        )
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA or data.get("root") != str(root):
        raise ValueError(f"manual-test marker does not own this exact directory: {root}")
    return data


def reset_lab(raw_root: Path) -> None:
    root = _safe_root(raw_root)
    if not root.exists():
        return
    _marker(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"manual-test root is not a real directory: {root}")

    def remove_read_only(function, path: str, _error) -> None:
        observed = os.lstat(path)
        if stat.S_ISLNK(observed.st_mode):
            function(path)
            return
        os.chmod(path, observed.st_mode | stat.S_IWUSR)
        function(path)

    # The marker goes last.  `rmtree` walks in directory order, so a removal that fails partway
    # through -- one unreadable file, one mount that went away -- could take the marker with it and
    # leave a half-deleted lab that this function then refuses to finish, permanently.  Removing
    # the contents first and the marker only once they are gone means a failed reset always leaves
    # a lab that is still owned and still resettable.
    for entry in root.iterdir():
        if entry.name == MARKER:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, onerror=remove_read_only)
        else:
            entry.unlink()
    shutil.rmtree(root, onerror=remove_read_only)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _initialize_repository(repo: Path, branch: str) -> None:
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", branch)
    _git(repo, "config", "user.name", "AART Manual Test")
    _git(repo, "config", "user.email", "manual-test@aart.invalid")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _publish_bare(repo: Path, remote: Path, branch: str) -> None:
    remote.parent.mkdir(parents=True, exist_ok=True)
    _run(("git", "clone", "--bare", str(repo), str(remote)), cwd=remote.parent)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", branch)


def _manifest_text(manifest: dict[str, object]) -> str:
    """One rendering of a fixture manifest, for the author repository and the Registry alike.

    A promoted version records the `input_digest` of the exact manifest bytes it vendored, and
    Source Sync recomputes that digest from the author repository.  Two renderings of the same
    dictionary are two different byte strings, so writing one into `skill.git` and the other into
    the pre-published Registry made the lab disagree with itself: the operator's very first Sync
    reported both fixtures `invalid` with `registry-version-immutable` (`QA-061`).
    """

    return json.dumps(manifest, indent=2) + "\n"


def _entry(path: str, content: str, *, executable: bool = False) -> SnapshotEntry:
    parsed = parse_relative_path(path)
    if not isinstance(parsed, Ok):
        raise RuntimeError(f"manual fixture path is invalid: {path}")
    return SnapshotEntry(
        parsed.value,
        SnapshotEntryKind.FILE,
        content.encode("utf-8"),
        executable,
    )


def _promote(
    current: SourceSnapshot,
    *,
    alias: str,
    url: str,
    revision: str,
    authored: tuple[SnapshotEntry, ...],
) -> SourceSnapshot:
    source_alias = SourceAlias(alias)
    compiled = compile_author_snapshot(
        SourceSnapshot(SnapshotOrigin.IMMUTABLE_GIT, authored),
        source_alias=source_alias,
        source=url,
        revision=revision,
    )
    if not isinstance(compiled, Ok):
        raise RuntimeError(compiled.diagnostics[0].message)
    approved = load_registry_versions(current)
    if not isinstance(approved, Ok):
        raise RuntimeError(approved.diagnostics[0].message)
    scanned = reconcile_source_scan(
        source_alias,
        revision,
        compiled.value,
        previous=(),
        approved=approved.value,
        target_registry=SourceAlias("manual-registry"),
    )
    if not isinstance(scanned, Ok):
        raise RuntimeError(scanned.diagnostics[0].message)
    bundle = dataclasses.replace(
        scanned.value.active[0], candidate=assess_candidate(scanned.value.active[0].candidate)
    )
    evidence = PromotionEvidence(
        ObjectDigest("sha256", hashlib.sha256((alias + "-validation").encode()).hexdigest()),
        ObjectDigest("sha256", hashlib.sha256((alias + "-policy").encode()).hexdigest()),
    )
    planned = plan_bulk_promotion(
        current,
        (bundle,),
        evidence=((bundle.candidate.id, evidence),),
        approved=approved.value,
        mode=PromotionMode.VENDORED,
    )
    if not isinstance(planned, Ok):
        raise RuntimeError(planned.diagnostics[0].message)
    projected = project_promotion(current, planned.value)
    if not isinstance(projected, Ok):
        raise RuntimeError(projected.diagnostics[0].message)
    return SourceSnapshot(SnapshotOrigin.LOCAL, projected.value.entries)


def _write_snapshot(root: Path, snapshot: SourceSnapshot) -> None:
    for entry in snapshot.entries:
        path = root.joinpath(*str(entry.path).split("/"))
        if entry.kind is SnapshotEntryKind.DIRECTORY:
            path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(entry.content)
        path.chmod(0o700 if entry.executable else 0o600)


#: The lab's own keychain, created empty and left unlocked. Named rather than derived so a reader
#: of `security list-keychains` inside the lab can tell at a glance which file is the fixture's.
LAB_KEYCHAIN = "aart-manual.keychain-db"


def _keychain(home: Path) -> None:
    """Give this lab home a keychain of its own, so the credential step has somewhere to write.

    `security` resolves the default keychain from `HOME`, and a lab home with only `.config` and
    `.cache` in it has none -- so the very first credential the operator stores made macOS offer
    `Keychain Not Found ... Reset To Defaults`, which is the one dialog a manual test must never
    put in front of anybody (`QA-084`). Creating one here means the write lands in the lab, the
    operator's real keychain is never a candidate, and `reset` takes the whole thing away with the
    directory.

    The password is empty on purpose: this keychain holds throwaway fixture values and protects
    nothing, so there is no secret to keep out of the repository. `Library/Preferences` has to
    exist first or `default-keychain -s` has nowhere to record the choice and silently forgets it.
    """

    if sys.platform != "darwin":
        return
    keychains = home / "Library/Keychains"
    keychains.mkdir(parents=True, exist_ok=True)
    (home / "Library/Preferences").mkdir(parents=True, exist_ok=True)
    path = str(keychains / LAB_KEYCHAIN)
    environment = dict(os.environ, HOME=str(home))
    if not Path(path).exists():
        subprocess.run(
            ("/usr/bin/security", "create-keychain", "-p", "", path),
            env=environment,
            check=True,
            capture_output=True,
        )
    for argv in (
        ("default-keychain", "-s", path),
        ("list-keychains", "-s", path),
        # A locked keychain raises its own dialog, which is the same failure by another name.
        ("unlock-keychain", "-p", "", path),
    ):
        subprocess.run(
            ("/usr/bin/security", *argv), env=environment, check=True, capture_output=True
        )


def _home(home: Path, remotes: Path) -> dict[str, str]:
    for suffix in (".config", ".local/share", ".cache"):
        (home / suffix).mkdir(parents=True, exist_ok=True)
    _keychain(home)
    _write(
        home / ".gitconfig",
        '[url "file://' + str(remotes.resolve()) + '/"]\n\tinsteadOf = https://manual.aart.test/\n',
    )
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "PYTHONPATH": str(CHECKOUT),
        }
    )
    return env


MCP_SERVER = """#!/usr/bin/env python3
import json
import os
import sys

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "aart-dummy-credential", "version": "1.0.0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "credential-status", "description": "Reports presence only",
                             "inputSchema": {"type": "object", "properties": {}}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text":
                  "dummy credential present: " + str(bool(os.environ.get("AART_DUMMY_TOKEN"))).lower()}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}), flush=True)
"""


def _maintainer_instructions(root: Path, run_id: str, branch: str) -> str:
    """START_HERE for a run whose Registry does not exist yet."""

    return f"""# AART manual test {run_id} — maintainer first

This lab is isolated from normal AART state. Everything uses `{branch}` and local bare remotes.

**The Registry is empty on purpose.** No manifest, no promotion, no configured Source. You build it
through the Maintainer TUI, which is the point of this run.

Act I — maintainer. Open the Maintainer TUI:

    python {CHECKOUT / "scripts/manual_test.py"} open maintainer --root {root}

Its current project is the empty registry checkout, so screen 46 offers **Initialize Registry**.
Then add the two author Sources, sync them, review the Candidates, validate, promote and commit —
all in the TUI. The author repositories are already published at:

    https://manual.aart.test/skill.git
    https://manual.aart.test/mcp.git

both at ref `{branch}`.

## What `https://manual.aart.test/...` is

Those look like GitHub URLs and are meant to: they are this lab's stand-in for two author teams'
repositories. `manual.aart.test` exists nowhere — `.test` is a reserved name that never resolves on
the internet. Inside the lab, Git is configured to swap that prefix for a folder on your disk:

    [url "file://<lab>/remotes/"]
        insteadOf = https://manual.aart.test/

So when AART fetches `https://manual.aart.test/skill.git`, Git actually reads
`<lab>/remotes/skill.git` locally. Nothing leaves your machine and no account is involved.

Why not simply use the folder path? Because AART refuses a `file://` origin on purpose — an origin
must be a credential-free HTTPS/SSH URL. The rewrite gives the lab a real-shaped remote, so the
genuine Git acquisition path is exercised rather than bypassed.

`skill.git` publishes the Skill `manual-check`; `mcp.git` publishes the credential-bearing MCP
`dummy-mcp`. In production these would be two teams' repositories.

Act II — consumer. Once you have published the Registry, open the clean consumer TUI:

    python {CHECKOUT / "scripts/manual_test.py"} open consumer --root {root}

Subscribe to `https://manual.aart.test/registry.git` at ref `{branch}`, then install from
Marketplace. Installing the MCP binds `dummy-token` to the isolated AART-home Keychain reference;
at the provider prompt enter disposable test text only. The MCP reports only whether a value exists
and never echoes it.

The step-by-step walkthrough is `docs/testing/TUI_MANUAL_WALKTHROUGH.md`.

Reset only this lab:

    python {CHECKOUT / "scripts/manual_test.py"} reset --root {root}
"""


def setup_lab(raw_root: Path, *, empty_registry: bool = False) -> ManualLab:
    """Build one disposable ecosystem.

    `empty_registry` decides who does the Maintainer run. The default publishes both fixtures so
    consumer testing is not blocked on publication (`QA-051`); with the flag the registry arrives
    with nothing in it -- no manifest, no promotion, no configured Source -- so Initialize Registry,
    Add Source, Sync, Candidates, validation, promotion and commit are all still ahead of the
    operator, in the TUI, which is the only way walking those screens tests anything (`QA-054`).
    """

    root = _safe_root(raw_root)
    if root.exists():
        reset_lab(root)
    run_id = uuid.uuid4().hex[:12]
    branch = f"manual/{run_id}"
    root.mkdir(parents=True)
    (root / MARKER).write_text(
        json.dumps({"schema": SCHEMA, "root": str(root), "run_id": run_id}) + "\n",
        encoding="utf-8",
    )

    remotes = root / "remotes"
    repositories = root / "repositories"
    skill_repo = repositories / "skill"
    mcp_repo = repositories / "mcp"
    registry_repo = repositories / "registry"
    maintainer_home = root / "maintainer-home"
    consumer_home = root / "consumer-home"
    consumer_project = root / "consumer-project"
    consumer_project.mkdir()
    maintainer_env = _home(maintainer_home, remotes)
    _home(consumer_home, remotes)

    skill_manifest = {
        "schema": "aart.dev/skill/v1",
        "artifact": {"name": "manual-check", "kind": "skill", "version": "1.0.0"},
        "payload": {"include": ["SKILL.md"]},
        "compatibility": {
            "harnesses": ["claude", "opencode", "tabnine"],
            "platforms": ["darwin", "linux"],
        },
    }
    _initialize_repository(skill_repo, branch)
    _write(skill_repo / "manual-check/aart.json", _manifest_text(skill_manifest))
    _write(
        skill_repo / "manual-check/SKILL.md", "# Manual check\n\nA disposable AART test skill.\n"
    )
    skill_revision = _commit(skill_repo, "feat: add disposable manual skill")
    _publish_bare(skill_repo, remotes / "skill.git", branch)

    mcp_manifest = {
        "schema": "aart.dev/mcp/v1",
        "artifact": {"name": "dummy-mcp", "kind": "mcp", "version": "1.0.0"},
        "payload": {"include": ["server.py"]},
        "transport": {"type": "stdio"},
        "runtime": {"type": "python", "version": ">=3.11"},
        "launch": {"type": "python", "entrypoint": "server.py"},
        "inputs": [
            {
                "id": "dummy-token",
                "kind": "secret",
                "required": True,
                "inject": {"type": "environment", "variable": "AART_DUMMY_TOKEN"},
                "help": {
                    "label": "Disposable dummy credential",
                    "description": "Use test text only; this server checks presence and never prints it.",
                    "format_hint": "any non-empty disposable test text",
                    # Manually issued: there is no page to visit, so the instruction is the label
                    # and no link is invented (D-263).
                    "obtain_from": {
                        "label": "Nothing issues it; make up disposable text such as lab-only-test",
                    },
                },
            }
        ],
        "compatibility": {
            "harnesses": ["claude", "opencode", "tabnine"],
            "platforms": ["darwin", "linux"],
        },
    }
    _initialize_repository(mcp_repo, branch)
    _write(mcp_repo / "dummy-mcp/aart.json", _manifest_text(mcp_manifest))
    _write(mcp_repo / "dummy-mcp/server.py", MCP_SERVER)
    mcp_revision = _commit(mcp_repo, "feat: add disposable credential MCP")
    _publish_bare(mcp_repo, remotes / "mcp.git", branch)

    _initialize_repository(registry_repo, branch)
    if empty_registry:
        # One commit so the branch exists and can be cloned, carrying nothing AART owns. Screen 46
        # then reports that the current project holds no Registry and offers Initialize Registry,
        # which is where the maintainer walkthrough is supposed to begin.
        _write(
            registry_repo / "README.md",
            f"# AART manual registry {run_id}\n\nEmpty on purpose: the Maintainer TUI creates it.\n",
        )
        _commit(registry_repo, "chore: empty registry repository")
        _publish_bare(registry_repo, remotes / "registry.git", branch)
        _write(root / "START_HERE.md", _maintainer_instructions(root, run_id, branch))
        return ManualLab(root, run_id, branch)
    _run(
        (
            sys.executable,
            "-m",
            "agent_artifacts.cli",
            "registry",
            "init",
            "--source",
            str(registry_repo),
            "--source-id",
            "manual-registry",
            "--display-name",
            f"AART Manual Registry {run_id}",
            "--yes",
        ),
        cwd=CHECKOUT,
        env=maintainer_env,
    )
    # The aliases here are the ones both walkthroughs tell the operator to configure: a
    # Candidate's identity includes its Source alias, so pre-promoting under a different one
    # makes the operator's first Sync see a stranger at an already-published version and
    # refuse it as a conflict (`QA-061`).
    current = SourceSnapshot(SnapshotOrigin.LOCAL, ())
    current = _promote(
        current,
        alias="manual-skill",
        url="https://manual.aart.test/skill.git",
        revision=skill_revision,
        authored=(
            _entry("manual-check/aart.json", _manifest_text(skill_manifest)),
            _entry("manual-check/SKILL.md", "# Manual check\n\nA disposable AART test skill.\n"),
        ),
    )
    current = _promote(
        current,
        alias="manual-mcp",
        url="https://manual.aart.test/mcp.git",
        revision=mcp_revision,
        authored=(
            _entry("dummy-mcp/aart.json", _manifest_text(mcp_manifest)),
            _entry("dummy-mcp/server.py", MCP_SERVER, executable=True),
        ),
    )
    _write_snapshot(registry_repo, current)
    _commit(registry_repo, "feat: publish disposable manual fixtures")
    _publish_bare(registry_repo, remotes / "registry.git", branch)

    _write(
        root / "START_HERE.md",
        f"""# AART manual test {run_id}

This lab is isolated from normal AART state. All repositories use `{branch}` and local bare remotes.

Open the maintainer TUI:

    python {CHECKOUT / "scripts/manual_test.py"} open maintainer --root {root}

Open the clean consumer TUI:

    python {CHECKOUT / "scripts/manual_test.py"} open consumer --root {root}

## What `https://manual.aart.test/...` is

Those look like GitHub URLs and are meant to: they are this lab's stand-in for two author teams'
repositories. `manual.aart.test` exists nowhere — `.test` is a reserved name that never resolves on
the internet. Inside the lab, Git is configured to swap that prefix for a folder on your disk:

    [url "file://<lab>/remotes/"]
        insteadOf = https://manual.aart.test/

So when AART fetches `https://manual.aart.test/skill.git`, Git actually reads
`<lab>/remotes/skill.git` locally. Nothing leaves your machine and no account is involved.

Why not simply use the folder path? Because AART refuses a `file://` origin on purpose — an origin
must be a credential-free HTTPS/SSH URL. The rewrite gives the lab a real-shaped remote, so the
genuine Git acquisition path is exercised rather than bypassed.

`skill.git` publishes the Skill `manual-check`; `mcp.git` publishes the credential-bearing MCP
`dummy-mcp`. In production these would be two teams' repositories.

In Registries use URL `https://manual.aart.test/registry.git`, ref `{branch}`.
Maintainer Sources can use `https://manual.aart.test/skill.git` and
`https://manual.aart.test/mcp.git`, both at the same ref.

Marketplace already contains the Skill and credential-bearing MCP so consumer testing is not
blocked on publication. Installing `manual-registry/mcp/dummy-mcp@1.0.0` binds `dummy-token` to the
isolated AART-home Keychain reference. At the provider prompt enter disposable test text only.
The MCP reports only whether a value exists and never echoes it.

Reset only this lab:

    python {CHECKOUT / "scripts/manual_test.py"} reset --root {root}
""",
    )
    return ManualLab(root, run_id, branch)


_ROLE_PROJECTS = {
    "maintainer": "repositories/registry",
    "consumer": "consumer-project",
}


def shell_environment(root: Path, role: str) -> tuple[dict[str, str], Path]:
    """The lab environment and working directory one role's commands run in.

    Separated from spawning so the CLI route can be described and tested without starting anything.
    A manual test whose HOME was mistyped runs against real state, which is the one failure this
    lab exists to make impossible (`QA-057`).
    """

    project = _ROLE_PROJECTS.get(role)
    if project is None:
        raise ValueError(f"unknown manual-test role: {role}")
    root = _safe_root(root)
    _marker(root)
    home = root / f"{role}-home"
    return _home(home, root / "remotes"), root / project


def _shell(root: Path, role: str) -> int:
    """Open an interactive shell inside the lab, so plain commands are already isolated."""

    env, cwd = shell_environment(root, role)
    env["AART_MANUAL_ROLE"] = role
    print(f"AART manual lab shell ({role}). HOME={env['HOME']}")
    print(f"Run AART as: python3 -m agent_artifacts.cli ...   (cwd: {cwd})")
    print("Leave with: exit")
    return subprocess.call((os.environ.get("SHELL", "/bin/sh"),), cwd=cwd, env=env)


def _open(root: Path, role: str) -> int:
    _marker(root)
    remotes = root / "remotes"
    home = root / ("maintainer-home" if role == "maintainer" else "consumer-home")
    project = root / ("repositories/registry" if role == "maintainer" else "consumer-project")
    env = _home(home, remotes)
    return subprocess.call(
        (sys.executable, "-m", "agent_artifacts.cli"),
        cwd=project,
        env=env,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("setup", "reset"):
        command = sub.add_parser(action)
        command.add_argument("--root", type=Path, default=DEFAULT_ROOT)
        if action == "setup":
            command.add_argument(
                "--empty-registry",
                action="store_true",
                help="leave the Registry unbuilt so the Maintainer TUI creates it",
            )
    opened = sub.add_parser("open")
    opened.add_argument("role", choices=("maintainer", "consumer"))
    opened.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    shell = sub.add_parser("shell")
    shell.add_argument("role", choices=("maintainer", "consumer"))
    shell.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = _safe_root(args.root)
    if args.action == "setup":
        lab = setup_lab(root, empty_registry=args.empty_registry)
        print(f"Fresh manual-test lab: {lab.root}")
        print(f"Run: {lab.run_id}; branch: {lab.branch}")
        if args.empty_registry:
            print("Registry: empty — build it through the Maintainer TUI")
        print(f"Start with: {lab.root / 'START_HERE.md'}")
        return 0
    if args.action == "reset":
        reset_lab(root)
        print(f"Removed marked manual-test lab: {root}")
        return 0
    if args.action == "shell":
        return _shell(root, args.role)
    return _open(root, args.role)


if __name__ == "__main__":
    raise SystemExit(main())
