"""CP-11 — comparing desired against current, and repairing only what drifted."""

from __future__ import annotations

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from aart_cli.application.installation_verification import InstallationObservation
from aart_cli.application.installed_state import (
    current_state_from_observation,
    desired_state_from_receipt,
)
from aart_cli.application.reconciliation import (
    RECONCILE_INVALID,
    RECONCILE_POLICY_VIOLATION,
    plan_repair,
    repair_converged,
    repair_plan_to_data,
)
from aart_cli.domain.credentials import (
    CredentialProviderRef,
    CredentialReference,
    credential_component_names,
)
from aart_cli.domain.effects import (
    ConfigureHarness,
    CopyTree,
    CreatePythonEnvironment,
    EffectCapabilities,
    InstallPythonDependencies,
    ReplaceCredential,
    RiskClass,
    StoreCredential,
    WriteFile,
)
from aart_cli.domain.harness import McpRegistration, Scope, mcp_target
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    ObjectDigest,
    SourceAlias,
)
from aart_cli.domain.installation_owner import credential_address, installation_owner
from aart_cli.domain.launch import Transport
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.receipts import InstallationReceipt
from aart_cli.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    Drift,
    DriftKind,
    compare_states,
)
from aart_cli.domain.result import Err, Ok

STATES = (ComponentState.MATCHED, ComponentState.ABSENT, ComponentState.DIVERGENT)

ARTIFACT = ArtifactCoordinate(SourceAlias("public"), ArtifactIdentity("mcp", "github"), "1.5.0")
ROOT = "/opt/agents/mcp/github"

PAYLOAD = ComponentId(Component.PAYLOAD)
ENVIRONMENT = ComponentId(Component.RUNTIME_ENVIRONMENT)
DEPENDENCIES = ComponentId(Component.RUNTIME_DEPENDENCIES)
TOKEN = ComponentId(Component.CREDENTIAL, "github-token")
LAUNCHER = ComponentId(Component.LAUNCHER)
HARNESS = ComponentId(Component.HARNESS, "tabnine")


def desired_state(*, extra: tuple[DesiredComponent, ...] = ()) -> DesiredState:
    return DesiredState(
        ARTIFACT,
        (
            DesiredComponent(PAYLOAD, (CopyTree("/store/github", f"{ROOT}/payload"),)),
            DesiredComponent(
                ENVIRONMENT,
                (
                    CreatePythonEnvironment(
                        "mcp/github", f"{ROOT}/runtime/.venv", "/usr/bin/python3"
                    ),
                ),
            ),
            DesiredComponent(
                DEPENDENCIES,
                (
                    InstallPythonDependencies(
                        f"{ROOT}/runtime/.venv",
                        f"{ROOT}/payload/requirements.txt",
                        "requirements",
                        "pip",
                    ),
                ),
            ),
            DesiredComponent(TOKEN, (ReplaceCredential("github-token", "macos-keychain"),)),
            DesiredComponent(
                LAUNCHER, (WriteFile(f"{ROOT}/launch.sh", "sha256:" + "a" * 64, True),)
            ),
            DesiredComponent(
                HARNESS,
                (ConfigureHarness("tabnine", "mcp/github", ".tabnine/agent/settings.json"),),
            ),
            *extra,
        ),
    )


def current_state(**states: ComponentState) -> CurrentState:
    """Everything matched unless named. `omit` drops components the inspector never looked at."""

    omitted = states.pop("omit", ())
    by_name = {
        "payload": PAYLOAD,
        "environment": ENVIRONMENT,
        "dependencies": DEPENDENCIES,
        "token": TOKEN,
        "launcher": LAUNCHER,
        "harness": HARNESS,
    }
    observed = []
    for name, identifier in by_name.items():
        if identifier in omitted:
            continue
        observed.append(_observed(identifier, states.get(name, ComponentState.MATCHED)))
    return CurrentState(ARTIFACT, tuple(observed))


