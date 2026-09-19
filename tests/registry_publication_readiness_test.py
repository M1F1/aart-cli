"""CP-26.18: publish, Push readiness and generated CI share one gate contract."""

from __future__ import annotations

import unittest

from aart_cli.application.registry_publication import prepare_registry_publication_state
from aart_cli.domain.result import Ok
from aart_cli.registry_commands.planning import project_registry_workspace_plan
from aart_cli.registry_commands.publication import REGISTRY_PUBLICATION_GATES
from aart_cli.registry_commands.templates import REGISTRY_CI_WORKFLOW
from aart_cli.runtime_contract import EXECUTABLE_CAPABILITIES, EXECUTABLE_VERSION
from tests.registry_maintenance_fixtures import (
    empty_registry_snapshot,
    replace_snapshot_file,
    snapshot_file,
)


def _prepare(snapshot):
    return prepare_registry_publication_state(
        snapshot,
        executable_version=EXECUTABLE_VERSION,
        available_capabilities=EXECUTABLE_CAPABILITIES,
    )


class RegistryPublicationReadinessTest(unittest.TestCase):
    def test_the_contract_names_every_mandatory_gate_once_in_order(self) -> None:
        self.assertEqual(
            tuple(item.name for item in REGISTRY_PUBLICATION_GATES),
            ("format", "lock", "build", "validate", "audit", "compatibility"),
        )

    def test_the_generated_workflow_runs_the_shared_gate_commands(self) -> None:
        workflow = REGISTRY_CI_WORKFLOW.decode("utf-8")

        for gate in REGISTRY_PUBLICATION_GATES:
            if not gate.in_generated_workflow:
                continue
            for command in gate.commands:
                expected = (
                    "aart-cli registry test --source . --compatibility ${{ matrix.compatibility }}"
                    if gate.name == "compatibility"
                    else command
                )
                with self.subTest(gate=gate.name, command=expected):
                    self.assertIn(expected, workflow)

    def test_the_one_gate_ci_does_not_run_is_the_one_that_could_prove_nothing_there(self) -> None:
        """CP-26.5: a lock over the approved representation resolves nothing.

        Sharing one list between `publish` and the generated workflow is only safe while the list
        says where each gate runs. Rendering it whole put `lock` back into every generated
        registry's CI as a step that can only ever report "nothing to resolve".
        """

        workflow = REGISTRY_CI_WORKFLOW.decode("utf-8")
        absent = tuple(
            item for item in REGISTRY_PUBLICATION_GATES if not item.in_generated_workflow
        )

        self.assertEqual(tuple(item.name for item in absent), ("lock",))
        for gate in absent:
            for command in gate.commands:
                with self.subTest(command=command):
                    self.assertNotIn(command, workflow)
        self.assertNotIn("aart-cli registry lock", workflow)

    def test_canonical_outputs_make_every_gate_green_and_leave_no_build_change(self) -> None:
        original = empty_registry_snapshot()
        first = _prepare(original)
        self.assertIsInstance(first, Ok)
        assert isinstance(first, Ok)
        projected = project_registry_workspace_plan(original, first.value.plan)
        self.assertIsInstance(projected, Ok)
        assert isinstance(projected, Ok)

        repeated = _prepare(projected.value)

        self.assertIsInstance(repeated, Ok)
        assert isinstance(repeated, Ok)
        self.assertEqual(repeated.value.plan.changed_paths, 0)
        self.assertTrue(repeated.value.passed)
        self.assertEqual(
            tuple(item.name for item in repeated.value.gates),
            tuple(item.name for item in REGISTRY_PUBLICATION_GATES),
        )

    def test_one_skipped_format_gate_makes_publication_unready(self) -> None:
        snapshot = empty_registry_snapshot()
        manifest = snapshot_file(snapshot, "aart-registry.json")
        unformatted = replace_snapshot_file(
            snapshot,
            "aart-registry.json",
            b"  " + manifest.replace(b":", b": ", 1),
        )

        prepared = _prepare(unformatted)

        self.assertIsInstance(prepared, Ok)
        assert isinstance(prepared, Ok)
        by_name = {item.name: item for item in prepared.value.gates}
        self.assertFalse(prepared.value.passed)
        self.assertFalse(by_name["format"].passed)
        self.assertIn("format would change", " ".join(by_name["format"].details))


if __name__ == "__main__":
    unittest.main()
