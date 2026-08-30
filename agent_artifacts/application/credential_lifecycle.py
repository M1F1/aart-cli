"""Pure credential-lifecycle planning: inspect, store, verify, replace, delete.

Two rules shape every function here. Replacement never needs the previous value, so no operation
accepts, returns or reports one. And a reference may serve several artifacts, so any mutation that
could break them names them first and destructive removal needs that list acknowledged.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_artifacts.domain.credentials import (
    CredentialIntent,
    CredentialObservation,
    CredentialState,
    ProviderState,
    credential_observation_to_data,
)
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import (
    DeleteCredential,
    Effect,
    ReplaceCredential,
    RiskClass,
    StoreCredential,
    VerifyCredential,
    effect_to_data,
)
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.policies import EffectivePolicy, effect_to_policy_key
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import artifact_coordinate_sort_key

CREDENTIAL_DEPENDANTS = DiagnosticCode("credential-dependants-unacknowledged")
CREDENTIAL_POLICY_VIOLATION = DiagnosticCode("credential-policy-violation")
CREDENTIAL_PROVIDER_UNAVAILABLE = DiagnosticCode("credential-provider-unavailable")
CREDENTIAL_STATE_CONFLICT = DiagnosticCode("credential-state-conflict")


def _error(
    code: DiagnosticCode,
    message: str,
    *,
    details: tuple[tuple[str, str], ...] = (),
) -> Err:
    return Err((Diagnostic(code, Severity.ERROR, message, details=details),))


@dataclass(frozen=True, slots=True)
class CredentialPlan:
    """One reviewable credential operation. It holds references and effects, never a value."""

    observation: CredentialObservation
    intent: CredentialIntent
    effects: tuple[Effect, ...]
    dependants: tuple[ArtifactCoordinate, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.observation, CredentialObservation) or not isinstance(
            self.intent, CredentialIntent
        ):
            raise ValueError("credential plan is invalid")
        object.__setattr__(
            self,
            "dependants",
            tuple(sorted(set(self.dependants), key=artifact_coordinate_sort_key)),
        )

    @property
    def risks(self) -> tuple[RiskClass, ...]:
        return tuple(sorted({effect.risk for effect in self.effects}))

    @property
    def requires_acknowledgement(self) -> bool:
        """Whether a human must see the dependants before this runs."""

        return bool(self.dependants) and self.intent in {
            CredentialIntent.REPLACE,
            CredentialIntent.DELETE,
        }


def _effects(intent: CredentialIntent, observation: CredentialObservation) -> tuple[Effect, ...]:
    reference = str(observation.reference.input)
    provider = observation.reference.provider.provider
    if intent is CredentialIntent.INSPECT:
        return ()
    if intent is CredentialIntent.VERIFY:
        return (VerifyCredential(reference, provider),)
    if intent is CredentialIntent.STORE:
        return (StoreCredential(reference, provider), VerifyCredential(reference, provider))
    if intent is CredentialIntent.REPLACE:
        return (ReplaceCredential(reference, provider), VerifyCredential(reference, provider))
    return (DeleteCredential(reference, provider),)


def plan_credential_mutation(
    intent: CredentialIntent,
    observation: CredentialObservation,
    dependants: tuple[ArtifactCoordinate, ...] = (),
    *,
    policy: EffectivePolicy,
    acknowledged_dependants: tuple[ArtifactCoordinate, ...] = (),
) -> Result[CredentialPlan]:
    """Plan one lifecycle operation without touching the provider.

    `policy` has no default. A permissive policy that appears because nobody passed one is how a
    restriction stops applying without anyone deciding it should.
    """

    if not isinstance(intent, CredentialIntent) or not isinstance(
        observation, CredentialObservation
    ):
        return _error(CREDENTIAL_STATE_CONFLICT, "credential intent or observation is invalid")

    reading_only = intent in {CredentialIntent.INSPECT, CredentialIntent.VERIFY}
    if not reading_only and observation.provider_state is not ProviderState.AVAILABLE:
        return _error(
            CREDENTIAL_PROVIDER_UNAVAILABLE,
            f"credential provider {observation.reference.provider.provider} is not available",
        )
    if intent is CredentialIntent.STORE and observation.state is CredentialState.PRESENT:
        return _error(
            CREDENTIAL_STATE_CONFLICT,
            f"credential {observation.reference.input} already exists; replace it explicitly",
        )
    if intent in {CredentialIntent.REPLACE, CredentialIntent.DELETE} and (
        observation.state is CredentialState.ABSENT
    ):
        return _error(
            CREDENTIAL_STATE_CONFLICT,
            f"credential {observation.reference.input} does not exist",
        )

    provider = observation.reference.provider.provider
    if (
        not reading_only
        and policy.allowed_credential_providers is not None
        and provider not in policy.allowed_credential_providers
    ):
        return _error(
            CREDENTIAL_POLICY_VIOLATION,
            f"credential provider {provider} is forbidden by effective policy",
        )

    effects = _effects(intent, observation)
    for effect in effects:
        if effect.risk > policy.risk_ceiling:
            return _error(
                CREDENTIAL_POLICY_VIOLATION,
                f"{effect_to_policy_key(effect)} exceeds the effective policy risk ceiling",
            )
        if not policy.permits_effect(effect):
            return _error(
                CREDENTIAL_POLICY_VIOLATION,
                f"{effect_to_policy_key(effect)} is forbidden by effective policy",
            )

    outstanding = set(dependants) - set(acknowledged_dependants)
    if intent is CredentialIntent.DELETE and outstanding:
        names = ", ".join(sorted(str(item) for item in outstanding))
        return _error(
            CREDENTIAL_DEPENDANTS,
            f"deleting {observation.reference.input} would affect artifacts still using it: {names}",
            details=(("dependants", names),),
        )
    try:
        return Ok(CredentialPlan(observation, intent, effects, dependants))
    except ValueError as error:
        return _error(CREDENTIAL_STATE_CONFLICT, f"credential plan is invalid: {error}")


def credential_plan_to_data(plan: CredentialPlan) -> dict[str, object]:
    return {
        "dependants": [str(item) for item in plan.dependants],
        "effects": [effect_to_data(effect) for effect in plan.effects],
        "intent": plan.intent.value,
        "observation": credential_observation_to_data(plan.observation),
        "requires_acknowledgement": plan.requires_acknowledgement,
        "risks": [risk.name.lower().replace("_", "-") for risk in plan.risks],
    }