def _observed(identifier: ComponentId, state: ComponentState):
    from aart_cli.domain.reconciliation import ObservedComponent

    return ObservedComponent(identifier, state)


def plan(current: CurrentState, *, policy: EffectivePolicy | None = None, desired=None):
    return plan_repair(desired or desired_state(), current, policy=policy or EffectivePolicy())


class ComponentAlgebraTest(unittest.TestCase):
    def test_a_component_that_can_repeat_must_be_named(self):
        ComponentId(Component.CREDENTIAL, "github-token")
        with self.assertRaises(ValueError):
            ComponentId(Component.CREDENTIAL)
        with self.assertRaises(ValueError):
            ComponentId(Component.HARNESS)

    def test_a_component_that_occurs_once_takes_no_name(self):
        ComponentId(Component.LAUNCHER)
        with self.assertRaises(ValueError):
            ComponentId(Component.LAUNCHER, "extra")

    def test_components_render_and_order_by_dependency_not_by_alphabet(self):
        self.assertEqual(str(LAUNCHER), "launcher")
        self.assertEqual(str(TOKEN), "credential:github-token")
        ordered = sorted((HARNESS, PAYLOAD, TOKEN, ENVIRONMENT), key=lambda item: item.sort_key)
        self.assertEqual(ordered, [PAYLOAD, ENVIRONMENT, TOKEN, HARNESS])

    def test_a_desired_component_reports_whether_all_its_effects_repair_alone(self):
        self.assertTrue(
            DesiredComponent(
                LAUNCHER, (WriteFile("/x/launch.sh", "sha256:" + "a" * 64),)
            ).independently_repairable
        )
        weak = _WeakEffect()
        self.assertFalse(DesiredComponent(PAYLOAD, (weak,)).independently_repairable)

    def test_a_state_refuses_to_hold_the_same_component_twice(self):
        with self.assertRaises(ValueError):
            DesiredState(
                ARTIFACT,
                (
                    DesiredComponent(LAUNCHER, (WriteFile("/a", "sha256:" + "a" * 64),)),
                    DesiredComponent(LAUNCHER, (WriteFile("/b", "sha256:" + "b" * 64),)),
                ),
            )


class _WeakEffect:
    """An effect an interpreter cannot repair on its own."""

    risk = RiskClass.HIGH_RISK_EXECUTION
    capabilities = EffectCapabilities(True, False, False, False)


