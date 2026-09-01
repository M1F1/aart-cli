"""Pure consumer-facing projections over the canonical application model.

These values are the seam between application behavior and every human frontend.  They do not
inspect, plan, execute, or retain credential material.  Fast and Verbose are presentation choices
over one :class:`ConsumerPlanView`; changing profile therefore cannot change a Selection or review
digest by construction.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
from itertools import groupby
from typing import cast

from agent_artifacts.domain.credentials import CredentialObservation, CredentialReference
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.effects import RiskClass, effect_to_data
from agent_artifacts.domain.inputs import (
    BoundInputs,
    ConfigInput,
    PersistedConfigValue,
    PolicyProvidedValue,
    PromptedConfigValue,
    RuntimeInput,
    SecretInput,
    SecretProviderReference,
    binding_kind,
)
from agent_artifacts.domain.plans import InstallPlan, install_plan_to_data
from agent_artifacts.domain.receipts import RECEIPT_INVALID
from agent_artifacts.domain.reconciliation import (
    CurrentState,
    DesiredState,
    DriftKind,
    compare_states,
)
from agent_artifacts.domain.remediations import remediation_to_data
from agent_artifacts.domain.requirements import requirement_to_data
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import Collection, OwnershipReason, ResolvedSelection
from agent_artifacts.domain.serialization import CanonicalValue, canonical_json_bytes
from agent_artifacts.marketplace.model import MarketplaceCatalog

from .execution import (
    InstallationExecutionOutcome,
    InstallationExecutionStatus,
    LifecycleExecutionOutcome,
    LifecycleExecutionStatus,
)
from .installation_proposal import InstallationProposal
from .intents import (
    InstalledHealth,
    LifecycleIntentKind,
    LifecyclePlan,
    MemberHealth,
    collection_health,
    installation_health,
)
from .maintainer_views import MaintainerScreen, maintainer_navigation_targets
from .removal_proposal import RemovalProposal

__all__ = [
    "ActivityDayView",
    "ActivityEntry",
    "ActivityOutcome",
    "ActivityRecord",
    "ActivityView",
    "ApplicationScreen",
    "ConfigInputView",
    "ConsumerPlanView",
    "ConsumerScreen",
    "ConsumerSession",
    "CONSUMER_SETTINGS_INVALID",
    "ConsumerSettings",
    "SETTING_ROWS",
    "CredentialInputView",
    "CredentialRecordView",
    "EffectView",
    "InstalledArtifactView",
    "InstalledCollectionView",
    "InputView",
    "LifecycleDriftView",
    "LifecycleOutcomeView",
    "LifecyclePlanView",
    "LifecycleStepOutcomeView",
    "LifecycleStepView",
    "MarketplaceCollectionView",
    "OwnershipView",
    "PresentationProfile",
    "ReceiptArtifactView",
    "ReceiptDetailView",
    "RemediationView",
    "RequirementView",
    "SelectionMode",
    "SelectionView",
    "UndoAvailability",
    "DashboardView",
    "DoctorView",
    "RegistryView",
    "activity_from_receipts",
    "activity_view_to_data",
    "consumer_plan_to_data",
    "settings_from_data",
    "settings_to_data",
    "install_flow_screens",
    "keeps_focus",
    "navigation_targets",
    "project_activity",
    "project_dashboard",
    "project_doctor",
    "project_install_plan",
    "project_installed_artifact",
    "project_installed_collection",
    "project_unadopted_installation",
    "project_lifecycle_outcome",
    "project_lifecycle_plan",
    "project_credential_record",
    "project_collection",
    "project_required_inputs",
    "project_installation_receipt",
    "project_receipt_detail",
    "project_registries",
    "project_selection",
    "receipt_detail_from_data",
    "receipt_detail_to_data",
]


class PresentationProfile(str, Enum):
    FAST = "fast"
    VERBOSE = "verbose"


class ConsumerScreen(str, Enum):
    """The accepted consumer screen catalog, including the 04A customization state."""

    DASHBOARD = "01-dashboard"
    MARKETPLACE = "02-marketplace"
    ARTIFACT_DETAILS = "03-artifact-details"
    COLLECTION_PREVIEW = "04-collection"
    COLLECTION_CUSTOMIZE = "04a-customize-collection"
    REVIEW_SELECTION = "05-review-selection"
    AUTOMATIC_INSPECTION = "06-automatic-inspection"
    REQUIRED_INPUTS = "07-required-inputs"
    REMEDIATION = "08-remediation"
    READY = "09-ready"
    INSTALLING = "10-installing"
    SUCCESS = "11-success"
    INSTALLED = "12-installed"
    INSTALLED_ARTIFACT_DETAILS = "13-installed-artifact-details"
    INSTALLED_COLLECTION_DETAILS = "14-installed-collection-details"
    UPDATES = "15-updates"
    UPDATE_INPUTS = "16-update-inputs"
    UPDATING = "17-updating"
    UNINSTALL_REVIEW = "18-uninstall-review"
    UNINSTALLING = "19-uninstalling"
    VERIFY_REPAIR = "20-verify-repair"
    REGISTRIES = "21-registries"
    CREDENTIALS = "22-credentials"
    CREDENTIAL_DETAILS = "23-credential-details"
    CREDENTIAL_ACTION = "24-credential-action"
    ACTIVITY = "25-activity"
    ACTIVITY_DETAILS = "26-activity-details"
    RECEIPT_DETAILS = "27-receipt-details"
    SETTINGS = "28-settings"
    DOCTOR = "29-doctor"


ApplicationScreen = ConsumerScreen | MaintainerScreen


class SelectionMode(str, Enum):
    ARTIFACTS = "artifacts"
    EXACT_COLLECTION = "exact-collection"
    CUSTOM_COLLECTION = "custom-collection"


_EMPTY_BOUND_INPUTS = BoundInputs()


def _identity(data: object) -> str:
    encoded = canonical_json_bytes(cast(CanonicalValue, data))
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _risk_label(name: str) -> str:
    return name.lower().replace("_", "-")


@dataclass(frozen=True, slots=True)
class SelectionView:
    mode: SelectionMode
    artifacts: tuple[str, ...]
    collections: tuple[str, ...]
    derived_from: tuple[str, ...]
    resolved: tuple[str, ...]
    semantic_identity: str
    explanation: str


def project_selection(selection: ResolvedSelection) -> SelectionView:
    """Preserve direct, exact-Collection and derived/custom intent as distinct identities."""

    if not isinstance(selection, ResolvedSelection):
        raise ValueError("consumer Selection projection needs a resolved Selection")
    intent = selection.selection
    if intent.collections:
        mode = SelectionMode.EXACT_COLLECTION
        explanation = "This is an exact Collection; its versioned membership stays authoritative."
    elif intent.derived_from:
        mode = SelectionMode.CUSTOM_COLLECTION
        explanation = "This is a custom selection derived from a Collection, not that Collection."
    else:
        mode = SelectionMode.ARTIFACTS
        explanation = "These artifacts were selected directly."
    artifacts = tuple(str(item) for item in intent.artifacts)
    collections = tuple(str(item) for item in intent.collections)
    derived_from = tuple(str(item) for item in intent.derived_from)
    resolved = tuple(str(item.version.coordinate) for item in selection.artifacts)
    identity_data = {
        "artifacts": list(artifacts),
        "collections": list(collections),
        "derived_from": list(derived_from),
        "resolved": [
            {
                "coordinate": str(item.version.coordinate),
                "digest": str(item.version.canonical_digest),
                "object_digest": str(item.version.object_digest),
                "ownership": [
                    {"kind": owner.kind.value, "owner": owner.owner} for owner in item.ownership
                ],
            }
            for item in selection.artifacts
        ],
    }
    return SelectionView(
        mode,
        artifacts,
        collections,
        derived_from,
        resolved,
        _identity(identity_data),
        explanation,
    )


@dataclass(frozen=True, slots=True)
class RequirementView:
    id: str
    kind: str
    state: str
    detail: str
    owners: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RemediationView:
    kind: str
    risk: str
    owners: tuple[str, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class EffectView:
    kind: str
    risk: str
    owners: tuple[str, ...]
    summary: str
    inspectable: bool
    reversible: bool


@dataclass(frozen=True, slots=True)
class ConfigInputView:
    id: str
    label: str
    required: bool
    binding: str
    exposure: str
    description: str
    example: str | None
    format_hint: str | None
    obtain_from: tuple[str, str] | None
    validation_hint: str
    default: str | None
    current: str | None
    configured: bool
    source: str | None


@dataclass(frozen=True, slots=True)
class CredentialInputView:
    """Reference/provider/health only. There is deliberately no credential value field."""

    id: str
    label: str
    required: bool
    binding: str
    exposure: str
    description: str
    format_hint: str | None
    obtain_from: tuple[str, str] | None
    provider_reference: str | None
    provider: str | None
    provider_state: str
    health: str
    detail: str


InputView = ConfigInputView | CredentialInputView


def _source_name(source: object) -> str:
    if isinstance(source, PersistedConfigValue):
        return "persisted"
    if isinstance(source, PromptedConfigValue):
        return "prompted"
    if isinstance(source, PolicyProvidedValue):
        return "policy"
    if isinstance(source, SecretProviderReference):
        return "credential-provider"
    raise ValueError("unsupported input source")


def _config_current(source: object) -> str:
    if isinstance(source, (PersistedConfigValue, PromptedConfigValue, PolicyProvidedValue)):
        return source.value
    raise ValueError("a config input has a non-config source")


def project_required_inputs(
    inputs: tuple[RuntimeInput, ...],
    *,
    bound_inputs: BoundInputs = _EMPTY_BOUND_INPUTS,
    credential_observations: tuple[CredentialObservation, ...] = (),
) -> tuple[InputView, ...]:
    """Project input guidance and binding state without ever projecting credential material."""

    if any(not isinstance(item, (SecretInput, ConfigInput)) for item in inputs):
        raise ValueError("required input projection received an invalid input")
    if not isinstance(bound_inputs, BoundInputs) or any(
        not isinstance(item, CredentialObservation) for item in credential_observations
    ):
        raise ValueError("required input projection received invalid binding evidence")
    bound_by_id = {item.input.id: item for item in bound_inputs.inputs}
    observations = {item.reference: item for item in credential_observations}
    projected: list[InputView] = []
    for runtime_input in sorted(inputs, key=lambda item: item.id.value):
        guidance = runtime_input.guidance
        label = runtime_input.id.value if guidance is None else guidance.label
        description = "" if guidance is None else guidance.description
        format_hint = None if guidance is None else guidance.format_hint
        obtain_from = (
            None
            if guidance is None or guidance.obtain_from is None
            else (guidance.obtain_from.label, guidance.obtain_from.url)
        )
        binding = binding_kind(runtime_input.binding)
        exposure = runtime_input.binding.exposure.name.lower().replace("_", "-")
        bound = bound_by_id.get(runtime_input.id)
        if isinstance(runtime_input, SecretInput):
            source = None if bound is None else bound.source
            if source is not None and not isinstance(source, SecretProviderReference):
                raise ValueError("a credential input has a non-credential source")
            reference: CredentialReference | None = None if source is None else source.reference
            observation = None if reference is None else observations.get(reference)
            projected.append(
                CredentialInputView(
                    runtime_input.id.value,
                    label,
                    runtime_input.required,
                    binding,
                    exposure,
                    description,
                    format_hint,
                    obtain_from,
                    None if reference is None else str(reference),
                    None if reference is None else reference.provider.provider,
                    "unknown" if observation is None else observation.provider_state.value,
                    "unknown" if observation is None else observation.state.value,
                    "" if observation is None else observation.detail,
                )
            )
            continue
        projected.append(
            ConfigInputView(
                runtime_input.id.value,
                label,
                runtime_input.required,
                binding,
                exposure,
                description,
                None if guidance is None else guidance.example,
                format_hint,
                obtain_from,
                "" if guidance is None else guidance.validation_hint,
                runtime_input.default,
                None if bound is None else _config_current(bound.source),
                bound is not None,
                None if bound is None else _source_name(bound.source),
            )
        )
    return tuple(projected)


def _summary(data: dict[str, object]) -> str:
    kind = str(data["kind"])
    details = ", ".join(
        f"{key}={value}"
        for key, value in sorted(data.items())
        if key not in {"capabilities", "kind", "risk", "requirement"} and value is not None
    )
    return kind if not details else f"{kind}: {details}"


@dataclass(frozen=True, slots=True)
class ConsumerPlanView:
    canonical: InstallPlan
    selection: SelectionView
    platform: str
    requirements: tuple[RequirementView, ...]
    remediations: tuple[RemediationView, ...]
    effects: tuple[EffectView, ...]
    risks: tuple[str, ...]
    inputs: tuple[InputView, ...]
    review_digest: str
    policy_digest: str

    @property
    def semantic_identity(self) -> str:
        return _identity(
            {
                "plan": self.review_digest,
                "selection": self.selection.semantic_identity,
            }
        )


def project_install_plan(
    plan: InstallPlan,
    *,
    inputs: tuple[RuntimeInput, ...] = (),
    bound_inputs: BoundInputs = _EMPTY_BOUND_INPUTS,
    credential_observations: tuple[CredentialObservation, ...] = (),
) -> ConsumerPlanView:
    if not isinstance(plan, InstallPlan):
        raise ValueError("consumer plan projection needs a canonical install plan")
    requirements = tuple(
        RequirementView(
            str(item.requirement.requirement.id),
            str(requirement_to_data(item.requirement.requirement)["kind"]),
            item.state.value,
            item.detail,
            tuple(str(owner) for owner in item.requirement.owners),
        )
        for item in plan.requirements
    )
    remediations = []
    for remediation in plan.remediations:
        data = remediation_to_data(remediation.remediation)
        remediations.append(
            RemediationView(
                str(data["kind"]),
                _risk_label(remediation.risk.name),
                tuple(str(owner) for owner in remediation.owners),
                _summary(data),
            )
        )
    effects = []
    for planned_effect in plan.mutation.effects:
        data = effect_to_data(planned_effect.effect)
        capabilities = data["capabilities"]
        assert isinstance(capabilities, dict)
        effects.append(
            EffectView(
                str(data["kind"]),
                _risk_label(planned_effect.effect.risk.name),
                tuple(str(owner) for owner in planned_effect.owners),
                _summary(data),
                bool(capabilities["inspectable"]),
                bool(capabilities["reversible"]),
            )
        )
    return ConsumerPlanView(
        plan,
        project_selection(plan.selection),
        plan.platform,
        requirements,
        tuple(remediations),
        tuple(effects),
        tuple(_risk_label(item.name) for item in plan.mutation.risks),
        project_required_inputs(
            inputs,
            bound_inputs=bound_inputs,
            credential_observations=credential_observations,
        ),
        str(plan.review_digest),
        str(plan.policy_digest),
    )


def _input_to_data(input_view: InputView) -> dict[str, object]:
    common: dict[str, object] = {
        "binding": input_view.binding,
        "description": input_view.description,
        "exposure": input_view.exposure,
        "format_hint": input_view.format_hint,
        "id": input_view.id,
        "label": input_view.label,
        "obtain_from": input_view.obtain_from,
        "required": input_view.required,
    }
    if isinstance(input_view, CredentialInputView):
        return {
            **common,
            "detail": input_view.detail,
            "health": input_view.health,
            "kind": "credential",
            "provider": input_view.provider,
            "provider_reference": input_view.provider_reference,
            "provider_state": input_view.provider_state,
        }
    return {
        **common,
        "configured": input_view.configured,
        "current": input_view.current,
        "default": input_view.default,
        "example": input_view.example,
        "kind": "config",
        "source": input_view.source,
        "validation_hint": input_view.validation_hint,
    }


@dataclass(frozen=True, slots=True)
class MarketplaceCollectionView:
    coordinate: str
    summary: str
    members: tuple[str, ...]
    selected: tuple[str, ...]
    kind_counts: tuple[tuple[str, int], ...]
    exact: bool
    semantic_identity: str
    inputs: tuple[InputView, ...] = ()


def project_collection(
    collection: Collection,
    *,
    selected: tuple[str, ...] | None = None,
    inputs: tuple[InputView, ...] = (),
) -> MarketplaceCollectionView:
    if not isinstance(collection, Collection) or any(
        not isinstance(item, (ConfigInputView, CredentialInputView)) for item in inputs
    ):
        raise ValueError("Collection projection needs a canonical Collection and input views")
    members = tuple(str(item.request) for item in collection.members)
    selected_members = members if selected is None else tuple(dict.fromkeys(selected))
    if any(item not in members for item in selected_members):
        raise ValueError("Collection selection contains a non-member")
    counts = tuple(
        (kind, sum(item.request.identity.kind == kind for item in collection.members))
        for kind in sorted({item.request.identity.kind for item in collection.members})
    )
    identity = _identity(
        {
            "collection": str(collection.coordinate),
            "registry_snapshot": str(collection.registry_snapshot),
            "selected": list(selected_members),
        }
    )
    return MarketplaceCollectionView(
        str(collection.coordinate),
        collection.summary,
        members,
        selected_members,
        counts,
        selected_members == members,
        identity,
        inputs,
    )


def consumer_plan_to_data(view: ConsumerPlanView) -> dict[str, object]:
    """Complete machine projection; it never depends on the human presentation profile."""

    canonical = install_plan_to_data(view.canonical)
    mutation = canonical["mutation"]
    assert isinstance(mutation, dict)
    return {
        "effects": mutation["effects"],
        "inputs": [_input_to_data(item) for item in view.inputs],
        "platform": canonical["platform"],
        "policy_digest": canonical["policy_digest"],
        "remediations": canonical["remediations"],
        "requirements": canonical["requirements"],
        "review_digest": canonical["review_digest"],
        "risks": mutation["risks"],
        "selection": canonical["selection"],
        "selection_mode": view.selection.mode.value,
        "semantic_identity": view.semantic_identity,
    }


def install_flow_screens(view: ConsumerPlanView) -> tuple[ConsumerScreen, ...]:
    """Return the accepted install flow, inserting question screens only when necessary."""

    screens = [ConsumerScreen.REVIEW_SELECTION, ConsumerScreen.AUTOMATIC_INSPECTION]
    if view.inputs:
        screens.append(ConsumerScreen.REQUIRED_INPUTS)
    if view.remediations:
        screens.append(ConsumerScreen.REMEDIATION)
    screens.extend((ConsumerScreen.READY, ConsumerScreen.INSTALLING, ConsumerScreen.SUCCESS))
    return tuple(screens)


@dataclass(frozen=True, slots=True)
class ConsumerSession:
    screen: ApplicationScreen
    profile: PresentationProfile = PresentationProfile.FAST
    semantic_identity: str | None = None
    selection_identity: str | None = None
    review_digest: str | None = None
    history: tuple[ApplicationScreen, ...] = ()

    @classmethod
    def from_plan(cls, view: ConsumerPlanView) -> ConsumerSession:
        return cls(
            ConsumerScreen.READY,
            PresentationProfile.FAST,
            view.semantic_identity,
            view.selection.semantic_identity,
            view.review_digest,
        )

    def switch_profile(self, profile: PresentationProfile) -> ConsumerSession:
        if not isinstance(profile, PresentationProfile):
            raise ValueError("consumer presentation profile is invalid")
        return replace(self, profile=profile)

    def navigate(self, screen: ApplicationScreen) -> ConsumerSession:
        if not isinstance(screen, (ConsumerScreen, MaintainerScreen)):
            raise ValueError("application screen is invalid")
        if screen is self.screen:
            return self
        return replace(self, screen=screen, history=(*self.history, self.screen))

    def back(self) -> ConsumerSession:
        if not self.history:
            return self
        return replace(self, screen=self.history[-1], history=self.history[:-1])


@dataclass(frozen=True, slots=True)
class LifecycleDriftView:
    component: str
    kind: str
    repairable: bool


@dataclass(frozen=True, slots=True)
class OwnershipView:
    kind: str
    owner: str


@dataclass(frozen=True, slots=True)
class CredentialRecordView:
    """One provider reference and its observed health, never its material."""

    reference: str
    input: str
    provider: str
    service: str
    account: str
    provider_state: str
    health: str
    detail: str
    dependants: tuple[str, ...]
    actions: tuple[str, ...]


def project_credential_record(
    observation: CredentialObservation,
    *,
    dependants: tuple[str, ...] = (),
) -> CredentialRecordView:
    if not isinstance(observation, CredentialObservation) or any(
        not isinstance(item, str) or not item or any(character in item for character in "\r\n")
        for item in dependants
    ):
        raise ValueError("credential record projection is invalid")
    reference = observation.reference
    ordered_dependants = tuple(sorted(set(dependants)))
    actions = ("verify", "replace") if ordered_dependants else ("verify", "replace", "delete")
    return CredentialRecordView(
        str(reference),
        reference.input.value,
        reference.provider.provider,
        reference.provider.service,
        reference.provider.account,
        observation.provider_state.value,
        observation.state.value,
        observation.detail,
        ordered_dependants,
        actions,
    )


@dataclass(frozen=True, slots=True)
class InstalledArtifactView:
    coordinate: str
    health: str
    ownership: tuple[OwnershipView, ...]
    drift: tuple[LifecycleDriftView, ...]
    actions: tuple[str, ...]
    credentials: tuple[CredentialRecordView, ...] = ()


def _drift_view(desired: DesiredState, current: CurrentState) -> tuple[LifecycleDriftView, ...]:
    return tuple(
        LifecycleDriftView(str(item.component), item.kind.value, item.repairable)
        for item in compare_states(desired, current)
    )


def _ownership_view(values: tuple[OwnershipReason, ...]) -> tuple[OwnershipView, ...]:
    return tuple(
        OwnershipView(item.kind.value, item.owner)
        for item in sorted(values, key=lambda item: item.sort_key)
    )


def project_installed_artifact(
    desired: DesiredState,
    current: CurrentState,
    *,
    ownership: tuple[OwnershipReason, ...] = (),
    update_available: bool = False,
    credentials: tuple[CredentialRecordView, ...] = (),
) -> InstalledArtifactView:
    """Project measured installed health; mutation success is never health evidence."""

    if any(not isinstance(item, OwnershipReason) for item in ownership) or any(
        not isinstance(item, CredentialRecordView) for item in credentials
    ):
        raise ValueError("installed artifact projection received invalid ownership or credentials")
    health = installation_health(desired, current, update_available=update_available)
    actions = ["details", "verify", "configure", "uninstall"]
    if health.value == "update":
        actions.insert(2, "update")
    if health.value in {"attention", "broken"}:
        actions.insert(2, "repair")
    return InstalledArtifactView(
        str(desired.artifact),
        health.value,
        _ownership_view(ownership),
        _drift_view(desired, current),
        tuple(actions),
        credentials,
    )


def project_unadopted_installation(coordinate: str) -> InstalledArtifactView:
    """Project an installation only the legacy manifest knows about.

    AART installed this and recorded it, but it recorded it in the project or user manifest rather
    than as a canonical receipt, and canonical receipts are what the desired/current comparison is
    built from. There is therefore no desired state to compare against and nothing measured it, so
    every honest field here is a refusal to claim: health is unknown rather than ready, the single
    drift is ``unobserved`` rather than a fault, and no action is offered.

    Offering ``repair`` would promise reconciliation against a desired state nobody holds; offering
    ``uninstall`` would promise a removal the canonical effects cannot describe. Both are worse than
    an empty list, which at least says plainly that this is somebody else's to operate for now.

    What is *not* optional is that it appears at all. Leaving it out would let the canonical view
    answer "not installed" about something that is installed, which is the one answer that lets a
    later install quietly write over it.
    """

    if not isinstance(coordinate, str) or not coordinate or any(c in coordinate for c in "\r\n"):
        raise ValueError("an unadopted installation projection needs a coordinate")
    return InstalledArtifactView(
        coordinate,
        InstalledHealth.UNKNOWN.value,
        (),
        (LifecycleDriftView("installation", DriftKind.UNOBSERVED.value, False),),
        (),
    )


@dataclass(frozen=True, slots=True)
class InstalledCollectionView:
    collection: str
    health: str
    members: tuple[MemberHealth, ...]
    members_requiring_attention: tuple[str, ...]
    actions: tuple[str, ...]


def project_installed_collection(
    name: str, members: tuple[MemberHealth, ...]
) -> InstalledCollectionView:
    if not isinstance(name, str) or not name or any(character in name for character in "\r\n"):
        raise ValueError("installed Collection name is invalid")
    projected = collection_health(members)
    return InstalledCollectionView(
        name,
        projected.status.value,
        projected.members,
        tuple(item.artifact for item in projected.members_requiring_attention),
        ("details", "verify", "update", "uninstall"),
    )


@dataclass(frozen=True, slots=True)
class LifecycleStepView:
    component: str
    effect: str
    risk: str
    summary: str


@dataclass(frozen=True, slots=True)
class LifecyclePlanView:
    kind: str
    artifact: str
    retained: bool
    ownership: tuple[OwnershipView, ...]
    retained_ownership: tuple[OwnershipView, ...]
    drift: tuple[LifecycleDriftView, ...]
    steps: tuple[LifecycleStepView, ...]
    escalated: tuple[str, ...]
    risks: tuple[str, ...]
    complete: bool
    review_digest: str


def project_lifecycle_plan(plan: LifecyclePlan) -> LifecyclePlanView:
    if not isinstance(plan, LifecyclePlan):
        raise ValueError("lifecycle plan projection needs a canonical lifecycle plan")
    repair = plan.repair
    steps = []
    for step in repair.steps:
        data = effect_to_data(step.effect)
        steps.append(
            LifecycleStepView(
                str(step.component),
                str(data["kind"]),
                _risk_label(step.effect.risk.name),
                _summary(data),
            )
        )
    return LifecyclePlanView(
        plan.intent.kind.value,
        str(repair.artifact),
        plan.intent.retained,
        _ownership_view(plan.intent.ownership),
        _ownership_view(plan.intent.retained_ownership),
        tuple(
            LifecycleDriftView(str(item.component), item.kind.value, item.repairable)
            for item in repair.drift
        ),
        tuple(steps),
        tuple(str(item) for item in repair.escalated),
        tuple(_risk_label(item.name) for item in repair.risks),
        repair.complete,
        str(repair.review_digest),
    )


@dataclass(frozen=True, slots=True)
class LifecycleStepOutcomeView:
    component: str
    effect: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class LifecycleOutcomeView:
    kind: str
    artifact: str
    status: str
    review_digest: str
    steps: tuple[LifecycleStepOutcomeView, ...]
    residual_drift: tuple[LifecycleDriftView, ...]
    restoration_status: str | None
    detail: str


def project_lifecycle_outcome(outcome: LifecycleExecutionOutcome) -> LifecycleOutcomeView:
    if not isinstance(outcome, LifecycleExecutionOutcome):
        raise ValueError("lifecycle outcome projection needs a canonical execution outcome")
    steps = tuple(
        LifecycleStepOutcomeView(
            str(item.component),
            str(effect_to_data(item.effect)["kind"]),
            item.status.value,
            item.detail,
        )
        for item in outcome.primary.steps
    )
    residual = tuple(
        LifecycleDriftView(str(item.component), item.kind.value, item.repairable)
        for item in outcome.primary.residual_drift
    )
    return LifecycleOutcomeView(
        outcome.plan.intent.kind.value,
        str(outcome.plan.repair.artifact),
        outcome.status.value,
        str(outcome.plan.review_digest),
        steps,
        residual,
        None if outcome.restoration is None else outcome.restoration.status.value,
        outcome.detail or outcome.primary.detail,
    )


class ActivityOutcome(str, Enum):
    """What one past action amounts to, in the vocabulary a timeline reader scans."""

    SUCCEEDED = "succeeded"
    ATTENTION = "attention"
    PARTIAL = "partial"
    INTERRUPTED = "interrupted"
    RESTORED = "restored"
    FAILED = "failed"

    @property
    def mark(self) -> str:
        return _ACTIVITY_MARKS[self]


_ACTIVITY_MARKS: dict[ActivityOutcome, str] = {
    ActivityOutcome.SUCCEEDED: "✓",
    ActivityOutcome.ATTENTION: "!",
    ActivityOutcome.PARTIAL: "◐",
    ActivityOutcome.INTERRUPTED: "…",
    ActivityOutcome.RESTORED: "↶",
    ActivityOutcome.FAILED: "✗",
}

_ACTIVITY_OUTCOMES: dict[LifecycleExecutionStatus, ActivityOutcome] = {
    LifecycleExecutionStatus.COMPLETED: ActivityOutcome.SUCCEEDED,
    LifecycleExecutionStatus.COMPLETED_WITH_ATTENTION: ActivityOutcome.ATTENTION,
    LifecycleExecutionStatus.PARTIALLY_APPLIED: ActivityOutcome.PARTIAL,
    LifecycleExecutionStatus.INTERRUPTED: ActivityOutcome.INTERRUPTED,
    LifecycleExecutionStatus.RESTORED: ActivityOutcome.RESTORED,
    LifecycleExecutionStatus.RESTORATION_FAILED: ActivityOutcome.FAILED,
    LifecycleExecutionStatus.FAILED: ActivityOutcome.FAILED,
}

#: What a person did, in the past tense they did it in -- not which effects carried it out.
_ACTIVITY_VERBS: dict[LifecycleIntentKind, str] = {
    LifecycleIntentKind.INSTALL: "Installed",
    LifecycleIntentKind.UPDATE: "Updated",
    LifecycleIntentKind.CONFIGURE: "Reconfigured",
    LifecycleIntentKind.REPAIR: "Repaired",
    LifecycleIntentKind.CREDENTIAL_ROTATION: "Replaced credentials for",
    LifecycleIntentKind.HARNESS_RECONFIGURATION: "Reconnected",
    LifecycleIntentKind.DOWNGRADE: "Downgraded",
    LifecycleIntentKind.UNINSTALL: "Uninstalled",
}


def _moment(recorded_at: object, label: str) -> datetime:
    """Parse one recorded moment, or refuse it.

    An offset is required rather than assumed.  A naive timestamp read back on another machine
    would silently move the action into a different day, and the day is what a timeline is for.
    """

    if not isinstance(recorded_at, str) or "T" not in recorded_at:
        raise ValueError(f"{label} needs an ISO-8601 date and time")
    try:
        moment = datetime.fromisoformat(recorded_at)
    except ValueError as error:
        raise ValueError(f"{recorded_at!r} is not an ISO-8601 timestamp") from error
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(f"{label} needs an explicit UTC offset")
    return moment


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    """One finished lifecycle action, with the moment it finished.

    The moment is supplied rather than read.  This layer has no clock, and a receipt that dated
    itself when somebody opened it would be a record of the reading, not of the action.
    """

    recorded_at: str
    outcome: LifecycleExecutionOutcome
    moment: datetime = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, LifecycleExecutionOutcome):
            raise ValueError("an activity record needs a lifecycle execution outcome")
        object.__setattr__(self, "moment", _moment(self.recorded_at, "an activity record"))


@dataclass(frozen=True, slots=True)
class ActivityEntry:
    recorded_at: str
    time: str
    intent: str
    artifact: str
    summary: str
    outcome: ActivityOutcome
    mark: str
    review_digest: str
    detail: str


@dataclass(frozen=True, slots=True)
class ActivityDayView:
    label: str
    entries: tuple[ActivityEntry, ...]


@dataclass(frozen=True, slots=True)
class ActivityView:
    days: tuple[ActivityDayView, ...]

    @property
    def entries(self) -> tuple[ActivityEntry, ...]:
        return tuple(entry for day in self.days for entry in day.entries)


def _day_label(day: date, today: date) -> str:
    elapsed = (today - day).days
    if elapsed == 0:
        return "Today"
    if elapsed == 1:
        return "Yesterday"
    return day.isoformat()


def _activity_summary(outcome: LifecycleExecutionOutcome) -> str:
    intent = outcome.plan.intent
    verb = _ACTIVITY_VERBS[intent.kind]
    coordinate = outcome.plan.repair.artifact
    versioned = (LifecycleIntentKind.UPDATE, LifecycleIntentKind.DOWNGRADE)
    if intent.kind in versioned and intent.previous is not None:
        before, after = intent.previous.artifact.version, coordinate.version
        if before is not None and after is not None and before != after:
            return f"{verb} {coordinate.source}/{coordinate.artifact} {before} → {after}"
    return f"{verb} {coordinate}"


def _activity_entry(record: ActivityRecord) -> ActivityEntry:
    outcome = record.outcome
    activity = _ACTIVITY_OUTCOMES[outcome.status]
    return ActivityEntry(
        record.moment.isoformat(),
        record.moment.strftime("%H:%M"),
        outcome.plan.intent.kind.value,
        str(outcome.plan.repair.artifact),
        _activity_summary(outcome),
        activity,
        activity.mark,
        str(outcome.plan.review_digest),
        outcome.detail or outcome.primary.detail,
    )


def _receipt_entry(view: ReceiptDetailView) -> ActivityEntry:
    return ActivityEntry(
        view.moment.isoformat(),
        view.moment.strftime("%H:%M"),
        view.intent,
        view.artifact,
        view.summary,
        view.outcome,
        view.outcome.mark,
        view.review_digest,
        view.detail,
    )


def _timeline(entries: tuple[tuple[datetime, ActivityEntry], ...], today: date) -> ActivityView:
    if not isinstance(today, date) or isinstance(today, datetime):
        raise ValueError("activity projection needs the reader's current date")
    ordered = sorted(entries, key=lambda item: item[0], reverse=True)
    return ActivityView(
        tuple(
            ActivityDayView(_day_label(day, today), tuple(entry for _, entry in group))
            for day, group in groupby(ordered, key=lambda item: item[0].date())
        )
    )


def project_activity(records: tuple[ActivityRecord, ...], *, today: date) -> ActivityView:
    """Group finished actions into the days a person remembers them by, newest first.

    `today` is a parameter for the same reason the record carries its own moment: there is no
    clock here, and "Today" has to mean the reader's today rather than the machine's UTC one.
    """

    if any(not isinstance(item, ActivityRecord) for item in records):
        raise ValueError("activity projection needs activity records")
    return _timeline(tuple((item.moment, _activity_entry(item)) for item in records), today)


def activity_from_receipts(receipts: tuple[ReceiptDetailView, ...], *, today: date) -> ActivityView:
    """The same timeline, rebuilt from receipts that outlived the process that ran them.

    A stored receipt already carries the sentence the timeline shows, so nothing is re-derived from
    a plan this run never made.  That is what lets Activity survive a restart at all.
    """

    if any(not isinstance(item, ReceiptDetailView) for item in receipts):
        raise ValueError("activity projection needs receipt detail views")
    return _timeline(tuple((item.moment, _receipt_entry(item)) for item in receipts), today)


def activity_view_to_data(view: ActivityView) -> dict[str, object]:
    if not isinstance(view, ActivityView):
        raise ValueError("activity serialization needs an activity view")
    return {
        "days": [
            {
                "entries": [
                    {
                        "artifact": entry.artifact,
                        "detail": entry.detail,
                        "intent": entry.intent,
                        "outcome": entry.outcome.value,
                        "recorded_at": entry.recorded_at,
                        "review_digest": entry.review_digest,
                        "summary": entry.summary,
                    }
                    for entry in day.entries
                ],
                "label": day.label,
            }
            for day in view.days
        ]
    }


_UNDO_NOTHING_APPLIED = "nothing took effect, so there is nothing to undo"
_UNDO_CREDENTIAL = (
    "a credential change cannot be undone: no previous value is retained anywhere, deliberately"
)
_UNDO_AVAILABLE = "every change that took effect can be reversed from what was retained"


@dataclass(frozen=True, slots=True)
class UndoAvailability:
    """Whether this receipt can actually be undone, and if not, why not.

    A receipt is a record, not a promise of reversal.  Undo exists only where the effects that ran
    are reversible and the state needed to reverse them was already retained for another reason.
    No old secret value is kept in order to manufacture one, so a credential mutation is never
    undoable here -- the honest answer is the refusal, not a restore that cannot happen.
    """

    available: bool
    reason: str
    components: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool) or not isinstance(self.reason, str):
            raise ValueError("undo availability is invalid")
        if self.components and not self.available:
            raise ValueError("undo names components only when it is available")


def _undo_availability(outcome: LifecycleExecutionOutcome) -> UndoAvailability:
    applied = outcome.primary.applied
    if not applied:
        return UndoAvailability(False, _UNDO_NOTHING_APPLIED)
    if any(step.effect.risk is RiskClass.CREDENTIAL_MUTATION for step in applied):
        return UndoAvailability(False, _UNDO_CREDENTIAL)
    irreversible = tuple(
        str(step.component) for step in applied if not step.effect.capabilities.reversible
    )
    if irreversible:
        return UndoAvailability(
            False,
            "nothing retained here can reverse " + ", ".join(irreversible),
        )
    return UndoAvailability(True, _UNDO_AVAILABLE, tuple(str(step.component) for step in applied))


@dataclass(frozen=True, slots=True)
class ReceiptArtifactView:
    """One member of a transaction, as that transaction's receipt accounts for it.

    A member that was never attempted is here too. A receipt that listed only what ran would make
    an abandoned half of a Selection indistinguishable from one nobody asked for.
    """

    coordinate: str
    status: str
    ownership: tuple[OwnershipView, ...] = ()
    steps: tuple[LifecycleStepOutcomeView, ...] = ()
    residual_drift: tuple[LifecycleDriftView, ...] = ()
    diagnostics: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ReceiptDetailView:
    recorded_at: str
    intent: str
    artifact: str
    summary: str
    status: str
    outcome: ActivityOutcome
    review_digest: str
    policy_digest: str
    steps: tuple[LifecycleStepOutcomeView, ...]
    residual_drift: tuple[LifecycleDriftView, ...]
    restoration_status: str | None
    undo: UndoAvailability
    detail: str
    selection: SelectionView | None = None
    artifacts: tuple[ReceiptArtifactView, ...] = ()
    moment: datetime = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "moment", _moment(self.recorded_at, "a receipt"))


def project_receipt_detail(record: ActivityRecord) -> ReceiptDetailView:
    """The technical receipt behind one timeline entry: intent, identity, effects, undo."""

    if not isinstance(record, ActivityRecord):
        raise ValueError("receipt projection needs an activity record")
    outcome = record.outcome
    projected = project_lifecycle_outcome(outcome)
    return ReceiptDetailView(
        record.moment.isoformat(),
        projected.kind,
        projected.artifact,
        _activity_summary(outcome),
        projected.status,
        _ACTIVITY_OUTCOMES[outcome.status],
        projected.review_digest,
        str(outcome.plan.repair.policy_digest),
        projected.steps,
        projected.residual_drift,
        projected.restoration_status,
        _undo_availability(outcome),
        projected.detail,
    )


#: What one whole Selection transaction amounts to, in the words a timeline already uses.
_TRANSACTION_OUTCOMES: dict[InstallationExecutionStatus, ActivityOutcome] = {
    InstallationExecutionStatus.COMPLETED: ActivityOutcome.SUCCEEDED,
    InstallationExecutionStatus.COMPLETED_WITH_ATTENTION: ActivityOutcome.ATTENTION,
    InstallationExecutionStatus.PARTIALLY_APPLIED: ActivityOutcome.PARTIAL,
    InstallationExecutionStatus.INTERRUPTED: ActivityOutcome.INTERRUPTED,
    InstallationExecutionStatus.FAILED: ActivityOutcome.FAILED,
}


def _transaction_undo(outcome: InstallationExecutionOutcome) -> UndoAvailability:
    """Undo for a transaction is the weakest of its members, never the average.

    Reversing half a Selection is not reversing it. If any member cannot be undone -- because it
    mutated a credential, because it applied something irreversible, or because it never ran and so
    left nothing to reverse -- the transaction as a whole cannot be, and the reason given is that
    member's own.
    """

    members = tuple(item.outcome for item in outcome.artifacts if item.outcome is not None)
    if len(members) != len(outcome.artifacts) or not members:
        return UndoAvailability(False, "not every artifact in this transaction ran")
    availabilities = tuple(_undo_availability(item) for item in members)
    refused = next((item for item in availabilities if not item.available), None)
    if refused is not None:
        return refused
    return UndoAvailability(
        True,
        _UNDO_AVAILABLE,
        tuple(sorted({component for item in availabilities for component in item.components})),
    )


#: How each lifecycle reads in a transaction summary. Only the kinds a reviewed Selection can
#: actually carry out appear here; anything else falls back to the neutral verb.
_TRANSACTION_VERBS: dict[LifecycleIntentKind, str] = {
    LifecycleIntentKind.INSTALL: "Installed",
    LifecycleIntentKind.UPDATE: "Updated",
    LifecycleIntentKind.REPAIR: "Repaired",
    LifecycleIntentKind.DOWNGRADE: "Downgraded",
    LifecycleIntentKind.UNINSTALL: "Removed",
}


def project_installation_receipt(
    outcome: InstallationExecutionOutcome,
    *,
    recorded_at: str,
) -> ReceiptDetailView:
    """One reviewed Selection transaction, as the single receipt a person reads.

    The transaction is the unit somebody confirmed, so it is the unit recorded: one entry on the
    timeline naming the Selection, with every member accounted for beneath it. Recording a receipt
    per artifact instead would leave no record of the thing that was actually reviewed, and no way
    to tell a Selection that half-applied from two unrelated installs.
    """

    if not isinstance(outcome, InstallationExecutionOutcome):
        raise ValueError("transaction receipt projection needs an installation execution outcome")
    # A removal has no Selection. It is planned from what is recorded rather than from what a
    # registry offers -- an artifact stays installed after its source is gone -- so there is no
    # resolution to project, and the members below say what was taken out.
    proposal = outcome.proposal
    plan = proposal.plan if isinstance(proposal, InstallationProposal) else None
    selection = None if plan is None else project_selection(plan.selection)
    artifacts = tuple(
        ReceiptArtifactView(
            str(item.plan.intent.desired.artifact),
            item.status,
            _ownership_view(item.plan.intent.resulting_ownership),
            () if item.outcome is None else project_lifecycle_outcome(item.outcome).steps,
            () if item.outcome is None else project_lifecycle_outcome(item.outcome).residual_drift,
            tuple(diagnostic.message for diagnostic in item.diagnostics),
            item.detail,
        )
        for item in outcome.artifacts
    )
    count = len(artifacts)
    # What the transaction was, taken from its members rather than assumed. Members can disagree
    # -- an update of several artifacts finds some already at the approved version, which is a
    # repair -- and in that case the verb somebody used is the one that named the whole action.
    kinds = {item.plan.intent.kind for item in outcome.artifacts}
    kind = kinds.pop() if len(kinds) == 1 else LifecycleIntentKind.UPDATE
    return ReceiptDetailView(
        recorded_at,
        kind.value,
        ", ".join(item.coordinate for item in artifacts),
        f"{_TRANSACTION_VERBS.get(kind, 'Installed')} {count} artifact{'' if count == 1 else 's'}",
        outcome.status.value,
        _TRANSACTION_OUTCOMES[outcome.status],
        str(proposal.review_digest),
        str(
            plan.policy_digest
            if plan is not None
            else cast(RemovalProposal, proposal).policy_digest
        ),
        tuple(step for item in artifacts for step in item.steps),
        tuple(drift for item in artifacts for drift in item.residual_drift),
        None,
        _transaction_undo(outcome),
        outcome.detail,
        selection,
        artifacts,
    )


def receipt_detail_to_data(view: ReceiptDetailView) -> dict[str, object]:
    if not isinstance(view, ReceiptDetailView):
        raise ValueError("receipt serialization needs a receipt detail view")
    return {
        "artifact": view.artifact,
        "detail": view.detail,
        "drift": [
            {"component": item.component, "kind": item.kind, "repairable": item.repairable}
            for item in view.residual_drift
        ],
        "intent": view.intent,
        "outcome": view.outcome.value,
        "policy_digest": view.policy_digest,
        "recorded_at": view.recorded_at,
        "restoration_status": view.restoration_status,
        "review_digest": view.review_digest,
        "status": view.status,
        "summary": view.summary,
        "steps": [
            {
                "component": item.component,
                "detail": item.detail,
                "effect": item.effect,
                "status": item.status,
            }
            for item in view.steps
        ],
        "undo": {
            "available": view.undo.available,
            "components": list(view.undo.components),
            "reason": view.undo.reason,
        },
        # Absent rather than null for a single-artifact receipt: a receipt written before
        # transactions existed has no Selection, and inventing an empty one would claim it did.
        **(
            {} if view.selection is None else {"selection": _selection_view_to_data(view.selection)}
        ),
        **(
            {}
            if not view.artifacts
            else {
                "artifacts": [
                    {
                        "coordinate": item.coordinate,
                        "detail": item.detail,
                        "diagnostics": list(item.diagnostics),
                        "drift": [
                            {
                                "component": drift.component,
                                "kind": drift.kind,
                                "repairable": drift.repairable,
                            }
                            for drift in item.residual_drift
                        ],
                        "ownership": [
                            {"kind": owner.kind, "owner": owner.owner} for owner in item.ownership
                        ],
                        "status": item.status,
                        "steps": [
                            {
                                "component": step.component,
                                "detail": step.detail,
                                "effect": step.effect,
                                "status": step.status,
                            }
                            for step in item.steps
                        ],
                    }
                    for item in view.artifacts
                ]
            }
        ),
    }


def _selection_view_to_data(view: SelectionView) -> dict[str, object]:
    return {
        "artifacts": list(view.artifacts),
        "collections": list(view.collections),
        "derived_from": list(view.derived_from),
        "explanation": view.explanation,
        "mode": view.mode.value,
        "resolved": list(view.resolved),
        "semantic_identity": view.semantic_identity,
    }


def _selection_view_from_data(data: object) -> SelectionView:
    if not isinstance(data, dict):
        raise ValueError("a receipt's selection must be a mapping")
    return SelectionView(
        SelectionMode(_string(data, "mode")),
        _strings(data, "artifacts"),
        _strings(data, "collections"),
        _strings(data, "derived_from"),
        _strings(data, "resolved"),
        _string(data, "semantic_identity"),
        _string(data, "explanation"),
    )


def _strings(data: dict[str, object], key: str) -> tuple[str, ...]:
    values = data.get(key, [])
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise ValueError(f"a receipt's {key} must be strings")
    return tuple(cast("list[str]", values))


_NAVIGATION: dict[ConsumerScreen, tuple[ConsumerScreen, ...]] = {
    ConsumerScreen.DASHBOARD: (
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.INSTALLED,
        ConsumerScreen.UPDATES,
        ConsumerScreen.REGISTRIES,
        ConsumerScreen.CREDENTIALS,
        ConsumerScreen.ACTIVITY,
        ConsumerScreen.DOCTOR,
        ConsumerScreen.SETTINGS,
    ),
    ConsumerScreen.MARKETPLACE: (
        ConsumerScreen.ARTIFACT_DETAILS,
        ConsumerScreen.COLLECTION_PREVIEW,
        ConsumerScreen.REVIEW_SELECTION,
    ),
    ConsumerScreen.ARTIFACT_DETAILS: (ConsumerScreen.REVIEW_SELECTION,),
    ConsumerScreen.COLLECTION_PREVIEW: (
        ConsumerScreen.COLLECTION_CUSTOMIZE,
        ConsumerScreen.REVIEW_SELECTION,
    ),
    ConsumerScreen.COLLECTION_CUSTOMIZE: (ConsumerScreen.REVIEW_SELECTION,),
    ConsumerScreen.REVIEW_SELECTION: (ConsumerScreen.AUTOMATIC_INSPECTION,),
    ConsumerScreen.AUTOMATIC_INSPECTION: (
        ConsumerScreen.REQUIRED_INPUTS,
        ConsumerScreen.REMEDIATION,
        ConsumerScreen.READY,
    ),
    ConsumerScreen.REQUIRED_INPUTS: (ConsumerScreen.REMEDIATION, ConsumerScreen.READY),
    ConsumerScreen.REMEDIATION: (ConsumerScreen.READY,),
    ConsumerScreen.READY: (ConsumerScreen.INSTALLING,),
    ConsumerScreen.INSTALLING: (ConsumerScreen.SUCCESS,),
    ConsumerScreen.SUCCESS: (ConsumerScreen.INSTALLED, ConsumerScreen.RECEIPT_DETAILS),
    ConsumerScreen.INSTALLED: (
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ConsumerScreen.INSTALLED_COLLECTION_DETAILS,
    ),
    ConsumerScreen.INSTALLED_ARTIFACT_DETAILS: (
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.UNINSTALL_REVIEW,
    ),
    ConsumerScreen.INSTALLED_COLLECTION_DETAILS: (ConsumerScreen.UNINSTALL_REVIEW,),
    ConsumerScreen.UPDATES: (ConsumerScreen.UPDATE_INPUTS, ConsumerScreen.UPDATING),
    ConsumerScreen.UPDATE_INPUTS: (ConsumerScreen.UPDATING,),
    ConsumerScreen.UPDATING: (ConsumerScreen.ACTIVITY_DETAILS,),
    ConsumerScreen.UNINSTALL_REVIEW: (ConsumerScreen.UNINSTALLING,),
    ConsumerScreen.UNINSTALLING: (ConsumerScreen.ACTIVITY_DETAILS,),
    ConsumerScreen.VERIFY_REPAIR: (ConsumerScreen.ACTIVITY_DETAILS,),
    ConsumerScreen.REGISTRIES: (),
    ConsumerScreen.CREDENTIALS: (ConsumerScreen.CREDENTIAL_DETAILS,),
    ConsumerScreen.CREDENTIAL_DETAILS: (ConsumerScreen.CREDENTIAL_ACTION,),
    ConsumerScreen.CREDENTIAL_ACTION: (ConsumerScreen.ACTIVITY_DETAILS,),
    ConsumerScreen.ACTIVITY: (ConsumerScreen.ACTIVITY_DETAILS,),
    ConsumerScreen.ACTIVITY_DETAILS: (ConsumerScreen.RECEIPT_DETAILS,),
    ConsumerScreen.RECEIPT_DETAILS: (),
    ConsumerScreen.SETTINGS: (),
    ConsumerScreen.DOCTOR: (ConsumerScreen.VERIFY_REPAIR,),
}


_KEEPS_FOCUS: frozenset[tuple[ConsumerScreen, ConsumerScreen]] = frozenset(
    {
        (ConsumerScreen.COLLECTION_PREVIEW, ConsumerScreen.COLLECTION_CUSTOMIZE),
        (ConsumerScreen.COLLECTION_PREVIEW, ConsumerScreen.REVIEW_SELECTION),
        (ConsumerScreen.COLLECTION_CUSTOMIZE, ConsumerScreen.REVIEW_SELECTION),
    }
)


def keeps_focus(current: ApplicationScreen, target: ApplicationScreen) -> bool:
    """Whether stepping between these two screens stays about the same thing.

    Normally the next screen is about the row somebody was on. A Collection is the exception: its
    preview lists members, so the row under the cursor is a member, while customizing is still
    about the Collection itself.
    """

    if not isinstance(current, (ConsumerScreen, MaintainerScreen)) or not isinstance(
        target, (ConsumerScreen, MaintainerScreen)
    ):
        raise ValueError("application navigation needs two screens")
    return (current, target) in _KEEPS_FOCUS


def navigation_targets(
    screen: ApplicationScreen, *, maintainer_mode: bool = False
) -> tuple[ApplicationScreen, ...]:
    """Accepted forward routes, with the complete Maintainer surface behind its opt-in."""

    if not isinstance(screen, (ConsumerScreen, MaintainerScreen)) or not isinstance(
        maintainer_mode, bool
    ):
        raise ValueError("application navigation needs a screen and a mode boundary")
    if isinstance(screen, MaintainerScreen):
        return maintainer_navigation_targets(screen) if maintainer_mode else ()
    targets: tuple[ApplicationScreen, ...] = _NAVIGATION[screen]
    if screen is ConsumerScreen.DASHBOARD and maintainer_mode:
        return (*targets, MaintainerScreen.DASHBOARD)
    return targets


#: Refusal for a stored preference file this frontend cannot mean.
CONSUMER_SETTINGS_INVALID = DiagnosticCode("consumer-settings-invalid")


@dataclass(frozen=True, slots=True)
class ConsumerSettings:
    profile: PresentationProfile = PresentationProfile.FAST
    default_scope: str = "project"
    show_updates: bool = True
    maintainer_mode: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile, PresentationProfile)
            or self.default_scope not in {"project", "user"}
            or not isinstance(self.show_updates, bool)
            or not isinstance(self.maintainer_mode, bool)
        ):
            raise ValueError("consumer settings are invalid")

    def with_profile(self, profile: PresentationProfile) -> ConsumerSettings:
        return replace(self, profile=profile)

    def with_maintainer_mode(self, enabled: bool) -> ConsumerSettings:
        if not isinstance(enabled, bool):
            raise ValueError("Maintainer Mode setting must be a boolean")
        return replace(self, maintainer_mode=enabled)

    def toggled(self, row: str) -> ConsumerSettings:
        """This preference, moved to its other value. Every control on screen 28 is binary."""

        if row == "detail-level":
            return self.with_profile(
                PresentationProfile.VERBOSE
                if self.profile is PresentationProfile.FAST
                else PresentationProfile.FAST
            )
        if row == "default-scope":
            return replace(
                self, default_scope="user" if self.default_scope == "project" else "project"
            )
        if row == "show-updates":
            return replace(self, show_updates=not self.show_updates)
        if row == "maintainer-mode":
            return self.with_maintainer_mode(not self.maintainer_mode)
        raise ValueError(f"no consumer setting is named {row}")


#: The controls of accepted screen 28, in the order the Product Specification lists them. They are
#: row identities rather than labels so a rename of what is drawn never rewrites what was stored.
SETTING_ROWS: tuple[str, ...] = (
    "detail-level",
    "default-scope",
    "show-updates",
    "maintainer-mode",
)


def settings_to_data(view: ConsumerSettings) -> dict[str, object]:
    """One consumer's preferences as plain data. No machine state, and nothing secret."""

    if not isinstance(view, ConsumerSettings):
        raise ValueError("settings serialization needs consumer settings")
    return {
        "detail_level": view.profile.value,
        "default_scope": view.default_scope,
        "show_updates": view.show_updates,
        "maintainer_mode": view.maintainer_mode,
    }


