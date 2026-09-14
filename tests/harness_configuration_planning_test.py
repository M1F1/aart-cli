"""Planning puts each harness's configuration beside the artifact, and records only where (D-264).

The values a person answers at install are ordinary configuration. They are planned as one file per
harness under the artifact root, each harness registration names its own file, the shared launcher
holds none of them, and the receipt keeps a path and a digest per harness -- never a value.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from agent_artifacts.application.installation_proposal import (
    PlannedInstallation,
    desired_state_for,
    intended_receipt,
)
from agent_artifacts.application.installation_verification import InstallationObservation
from agent_artifacts.application.installed_state import current_state_from_observation
from agent_artifacts.application.runtime_projection import configuration_projection
from agent_artifacts.domain.configuration_files import (
    CONFIGURATION_FILE_INVALID,
    parse_configuration_file,
)
from agent_artifacts.domain.effects import WriteFile
from agent_artifacts.domain.harness import Scope, mcp_target
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.inputs import PersistedConfigValue, SecretProviderReference
from agent_artifacts.domain.receipts import (
    installation_receipt_from_data,
    installation_receipt_to_data,
)
from agent_artifacts.domain.reconciliation import Component, ComponentId, ComponentState
from agent_artifacts.domain.result import Err, Ok
from tests.artifact_installation_test import ORG, ROOT, TOKEN, _description, _plan, _sources

HARNESSES = ("claude", "codex", "opencode", "tabnine")
TOKEN_SHAPED = "ghp" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def _targets(*harnesses: str):
    return tuple(mcp_target(name, Scope.USER) for name in harnesses)


def _planned(*harnesses: str) -> PlannedInstallation:
    planned = _plan(targets=_targets(*harnesses))
    assert isinstance(planned, Ok), planned
    return planned.value


class EachHarnessGetsItsOwnFileTest(unittest.TestCase):
    def test_every_harness_asked_for_has_a_file_holding_the_answered_values(self):
        planned = _planned("claude", "opencode")
        self.assertEqual(
            [(item.harness, item.path) for item in planned.configuration],
            [
                ("claude", f"{ROOT}/config/claude.conf"),
                ("opencode", f"{ROOT}/config/opencode.conf"),
            ],
        )
        for item in planned.configuration:
            self.assertEqual(parse_configuration_file(item.content), Ok(((ORG, "acme"),)))

    def test_each_registration_names_its_own_harness_so_the_launcher_reads_that_file(self):
        planned = _planned("claude", "opencode")
        self.assertEqual(
            [(item.target.harness, item.arguments) for item in planned.registrations],
            [("claude", ("claude",)), ("opencode", ("opencode",))],
        )

    def test_the_shared_launcher_holds_no_configuration_value(self):
        planned = _planned("claude")
        self.assertNotIn("acme", planned.launcher.content)

    def test_an_artifact_without_configuration_has_no_file_and_no_argument(self):
        description = _description(inputs=(_description().inputs[0],))
        planned = _plan(description, sources=(_sources()[0],), targets=_targets("claude"))
        assert isinstance(planned, Ok)
        self.assertEqual(planned.value.configuration, ())
        self.assertEqual(planned.value.registrations[0].arguments, ())
        self.assertNotIn("AART_HARNESS", planned.value.launcher.content)

    def test_a_credential_pasted_into_a_configuration_answer_is_never_planned_to_disk(self):
        refused = _plan(
            sources=(_sources()[0], PersistedConfigValue(ORG, TOKEN_SHAPED)),
            targets=_targets("claude"),
        )
        self.assertIsInstance(refused, Err)
        self.assertEqual(refused.diagnostics[0].code, CONFIGURATION_FILE_INVALID)
        self.assertNotIn(TOKEN_SHAPED, refused.diagnostics[0].message)

    @given(st.sets(st.sampled_from(HARNESSES), min_size=1))
    def test_the_configured_harnesses_are_exactly_the_registered_ones(self, chosen):
        planned = _planned(*sorted(chosen))
        self.assertEqual({item.harness for item in planned.configuration}, chosen)
        self.assertEqual(
            {(item.target.harness, item.arguments) for item in planned.registrations},
            {(name, (name,)) for name in chosen},
        )


class APlanThatWouldStartUnconfiguredIsRefusedTest(unittest.TestCase):
    def test_a_registration_that_does_not_name_its_file_is_refused(self):
        planned = _planned("claude")
        (registration,) = planned.registrations
        with self.assertRaisesRegex(ValueError, "would not name the configuration"):
            replace(planned, registrations=(replace(registration, arguments=()),))

    def test_configured_values_with_no_file_for_a_harness_are_refused(self):
        planned = _planned("claude")
        with self.assertRaisesRegex(ValueError, "has its own file"):
            replace(planned, configuration=())

    def test_a_file_holding_anything_but_the_reviewed_values_is_refused(self):
        planned = _planned("claude")
        other = configuration_projection(
            planned.environment, "claude", ((ORG, "someone-else"),)
        ).value
        with self.assertRaisesRegex(ValueError, "not the reviewed values"):
            replace(planned, configuration=(other,))


class TheReceiptKeepsWhereNotWhatTest(unittest.TestCase):
    def test_the_receipt_records_each_file_by_path_and_digest_and_round_trips(self):
        planned = _planned("claude", "tabnine")
        receipt = intended_receipt(planned)
        self.assertEqual(
            receipt.configuration_files, tuple(item.record for item in planned.configuration)
        )
        data = installation_receipt_to_data(receipt)
        self.assertNotIn("acme", json.dumps(data))
        self.assertEqual(installation_receipt_from_data(data), Ok(receipt))

    def test_a_receipt_without_configuration_is_written_exactly_as_before(self):
        description = _description(inputs=(_description().inputs[0],))
        planned = _plan(description, sources=(_sources()[0],), targets=_targets("claude"))
        assert isinstance(planned, Ok)
        self.assertNotIn(
            "configuration_files", installation_receipt_to_data(intended_receipt(planned.value))
        )

    def test_each_harness_file_is_its_own_component_and_not_the_launcher(self):
        planned = _planned("claude", "tabnine")
        components = {item.id: item for item in desired_state_for(planned).components}
        for item in planned.configuration:
            component = components[ComponentId(Component.CONFIGURATION, item.harness)]
            self.assertEqual(component.effects, (WriteFile(item.path, str(item.digest), False),))


class AFileChangedOrMissingIsReportedTest(unittest.TestCase):
    def _state(self, observed):
        planned = _planned("claude", "tabnine")
        receipt = intended_receipt(planned)
        current = current_state_from_observation(
            desired_state_for(planned),
            receipt,
            InstallationObservation(configuration_files=observed(receipt)),
        )
        return {
            item.id.name: item.state
            for item in current.components
            if item.id.component is Component.CONFIGURATION
        }

    def test_as_written_matches_edited_diverges_and_deleted_is_absent(self):
        states = self._state(
            lambda receipt: (
                ("claude", True, receipt.configuration_files[0].digest),
                ("tabnine", False, None),
            )
        )
        self.assertEqual(
            states, {"claude": ComponentState.MATCHED, "tabnine": ComponentState.ABSENT}
        )
        edited = self._state(
            lambda receipt: (
                ("claude", True, ObjectDigest("sha256", "0" * 64)),
                ("tabnine", True, None),
            )
        )
        self.assertEqual(
            edited, {"claude": ComponentState.DIVERGENT, "tabnine": ComponentState.UNKNOWN}
        )


class SecretsStayReferencesTest(unittest.TestCase):
    def test_no_secret_reference_becomes_a_configuration_line(self):
        planned = _planned("claude")
        (item,) = planned.configuration
        self.assertNotIn(str(TOKEN), item.content)
        self.assertTrue(any(isinstance(source, SecretProviderReference) for source in _sources()))


if __name__ == "__main__":
    unittest.main()