class ComparisonTest(unittest.TestCase):
    def test_an_installation_that_matches_has_no_drift(self):
        self.assertEqual(compare_states(desired_state(), current_state()), ())

    def test_each_observed_state_maps_to_the_drift_it_means(self):
        cases = {
            ComponentState.ABSENT: DriftKind.MISSING,
            ComponentState.DIVERGENT: DriftKind.DIVERGENT,
            ComponentState.UNKNOWN: DriftKind.UNVERIFIABLE,
        }
        for state, expected in cases.items():
            with self.subTest(state=state):
                drift = compare_states(desired_state(), current_state(token=state))
                self.assertEqual(drift, (Drift(TOKEN, expected, True),))

    def test_a_component_nobody_looked_at_is_drift_rather_than_a_match(self):
        drift = compare_states(desired_state(), current_state(omit=(LAUNCHER,)))
        self.assertEqual(drift, (Drift(LAUNCHER, DriftKind.UNOBSERVED, True),))

    def test_something_present_that_nothing_desires_is_named_and_not_repaired(self):
        stray = ComponentId(Component.HARNESS, "opencode")
        current = CurrentState(
            ARTIFACT,
            current_state().components + (_observed(stray, ComponentState.MATCHED),),
        )
        self.assertEqual(
            compare_states(desired_state(), current), (Drift(stray, DriftKind.UNEXPECTED, False),)
        )

    def _without_payload(self) -> DesiredState:
        """The desired state a doctor builds: no payload source, so no payload to repair."""
        kept = tuple(item for item in desired_state().components if item.id != PAYLOAD)
        self.assertEqual(len(kept), len(desired_state().components) - 1)
        return DesiredState(ARTIFACT, kept)

    def test_a_component_nothing_desires_that_is_gone_is_named_by_what_is_wrong(self):
        """INV-228: owned state changed outside AART is surfaced, in the words of the damage.

        A payload the reconciler has no source to repair from is still a payload that is gone.
        Calling that UNEXPECTED -- the word for something present nobody wanted, whose remedy is
        uninstall -- describes the opposite of the situation the operator is actually in.
        """
        for state, kind in (
            (ComponentState.ABSENT, DriftKind.MISSING),
            (ComponentState.DIVERGENT, DriftKind.DIVERGENT),
            (ComponentState.UNKNOWN, DriftKind.UNVERIFIABLE),
        ):
            with self.subTest(state=state):
                self.assertEqual(
                    compare_states(self._without_payload(), current_state(payload=state)),
                    (Drift(PAYLOAD, kind, False),),
                )

    def test_damage_nothing_can_repair_is_never_reported_as_repairable(self):
        """No effect was planned for it, so no plan may claim to put it right."""
        (drift,) = compare_states(
            self._without_payload(), current_state(payload=ComponentState.ABSENT)
        )
        self.assertFalse(drift.repairable)

    def test_comparing_states_for_different_artifacts_is_refused(self):
        other = ArtifactCoordinate(
            SourceAlias("public"), ArtifactIdentity("mcp", "gitlab"), "1.0.0"
        )
        with self.assertRaises(ValueError):
            compare_states(desired_state(), CurrentState(other, ()))

    def test_drift_is_ordered_by_dependency_so_a_reader_sees_the_cause_first(self):
        drift = compare_states(
            desired_state(),
            current_state(harness=ComponentState.DIVERGENT, environment=ComponentState.ABSENT),
        )
        self.assertEqual([item.component for item in drift], [ENVIRONMENT, HARNESS])