def settings_from_data(data: object) -> Result[ConsumerSettings]:
    """Read back preferences somebody chose, refusing anything this cannot mean.

    A stored preference is read strictly rather than repaired: silently falling back to Fast after
    somebody chose Verbose would be the frontend deciding a detail level for them, and silently
    falling back on Maintainer Mode is a mode boundary answering itself.
    """

    if not isinstance(data, dict):
        return Err((_settings_invalid("stored consumer settings must be a JSON object"),))
    known = {"detail_level", "default_scope", "show_updates", "maintainer_mode"}
    unknown = sorted(set(data) - known)
    if unknown:
        return Err(
            (_settings_invalid(f"stored consumer settings name {unknown[0]}, which AART does not"),)
        )
    detail = data.get("detail_level", PresentationProfile.FAST.value)
    if detail not in {item.value for item in PresentationProfile}:
        return Err((_settings_invalid("stored detail level must be fast or verbose"),))
    scope = data.get("default_scope", "project")
    if scope not in {"project", "user"}:
        return Err((_settings_invalid("stored default scope must be project or user"),))
    updates = data.get("show_updates", True)
    maintainer = data.get("maintainer_mode", False)
    if not isinstance(updates, bool) or not isinstance(maintainer, bool):
        return Err(
            (
                _settings_invalid(
                    "stored update visibility and Maintainer Mode must be true or false"
                ),
            )
        )
    return Ok(
        ConsumerSettings(
            PresentationProfile(detail),
            cast(str, scope),
            updates,
            maintainer,
        )
    )


