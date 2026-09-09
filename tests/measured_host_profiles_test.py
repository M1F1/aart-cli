"""The difference between the harnesses somebody named and the harnesses this machine happens to
have.

`aart marketplace install` never guesses: it refuses without `--profile`, so every profile it
places into was typed by the operator, and a profile that cannot be placed is a refusal -- they
asked for something that will not work.

The persistent shell has no such list. It installs into every harness whose target tables this
build measured, which is a capability set rather than a request. Codex is the case that makes the
distinction load-bearing: it is measured, so it belongs in that set, and it registers MCP servers
only at user scope, so it can host no project MCP at all. Treating the machine's set as a request
made the shell refuse *every* MCP install on any machine where Codex is measured.

What must not happen is the other extreme, a harness quietly dropped: an install that reports
success and leaves a harness somebody asked for with nothing to read and no way to start a server.
So the skip is narrow. A harness nobody measured stays a refusal however the profiles arrived, and
a Selection that nothing on this machine can host stays a refusal too.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.domain.harness import Scope, measured_harnesses
from agent_artifacts.domain.identifiers import SourceAlias
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.artifact_placement import PLACEMENT_UNAVAILABLE, placement_for
from agent_artifacts.io.object_store import publish_object
from agent_artifacts.protocol.authoring import compile_author_snapshot
from agent_artifacts.sources.local import read_local_snapshot
from agent_artifacts.sources.model import LocalSnapshotRequest, SnapshotLimits, source_instance_id
from agent_artifacts.store.model import (
    ObjectPublishCommand,
    make_object_candidate,
    object_store_paths,
)
from tests.artifact_installation_e2e_test import MANIFEST, SERVER_SOURCE
from tests.artifact_placement_resolution_test import SKILL_MANIFEST, _stored_artifact

MEMORY_MANIFEST = {
    "schema": "aart.dev/memory/v1",
    "artifact": {"name": "house-rules", "kind": "memory", "version": "1.0.0"},
    "payload": {"include": ["house.md"]},
    "compatibility": {"harnesses": ["claude"]},
}

#: What the persistent shell targets: every harness this build measured, not a list beside them.
MACHINE = ("claude", "codex", "opencode", "tabnine")


class _PlacementFixture(unittest.TestCase):
    """One authored artifact, compiled and published, ready to be placed against any profile set."""

    manifest: dict[str, object] = {}
    files: tuple[tuple[str, str], ...] = ()

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.scope = pathlib.Path(temporary.name).resolve()
        self.project = str(self.scope / "project")
        self.data = str(self.scope / "data")
        self.home = str(self.scope / "home")
        self.store = object_store_paths(str(self.scope / "store"))
        self.artifact = self._publish()

    def _publish(self):
        name = str(self.manifest["artifact"]["name"])  # type: ignore[index]
        repository = self.scope / "author"
        (repository / name).mkdir(parents=True)
        (repository / name / "aart.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        for filename, content in self.files:
            (repository / name / filename).write_text(content, encoding="utf-8")

        alias = SourceAlias("company")
        configured = ConfiguredSource(alias, SourceKind.SOURCE_LOCAL, str(repository), None, True)
        acquired = read_local_snapshot(
            LocalSnapshotRequest(
                source_instance_id(configured), alias, str(repository), SnapshotLimits()
            )
        )
        self.assertIsInstance(acquired, Ok, getattr(acquired, "diagnostics", ()))
        compiled = compile_author_snapshot(
            acquired.value.snapshot,
            source_alias=alias,
            source="https://github.company/company/artifacts.git",
            revision="e" * 40,
        )
        self.assertIsInstance(compiled, Ok, getattr(compiled, "diagnostics", ()))
        package = compiled.value[0]
        candidate = make_object_candidate(package.canonical_entries)
        self.assertIsInstance(candidate, Ok, getattr(candidate, "diagnostics", ()))
        published = publish_object(ObjectPublishCommand(self.store, candidate.value))
        self.assertIsInstance(published, Ok, getattr(published, "diagnostics", ()))
        return _stored_artifact(package.package, candidate.value.digest)

    def _place(self, **overrides):
        fields = {
            "scope": Scope.PROJECT,
            "profiles": MACHINE,
            "project_root": self.project,
            "data_root": self.data,
            "harness_root": self.project,
            "store": self.store,
        }
        fields.update(overrides)
        return placement_for(self.artifact, **fields)  # type: ignore[arg-type]


class MeasuredHarnessSetTest(unittest.TestCase):
    def test_the_measured_set_is_every_harness_any_table_names(self) -> None:
        self.assertEqual({"claude", "codex", "opencode", "tabnine"}, set(measured_harnesses()))

    def test_a_harness_nobody_measured_is_not_in_it(self) -> None:
        self.assertNotIn("emacs", measured_harnesses())


class ShellHostTest(unittest.TestCase):
    """What the persistent shell says about the profiles it installs into."""

    def _host(self):
        from agent_artifacts.configuration.paths import Platform, resolve_config_paths
        from agent_artifacts.tui import (
            _canonical_installation_host,
            _canonical_marketplace_target,
        )

        paths = resolve_config_paths(Platform.LINUX, home="/home/operator")
        return _canonical_installation_host(
            paths, "/project", "/home/operator", _canonical_marketplace_target()
        )

    def test_the_shell_installs_into_every_harness_this_build_measured(self) -> None:
        self.assertEqual(tuple(sorted(measured_harnesses())), self._host().profiles)

    def test_and_says_that_nobody_asked_for_them(self) -> None:
        """`aart marketplace install` refuses without `--profile`; the shell names none, so a
        measured harness that cannot host one artifact must not refuse the whole install."""

        self.assertFalse(self._host().profiles_requested)


class MachineProfileMcpPlacementTest(_PlacementFixture):
    """An MCP server, placed against the shell's measured harness set."""

    manifest = MANIFEST
    files = (("server.py", SERVER_SOURCE), ("requirements.txt", "# none\n"))

    def test_a_measured_harness_that_hosts_no_server_at_this_scope_is_left_out(self) -> None:
        placed = self._place(profiles_requested=False)

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual(
            ["claude", "opencode", "tabnine"],
            sorted(target.harness for target in placed.value.targets),
        )

    def test_the_same_harness_named_by_the_operator_is_still_refused(self) -> None:
        placed = self._place(profiles=("claude", "codex"))

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        self.assertIn("codex", placed.diagnostics[0].message)

    def test_a_harness_nobody_measured_is_named_even_when_nobody_named_it(self) -> None:
        placed = self._place(profiles=("claude", "emacs"), profiles_requested=False)

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        self.assertIn("emacs", placed.diagnostics[0].message)

    def test_a_machine_whose_every_harness_refuses_the_kind_is_refused(self) -> None:
        placed = self._place(profiles=("codex",), profiles_requested=False)

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        self.assertIn("codex", placed.diagnostics[0].message)