class MinimalRepairTest(unittest.TestCase):
    def test_an_installation_with_no_drift_plans_nothing(self):
        result = plan(current_state())
        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        self.assertEqual(result.value.steps, ())
        self.assertEqual(result.value.drift, ())
        self.assertTrue(repair_converged(desired_state(), current_state()))

    def test_one_bad_credential_repairs_the_credential_and_nothing_else(self):
        result = plan(current_state(token=ComponentState.DIVERGENT))
        self.assertEqual([step.component for step in result.value.steps], [TOKEN])
        self.assertEqual(
            result.value.steps[0].effect, ReplaceCredential("github-token", "macos-keychain")
        )

    def test_a_missing_environment_does_not_drag_the_payload_along(self):
        result = plan(current_state(environment=ComponentState.ABSENT))
        self.assertEqual([step.component for step in result.value.steps], [ENVIRONMENT])

    def test_steps_run_in_dependency_order_not_canonical_order(self):
        result = plan(
            current_state(
                harness=ComponentState.ABSENT,
                payload=ComponentState.ABSENT,
                dependencies=ComponentState.ABSENT,
            )
        )
        self.assertEqual(
            [step.component for step in result.value.steps], [PAYLOAD, DEPENDENCIES, HARNESS]
        )

    def test_a_component_that_cannot_repair_alone_escalates_instead_of_being_rebuilt(self):
        desired = DesiredState(
            ARTIFACT,
            (
                DesiredComponent(PAYLOAD, (_WeakEffect(),)),  # type: ignore[arg-type]
                DesiredComponent(LAUNCHER, (WriteFile(f"{ROOT}/launch.sh", "sha256:" + "a" * 64),)),
            ),
        )
        current = CurrentState(
            ARTIFACT,
            (
                _observed(PAYLOAD, ComponentState.DIVERGENT),
                _observed(LAUNCHER, ComponentState.DIVERGENT),
            ),
        )
        result = plan_repair(desired, current, policy=EffectivePolicy())
        self.assertEqual(result.value.escalated, (PAYLOAD,))
        self.assertEqual([step.component for step in result.value.steps], [LAUNCHER])
        self.assertFalse(result.value.complete)

    def test_something_unexpected_escalates_because_removal_is_not_this_engines_job(self):
        stray = ComponentId(Component.HARNESS, "opencode")
        current = CurrentState(
            ARTIFACT, current_state().components + (_observed(stray, ComponentState.MATCHED),)
        )
        result = plan(current)
        self.assertEqual(result.value.escalated, (stray,))
        self.assertEqual(result.value.steps, ())

    def test_a_repair_the_policy_forbids_fails_the_plan_rather_than_being_dropped(self):
        policy = EffectivePolicy(forbidden_effects=frozenset({"replace-credential"}))
        result = plan(current_state(token=ComponentState.DIVERGENT), policy=policy)
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, RECONCILE_POLICY_VIOLATION)

    def test_a_repair_above_the_risk_ceiling_fails_the_plan(self):
        policy = EffectivePolicy(risk_ceiling=RiskClass.LOCAL_MUTATION)
        result = plan(current_state(environment=ComponentState.ABSENT), policy=policy)
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, RECONCILE_POLICY_VIOLATION)

    def test_a_policy_that_forbids_nothing_that_drifted_still_plans(self):
        policy = EffectivePolicy(forbidden_effects=frozenset({"replace-credential"}))
        result = plan(current_state(launcher=ComponentState.DIVERGENT), policy=policy)
        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        self.assertEqual([step.component for step in result.value.steps], [LAUNCHER])

    def test_states_for_different_artifacts_fail_rather_than_raise(self):
        other = ArtifactCoordinate(
            SourceAlias("public"), ArtifactIdentity("mcp", "gitlab"), "1.0.0"
        )
        result = plan_repair(desired_state(), CurrentState(other, ()), policy=EffectivePolicy())
        self.assertIsInstance(result, Err)
        self.assertEqual(result.diagnostics[0].code, RECONCILE_INVALID)

    def test_a_plan_summarises_its_risks_and_digests_its_own_content(self):
        first = plan(current_state(environment=ComponentState.ABSENT)).value
        second = plan(current_state(environment=ComponentState.ABSENT)).value
        self.assertEqual(str(first.review_digest), str(second.review_digest))
        self.assertEqual(first.risks, (RiskClass.EXECUTABLE_INSTALL,))
        self.assertTrue(first.complete)

    def test_the_projection_names_components_and_never_carries_a_value(self):
        projected = repair_plan_to_data(plan(current_state(token=ComponentState.ABSENT)).value)
        self.assertEqual(
            projected["drift"],
            [{"component": "credential:github-token", "kind": "missing", "repairable": True}],
        )
        self.assertEqual(projected["escalated"], [])
        self.assertIn("review_digest", projected)

    def test_repairing_and_re_observing_a_matched_installation_converges(self):
        self.assertFalse(
            repair_converged(desired_state(), current_state(launcher=ComponentState.ABSENT))
        )
        self.assertTrue(repair_converged(desired_state(), current_state()))


class MinimalityPropertyTest(unittest.TestCase):
    @settings(max_examples=60, deadline=None)
    @given(
        st.fixed_dictionaries(
            {
                name: st.sampled_from(STATES)
                for name in (
                    "payload",
                    "environment",
                    "dependencies",
                    "token",
                    "launcher",
                    "harness",
                )
            }
        )
    )
    def test_planned_effects_are_only_the_drifted_components_effects(self, states):
        result = plan(current_state(**states))
        self.assertIsInstance(result, Ok, getattr(result, "diagnostics", ()))
        drifted = {item.component for item in result.value.drift}
        planned = {step.component for step in result.value.steps}
        self.assertTrue(planned <= drifted)
        matched = {
            component.id for component in desired_state().components if component.id not in drifted
        }
        self.assertEqual(planned & matched, set())

    @settings(max_examples=40, deadline=None)
    @given(st.sampled_from(STATES))
    def test_adding_a_matching_component_changes_no_plan(self, state):
        extra = DesiredComponent(
            ComponentId(Component.CONFIGURATION, "github-host"),
            (WriteFile(f"{ROOT}/config.json", "sha256:" + "c" * 64),),
        )
        before = plan(current_state(token=state)).value
        after = plan_repair(
            desired_state(extra=(extra,)),
            CurrentState(
                ARTIFACT,
                current_state(token=state).components
                + (_observed(extra.id, ComponentState.MATCHED),),
            ),
            policy=EffectivePolicy(),
        ).value
        self.assertEqual(
            [step.component for step in before.steps], [step.component for step in after.steps]
        )
        self.assertEqual(before.drift, after.drift)


