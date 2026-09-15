"""Measuring the machine an install has not happened on yet.

An install planned against an assumption that nothing is there is how a machine loses work nobody
knew about. So the paths a first install would occupy are looked at first, and whatever is found
there becomes state to compare rather than a file to overwrite.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from agent_artifacts.domain.credentials import (
    CredentialObservation,
    CredentialState,
    ProviderState,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.reconciliation import Component, ComponentState
from agent_artifacts.domain.result import Err, Ok
from agent_artifacts.io.harness import LocalHarnessRegistry
from agent_artifacts.io.installation_observation import (
    credential_component_states,
    observe_planned_installation,
)
from tests.artifact_installation_test import _plan


def _state(current, component: Component) -> ComponentState:
    return next(item.state for item in current.components if item.id.component is component)


class ObservedPlannedInstallationTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        planned = _plan()
        self.assertIsInstance(planned, Ok, getattr(planned, "diagnostics", ()))
        self.planned = planned.value

    def test_a_machine_with_nothing_installed_reports_the_payload_absent(self) -> None:
        current = observe_planned_installation(
            self.planned, registry=LocalHarnessRegistry(str(self.root))
        )

        self.assertEqual(str(current.artifact), str(self.planned.coordinate))
        self.assertIs(_state(current, Component.PAYLOAD), ComponentState.ABSENT)

    def test_the_credential_nobody_can_inspect_is_unknown_rather_than_absent(self) -> None:
        current = observe_planned_installation(
            self.planned, registry=LocalHarnessRegistry(str(self.root))
        )

        self.assertIs(_state(current, Component.CREDENTIAL), ComponentState.UNKNOWN)

    def test_it_refuses_anything_that_is_not_a_planned_installation(self) -> None:
        with self.assertRaises(ValueError):
            observe_planned_installation(
                object(),  # type: ignore[arg-type]
                registry=LocalHarnessRegistry(str(self.root)),
            )


class _Provider:
    provider = "macos-keychain"

    def __init__(self, answer) -> None:
        self.answer = answer

    def available(self) -> ProviderState:
        return ProviderState.AVAILABLE

    def inspect(self, reference):
        if isinstance(self.answer, Err):
            return self.answer
        return Ok(
            CredentialObservation(reference, ProviderState.AVAILABLE, self.answer, "measured")
        )


class CredentialComponentStateTest(unittest.TestCase):
    def _references(self):
        planned = _plan()
        assert isinstance(planned, Ok), planned
        from agent_artifacts.application.installation_proposal import intended_receipt

        return intended_receipt(planned.value).credentials

    def test_a_present_credential_matches(self) -> None:
        states = credential_component_states(
            self._references(), (_Provider(CredentialState.PRESENT),)
        )

        self.assertEqual([state for _, state in states], [ComponentState.MATCHED])

    def test_an_invalid_credential_is_divergent_rather_than_absent(self) -> None:
        """Divergent is repaired by replacing the value; absent by storing one. Different work."""

        states = credential_component_states(
            self._references(), (_Provider(CredentialState.INVALID),)
        )

        self.assertEqual([state for _, state in states], [ComponentState.DIVERGENT])

    def test_a_provider_that_failed_answers_unknown_rather_than_blocking_the_plan(self) -> None:
        refusal = Err((Diagnostic(DiagnosticCode("provider-unavailable"), Severity.ERROR, "no"),))

        states = credential_component_states(self._references(), (_Provider(refusal),))

        self.assertEqual([state for _, state in states], [ComponentState.UNKNOWN])

    def test_a_reference_with_no_provider_at_all_is_unknown(self) -> None:
        states = credential_component_states(self._references(), ())

        self.assertEqual([state for _, state in states], [ComponentState.UNKNOWN])


if __name__ == "__main__":
    unittest.main()