class MachineProfileDeliveryPlacementTest(_PlacementFixture):
    """A Skill: the same distinction, read off the delivery table instead."""

    manifest = SKILL_MANIFEST
    files = (("SKILL.md", "# review\n"), ("reference.md", "detail\n"))

    def test_a_measured_harness_that_reads_no_skill_at_this_scope_is_left_out(self) -> None:
        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles_requested=False)

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual(
            ["claude", "codex", "opencode"],
            sorted(item.harness for item in placed.value.deliveries),
        )

    def test_the_same_harness_named_by_the_operator_is_still_refused(self) -> None:
        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles=("tabnine",))

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        self.assertIn("tabnine", placed.diagnostics[0].message)

    def test_a_machine_that_reads_this_kind_nowhere_is_refused(self) -> None:
        placed = self._place(
            scope=Scope.USER,
            harness_root=self.home,
            profiles=("tabnine",),
            profiles_requested=False,
        )

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)


class MachineProfileMergePlacementTest(_PlacementFixture):
    """A memory block: merged into a shared file, and measured in a third table."""

    manifest = MEMORY_MANIFEST
    files = (("house.md", "Remember tests.\n"),)

    def test_a_measured_harness_with_no_memory_file_at_this_scope_is_left_out(self) -> None:
        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles_requested=False)

        self.assertIsInstance(placed, Ok, getattr(placed, "diagnostics", ()))
        self.assertEqual(
            ["claude", "codex", "opencode"],
            sorted(item.harness for item in placed.value.merges),
        )

    def test_the_same_harness_named_by_the_operator_is_still_refused(self) -> None:
        placed = self._place(scope=Scope.USER, harness_root=self.home, profiles=("tabnine",))

        self.assertIsInstance(placed, Err)
        self.assertIs(placed.diagnostics[0].code, PLACEMENT_UNAVAILABLE)
        self.assertIn("tabnine", placed.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