if __name__ == "__main__":
    unittest.main()


class InstalledStateBridgeTest(unittest.TestCase):
    """Turning a CP-10 receipt and observation into the states a reconciler compares."""

    def setUp(self) -> None:
        self.digest = ObjectDigest("sha256", "d" * 64)
        self.registration = McpRegistration(
            mcp_target("tabnine", Scope.PROJECT), "github", f"{ROOT}/launch.sh"
        )
        self.receipt = InstallationReceipt(
            "mcp/github",
            ROOT,
            f"{ROOT}/launch.sh",
            self.digest,
            f"{ROOT}/runtime/.venv/bin/python",
            Transport.STDIO,
            (self.registration,),
            (
                CredentialReference(
                    InputId("github-token"),
                    CredentialProviderRef("macos-keychain", "aart", "github-token"),
                ),
            ),
        )

    _desired_kwargs: dict = {}

    def desired(self, **kwargs):
        return desired_state_from_receipt(ARTIFACT, self.receipt, **kwargs)

    def observed(self, **kwargs):
        fields = {
            "launcher_present": True,
            "launcher_executable": True,
            "launcher_digest": self.digest,
            "interpreter_present": True,
            "registered_commands": (("tabnine", "github", f"{ROOT}/launch.sh"),),
        }
        credentials = kwargs.pop("credentials", (("github-token", ComponentState.MATCHED),))
        fields.update(kwargs)
        return current_state_from_observation(
            self.desired(**self._desired_kwargs),
            self.receipt,
            InstallationObservation(**fields),
            credentials=credentials,
        )

    def test_a_receipt_becomes_launcher_credential_and_harness_components(self):
        self.assertEqual(
            [component.id for component in self.desired().components],
            [
                ComponentId(Component.CREDENTIAL, "github-token"),
                ComponentId(Component.LAUNCHER),
                ComponentId(Component.HARNESS, "tabnine"),
            ],
        )

    def test_the_environment_appears_only_when_the_plan_says_what_built_it(self):
        self.assertNotIn(
            ComponentId(Component.RUNTIME_ENVIRONMENT),
            [component.id for component in self.desired().components],
        )
        with_base = self.desired(base_interpreter="/usr/bin/python3")
        self.assertIn(
            ComponentId(Component.RUNTIME_ENVIRONMENT),
            [component.id for component in with_base.components],
        )

    def test_a_credential_is_stored_when_absent_and_replaced_when_wrong(self):
        component = next(
            item
            for item in self.desired().components
            if item.id == ComponentId(Component.CREDENTIAL, "github-token")
        )
        self.assertIsInstance(component.effects_for(DriftKind.MISSING)[0], StoreCredential)
        self.assertIsInstance(component.effects_for(DriftKind.DIVERGENT)[0], ReplaceCredential)
        self.assertIsInstance(component.effects_for(DriftKind.UNVERIFIABLE)[0], ReplaceCredential)

    def test_an_intact_installation_reconciles_to_nothing(self):
        result = plan_repair(self.desired(), self.observed(), policy=EffectivePolicy())
        self.assertEqual(result.value.steps, ())
        self.assertTrue(result.value.complete)

    def test_each_damaged_component_produces_a_repair_for_only_itself(self):
        cases = (
            (ComponentId(Component.LAUNCHER), {"launcher_present": False}),
            (
                ComponentId(Component.LAUNCHER),
                {"launcher_digest": ObjectDigest("sha256", "e" * 64)},
            ),
            (ComponentId(Component.LAUNCHER), {"launcher_executable": False}),
            (
                ComponentId(Component.HARNESS, "tabnine"),
                {"registered_commands": (("tabnine", "github", None),)},
            ),
            (
                ComponentId(Component.CREDENTIAL, "github-token"),
                {"credentials": (("github-token", ComponentState.DIVERGENT),)},
            ),
        )
        for component, override in cases:
            with self.subTest(component=str(component)):
                result = plan_repair(
                    self.desired(), self.observed(**override), policy=EffectivePolicy()
                )
                self.assertEqual([step.component for step in result.value.steps], [component])

    def test_a_harness_pointing_somewhere_else_is_divergent_not_missing(self):
        current = self.observed(registered_commands=(("tabnine", "github", "/elsewhere.sh"),))
        drift = compare_states(self.desired(), current)
        self.assertEqual(
            drift, (Drift(ComponentId(Component.HARNESS, "tabnine"), DriftKind.DIVERGENT, True),)
        )

    def test_a_partial_desired_state_does_not_make_a_good_environment_unexpected(self):
        """The regression this pairing exists for: describing less must not invent drift."""

        partial = self.desired()
        without_environment = current_state_from_observation(
            partial,
            self.receipt,
            InstallationObservation(
                launcher_present=True,
                launcher_executable=True,
                launcher_digest=self.digest,
                interpreter_present=True,
                registered_commands=(("tabnine", "github", f"{ROOT}/launch.sh"),),
            ),
            credentials=(("github-token", ComponentState.MATCHED),),
        )
        self.assertEqual(compare_states(partial, without_environment), ())
        self.assertNotIn(
            ComponentId(Component.RUNTIME_ENVIRONMENT),
            [item.id for item in without_environment.components],
        )

    def test_a_current_state_must_be_paired_with_the_desired_state_it_answers(self):
        with self.assertRaises(ValueError):
            current_state_from_observation(
                ARTIFACT,  # type: ignore[arg-type]
                self.receipt,
                InstallationObservation(),
            )