def _settings_invalid(message: str) -> Diagnostic:
    return Diagnostic(CONSUMER_SETTINGS_INVALID, Severity.ERROR, message)


@dataclass(frozen=True, slots=True)
class RegistryView:
    alias: str
    availability: str
    health: str
    artifact_count: int
    last_sync_age_seconds: int | None
    kind: str
    origin: str
    revision: str | None
    snapshot_digest: str | None
    trust: tuple[str, ...]
    actions: tuple[str, ...] = ("details", "sync")


def project_registries(catalog: MarketplaceCatalog) -> tuple[RegistryView, ...]:
    if not isinstance(catalog, MarketplaceCatalog):
        raise ValueError("registry projection needs a marketplace catalog")
    rows = []
    for source in catalog.sources:
        source_items = tuple(item for item in catalog.items if item.source.alias == source.alias)
        availability = (
            "connected" if source.health.value in {"healthy", "stale"} else "not-connected"
        )
        rows.append(
            RegistryView(
                source.alias.value,
                availability,
                source.health.value,
                len(source_items),
                source.age_seconds,
                source.kind.value,
                source.origin,
                source.resolved_revision,
                None if source.snapshot_digest is None else str(source.snapshot_digest),
                tuple(sorted({item.trust.kind.value for item in source_items})),
            )
        )
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class DashboardView:
    installed_count: int
    ready_count: int
    update_count: int
    attention_count: int
    registry_count: int
    credential_attention_count: int
    recent_activity: tuple[str, ...]


