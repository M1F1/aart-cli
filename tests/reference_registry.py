"""The shared reference content, published as the Registry a consumer reads (INV-269, CP-32).

The consumer e2e tests used to subscribe to `native-source-v1` directly, as an authoring source a
consumer could install from. A consumer reads only Registries, so the same content -- the
`code-review` Skill, the `house` memory and the `essentials` Collection -- is taken through the
real promotion pipeline into an approved Registry, committed to a Git checkout and connected as a
`registry-local` under the alias the tests already use.

Tests that change what the Registry publishes edit the checkout and call :func:`commit`: a local
Registry is read as its branch commits it, never as the worktree.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from aart_cli.protocol.native_tree import SnapshotEntry, SnapshotOrigin, SourceSnapshot
from tests.configured_installation_draft_e2e_test import (
    Authored,
    AuthoredSetup,
    RegistryCollection,
    _promote_one,
)
from tests.registry_maintenance_fixtures import empty_registry_snapshot, write_snapshot

#: The alias a consumer connects the reference Registry under, and the Registry it promotes into.
ALIAS = "reference"
#: What the Registry declares itself to be, in both identity markers.
DECLARED_ID = "reference-native-source"
BRANCH = "main"

SKILL_BODY = (
    "---\n"
    "name: code-review\n"
    "description: Review code changes with a repeatable quality checklist.\n"
    "---\n\n"
    "# Code review\n\n"
    "Check correctness, security, performance, tests, and maintainability before merging.\n"
)
HOUSE_BODY = "# House conventions\n\nPrefer small, reviewable changes.\n"


def skill(
    version: str = "1.0.0",
    body: str = SKILL_BODY,
    harnesses: tuple[str, ...] = ("claude", "tabnine"),
    platforms: tuple[str, ...] = (),
    **extra: object,
) -> Authored:
    """The `code-review` Skill; `platforms` is what a Skill declaring setup must name a superset of."""

    compatibility: dict[str, object] = {"harnesses": list(harnesses)}
    if platforms:
        compatibility["platforms"] = list(platforms)
    manifest: dict[str, object] = {
        "schema": "aart-cli.dev/skill/v1",
        "artifact": {
            "name": "code-review",
            "kind": "skill",
            "summary": "Review code changes with a repeatable quality checklist.",
            "x-fixture-version": version,
        },
        "payload": {"include": ["SKILL.md"]},
        "compatibility": compatibility,
        **extra,
    }
    return (
        ("code-review/aart-cli.json", json.dumps(manifest)),
        ("code-review/SKILL.md", body),
    )


def memory(name: str = "house", body: str = HOUSE_BODY, version: str = "1.0.0") -> Authored:
    manifest = {
        "schema": "aart-cli.dev/memory/v1",
        "artifact": {
            "name": name,
            "kind": "memory",
            "summary": "House conventions injected into the harness instruction file.",
            "x-fixture-version": version,
        },
        "payload": {"include": ["HOUSE.md"]},
        "compatibility": {"harnesses": ["claude", "tabnine"]},
    }
    return ((f"{name}/aart-cli.json", json.dumps(manifest)), (f"{name}/HOUSE.md", body))


ESSENTIALS = RegistryCollection(
    "essentials",
    "Install the essential reviewed agent artifacts.",
    ("skill/code-review",),
)

#: What `native-source-v1` held, in the order a Maintainer would promote it.
REFERENCE_CONTENT: tuple[Authored, ...] = (skill(), memory(), ESSENTIALS)


def reference_snapshot(
    *authored: Authored,
    declared_id: str = DECLARED_ID,
    setup: AuthoredSetup | None = None,
) -> SourceSnapshot:
    """The reference Registry: identity markers first, then each promotion in order.

    `setup` is declared on the Skill alone, as `native-source-v1` carried it when a test taught
    the Skill a setup: the memory and the Collection never declare one.
    """

    markers = tuple(
        SnapshotEntry(
            entry.path,
            entry.kind,
            entry.content.replace(b"test-registry", declared_id.encode()),
            entry.executable,
        )
        for entry in empty_registry_snapshot().entries
    )
    published = SourceSnapshot(SnapshotOrigin.LOCAL, ())
    for index, tree in enumerate(authored or REFERENCE_CONTENT):
        declares_setup = not isinstance(tree, RegistryCollection) and tree[0][0].startswith(
            "code-review/"
        )
        published = _promote_one(
            tree,
            onto=published,
            revision=f"{index:x}" * 40,
            setup=setup if declares_setup else None,
            registry_alias=ALIAS,
        )
    return SourceSnapshot(published.origin, (*markers, *published.entries))


def _git(root: Path, *argv: str) -> str:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "AART Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "AART Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    completed = subprocess.run(
        ["git", "-C", str(root), *argv],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return completed.stdout.strip()


def commit(root: Path, message: str = "publish") -> str:
    """Commit whatever the checkout holds now, and return the new revision."""

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def write_reference_registry(root: Path, snapshot: SourceSnapshot | None = None) -> Path:
    """Materialize the reference Registry as a Git checkout with its content committed."""

    root.mkdir(parents=True, exist_ok=True)
    write_snapshot(root, snapshot or reference_snapshot())
    _git(root, "init", "-q", "-b", BRANCH)
    commit(root, "approved registry")
    return root


def republish(
    root: Path,
    *authored: Authored,
    declared_id: str = DECLARED_ID,
    setup: AuthoredSetup | None = None,
) -> str:
    """Replace the Registry's content with a fresh promotion of `authored`, then commit it."""

    for path in root.iterdir():
        if path.name == ".git":
            continue
        if path.is_dir():
            _remove_tree(path)
        else:
            path.unlink()
    write_snapshot(root, reference_snapshot(*authored, declared_id=declared_id, setup=setup))
    return commit(root, "republish")


def _remove_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            _remove_tree(child)
        else:
            child.unlink()
    path.rmdir()