class CredentialComponentNamesTest(unittest.TestCase):
    """§169.4-6: one declared input, several installations, and a name that still says which.

    The input id was a name while one artifact held one item for it. Each installation holding its
    own means the id alone can appear four times in one desired state, where naming the same
    component twice is refused -- correctly, because nothing downstream could tell the four apart.
    """

    def _reference(self, harness: str, input_id: str = "github-token"):
        return CredentialReference(
            InputId(input_id),
            credential_address(
                installation_owner(
                    ArtifactCoordinate(
                        SourceAlias("company"), ArtifactIdentity("mcp", "github"), "1.0.0"
                    ),
                    scope=Scope.PROJECT,
                    root="/work/project",
                    harness=harness,
                ),
                InputId(input_id),
            ),
        )

    def test_one_item_for_an_input_keeps_the_name_it_always_had(self):
        names = credential_component_names((self._reference("claude"),))

        self.assertEqual(("github-token",), names)

    def test_installations_holding_their_own_item_are_told_apart(self):
        references = (self._reference("claude"), self._reference("opencode"))

        names = credential_component_names(references)

        self.assertEqual(2, len(set(names)))
        for name in names:
            self.assertTrue(name.startswith("github-token."))
            self.assertIsNotNone(ComponentId(Component.CREDENTIAL, name))

    def test_a_name_is_the_same_every_time_it_is_asked_for(self):
        references = (self._reference("claude"), self._reference("opencode"))

        self.assertEqual(
            credential_component_names(references), credential_component_names(references)
        )

    def test_a_second_input_is_not_disambiguated_because_another_one_was(self):
        references = (
            self._reference("claude"),
            self._reference("opencode"),
            self._reference("claude", "github-org"),
        )

        names = credential_component_names(references)

        self.assertEqual("github-org", names[2])