def project_dashboard(
    artifacts: tuple[InstalledArtifactView, ...],
    *,
    registry_count: int,
    credential_attention_count: int = 0,
    recent_activity: tuple[str, ...] = (),
) -> DashboardView:
    if (
        any(not isinstance(item, InstalledArtifactView) for item in artifacts)
        or not isinstance(registry_count, int)
        or isinstance(registry_count, bool)
        or registry_count < 0
        or not isinstance(credential_attention_count, int)
        or isinstance(credential_attention_count, bool)
        or credential_attention_count < 0
        or any(
            not isinstance(item, str) or not item or any(character in item for character in "\r\n")
            for item in recent_activity
        )
    ):
        raise ValueError("dashboard projection is invalid")
    return DashboardView(
        len(artifacts),
        sum(item.health == "ready" for item in artifacts),
        sum(item.health == "update" for item in artifacts),
        sum(item.health in {"attention", "broken"} for item in artifacts),
        registry_count,
        credential_attention_count,
        recent_activity,
    )


@dataclass(frozen=True, slots=True)
class DoctorView:
    ready_count: int
    attention_count: int
    issues: tuple[str, ...]
    repairable_issues: tuple[str, ...]
    actions: tuple[str, ...]


def project_doctor(artifacts: tuple[InstalledArtifactView, ...]) -> DoctorView:
    if any(not isinstance(item, InstalledArtifactView) for item in artifacts):
        raise ValueError("Doctor projection needs installed artifact views")
    issues = tuple(item.coordinate for item in artifacts if item.health in {"attention", "broken"})
    repairable = tuple(
        item.coordinate
        for item in artifacts
        if item.drift and all(drift.repairable for drift in item.drift)
    )
    actions = ("repair-issues",) if repairable else ()
    return DoctorView(
        sum(item.health in {"ready", "update"} for item in artifacts),
        len(issues),
        issues,
        repairable,
        actions,
    )


