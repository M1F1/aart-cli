"""CP-07 read-only local inspection adapter integration."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from agent_artifacts.application.installation_planning import (
    ArtifactInstallIntent,
    inspect_requirements,
    prepare_install_plan,
)
from agent_artifacts.domain.effects import CopyTree
from agent_artifacts.domain.inspection import FactState
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.requirements import (
    ExecutableRequirement,
    FilesystemRequirement,
    RequirementId,
    RuntimeRequirement,
)
from agent_artifacts.domain.result import Ok
from agent_artifacts.io.environment_inspection import LocalEnvironmentInspector
from tests.environment_planning_test import _resolved, _selection


class EnvironmentInspectionIntegrationTest(unittest.TestCase):
    def test_local_adapter_observes_without_mutating_the_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "marker.txt"
            marker.write_text("unchanged", encoding="utf-8")
            requirements = (
                RuntimeRequirement(RequirementId("python"), "python", ">=3.10"),
                ExecutableRequirement(
                    RequirementId("python-executable"), Path(sys.executable).name
                ),
                FilesystemRequirement(RequirementId("workspace-read"), str(marker), "read"),
                ExecutableRequirement(
                    RequirementId("missing-executable"),
                    "aart-intentionally-absent-executable",
                ),
            )
            before = (marker.read_bytes(), marker.stat().st_mode, tuple(sorted(os.listdir(root))))

            result = inspect_requirements(requirements, LocalEnvironmentInspector())

            assert isinstance(result, Ok), result
            facts = {item.requirement: item for item in result.value.facts}
            self.assertEqual(facts[RequirementId("python")].state, FactState.AVAILABLE)
            self.assertEqual(facts[RequirementId("workspace-read")].state, FactState.AVAILABLE)
            self.assertEqual(
                facts[RequirementId("missing-executable")].state,
                FactState.UNAVAILABLE,
            )
            self.assertEqual(
                before,
                (marker.read_bytes(), marker.stat().st_mode, tuple(sorted(os.listdir(root)))),
            )

    def test_exact_resolved_artifact_flows_through_inspection_into_one_plan(self) -> None:
        artifact = _resolved("github", character="1")
        selection = _selection(artifact)
        requirement = RuntimeRequirement(RequirementId("python"), "python", ">=3.10")
        inspector = LocalEnvironmentInspector()

        facts = inspect_requirements((requirement,), inspector)
        assert isinstance(facts, Ok), facts
        planned = prepare_install_plan(
            selection,
            (
                ArtifactInstallIntent(
                    artifact,
                    (requirement,),
                    (CopyTree("payload", ".aart/mcp/github"),),
                    runtime="python",
                    transport="stdio",
                ),
            ),
            facts.value,
            EffectivePolicy(
                allowed_registries=frozenset({"company"}),
                allowed_runtimes=frozenset({"python"}),
                allowed_transports=frozenset({"stdio"}),
            ),
        )

        assert isinstance(planned, Ok), planned
        self.assertEqual(planned.value.selection, selection)
        self.assertEqual(planned.value.requirements[0].state.value, "satisfied")
        self.assertEqual(len(planned.value.mutation.effects), 1)


if __name__ == "__main__":
    unittest.main()
