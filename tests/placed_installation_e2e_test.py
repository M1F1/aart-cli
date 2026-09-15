"""One authored Skill, installed the way a person installs one, and taken back out again.

The canonical pipeline could not carry this artifact at all (B-033). It refused anything declaring
no launch contract, so four of the five kinds -- Skill, guideline, hook, memory -- could be
compiled and published but never planned, executed or recorded, and the legacy installer stayed the
only thing that could describe them. This is the proof that the whole path now carries one, through
the same composed adapter an MCP server goes through rather than a second one written for Skills.

Every step is the real one. The manifest is compiled, scanned, promoted and published into a
registry snapshot; the install resolves that approved version, materializes the verified object,
plans, reviews, takes a lease, executes and records; and what is asserted afterwards is read back
off the disk, not taken from the executor's verdict. An install that reports success and leaves the
harness with nothing to read is exactly the failure INV-010 exists to prevent, so the assertions
are about the file the harness opens.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest
from datetime import date

from agent_artifacts.application.execution import (
    ExecutionStatus,
    InstallationExecutionStatus,
    execute_repair,
)
from agent_artifacts.application.installed_state import removal_state_from_placement
from agent_artifacts.application.reconciliation import plan_repair
from agent_artifacts.configuration.model import SourceKind
from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.identifiers import ArtifactIdentity, SourceId
from agent_artifacts.domain.placement import artifact_root
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.reconciliation import Component, ComponentId
from agent_artifacts.domain.result import Ok
from agent_artifacts.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    VersionConstraint,
)
from agent_artifacts.io.configured_installation_action import (
    InstallationHost,
    complete_configured_installation,
    prepare_configured_installation,
)
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.installation_execution import interpreters_for
from agent_artifacts.io.installation_observation import observe_planned_installation
from agent_artifacts.io.source_store import publish_source_snapshot
from agent_artifacts.sources.model import (
    SourcePublishCommand,
    ValidatedSourceCandidate,
    make_source_candidate,
    source_instance_id,
    source_store_paths,
)
from tests.artifact_installation_e2e_test import MOMENT
from tests.configured_installation_draft_e2e_test import _published_registry
from tests.marketplace_fixtures import configured_source, effective_configuration

TODAY = date(2026, 8, 31)

SKILL_MANIFEST = {
    "schema": "aart.dev/skill/v1",
    "artifact": {"name": "code-review", "kind": "skill", "version": "1.2.0"},
    "payload": {"include": ["SKILL.md", "reference/style.md"]},
    "compatibility": {"harnesses": ["claude"]},
}

SKILL_BODY = "# Code review\n\nRead reference/style.md before commenting.\n"
STYLE_BODY = "Prefer naming the failure over describing the code.\n"

AUTHORED_SKILL: tuple[tuple[str, str], ...] = (
    ("code-review/aart.json", json.dumps(SKILL_MANIFEST)),
    ("code-review/SKILL.md", SKILL_BODY),
    ("code-review/reference/style.md", STYLE_BODY),
)


class PlacedInstallationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name).resolve()
        self.data_root = str(self.root / "data")
        self.project_root = str(self.root / "project")
        self.user_home = str(self.root / "home")
        for path in (self.project_root, self.user_home):
            pathlib.Path(path).mkdir(parents=True)

        self.source = configured_source("company", SourceKind.REGISTRY_GIT)
        self.effective = effective_configuration((self.source,), default_registry="company")
        candidate = make_source_candidate(
            source_instance_id(self.source),
            self.source.alias,
            "a" * 40,
            _published_registry(AUTHORED_SKILL),
        )
        assert isinstance(candidate, Ok), candidate
        written = publish_source_snapshot(
            SourcePublishCommand(
                source_store_paths(self.data_root, source_instance_id(self.source)),
                ValidatedSourceCandidate(candidate.value, SourceId("company-registry")),
                90,
            )
        )
        self.assertIsInstance(written, Ok, getattr(written, "diagnostics", ()))

        self.selection = ArtifactSelection(
            (
                ArtifactRequest(
                    ArtifactIdentity("skill", "code-review"),
                    VersionConstraint("*"),
                    self.source.alias,
                ),
            )
        )
        self.host = InstallationHost(
            data_root=self.data_root,
            project_root=self.project_root,
            user_home=self.user_home,
            scope=Scope.PROJECT,
            profiles=("claude",),
        )

    # -- the flow a person goes through ------------------------------------------------------

    def _prepare(self):
        prepared = prepare_configured_installation(
            self.effective,
            self.selection,
            host=self.host,
            sources=(),
            policy=EffectivePolicy(),
            selected_remediations=None,
        )
        self.assertIsInstance(prepared, Ok, getattr(prepared, "diagnostics", ()))
        return prepared.value

    def _complete(self, prepared):
        completed = complete_configured_installation(
            prepared,
            expected_review_digest=prepared.review_digest,
            host=self.host,
            policy=EffectivePolicy(),
            recorded_at=MOMENT,
            today=TODAY,
            offline=True,
        )
        self.assertIsInstance(completed, Ok, getattr(completed, "diagnostics", ()))
        return completed.value

    def _install(self):
        prepared = self._prepare()
        return prepared, self._complete(prepared)

    @property
    def delivered(self) -> pathlib.Path:
        return pathlib.Path(self.project_root) / ".claude/skills/code-review"

    def _installed_root(self, prepared) -> str:
        return artifact_root(
            prepared.action.installations[0].coordinate,
            Scope.PROJECT,
            project_root=self.project_root,
            data_root=self.data_root,
        )

    # -- what the install has to be true of ---------------------------------------------------

    def test_a_skill_reaches_a_reviewable_action_with_nothing_to_answer(self) -> None:
        """An artifact that starts nothing declares no inputs, so screen 07 has nothing to ask."""

        prepared = self._prepare()

        self.assertTrue(prepared.ready)
        self.assertEqual((), prepared.draft.inputs.unanswered)
        self.assertIsNotNone(prepared.review_digest)

    def test_planning_a_skill_writes_nothing_where_the_harness_reads(self) -> None:
        prepared = self._prepare()

        self.assertFalse(self.delivered.exists(), "planning delivered before anybody confirmed")
        self.assertFalse(pathlib.Path(self._installed_root(prepared)).exists())

    def test_installing_puts_the_authored_files_where_the_harness_reads_them(self) -> None:
        self._install()

        self.assertEqual(SKILL_BODY, (self.delivered / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(
            STYLE_BODY,
            (self.delivered / "reference/style.md").read_text(encoding="utf-8"),
            "a Skill is delivered as a tree, so what is nested in the payload stays nested",
        )

    def test_what_is_delivered_is_a_copy_of_the_tree_this_install_owns(self) -> None:
        """Not a link into the store and not the store's object itself: uninstalling this artifact
        must not be able to take away a tree another installation of the same version shares."""

        prepared, _ = self._install()
        payload = pathlib.Path(self._installed_root(prepared)) / "payload"

        self.assertFalse(self.delivered.is_symlink())
        self.assertEqual(
            (payload / "SKILL.md").read_text(encoding="utf-8"),
            (self.delivered / "SKILL.md").read_text(encoding="utf-8"),
        )

    def test_nothing_is_launched_registered_or_given_an_interpreter(self) -> None:
        """INV-010: kind, package format and runtime protocol are separate dimensions. A Skill
        that acquired a launcher would have a later reconciler repair a process nobody installed
        into existence."""

        prepared, _ = self._install()
        installed = pathlib.Path(self._installed_root(prepared))

        self.assertFalse((installed / "bin").exists(), "a Skill was given a launcher to run")
        self.assertFalse((installed / "env").exists(), "a Skill was given its own interpreter")
        self.assertFalse(
            (pathlib.Path(self.project_root) / ".claude/settings.json").exists(),
            "a Skill was registered with a harness rather than delivered to it",
        )

    def test_what_the_harness_reads_is_not_readable_by_anyone_else(self) -> None:
        self._install()

        self.assertEqual(0, os.stat(self.delivered / "SKILL.md").st_mode & 0o077)

    def test_the_install_is_recorded_and_the_machine_read_back_from_disk_reports_it(self) -> None:
        prepared, completed = self._install()

        self.assertIs(completed.action.execution.status, InstallationExecutionStatus.COMPLETED)
        self.assertEqual(
            completed.action.recorded.receipt.review_digest, str(prepared.review_digest)
        )
        coordinate = str(prepared.action.installations[0].coordinate)
        installed = {view.coordinate: view for view in completed.machine.installed}
        self.assertIn(coordinate, installed)
        self.assertEqual(
            "ready",
            installed[coordinate].health,
            "a Skill nothing is wrong with was read back as something else",
        )

    def test_an_edited_delivery_is_drift_the_reread_machine_reports(self) -> None:
        """The delivery digest is what makes this detectable. Without it an install would look
        healthy whatever somebody had since written into the directory the harness reads."""

        prepared, completed = self._install()
        (self.delivered / "SKILL.md").chmod(0o600)
        (self.delivered / "SKILL.md").write_text("# not what was approved\n", encoding="utf-8")

        planned = prepared.action.installations[0]
        current = observe_planned_installation(
            planned, registry=LocalHarnessRegistry(self.project_root)
        )
        delivery = ComponentId(Component.DELIVERY, "claude")
        state = {item.id: item.state for item in current.components}

        self.assertIn(delivery, state)
        self.assertNotEqual("matched", state[delivery].value)

    # -- and what taking it back out has to be true of ----------------------------------------

    def test_withdrawing_takes_the_skill_out_of_the_harness_directory(self) -> None:
        prepared, _ = self._install()
        neighbour = self.delivered.parent / "somebody-elses-skill"
        neighbour.mkdir()

        planned = prepared.action.installations[0]
        removal = removal_state_from_placement(
            planned.coordinate,
            prepared.action.offer.installations[0].deliveries and _receipt(planned),
        )
        interpreters = interpreters_for(
            (planned,), registry=LocalHarnessRegistry(self.project_root)
        )
        self.assertIsInstance(interpreters, Ok, getattr(interpreters, "diagnostics", ()))

        def inspect():
            return observe_planned_installation(
                planned, registry=LocalHarnessRegistry(self.project_root)
            )

        repair = plan_repair(removal, inspect(), policy=EffectivePolicy())
        self.assertIsInstance(repair, Ok, getattr(repair, "diagnostics", ()))
        outcome = execute_repair(repair.value, removal, interpreters.value, inspect=inspect)

        self.assertIs(outcome.value.status, ExecutionStatus.CONVERGED)
        self.assertFalse(self.delivered.exists(), "the Skill is still where the harness reads it")
        self.assertFalse(
            pathlib.Path(self._installed_root(prepared)).exists(),
            "the artifact's own tree outlived the artifact",
        )
        self.assertTrue(
            neighbour.is_dir(),
            "withdrawing one Skill took away the directory the harness reads all of them from",
        )


def _receipt(planned):
    from agent_artifacts.application.installation_proposal import intended_placement_receipt

    return intended_placement_receipt(planned)


if __name__ == "__main__":
    unittest.main()