def _view_error(message: str) -> Err:
    return Err((Diagnostic(RECEIPT_INVALID, Severity.ERROR, message),))


def _string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"a receipt needs a {key}")
    return value


def _rows(data: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    rows = data.get(key, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"a receipt's {key} must be a list of records")
    return tuple(cast("list[dict[str, object]]", rows))


def receipt_detail_from_data(data: object) -> Result[ReceiptDetailView]:
    """The exact inverse of :func:`receipt_detail_to_data`.

    Undo is read back rather than recomputed.  What could be reversed was decided by the effects
    that actually ran, and a later process has no standing to upgrade that answer.
    """

    if not isinstance(data, dict):
        return _view_error("a receipt must be a mapping")
    try:
        restoration = data.get("restoration_status")
        if restoration is not None and not isinstance(restoration, str):
            raise ValueError("a receipt's restoration status must be a string or absent")
        undo = data.get("undo")
        if not isinstance(undo, dict) or not isinstance(undo.get("available"), bool):
            raise ValueError("a receipt needs an undo availability")
        components = undo.get("components", [])
        if not isinstance(components, list) or any(
            not isinstance(item, str) for item in components
        ):
            raise ValueError("a receipt's undo components must be strings")
        return Ok(
            ReceiptDetailView(
                _string(data, "recorded_at"),
                _string(data, "intent"),
                _string(data, "artifact"),
                _string(data, "summary"),
                _string(data, "status"),
                ActivityOutcome(_string(data, "outcome")),
                _string(data, "review_digest"),
                _string(data, "policy_digest"),
                tuple(
                    LifecycleStepOutcomeView(
                        _string(row, "component"),
                        _string(row, "effect"),
                        _string(row, "status"),
                        _string(row, "detail"),
                    )
                    for row in _rows(data, "steps")
                ),
                tuple(
                    LifecycleDriftView(
                        _string(row, "component"),
                        _string(row, "kind"),
                        bool(row.get("repairable")),
                    )
                    for row in _rows(data, "drift")
                ),
                restoration,
                UndoAvailability(
                    cast("bool", undo["available"]),
                    _string(undo, "reason"),
                    tuple(cast("list[str]", components)),
                ),
                _string(data, "detail"),
                None if "selection" not in data else _selection_view_from_data(data["selection"]),
                tuple(
                    ReceiptArtifactView(
                        _string(row, "coordinate"),
                        _string(row, "status"),
                        tuple(
                            OwnershipView(_string(owner, "kind"), _string(owner, "owner"))
                            for owner in _rows(row, "ownership")
                        ),
                        tuple(
                            LifecycleStepOutcomeView(
                                _string(step, "component"),
                                _string(step, "effect"),
                                _string(step, "status"),
                                _string(step, "detail"),
                            )
                            for step in _rows(row, "steps")
                        ),
                        tuple(
                            LifecycleDriftView(
                                _string(drift, "component"),
                                _string(drift, "kind"),
                                bool(drift.get("repairable")),
                            )
                            for drift in _rows(row, "drift")
                        ),
                        _strings(row, "diagnostics"),
                        _string(row, "detail"),
                    )
                    for row in _rows(data, "artifacts")
                ),
            )
        )
    except ValueError as error:
        return _view_error(str(error))
