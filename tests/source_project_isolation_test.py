"""No Registry operation writes anything beneath a project directory.

This is the boundary that makes `consume registry remove` safe to offer at all: a subscription, its
managed snapshot, the object store, and installed files are four different things, and Registry
operations own only the first two.  That claim is what stops unsubscribing from silently deleting a
skill out of someone's repository, so it is asserted here against the real CLI over a real project
with real installed artifacts rather than left to inspection.

The whole `consume registry` family runs against a project that already holds an installed
payload.  Every file beneath the project is compared byte for byte, including modification times:
these operations should not so much as open a project file.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from aart_cli import cli
from tests.marketplace_lifecycle_e2e_test import _COORDINATE, _PLACED, _environment
from tests.reference_registry import REFERENCE_CONTENT, reference_snapshot, write_reference_registry

_INSTALLED = _PLACED


def _records(env) -> Path:
    return Path(env.paths.data_root) / "state" / "installations"


def _mirror(env) -> Path:
    """A second Registry, so `add` has somewhere to point and `remove` leaves one behind."""

    return write_reference_registry(
        env.root / "mirror-registry",
        reference_snapshot(*REFERENCE_CONTENT, declared_id="mirror-registry"),
    )


def _add_mirror(env) -> tuple[str, ...]:
    return (
        "consume",
        "registry",
        "add",
        "--alias",
        "mirror",
        "--kind",
        "local",
        "--location",
        str(_mirror(env)),
        "--ref",
        "main",
    )


def _source(env, *argv):
    """Run one `consume registry` subcommand and return ``(exit_code, parsed_json)``.

    The family takes no ``--project``: Registries are user-scope state, which is exactly the
    property under test, so these commands cannot even name a project to write into.
    """

    stdout = io.StringIO()
    with (
        mock.patch.dict(os.environ, env.xdg, clear=False),
        contextlib.redirect_stdout(stdout),
        mock.patch("os.getcwd", return_value=str(env.project)),
    ):
        code = cli.main([*argv, "--json"])
    raw = stdout.getvalue()
    return code, (json.loads(raw) if raw.strip() else None)


def _entry(path: Path) -> tuple[str, ...]:
    """Describe one path completely enough that any write to it changes the description."""

    if path.is_symlink():
        return ("symlink", os.readlink(path))
    stat = path.stat()
    if path.is_dir():
        return ("dir", str(stat.st_mode))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return ("file", str(stat.st_mode), str(stat.st_mtime_ns), digest)


def _project_snapshot(project: Path) -> dict[str, tuple[str, ...]]:
    return {str(path.relative_to(project)): _entry(path) for path in sorted(project.rglob("*"))}


def _stable_entry(path: Path) -> tuple[str, ...]:
    """Like :func:`_entry` without the modification time, for comparing two separate runs."""

    described = _entry(path)
    return described if described[0] != "file" else (described[0], described[1], described[3])


def _stable_snapshot(project: Path) -> dict[str, tuple[str, ...]]:
    return {
        str(path.relative_to(project)): _stable_entry(path) for path in sorted(project.rglob("*"))
    }


class SourceOperationProjectIsolationTest(unittest.TestCase):
    def test_no_source_operation_writes_beneath_the_project(self) -> None:
        with _environment() as env:
            install_code, installed = env.run(
                "consume", "install", _COORDINATE, "--profile", "claude", "--yes"
            )
            self.assertEqual(install_code, 0, installed)
            self.assertTrue((env.project / _INSTALLED / "SKILL.md").is_file())

            before = _project_snapshot(env.project)

            operations = (
                _add_mirror(env),
                ("consume", "registry", "list"),
                ("consume", "registry", "sync"),
                ("consume", "registry", "health"),
                ("consume", "registry", "remove", "--alias", "reference"),
                ("consume", "registry", "remove", "--alias", "reference", "--yes"),
            )
            for operation in operations:
                code, payload = _source(env, *operation)
                self.assertEqual(code, 0, (operation, payload))
                self.assertEqual(
                    _project_snapshot(env.project),
                    before,
                    f"`aart {' '.join(operation)}` changed the project tree",
                )

    def test_the_installation_record_outlives_the_subscription(self) -> None:
        """A project naming a removed alias keeps its record, rather than losing it.

        Status still lists the installation; it does not yet say its Registry is gone (B-205).
        """

        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            _source(env, *_add_mirror(env))
            records_before = {path.name: path.read_bytes() for path in _records(env).iterdir()}

            _source(env, "consume", "registry", "remove", "--alias", "reference", "--yes")

            self.assertEqual(
                {path.name: path.read_bytes() for path in _records(env).iterdir()}, records_before
            )
            code, status = env.run("consume", "status", "--profile", "claude")
            self.assertEqual(code, 0, status)
            self.assertEqual([item["key"] for item in status["items"]], [f"{_COORDINATE}@1.0.0"])


class UninstallAfterSourceRemovalTest(unittest.TestCase):
    """Uninstall plans from the installation records, so removing a Registry cannot strand a project.

    `consume registry remove`'s review names uninstall as a valid exit.  That claim was false while uninstall
    resolved through the catalog first: with the subscription gone there was nothing to resolve
    through, and the command refused with `artifact-not-found` for an artifact it had a complete
    record of.  The removal is what these tests hold constant — the outcome must not depend on it.
    """

    def test_uninstall_succeeds_after_the_source_it_came_from_is_removed(self) -> None:
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
            installed = env.project / _INSTALLED
            self.assertTrue(installed.exists())
            removed_code, removed = _source(
                env, "consume", "registry", "remove", "--alias", "reference", "--yes"
            )
            self.assertEqual(removed_code, 0, removed)

            code, payload = env.run(
                "consume", "uninstall", _COORDINATE, "--profile", "claude", "--yes"
            )

            self.assertEqual(code, 0, payload)
            self.assertTrue(payload["finalized"], payload)
            self.assertFalse(installed.exists(), sorted(map(str, env.project.rglob("*"))))

    def test_the_removal_changes_nothing_about_what_uninstall_leaves_behind(self) -> None:
        """Two runs differing only in whether the subscription was removed must land identically."""

        def _uninstalled(remove_source: bool) -> dict[str, tuple[str, ...]]:
            with _environment() as env:
                env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")
                if remove_source:
                    _source(env, "consume", "registry", "remove", "--alias", "reference", "--yes")
                code, payload = env.run(
                    "consume", "uninstall", _COORDINATE, "--profile", "claude", "--yes"
                )
                self.assertEqual(code, 0, payload)
                return _stable_snapshot(env.project)

        self.assertEqual(_uninstalled(remove_source=True), _uninstalled(remove_source=False))

    def test_an_uninstall_selector_naming_nothing_installed_says_exactly_that(self) -> None:
        # Resolving from the records must not turn "you never installed this" into "uninstall
        # everything": an empty selection is how a bare `uninstall` selects the whole project.
        with _environment() as env:
            env.run("consume", "install", _COORDINATE, "--profile", "claude", "--yes")

            code, payload = env.run(
                "consume",
                "uninstall",
                "reference/skill/absent",
                "--profile",
                "claude",
                "--yes",
            )

            self.assertEqual(code, 1, payload)
            self.assertEqual(payload["diagnostics"][0]["code"], "installation-not-found")
            self.assertTrue((env.project / _INSTALLED).exists())


if __name__ == "__main__":
    unittest.main()
