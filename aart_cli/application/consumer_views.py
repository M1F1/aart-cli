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

from aart_cli.configuration.model import SourceKind
from aart_cli.domain.configuration_files import configuration_value_problem
from aart_cli.domain.credentials import (
    CredentialObservation,
    CredentialReference,
    CredentialState,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.effects import RiskClass, effect_to_data
from aart_cli.domain.inputs import (
    SKIPPED_INPUT,
    BoundInputs,
    ConfigInput,
    InputValidation,
    PersistedConfigValue,
    PolicyProvidedValue,
    PromptedConfigValue,
    RuntimeInput,
    SecretInput,
    SecretProviderReference,
    binding_kind,
    validate_config_value,
)
from aart_cli.domain.plans import InstallPlan, install_plan_to_data
from aart_cli.domain.receipts import (
    RECEIPT_INVALID,
    ArtifactReceipt,
    InstallationReceipt,
    PlacedArtifactReceipt,
)
from aart_cli.domain.reconciliation import (
    Component,
    ComponentId,
    CurrentState,
    DesiredState,
    DriftKind,
    compare_states,
)
from aart_cli.domain.remediations import remediation_to_data
from aart_cli.domain.requirements import requirement_to_data
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.selection import Collection, OwnershipReason, ResolvedSelection
from aart_cli.domain.serialization import CanonicalValue, canonical_json_bytes
from aart_cli.marketplace.model import MarketplaceCatalog

from .credential_guidance import (
    CredentialGuidance,
    gather_credential_guidance,
    guidance_by_input,
)
from .execution import (
    InstallationExecutionOutcome,
    InstallationExecutionStatus,
    LifecycleExecutionOutcome,
    LifecycleExecutionStatus,
    StepProgress,
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
    "installed_cells",
    "marketplace_cells",
    "ALL_ARTIFACTS",
    "ALL_INSTALLATIONS",
    "PLACEHOLDER_WARNING",
    "InstallSecretView",
    "choose_pair_scope",
    "default_pair_scopes",
    "settings_pairs",
    "pair_scope_from_key",
    "pair_scope_key",
    "scope_choice_offered",
    "scope_matrix_columns",
    "scope_matrix_from_row",
    "scope_matrix_rows",
    "placeholders_left",
    "secrets_to_ask",
    "MATRIX_ROW_PREFIX",
    "matrix_columns",
    "matrix_from_row",
    "matrix_rows",
    "pair_choice_problems",
    "pair_from_key",
    "pairs_confirmed",
    "pair_key",
    "pairs_harnesses",
    "toggle_matrix_cell",
    "TARGET_ROW_PREFIX",
    "HarnessTargetView",
    "target_choice_problems",
    "harness_choice_problems",
    "target_from_row",
    "target_row",
    "targets_confirmed",
    "ActivityDayView",
    "ActivityEntry",
    "ActivityOutcome",
    "ActivityRecord",
    "ActivityView",
    "ApplicationScreen",
    "ConfigInputView",
    "config_input_value_problem",
    "ConfigurationFileView",
    "ConsumerPlanView",
    "ConsumerScreen",
    "ConsumerSession",
    "CONSUMER_SETTINGS_INVALID",
    "ConsumerSettings",
    "SETTING_PURPOSE",
    "SETTING_ROWS",
    "DEFAULT_HARNESS_ROW_PREFIX",
    "INSTALL_PATH_CUSTOM",
    "INSTALL_PATH_DEFAULT",
    "INSTALL_PATH_PURPOSE",
    "INSTALL_PATH_ROWS",
    "default_harness_from_row",
    "default_harness_row",
    "setting_purpose",
    "setting_rows",
    "SUCCESS_CHOICES",
    "McpTestEntryView",
    "McpTestResultView",
    "McpTestStageView",
    "McpTestView",
    "SUCCESS_PURPOSE",
    "CredentialInputView",
    "CredentialRecordView",
    "EffectView",
    "InstalledArtifactView",
    "InstalledCollectionView",
    "under_collections",
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
    "material_remediations",
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
    LESS_INFO = "less-info"
    MORE_INFO = "more-info"

    @property
    def toggle_label(self) -> str:
        """What pressing `v` gives from this profile, not the mode it is in (D-398).

        Declared with the type so the reducer that draws the legend never names a profile, which
        is the reachability half of INV-149/INV-152.
        """

        return "Less info" if self is PresentationProfile.MORE_INFO else "More info"


class ConsumerScreen(str, Enum):
    """The accepted consumer screen catalog, including the 04A customization state."""

    DASHBOARD = "01-dashboard"
    MARKETPLACE = "02-marketplace"
    ARTIFACT_DETAILS = "03-artifact-details"
    COLLECTION_PREVIEW = "04-collection"
    COLLECTION_CUSTOMIZE = "04a-customize-collection"
    # 05p chooses the install path after Install (§173.7): Default takes the harnesses, scope and
    # Python installer from Settings and skips 05 and 07a; Custom is 05 onwards.
    INSTALL_PATH = "05p-install-path"
    REVIEW_SELECTION = "05-review-selection"
    AUTOMATIC_INSPECTION = "06-automatic-inspection"
    REQUIRED_INPUTS = "07-required-inputs"
    # 07a puts each artifact×harness pair on one scope (§172.5). It follows the configuration form
    # and appears only when some pair is offered more than one scope.
    INSTALL_SCOPE = "07a-scope"
    # 07b asks each secret once per artifact, into a hidden prompt, before Ready (§172.6). It
    # appears only when some new installation holds no value for a secret it reads.
    INSTALL_CREDENTIALS = "07b-credentials"
    READY = "09-ready"
    INSTALLING = "10-installing"
    SUCCESS = "11-success"
    # 11a is the optional test of the MCP installations a committed install just made (§170.4,
    # D-378). It follows the install rather than belonging to it: nothing on it can change what 11
    # reports, and leaving it unvisited is a complete installation.
    MCP_TEST = "11a-test-mcp-installations"
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
    REGISTRY_ADD = "21a-add-registry"
    REGISTRY_REVIEW = "21b-review-registry"
    # 21c is the reviewed refresh of an already-connected registry (B-084).  161.7 draws `[ Sync ]`
    # on screen 21 itself, and the row projection has always advertised the action; what was
    # missing was a screen on which to state which registry and which ref are about to be fetched
    # before anything is.
    REGISTRY_SYNC = "21c-sync-registry"
    REGISTRY_REMOVE = "21d-disconnect-registry"
    CREDENTIALS = "22-user-variables-and-credentials"
    USER_INPUT_DETAILS = "22a-artifact-variables-and-credentials"
    CONFIGURATION_TARGETS = "22b-choose-configuration-harnesses"
    CONFIGURATION_VALUE = "22c-edit-configuration-value"
    CONFIGURATION_REVIEW = "22d-review-configuration-change"
    CREDENTIAL_DETAILS = "23-credential-details"
    CREDENTIAL_ACTION = "24-credential-action"
    # 24a states what a chosen credential action does before it does it, and is where Verify's
    # answer is drawn. Screen 24 is the choice; a review of its own keeps the rows and the
    # consequences on separate screens, the way 21c/21d did for a Registry row (D-262).
    CREDENTIAL_REVIEW = "24a-review-credential-action"
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


#: How screen 05 addresses one harness row, so a row is never a bare name a renderer must guess at.
TARGET_ROW_PREFIX = "target:"


@dataclass(frozen=True, slots=True)
class HarnessTargetView:
    """One harness a selection can be installed into, and which of its artifacts it can host.

    Eligibility is derived: the artifact's declared compatibility, the measured target tables for
    its kind at this scope, and policy. Choosing among these is the user's intent (D-260).
    """

    harness: str
    artifacts: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.harness, str)
            or not self.harness
            or ":" in self.harness
            or any(character in self.harness for character in "\r\n")
            or not isinstance(self.artifacts, tuple)
            or not self.artifacts
            or any(not isinstance(item, str) or not item for item in self.artifacts)
        ):
            raise ValueError("a harness target view is invalid")


#: How screen 05 addresses one Python-backend row, in the same shape as a harness row so the list
#: has one kind of control rather than a control and a special case.
INSTALLER_ROW_PREFIX = "installer:"


def installer_row(installer: str) -> str:
    return f"{INSTALLER_ROW_PREFIX}{installer}"


def installer_from_row(row: str) -> str | None:
    if not isinstance(row, str) or not row.startswith(INSTALLER_ROW_PREFIX):
        return None
    installer = row[len(INSTALLER_ROW_PREFIX) :]
    return installer if installer in ("pip", "uv") else None


def target_row(harness: str) -> str:
    return f"{TARGET_ROW_PREFIX}{harness}"


def target_from_row(row: str) -> str | None:
    if not isinstance(row, str) or not row.startswith(TARGET_ROW_PREFIX):
        return None
    harness = row[len(TARGET_ROW_PREFIX) :]
    return harness or None


def target_choice_problems(view: ConsumerPlanView, chosen: tuple[str, ...]) -> tuple[str, ...]:
    """Why these chosen harnesses cannot be installed into, in words; empty when they can.

    A plan that offers no choice has nothing to object to. Otherwise the choice must name at least
    one harness, every name must still be eligible (a stale choice is refused, never replaced), and
    every artifact must be hosted by some chosen harness.
    """

    return harness_choice_problems(view.targets, view.selection.resolved, chosen)


def harness_choice_problems(
    targets: tuple[HarnessTargetView, ...],
    resolved: tuple[str, ...],
    chosen: tuple[str, ...],
) -> tuple[str, ...]:
    """`target_choice_problems` over eligibility alone, for a selection that has no plan yet.

    Configuration belongs to one installation, and an installation is a harness, so the harness is
    chosen before anything is asked (#50). That choice is made while the inputs are still
    unanswered and no plan exists, so it is judged against what placement measured.
    """

    if not targets:
        return ()
    if not chosen:
        return ("Choose at least one harness to install into.",)
    eligible = {item.harness: item for item in targets}
    problems = [
        f"{harness} cannot host anything in this selection; untick it."
        for harness in chosen
        if harness not in eligible
    ]
    hosted = {
        artifact
        for harness in chosen
        if harness in eligible
        for artifact in eligible[harness].artifacts
    }
    for artifact in resolved:
        if artifact in hosted:
            continue
        options = ", ".join(item.harness for item in targets if artifact in item.artifacts)
        problems.append(
            f"None of the chosen harnesses can host {artifact}; it can go into {options}."
            if options
            else f"No eligible harness can host {artifact}."
        )
    return tuple(problems)


#: Screen 05's matrix (§172.2). A row is one artifact with the harnesses it can go into, so the
#: reducer reads the whole matrix off the rows it was given and needs no second channel for it.
MATRIX_ROW_PREFIX = "pairs:"
#: The artifact a row names when it is the "All artifacts" row, which ticks a whole column.
ALL_ARTIFACTS = "*"


def pair_key(artifact: str, harness: str) -> str:
    """One chosen artifact×harness pair, as the state and the command carry it."""

    return f"{artifact}\t{harness}"


def pair_from_key(key: str) -> tuple[str, str] | None:
    artifact, separator, harness = key.partition("\t")
    return (artifact, harness) if separator and artifact and harness else None


def pairs_harnesses(pairs: tuple[str, ...]) -> tuple[str, ...]:
    """The harnesses some pair goes into, in the order they were first chosen."""

    return tuple(
        dict.fromkeys(parsed[1] for parsed in map(pair_from_key, pairs) if parsed is not None)
    )


def default_pairs(targets: tuple[HarnessTargetView, ...]) -> tuple[str, ...]:
    """The pairs 05 starts with: an artifact that only one harness can host has it ticked (§172.2).

    Every other artifact starts with nothing ticked, so a real choice is always the person's.
    """

    options: dict[str, list[str]] = {}
    for target in targets:
        for artifact in target.artifacts:
            options.setdefault(artifact, []).append(target.harness)
    return tuple(
        pair_key(artifact, harnesses[0])
        for artifact, harnesses in options.items()
        if len(harnesses) == 1
    )


def settings_pairs(
    targets: tuple[HarnessTargetView, ...], harnesses: tuple[str, ...]
) -> tuple[str, ...]:
    """The pairs the Default path installs (§173.7): each artifact on the Settings harnesses.

    `targets` are the detected harnesses and what each can host, so a Settings harness that is not
    detected, or cannot host an artifact, gives that artifact nothing. With no harness in Settings,
    every detected harness that can host an artifact is used.
    """

    return tuple(
        pair_key(artifact, target.harness)
        for target in targets
        if not harnesses or target.harness in harnesses
        for artifact in target.artifacts
    )


def matrix_rows(targets: tuple[HarnessTargetView, ...]) -> tuple[str, ...]:
    """Screen 05's rows: "All artifacts" when there are several, then one row per artifact."""

    columns = tuple(item.harness for item in targets)
    if any("," in harness or "\t" in harness for harness in columns):
        raise ValueError("a harness name cannot be drawn as a matrix column")
    artifacts = tuple(dict.fromkeys(artifact for item in targets for artifact in item.artifacts))
    rows = tuple(
        f"{MATRIX_ROW_PREFIX}{artifact}\t"
        + ",".join(item.harness for item in targets if artifact in item.artifacts)
        for artifact in artifacts
    )
    if len(rows) > 1:
        rows = (f"{MATRIX_ROW_PREFIX}{ALL_ARTIFACTS}\t{','.join(columns)}", *rows)
    return rows


def matrix_from_row(row: str) -> tuple[str, tuple[str, ...]] | None:
    """The artifact a matrix row names, or `ALL_ARTIFACTS`, and the harnesses it can go into."""

    if not isinstance(row, str) or not row.startswith(MATRIX_ROW_PREFIX):
        return None
    artifact, separator, harnesses = row[len(MATRIX_ROW_PREFIX) :].partition("\t")
    if not separator or not artifact or not harnesses:
        return None
    return artifact, tuple(harnesses.split(","))


def matrix_columns(rows: tuple[str, ...]) -> tuple[str, ...]:
    """The matrix's harness columns in host order, read off its rows."""

    return tuple(
        dict.fromkeys(
            harness
            for parsed in map(matrix_from_row, rows)
            if parsed is not None
            for harness in parsed[1]
        )
    )


def toggle_matrix_cell(
    rows: tuple[str, ...], pairs: tuple[str, ...], row: str, harness: str
) -> tuple[str, ...]:
    """The pairs after Space on one cell: one pair, or a whole column on the "All artifacts" row.

    A cell the artifact cannot go into changes nothing. The "All artifacts" row ticks the column
    over every artifact it can host, unless all of those are ticked already, in which case it
    clears them; other columns are left alone.
    """

    parsed = matrix_from_row(row)
    if parsed is None or harness not in parsed[1]:
        return pairs
    artifact, _ = parsed
    if artifact != ALL_ARTIFACTS:
        key = pair_key(artifact, harness)
        return tuple(item for item in pairs if item != key) if key in pairs else (*pairs, key)
    column = tuple(
        pair_key(candidate, harness)
        for candidate, harnesses in (
            item for item in map(matrix_from_row, rows) if item is not None
        )
        if candidate != ALL_ARTIFACTS and harness in harnesses
    )
    if all(key in pairs for key in column):
        return tuple(item for item in pairs if item not in column)
    return (*pairs, *(key for key in column if key not in pairs))


def pair_choice_problems(
    targets: tuple[HarnessTargetView, ...], pairs: tuple[str, ...]
) -> tuple[str, ...]:
    """Why these pairs cannot be installed, in words; empty when they can (§172.2).

    Every pair has to be one the matrix offers -- a stale one is refused, never replaced -- and
    every artifact has to go into at least one harness.
    """

    if not targets:
        return ()
    if not pairs:
        return ("Choose at least one harness.",)
    hosts = {item.harness: item.artifacts for item in targets}
    chosen = [parsed for parsed in map(pair_from_key, pairs) if parsed is not None]
    problems = [
        f"{artifact} cannot go into {harness}; untick it."
        for artifact, harness in chosen
        if artifact not in hosts.get(harness, ())
    ]
    covered = {artifact for artifact, harness in chosen if artifact in hosts.get(harness, ())}
    for artifact in dict.fromkeys(item for value in hosts.values() for item in value):
        if artifact not in covered:
            options = ", ".join(item.harness for item in targets if artifact in item.artifacts)
            problems.append(f"Choose a harness for {artifact}; it can go into {options}.")
    return tuple(problems)


#: How screen 07a addresses one row: `scopes:<pair_key>\t<scope,…>`, the scopes that pair may go to.
SCOPE_MATRIX_PREFIX = "scopes:"
#: The pair of 07a's "All installations" row, offered only when there is more than one pair.
ALL_INSTALLATIONS = "*"
_SCOPE_ORDER = ("project", "user")


def pair_scope_key(pair: str, scope: str) -> str:
    """One pair's chosen scope, as 07a holds it: the pair key, a tab, the scope."""

    return f"{pair}\t{scope}"


def pair_scope_from_key(key: str) -> tuple[str, str] | None:
    pair, separator, scope = key.rpartition("\t") if isinstance(key, str) else ("", "", "")
    if not separator or scope not in _SCOPE_ORDER or pair_from_key(pair) is None:
        return None
    return pair, scope


def scope_matrix_rows(offers: tuple[tuple[str, tuple[str, ...]], ...]) -> tuple[str, ...]:
    """07a's rows (§172.5): "All installations" when there are several pairs, then one per pair."""

    rows = tuple(
        f"{SCOPE_MATRIX_PREFIX}{pair}\t{','.join(scopes)}" for pair, scopes in offers if scopes
    )
    if len(rows) > 1:
        offered = tuple(
            scope for scope in _SCOPE_ORDER if any(scope in scopes for _, scopes in offers)
        )
        rows = (f"{SCOPE_MATRIX_PREFIX}{ALL_INSTALLATIONS}\t{','.join(offered)}", *rows)
    return rows


def scope_matrix_from_row(row: str) -> tuple[str, tuple[str, ...]] | None:
    if not isinstance(row, str) or not row.startswith(SCOPE_MATRIX_PREFIX):
        return None
    pair, separator, offered = row[len(SCOPE_MATRIX_PREFIX) :].rpartition("\t")
    scopes = tuple(item for item in offered.split(",") if item)
    if (
        not separator
        or not scopes
        or any(item not in _SCOPE_ORDER for item in scopes)
        or (pair != ALL_INSTALLATIONS and pair_from_key(pair) is None)
    ):
        return None
    return pair, scopes


def scope_matrix_columns(rows: tuple[str, ...]) -> tuple[str, ...]:
    offered = {
        scope for parsed in map(scope_matrix_from_row, rows) if parsed for scope in parsed[1]
    }
    return tuple(scope for scope in _SCOPE_ORDER if scope in offered)


def choose_pair_scope(
    rows: tuple[str, ...], chosen: tuple[str, ...], row: str, scope: str
) -> tuple[str, ...]:
    """Put one pair on `scope`, or with the All row every pair that may go there (§172.5).

    Each pair has exactly one scope, so choosing one moves the pair rather than adding to it. A
    scope a pair is not offered changes nothing for that pair.
    """

    parsed = scope_matrix_from_row(row)
    if parsed is None:
        return chosen
    pair, _offered = parsed
    moved = {
        item[0]
        for item in map(scope_matrix_from_row, rows)
        if item is not None
        and item[0] != ALL_INSTALLATIONS
        and (pair in (ALL_INSTALLATIONS, item[0]))
        and scope in item[1]
    }
    if not moved:
        return chosen
    kept = tuple(key for key in chosen if (pair_scope_from_key(key) or ("", ""))[0] not in moved)
    order = [
        item[0]
        for item in map(scope_matrix_from_row, rows)
        if item is not None and item[0] in moved
    ]
    return (*kept, *(pair_scope_key(item, scope) for item in order))


def default_pair_scopes(
    offers: tuple[tuple[str, tuple[str, ...]], ...],
    preferred: str,
    chosen: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Each pair's scope: what was chosen for it, else the Settings default, else what it offers.

    §172.5: a pair starts on the Settings default when that is offered, and on the only offered
    scope otherwise. A choice for a pair no longer offered, or for a scope it no longer offers, is
    dropped rather than carried.
    """

    held = dict(item for item in map(pair_scope_from_key, chosen) if item is not None)
    scopes: list[str] = []
    for pair, offered in offers:
        if not offered:
            continue
        scope = held.get(pair)
        if scope not in offered:
            scope = preferred if preferred in offered else offered[0]
        scopes.append(pair_scope_key(pair, scope))
    return tuple(scopes)


def scope_choice_offered(rows: tuple[str, ...]) -> bool:
    """Whether 07a has anything to ask: some pair may go to more than one scope."""

    return any(
        parsed is not None and parsed[0] != ALL_INSTALLATIONS and len(parsed[1]) > 1
        for parsed in map(scope_matrix_from_row, rows)
    )


def pairs_confirmed(view: ConsumerPlanView, pairs: tuple[str, ...]) -> bool:
    """Whether this plan is the one prepared for exactly these ticked pairs, and may continue."""

    if not view.targets:
        return True
    return not pair_choice_problems(view.targets, pairs) and set(pairs) == set(view.chosen_pairs)


def targets_confirmed(view: ConsumerPlanView, chosen: tuple[str, ...]) -> bool:
    """Whether this plan is the one prepared for exactly these chosen harnesses, and may continue."""

    if not view.targets:
        return True
    return not target_choice_problems(view, chosen) and set(chosen) == set(view.chosen_targets)


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
    #: What this change is to somebody reading it, where the effect kind alone does not say. It is
    #: the kind for every effect whose kind is already unambiguous; see `_outcome`.
    outcome: str


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
    obtain_from: tuple[str, str | None] | None
    validation_hint: str
    default: str | None
    current: str | None
    configured: bool
    source: str | None
    #: The domain validation rule is retained for an interactive adapter. It is deliberately
    #: omitted from serialized output: the public projection already carries its human hint, while
    #: the form needs the actual rule to refuse every invalid value rather than reimplement it.
    validation: InputValidation | None = None
    #: Which installation is being asked (D-353). Two rows may share `id` -- one artifact on two
    #: harnesses is two installations and therefore two questions -- so `id` is no longer a row key.
    owner: str = ""

    @property
    def row(self) -> str:
        """The key that identifies this field on screen 07, unique where `id` is not."""

        return f"{self.owner}\t{self.id}" if self.owner else self.id


def config_input_value_problem(view: ConfigInputView, value: str) -> str | None:
    """Return the first domain-owned reason this screen-07 answer cannot be accepted."""

    if not isinstance(view, ConfigInputView) or not isinstance(value, str):
        raise ValueError("config input validation needs a projected field and text")
    return configuration_value_problem(value) or validate_config_value(view.validation, value)


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
    obtain_from: tuple[str, str | None] | None
    provider_reference: str | None
    provider: str | None
    provider_state: str
    health: str
    detail: str
    #: What each artifact needing it says about it, grouped by what they say (D-263).
    guidance: tuple[CredentialGuidance, ...] = ()
    #: Which installation is being asked (D-353). See `ConfigInputView.owner`.
    owner: str = ""

    @property
    def row(self) -> str:
        """The key that identifies this field on screen 07, unique where `id` is not."""

        return f"{self.owner}\t{self.id}" if self.owner else self.id


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
    declared_by: tuple[tuple[str, RuntimeInput], ...] = (),
    owner: str = "",
) -> tuple[InputView, ...]:
    """Project input guidance and binding state without ever projecting credential material.

    `declared_by` names which artifact declared each input, so a credential can say who needs it
    and keep each owner's own instructions. Without it the single declaration explains itself.

    `owner` names the installation these fields belong to, and is what makes `InputView.row` unique
    when the same declared input is asked separately of several installations (D-353). A caller
    projecting one installation at a time passes it; one projecting a single declaration need not.
    """

    if any(not isinstance(item, (SecretInput, ConfigInput)) for item in inputs):
        raise ValueError("required input projection received an invalid input")
    if not isinstance(bound_inputs, BoundInputs) or any(
        not isinstance(item, CredentialObservation) for item in credential_observations
    ):
        raise ValueError("required input projection received invalid binding evidence")
    bound_by_id = {item.input.id: item for item in bound_inputs.inputs}
    observations = {item.reference: item for item in credential_observations}
    owned_guidance = guidance_by_input(declared_by)
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
                    owned_guidance.get(runtime_input.id.value)
                    or gather_credential_guidance(
                        runtime_input.id.value, (("", runtime_input.guidance),)
                    ),
                    owner,
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
                runtime_input.validation,
                owner,
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


def _outcome(data: dict[str, object]) -> str:
    """What a change is to the person reading it, where its effect kind covers more than one thing.

    One `write-file` is the executable launcher a harness runs; another is the configuration file
    that harness reads, one per harness (D-264). A single count over the kind therefore told somebody
    installing one MCP server that two launchers would be written, which is a number they cannot
    reconcile with what they asked for. The plan already distinguishes them -- a launcher is written
    executable and a configuration file is not -- so the distinction is read, never guessed.
    """

    kind = str(data["kind"])
    if kind != "write-file":
        return kind
    return "write-launcher" if data.get("executable") else "write-configuration"


@dataclass(frozen=True, slots=True)
class InstallSecretView:
    """One secret input of one artifact on screen 07b, asked once for all its installations.

    There is no value here and no reference: what 07b knows is which question it asks and whether
    every installation it would answer already holds a stored value (§172.6).
    """

    #: `<alias>/<kind>/<name>\t<input>`, the same key 07 gives an artifact's ordinary input.
    row: str
    label: str
    #: Every installation of this artifact already holds a stored value, so 07b says it is
    #: configured securely.
    configured: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.row, str)
            or "\t" not in self.row
            or any(character in self.row for character in "\r\n")
            or not isinstance(self.label, str)
            or not self.label
            or not isinstance(self.configured, bool)
        ):
            raise ValueError("an install secret view is invalid")

    @property
    def artifact(self) -> str:
        return self.row.split("\t", 1)[0]

    @property
    def input(self) -> str:
        return self.row.split("\t", 1)[1]


def secrets_to_ask(view: ConsumerPlanView) -> tuple[InstallSecretView, ...]:
    """The secrets 07b asks for: the ones some new installation does not hold yet."""

    return tuple(item for item in view.secrets if not item.configured)


#: What Doctor, Installed and Credentials and variables say about a value still left by a skip
#: (§172.3). The words are the specification's.
PLACEHOLDER_WARNING = f"Still the {SKIPPED_INPUT} placeholder — set it in Credentials and variables"


def placeholders_left(view: ConsumerPlanView, entered: tuple[str, ...]) -> tuple[str, ...]:
    """Every `<artifact>\t<input>` this plan will store as `AART_NOT_SET`, for Ready (§172.6).

    The ordinary ones are in the plan. A secret is one 07b asked for and nobody entered: which were
    entered is the screen's to know, and only as row keys.
    """

    secrets = tuple(item.row for item in secrets_to_ask(view) if item.row not in entered)
    return tuple(sorted({*view.config_placeholders, *secrets}))


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
    #: The harnesses this selection could be installed into, each with the artifacts it can host.
    #: Empty for a plan that offers no choice (an update keeps what is installed). CP-23 task 10.
    targets: tuple[HarnessTargetView, ...] = ()
    #: The harnesses this plan was prepared for, as somebody chose them. Empty while nothing is
    #: chosen: such a plan is eligibility to choose from, never a plan to confirm (D-260).
    chosen_targets: tuple[str, ...] = ()
    #: The artifact×harness pairs this plan was prepared for (§172.2), as `pair_key` strings.
    chosen_pairs: tuple[str, ...] = ()
    #: 07a's rows: each prepared pair and the scopes it may go to (§172.5), `scope_matrix_rows`.
    scope_offers: tuple[str, ...] = ()
    #: The scope each pair was prepared for, as `pair_scope_key` strings.
    chosen_pair_scopes: tuple[str, ...] = ()
    #: Screen 07b's secrets, one per artifact and input (§172.6).
    secrets: tuple[InstallSecretView, ...] = ()
    #: The ordinary inputs this plan writes as `AART_NOT_SET`, one `<artifact>\t<input>` row per
    #: artifact (§172.6): what Ready lists beside the secrets 07b left unentered.
    config_placeholders: tuple[str, ...] = ()
    #: Which install scopes this selection may go to and which one it is going to, or `None` for a
    #: plan whose scope is not the operator's to choose (an update keeps where it already is).
    #: Screen 05 draws it only when there is something to decide (issue #11a, D-295).
    scope_choice: InstallScopeChoiceView | None = None
    #: Which Python backend may resolve this selection's dependencies and which one is going to,
    #: or `None` when nothing here declares Python dependencies -- then there is no question to
    #: ask, rather than a question with one answer (issue #11b).
    installer_choice: PythonInstallerChoiceView | None = None

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
    declared_by: tuple[tuple[str, RuntimeInput], ...] = (),
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
                _outcome(data),
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
            declared_by=declared_by,
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
        "targets": [
            {"harness": target.harness, "artifacts": list(target.artifacts)}
            for target in view.targets
        ],
        "chosen_targets": list(view.chosen_targets),
        "chosen_pairs": list(view.chosen_pairs),
        "chosen_pair_scopes": list(view.chosen_pair_scopes),
        "secrets": [{"row": item.row, "configured": item.configured} for item in view.secrets],
        "config_placeholders": list(view.config_placeholders),
    }


#: CP-23 task 08 (D-258): harness configuration is derived from where the artifact is delivered,
#: so the Harnesses line already says it. Every other remediation installs software, stores or
#: redirects a credential, or opens network access -- a material change that Ready, the one final
#: review, lists before it is confirmed (D-403, which folded screen 08 into it).
ROUTINE_REMEDIATION_KINDS = frozenset({"configure-harness"})


def material_remediations(view: ConsumerPlanView) -> tuple[RemediationView, ...]:
    """The changes Ready lists in every mode, because confirming it agrees to them (§161.5)."""

    return tuple(item for item in view.remediations if item.kind not in ROUTINE_REMEDIATION_KINDS)


def install_flow_screens(view: ConsumerPlanView) -> tuple[ConsumerScreen, ...]:
    """Return the accepted install flow, inserting question screens only when necessary."""

    # Automatic inspection is work AART performs between these screens, not a decision the user
    # must acknowledge. The projection remains available for diagnostics/Verbose presentation.
    screens = [ConsumerScreen.REVIEW_SELECTION]
    if view.inputs:
        screens.append(ConsumerScreen.REQUIRED_INPUTS)
    if scope_choice_offered(view.scope_offers):
        screens.append(ConsumerScreen.INSTALL_SCOPE)
    if secrets_to_ask(view):
        screens.append(ConsumerScreen.INSTALL_CREDENTIALS)
    screens.extend((ConsumerScreen.READY, ConsumerScreen.INSTALLING, ConsumerScreen.SUCCESS))
    return tuple(screens)


@dataclass(frozen=True, slots=True)
class ConsumerSession:
    screen: ApplicationScreen
    profile: PresentationProfile = PresentationProfile.LESS_INFO
    semantic_identity: str | None = None
    selection_identity: str | None = None
    review_digest: str | None = None
    history: tuple[ApplicationScreen, ...] = ()

    @classmethod
    def from_plan(cls, view: ConsumerPlanView) -> ConsumerSession:
        return cls(
            ConsumerScreen.READY,
            PresentationProfile.LESS_INFO,
            view.semantic_identity,
            view.selection.semantic_identity,
            view.review_digest,
        )

    def switch_profile(self, profile: PresentationProfile) -> ConsumerSession:
        if not isinstance(profile, PresentationProfile):
            raise ValueError("consumer presentation profile is invalid")
        return replace(self, profile=profile)

    def navigate(self, screen: ApplicationScreen) -> ConsumerSession:
        """Go to a screen, rewinding rather than pushing when it is somewhere already stood.

        A journey that finishes lands on the list it started from, and pushing there would put that
        list on the stack twice: Esc then walks back into the wizard that has already run, which is
        what the operator hit from Initialize Registry and from an install (`QA-072`). `QA-027` gave
        those journeys a forward exit and left the stack alone, so the fault outlived the fix.

        Returning to a place already stood in is a return, not a step deeper. Rewinding to it drops
        exactly the screens walked since -- the finished sequence -- and nothing else, so the stack
        stays the honest record of where the reader still is rather than of everywhere they went.
        """

        if not isinstance(screen, (ConsumerScreen, MaintainerScreen)):
            raise ValueError("application screen is invalid")
        if screen is self.screen:
            return self
        if screen in self.history:
            return replace(self, screen=screen, history=self.history[: self.history.index(screen)])
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
    #: The provider holds exactly `AART_NOT_SET`, compared in its own processes (§172.3).
    placeholder: bool = False


@dataclass(frozen=True, slots=True)
class ConfigurationFileView:
    """One installed harness's ordinary values, read from its artifact-owned file."""

    coordinate: str
    harness: str
    path: str
    state: str
    values: tuple[tuple[str, str], ...]
    detail: str = ""
    inputs: tuple[str, ...] = ()
    #: The installation this file belongs to (§169.3). An installation owns exactly one
    #: configuration file, so this is what a lookup addresses it by; the coordinate no longer is,
    #: because three harnesses are three files that all carry it. Empty where the record names no
    #: owner, and `row` is then the coordinate.
    installation: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coordinate, str)
            or not self.coordinate
            or not isinstance(self.harness, str)
            or not self.harness
            or not isinstance(self.path, str)
            or not self.path.startswith("/")
            or self.state not in {"matched", "changed-outside-aart", "missing", "unreadable"}
            or not isinstance(self.detail, str)
            or any(
                character in self.coordinate + self.harness + self.path + self.detail
                for character in "\r\n"
            )
            or not isinstance(self.values, tuple)
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0]
                or not isinstance(item[1], str)
                or any(character in item[0] + item[1] for character in "\r\n")
                for item in self.values
            )
            or len({item[0] for item in self.values}) != len(self.values)
            or not isinstance(self.inputs, tuple)
            or any(
                not isinstance(item, str)
                or not item
                or any(character in item for character in "\r\n")
                for item in self.inputs
            )
            or len(set(self.inputs)) != len(self.inputs)
            or not isinstance(self.installation, str)
            or any(character in self.installation for character in "\r\n")
        ):
            raise ValueError("configuration file view is invalid")

    @property
    def row(self) -> str:
        """The key this file is looked up by: its installation, or its artifact where none is named."""

        return self.installation or self.coordinate

    @property
    def placeholders(self) -> tuple[str, ...]:
        """The values in this file that are still `AART_NOT_SET`, by comparing the text (§172.3)."""

        return tuple(name for name, value in self.values if value == SKIPPED_INPUT)


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
    actions: tuple[str, ...]
    if observation.state is CredentialState.ABSENT:
        actions = ("verify", "set")
    elif observation.state is CredentialState.UNKNOWN:
        actions = ("verify",)
    else:
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
        observation.placeholder,
    )


@dataclass(frozen=True, slots=True)
class InstalledPathView:
    """One path this artifact owns, the part it plays, and what was measured about it.

    `state` is the observation's word for that component, or `unobserved` when nothing looked.
    An unmeasured path is honestly unmeasured: calling it `matched` would report a verification
    that never happened, and omitting it would hide a location somebody is looking for (issue #17).
    """

    role: str
    path: str
    harness: str = ""
    state: str = "unobserved"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.role, str)
            or not self.role
            or not isinstance(self.path, str)
            or not self.path.startswith("/")
            or not isinstance(self.harness, str)
            or not isinstance(self.state, str)
            or not self.state
        ):
            raise ValueError("an installed path view is invalid")


#: Which roles answer "where is it" for somebody who did not ask for detail: the bytes AART placed
#: and the places a harness reads them from. The rest are real and owned, and Verbose lists them.
_USER_FACING_ROLES: frozenset[str] = frozenset({"payload", "delivery", "merge", "settings"})


@dataclass(frozen=True, slots=True)
class InstalledArtifactView:
    coordinate: str
    health: str
    ownership: tuple[OwnershipView, ...]
    drift: tuple[LifecycleDriftView, ...]
    actions: tuple[str, ...]
    credentials: tuple[CredentialRecordView, ...] = ()
    #: Every path this installation's receipt records, in the order the receipt records them.
    #: Empty when no receipt answers for it, because a location nobody wrote down cannot be
    #: recovered by guessing a harness's layout (issue #17).
    installation: tuple[InstalledPathView, ...] = ()
    #: `project`, `user`, or empty when the receipt records no scope or records more than one.
    scope: str = ""
    #: Which harness this installation is (§169.3), `harness+profile` where the harness has
    #: profiles. Empty where the record names no owner, which is what a row with no harness in it
    #: means: nobody wrote down which installation this was.
    harness: str = ""
    #: The inputs this installation still holds as `AART_NOT_SET`, ordinary and secret alike
    #: (§172.3). Filled where the machine is assembled, which is where both are known.
    placeholders: tuple[str, ...] = ()
    #: The concrete root this installation was made into (§169.3): the project directory for a
    #: project-scope installation. Empty where the record names no owner.
    root: str = ""

    @property
    def row(self) -> str:
        """The key a row, a focus and a lookup address this installation by.

        `coordinate` names the artifact and is what a person reads; this names the installation
        and is what an action is aimed at. They were the same string until each harness became its
        own installation, and keeping them the same now would make two of three rows unreachable
        -- rows have to be distinct, and an action addressed to the coordinate would reach
        whichever installation a dictionary happened to keep.
        """

        return f"{self.coordinate}#{self.harness}" if self.harness else self.coordinate

    @property
    def user_facing_paths(self) -> tuple[InstalledPathView, ...]:
        return tuple(item for item in self.installation if item.role in _USER_FACING_ROLES)


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


def _observed_states(current: CurrentState) -> dict[ComponentId, str]:
    return {item.id: item.state.value for item in current.components}


def _recorded_scope(receipt: ArtifactReceipt | None) -> str:
    """The scope the receipt wrote down, and nothing else.

    Only an MCP registration records one. A delivery records a harness and a destination, so
    reading a scope off that destination would mean deciding which directories belong to a project
    and which to a home -- a guess about somebody else's disk, which is what issue #17 rules out.
    Disagreeing registrations collapse to nothing rather than to whichever came first.
    """

    if not isinstance(receipt, InstallationReceipt):
        return ""
    scopes = {item.target.scope.value for item in receipt.registrations}
    return scopes.pop() if len(scopes) == 1 else ""


def _installed_paths(
    receipt: ArtifactReceipt | None, current: CurrentState
) -> tuple[InstalledPathView, ...]:
    """Every path this receipt records, joined to the component that measured it.

    The join is by component identity rather than by path, because that is how the reconciler
    already addresses these things: the observation for a delivery is `delivery:<harness>`, and
    matching on the path string instead would silently stop working the day a harness moves a file.
    """

    if receipt is None:
        return ()
    states = _observed_states(current)

    def observed(component: Component, qualifier: str = "") -> str:
        identifier = ComponentId(component, qualifier) if qualifier else ComponentId(component)
        return states.get(identifier, "unobserved")

    paths = [InstalledPathView("payload", receipt.root, state=observed(Component.PAYLOAD))]
    if isinstance(receipt, PlacedArtifactReceipt):
        paths.extend(
            InstalledPathView(
                "delivery",
                item.destination,
                item.harness,
                observed(Component.DELIVERY, item.harness),
            )
            for item in receipt.deliveries
        )
        paths.extend(
            InstalledPathView(
                "merge", item.destination, item.harness, observed(Component.MERGE, item.harness)
            )
            for item in receipt.merges
        )
        paths.extend(
            InstalledPathView(
                "settings",
                item.destination,
                item.harness,
                observed(Component.SETTINGS, item.harness),
            )
            for item in receipt.settings
        )
        return tuple(paths)
    paths.append(
        InstalledPathView("launcher", receipt.launcher, state=observed(Component.LAUNCHER))
    )
    paths.append(
        InstalledPathView(
            "interpreter", receipt.interpreter, state=observed(Component.RUNTIME_ENVIRONMENT)
        )
    )
    paths.extend(
        InstalledPathView(
            "configuration",
            item.path,
            item.harness,
            observed(Component.CONFIGURATION, item.harness),
        )
        for item in receipt.configuration_files
    )
    return tuple(paths)


def project_installed_artifact(
    desired: DesiredState,
    current: CurrentState,
    *,
    ownership: tuple[OwnershipReason, ...] = (),
    update_available: bool = False,
    credentials: tuple[CredentialRecordView, ...] = (),
    receipt: ArtifactReceipt | None = None,
    harness: str = "",
) -> InstalledArtifactView:
    """Project measured installed health; mutation success is never health evidence."""

    if any(not isinstance(item, OwnershipReason) for item in ownership) or any(
        not isinstance(item, CredentialRecordView) for item in credentials
    ):
        raise ValueError("installed artifact projection received invalid ownership or credentials")
    health = installation_health(desired, current, update_available=update_available)
    owner = None if receipt is None else receipt.owner
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
        _installed_paths(receipt, current),
        _recorded_scope(receipt) if owner is None else owner.scope.value,
        harness,
        root="" if owner is None else owner.root,
    )


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}" if count else ""


def marketplace_cells(
    key: str, installed: tuple[InstalledArtifactView, ...], eligible: tuple[str, ...]
) -> tuple[str, ...]:
    """One Marketplace row's columns (§173.8), read off the installations of any version.

    The offer, then: installed or not or with an update available; the scopes it is installed in,
    with how many projects; the harnesses, each detected one that could host it and a `✓` on each
    that holds it; and the inputs still `AART_NOT_SET`, summed over installations because each
    keeps its own (§169.4). The two harness facts share one column so a row fits the measure.
    """

    artifact = key.partition("@")[0]
    held = tuple(item for item in installed if item.coordinate.partition("@")[0] == artifact)
    if not held:
        status = "not installed"
    elif any(item.health == "update" for item in held):
        status = "update available"
    else:
        status = "installed"
    projects = _counted(
        len({item.root for item in held if item.scope == "project" and item.root}), "project"
    )
    user = any(item.scope == "user" for item in held)
    holding = {item.harness for item in held if item.harness}
    unset = sum(len(item.placeholders) for item in held)
    return (
        key,
        status,
        " + ".join(part for part in ("user" if user else "", projects) if part),
        ", ".join(
            f"{harness} ✓" if harness in holding else harness
            for harness in sorted(holding | set(eligible))
        ),
        f"{unset} not set" if unset else "",
    )


def installed_cells(view: InstalledArtifactView, health: str) -> tuple[str, ...]:
    """One Installed row's columns after its key (§173.8): health, scope, project, unset inputs.

    The project is the root's last name; the whole path is detail, under More info.
    """

    project = view.root.rstrip("/").rpartition("/")[2] if view.scope == "project" else ""
    unset = len(view.placeholders)
    return (health, view.scope, project, f"{unset} not set" if unset else "")


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


def under_collections(
    collections: tuple[InstalledCollectionView, ...], installations: tuple[str, ...]
) -> tuple[tuple[str, bool], ...]:
    """Each Collection, then its member installations under it, then every other installation.

    Installed and Doctor share this order (§173.6). Each pair is a row and whether it is drawn under
    a Collection. A member of two Collections is drawn once, under the first, because a row is an
    installation and two rows for one would leave the second unreachable.
    """

    present = set(installations)
    placed: set[str] = set()
    ordered: list[tuple[str, bool]] = []
    for collection in collections:
        ordered.append((collection.collection, False))
        for member in collection.members:
            if member.artifact in present and member.artifact not in placed:
                placed.add(member.artifact)
                ordered.append((member.artifact, True))
    ordered.extend((row, False) for row in installations if row not in placed)
    return tuple(ordered)


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
    #: The other artifacts one reviewed action takes with it -- several ticked on Installed and
    #: uninstalled together (D-393). Empty for an action on one artifact.
    also: tuple["LifecyclePlanView", ...] = ()


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
class RunningStepView:
    """One step of a plan that is running now, or has just finished."""

    component: str
    effect: str
    status: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RunningInstallationView:
    """What a reviewed plan has done so far, while it is still doing it.

    It is a projection of the plan's own steps, so what is reported while it runs cannot say
    anything the review did not: the same components, the same effects, the same order.
    """

    artifact: str
    steps: tuple[RunningStepView, ...]
    done: int
    total: int

    @property
    def finished(self) -> bool:
        return self.done == self.total


#: What a step that has been reached but has not finished reads as. It is not a `StepStatus`,
#: because the execution has no outcome to report for it yet.
RUNNING = "running"


def project_running_installation(reports: tuple[StepProgress, ...]) -> RunningInstallationView:
    """Fold the reports a running plan has made so far into one screen's worth of state.

    Each step is held once, at the latest thing said about it, so a step announced as reached and
    then as applied is one line that changed rather than two lines. Pure: it is given what the
    execution said and reads nothing.
    """

    if any(not isinstance(item, StepProgress) for item in reports):
        raise ValueError("a running installation is projected from step progress reports")
    latest: dict[int, StepProgress] = {}
    for report in reports:
        latest[report.index] = report
    total = max((item.total for item in reports), default=0)
    artifacts = {str(item.artifact) for item in reports if item.artifact is not None}
    steps = tuple(
        RunningStepView(
            str(item.component),
            str(effect_to_data(item.effect)["kind"]),
            RUNNING if item.status is None else item.status.value,
            item.detail,
        )
        for _, item in sorted(latest.items())
    )
    return RunningInstallationView(
        artifacts.pop() if len(artifacts) == 1 else "",
        steps,
        sum(1 for item in latest.values() if item.status is not None),
        total,
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
        # Python 3.10 does not accept the RFC 3339 UTC designator even though 3.11+ does.
        # Normalize only that suffix; explicit numeric offsets retain their original meaning.
        encoded = (
            recorded_at.removesuffix("Z") + "+00:00" if recorded_at.endswith("Z") else recorded_at
        )
        moment = datetime.fromisoformat(encoded)
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
    source_revision: str | None = None


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
    revisions = (
        {}
        if plan is None
        else {item.version.coordinate: item.source_revision for item in plan.selection.artifacts}
    )
    artifacts = tuple(
        ReceiptArtifactView(
            str(item.plan.intent.desired.artifact),
            item.status,
            _ownership_view(item.plan.intent.resulting_ownership),
            () if item.outcome is None else project_lifecycle_outcome(item.outcome).steps,
            () if item.outcome is None else project_lifecycle_outcome(item.outcome).residual_drift,
            tuple(diagnostic.message for diagnostic in item.diagnostics),
            item.detail,
            revisions.get(item.plan.intent.desired.artifact),
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
                        **(
                            {}
                            if item.source_revision is None
                            else {"source_revision": item.source_revision}
                        ),
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
        ConsumerScreen.INSTALL_PATH,
    ),
    ConsumerScreen.ARTIFACT_DETAILS: (ConsumerScreen.INSTALL_PATH,),
    ConsumerScreen.COLLECTION_PREVIEW: (
        ConsumerScreen.COLLECTION_CUSTOMIZE,
        ConsumerScreen.INSTALL_PATH,
    ),
    # Custom goes on to 05; Default to whatever still needs deciding (§173.7).
    ConsumerScreen.INSTALL_PATH: (
        ConsumerScreen.REVIEW_SELECTION,
        ConsumerScreen.REQUIRED_INPUTS,
        ConsumerScreen.INSTALL_CREDENTIALS,
        ConsumerScreen.READY,
    ),
    ConsumerScreen.COLLECTION_CUSTOMIZE: (ConsumerScreen.INSTALL_PATH,),
    ConsumerScreen.REVIEW_SELECTION: (
        ConsumerScreen.AUTOMATIC_INSPECTION,
        ConsumerScreen.REQUIRED_INPUTS,
        ConsumerScreen.INSTALL_SCOPE,
        ConsumerScreen.INSTALL_CREDENTIALS,
        ConsumerScreen.READY,
    ),
    ConsumerScreen.AUTOMATIC_INSPECTION: (
        ConsumerScreen.REQUIRED_INPUTS,
        ConsumerScreen.INSTALL_SCOPE,
        ConsumerScreen.INSTALL_CREDENTIALS,
        ConsumerScreen.READY,
    ),
    ConsumerScreen.REQUIRED_INPUTS: (
        ConsumerScreen.INSTALL_SCOPE,
        ConsumerScreen.INSTALL_CREDENTIALS,
        ConsumerScreen.READY,
    ),
    ConsumerScreen.INSTALL_SCOPE: (ConsumerScreen.INSTALL_CREDENTIALS, ConsumerScreen.READY),
    ConsumerScreen.INSTALL_CREDENTIALS: (ConsumerScreen.READY,),
    ConsumerScreen.READY: (ConsumerScreen.INSTALLING,),
    ConsumerScreen.INSTALLING: (ConsumerScreen.SUCCESS,),
    ConsumerScreen.SUCCESS: (
        ConsumerScreen.MARKETPLACE,
        ConsumerScreen.INSTALLED,
        ConsumerScreen.RECEIPT_DETAILS,
        ConsumerScreen.MCP_TEST,
    ),
    ConsumerScreen.MCP_TEST: (),
    ConsumerScreen.INSTALLED: (
        ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ConsumerScreen.INSTALLED_COLLECTION_DETAILS,
        # What is ticked here is uninstalled from here (D-393), and tested from here (D-395).
        ConsumerScreen.UNINSTALL_REVIEW,
        ConsumerScreen.MCP_TEST,
    ),
    ConsumerScreen.INSTALLED_ARTIFACT_DETAILS: (
        ConsumerScreen.VERIFY_REPAIR,
        ConsumerScreen.UNINSTALL_REVIEW,
        ConsumerScreen.MCP_TEST,
    ),
    ConsumerScreen.INSTALLED_COLLECTION_DETAILS: (ConsumerScreen.UNINSTALL_REVIEW,),
    ConsumerScreen.UPDATES: (ConsumerScreen.UPDATE_INPUTS, ConsumerScreen.UPDATING),
    ConsumerScreen.UPDATE_INPUTS: (ConsumerScreen.UPDATING,),
    ConsumerScreen.UPDATING: (ConsumerScreen.ACTIVITY_DETAILS,),
    ConsumerScreen.UNINSTALL_REVIEW: (ConsumerScreen.UNINSTALLING,),
    ConsumerScreen.UNINSTALLING: (ConsumerScreen.ACTIVITY_DETAILS,),
    ConsumerScreen.VERIFY_REPAIR: (ConsumerScreen.ACTIVITY_DETAILS,),
    ConsumerScreen.REGISTRIES: (
        ConsumerScreen.REGISTRY_ADD,
        ConsumerScreen.REGISTRY_SYNC,
        ConsumerScreen.REGISTRY_REMOVE,
    ),
    ConsumerScreen.REGISTRY_SYNC: (ConsumerScreen.REGISTRIES,),
    ConsumerScreen.REGISTRY_REMOVE: (ConsumerScreen.REGISTRIES,),
    ConsumerScreen.REGISTRY_ADD: (ConsumerScreen.REGISTRY_REVIEW,),
    ConsumerScreen.REGISTRY_REVIEW: (ConsumerScreen.REGISTRIES,),
    ConsumerScreen.CREDENTIALS: (ConsumerScreen.USER_INPUT_DETAILS,),
    ConsumerScreen.USER_INPUT_DETAILS: (
        ConsumerScreen.CONFIGURATION_TARGETS,
        ConsumerScreen.CREDENTIAL_DETAILS,
    ),
    ConsumerScreen.CONFIGURATION_TARGETS: (ConsumerScreen.CONFIGURATION_VALUE,),
    ConsumerScreen.CONFIGURATION_VALUE: (ConsumerScreen.CONFIGURATION_REVIEW,),
    ConsumerScreen.CONFIGURATION_REVIEW: (ConsumerScreen.USER_INPUT_DETAILS,),
    ConsumerScreen.CREDENTIAL_DETAILS: (ConsumerScreen.CREDENTIAL_ACTION,),
    ConsumerScreen.CREDENTIAL_ACTION: (ConsumerScreen.CREDENTIAL_REVIEW,),
    ConsumerScreen.CREDENTIAL_REVIEW: (
        ConsumerScreen.CREDENTIAL_DETAILS,
        ConsumerScreen.CREDENTIALS,
    ),
    ConsumerScreen.ACTIVITY: (ConsumerScreen.ACTIVITY_DETAILS,),
    # A finished uninstall returns to the list it was started from (D-400).
    ConsumerScreen.ACTIVITY_DETAILS: (ConsumerScreen.RECEIPT_DETAILS, ConsumerScreen.INSTALLED),
    ConsumerScreen.RECEIPT_DETAILS: (),
    ConsumerScreen.SETTINGS: (),
    ConsumerScreen.DOCTOR: (ConsumerScreen.VERIFY_REPAIR,),
}


_KEEPS_FOCUS: frozenset[tuple[ConsumerScreen, ConsumerScreen]] = frozenset(
    {
        (ConsumerScreen.COLLECTION_PREVIEW, ConsumerScreen.COLLECTION_CUSTOMIZE),
        (ConsumerScreen.COLLECTION_PREVIEW, ConsumerScreen.INSTALL_PATH),
        (ConsumerScreen.COLLECTION_CUSTOMIZE, ConsumerScreen.INSTALL_PATH),
        # 05p's rows are the two paths, so what follows it is still about what Install was for.
        (ConsumerScreen.INSTALL_PATH, ConsumerScreen.REVIEW_SELECTION),
        (ConsumerScreen.INSTALL_PATH, ConsumerScreen.REQUIRED_INPUTS),
        (ConsumerScreen.INSTALL_PATH, ConsumerScreen.INSTALL_CREDENTIALS),
        (ConsumerScreen.INSTALL_PATH, ConsumerScreen.READY),
        # CP-23 task 06: Success is focused on the receipt its operation recorded, so opening the
        # receipt from it opens that one rather than whichever row the cursor was on.
        (ConsumerScreen.SUCCESS, ConsumerScreen.RECEIPT_DETAILS),
        # 11a tests the installations of the transaction Success is about, so it keeps that subject.
        (ConsumerScreen.SUCCESS, ConsumerScreen.MCP_TEST),
        # ... as it tests the one installation a details screen is about (D-395).
        (ConsumerScreen.INSTALLED_ARTIFACT_DETAILS, ConsumerScreen.MCP_TEST),
        # CP-23 task 12: 24's rows are verbs, so the review they open is still about the credential
        # rather than about the word "replace" (D-262).
        (ConsumerScreen.CREDENTIAL_ACTION, ConsumerScreen.CREDENTIAL_REVIEW),
        (ConsumerScreen.CONFIGURATION_TARGETS, ConsumerScreen.CONFIGURATION_VALUE),
        (ConsumerScreen.CONFIGURATION_VALUE, ConsumerScreen.CONFIGURATION_REVIEW),
    }
)


#: Every screen's own identifier, in one frozen set so the check cannot fall behind the catalogue.
_SCREEN_IDENTIFIERS: frozenset[str] = frozenset(
    {screen.value for screen in ConsumerScreen} | {screen.value for screen in MaintainerScreen}
)


def is_screen_identifier(value: str) -> bool:
    """Whether this string is the name of a screen rather than the name of a thing (`QA-077`).

    Screen identifiers are internal: `31-sources` is where the reader is, never what they are
    looking at. One reached the operator as a Source alias, in a refusal that then named no Source
    at all, so the two vocabularies are told apart here rather than by each caller remembering that
    a dashboard's rows are destinations.
    """

    if not isinstance(value, str):
        raise ValueError("a screen identifier is a string")
    return value in _SCREEN_IDENTIFIERS


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
INSTALL_SCOPE_UNAVAILABLE = DiagnosticCode("install-scope-unavailable")

#: The complete scope vocabulary, in the order the flow offers it.
_INSTALL_SCOPES: tuple[str, ...] = ("project", "user")


@dataclass(frozen=True, slots=True)
class InstallScopeChoiceView:
    """The scopes this operation may install into, and which one it is currently going to.

    The view cannot describe an impossible offer: the selection is always one of the offered
    scopes, and the offer is never empty. A screen that drew a scope the plan could not honour
    would be the fault this task is fixing wearing different clothes (issue #11a).
    """

    offered: tuple[str, ...]
    selected: str

    def __post_init__(self) -> None:
        if (
            not self.offered
            or tuple(sorted(set(self.offered))) != self.offered
            or not set(self.offered) <= set(_INSTALL_SCOPES)
            or self.selected not in self.offered
        ):
            raise ValueError("installation scope choice is invalid")

    @property
    def is_a_choice(self) -> bool:
        """Whether there is anything to decide, or only something to disclose."""

        return len(self.offered) > 1

    def choose(self, scope: str) -> InstallScopeChoiceView:
        if scope not in self.offered:
            raise ValueError("installation scope was not offered")
        return replace(self, selected=scope)


def offer_install_scopes(
    declared: tuple[tuple[str, ...], ...],
    *,
    project_available: bool,
    preferred: str,
) -> Result[InstallScopeChoiceView]:
    """Which scopes every member of the selection supports and this machine can actually host.

    The preference seeds the choice and never widens it: a selection that cannot honour the
    preference falls to what it can, because a default that loses is still a default. A selection
    whose members share no scope is refused rather than resolved -- installing them together has
    no correct answer, and picking one would make the flow choose where the operator's files go.
    """

    if not declared:
        return Err(
            (
                Diagnostic(
                    INSTALL_SCOPE_UNAVAILABLE,
                    Severity.ERROR,
                    "an empty selection has no installation scope to choose",
                ),
            )
        )
    common = set(_INSTALL_SCOPES)
    for item in declared:
        common &= set(item)
    if not project_available:
        common -= {"project"}
    if not common:
        return Err(
            (
                Diagnostic(
                    INSTALL_SCOPE_UNAVAILABLE,
                    Severity.ERROR,
                    "this selection has no installation scope every artifact supports here",
                ),
            )
        )
    offered = tuple(scope for scope in sorted(common))
    return Ok(InstallScopeChoiceView(offered, preferred if preferred in common else offered[0]))


#: A selection with no Python dependencies, or none the offered backends all satisfy.
PYTHON_INSTALLER_UNAVAILABLE = DiagnosticCode("python-installer-unavailable")

#: The complete backend vocabulary, in the order the flow offers it.
_PYTHON_INSTALLERS: tuple[str, ...] = ("pip", "uv")


@dataclass(frozen=True, slots=True)
class PythonInstallerChoiceView:
    """The backends that could resolve this operation's dependencies, and which one is going to.

    The twin of `InstallScopeChoiceView` and deliberately a separate type: scope decides where an
    artifact's files land, the backend decides what resolves its Python dependencies, and one
    answer is not evidence about the other (issue #11b).
    """

    offered: tuple[str, ...]
    selected: str

    def __post_init__(self) -> None:
        if (
            not self.offered
            or tuple(sorted(set(self.offered))) != self.offered
            or not set(self.offered) <= set(_PYTHON_INSTALLERS)
            or self.selected not in self.offered
        ):
            raise ValueError("Python installer choice is invalid")

    @property
    def is_a_choice(self) -> bool:
        """Whether there is anything to decide, or only something to disclose."""

        return len(self.offered) > 1

    def choose(self, installer: str) -> PythonInstallerChoiceView:
        if installer not in self.offered:
            raise ValueError("Python installer was not offered")
        return replace(self, selected=installer)


def offer_python_installers(
    usable: tuple[tuple[str, ...], ...],
    *,
    preferred: str,
) -> Result[PythonInstallerChoiceView]:
    """Which backends every dependency contract in this selection can be installed by.

    `usable` is one entry per artifact that declares Python dependencies, already narrowed by the
    planner to what this specification, this machine and this policy allow. An empty `usable` is
    not a choice with no answer but a question that does not arise -- nothing here needs Python --
    and an empty intersection is refused rather than resolved, because running two backends for one
    reviewed install is the thing `chosen_installer` exists to prevent.
    """

    if not usable:
        return Err(
            (
                Diagnostic(
                    PYTHON_INSTALLER_UNAVAILABLE,
                    Severity.ERROR,
                    "nothing in this selection declares Python dependencies",
                ),
            )
        )
    common = set(_PYTHON_INSTALLERS)
    for item in usable:
        common &= set(item)
    if not common:
        return Err(
            (
                Diagnostic(
                    PYTHON_INSTALLER_UNAVAILABLE,
                    Severity.ERROR,
                    "this selection has no Python installer every artifact can be installed by",
                ),
            )
        )
    offered = tuple(sorted(common))
    return Ok(PythonInstallerChoiceView(offered, preferred if preferred in common else offered[0]))


@dataclass(frozen=True, slots=True)
class ConsumerSettings:
    profile: PresentationProfile = PresentationProfile.LESS_INFO
    default_scope: str = "project"
    show_updates: bool = True
    maintainer_mode: bool = False
    #: Which backend resolves Python dependencies when more than one could. `pip` is the default
    #: because every Python that can build an environment already has it, so the preference starts
    #: on the backend that is never the reason an install cannot run (issue #11b).
    python_installer: str = "pip"
    #: The harnesses the Default install path uses (§173.7). Empty means every detected harness
    #: that can host the artifact.
    default_harnesses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.default_harnesses, tuple)
            or any(not _is_harness_name(item) for item in self.default_harnesses)
            or len(set(self.default_harnesses)) != len(self.default_harnesses)
        ):
            raise ValueError("consumer settings are invalid")
        if (
            not isinstance(self.profile, PresentationProfile)
            or self.default_scope not in {"project", "user"}
            or not isinstance(self.show_updates, bool)
            or not isinstance(self.maintainer_mode, bool)
            or self.python_installer not in set(_PYTHON_INSTALLERS)
        ):
            raise ValueError("consumer settings are invalid")

    def with_profile(self, profile: PresentationProfile) -> ConsumerSettings:
        return replace(self, profile=profile)

    def with_maintainer_mode(self, enabled: bool) -> ConsumerSettings:
        if not isinstance(enabled, bool):
            raise ValueError("Registry Maintainer Mode setting must be a boolean")
        return replace(self, maintainer_mode=enabled)

    def toggled(self, row: str) -> ConsumerSettings:
        """This preference, moved to its other value. Every control on screen 28 is binary."""

        if row == "detail-level":
            return self.with_profile(
                PresentationProfile.MORE_INFO
                if self.profile is PresentationProfile.LESS_INFO
                else PresentationProfile.LESS_INFO
            )
        if row == "default-scope":
            return replace(
                self, default_scope="user" if self.default_scope == "project" else "project"
            )
        if row == "show-updates":
            return replace(self, show_updates=not self.show_updates)
        if row == "python-installer":
            return replace(self, python_installer="uv" if self.python_installer == "pip" else "pip")
        if row == "maintainer-mode":
            return self.with_maintainer_mode(not self.maintainer_mode)
        harness = default_harness_from_row(row)
        if harness is not None:
            return replace(
                self,
                default_harnesses=(
                    tuple(item for item in self.default_harnesses if item != harness)
                    if harness in self.default_harnesses
                    else (*self.default_harnesses, harness)
                ),
            )
        raise ValueError(f"no consumer setting is named {row}")


#: Screen 11's actions, in the order the Product Specification names them, as the screens they open
#: (CP-23 task 06). The row identity is the destination, as on a dashboard, so a choice can never
#: be carried forward as though it were the subject of the screen it opens. Undo is not one: this
#: surface has no reviewed installation undo, so offering it would be a name without an action
#: (D-256).
#:
#: Testing MCPs is offered only when the transaction installed at least one MCP (§170.4), so the
#: screen drops that row otherwise; the order of the rest never changes.
SUCCESS_CHOICES: tuple[tuple[ConsumerScreen, str], ...] = (
    (ConsumerScreen.INSTALLED, "View installed"),
    (ConsumerScreen.RECEIPT_DETAILS, "View receipt"),
    (ConsumerScreen.MCP_TEST, "Test installed MCPs"),
    (ConsumerScreen.MARKETPLACE, "Done"),
)

SUCCESS_PURPOSE: dict[ConsumerScreen, str] = {
    ConsumerScreen.INSTALLED: "Opens Installed: everything AART manages here and whether it is healthy.",
    ConsumerScreen.RECEIPT_DETAILS: "Opens the receipt this install recorded: what ran, its effects "
    "and why Undo is or is not possible.",
    ConsumerScreen.MCP_TEST: "Reviews a test of the MCPs this install made: their startup and one "
    "declared call each. Nothing runs until you confirm, and no result changes this install.",
    ConsumerScreen.MARKETPLACE: "Returns to Marketplace and leaves this finished install behind; "
    "nothing runs again.",
}
"""Where each Success choice goes, for the block `[v]` opens."""


@dataclass(frozen=True, slots=True)
class McpTestEntryView:
    """What testing one installation will call, as the offer states it (§170.4).

    `tool` is empty where the installed content declares no smoke operation. `arguments` are as
    declared, so a reference to a configuration input is drawn as that reference, never its value.
    """

    installation: str
    tool: str
    arguments: str


@dataclass(frozen=True, slots=True)
class McpTestStageView:
    stage: str
    outcome: str
    reason: str


@dataclass(frozen=True, slots=True)
class McpTestResultView:
    installation: str
    stages: tuple[McpTestStageView, ...]

    @property
    def passed(self) -> bool:
        return bool(self.stages) and all(item.outcome == "PASS" for item in self.stages)


@dataclass(frozen=True, slots=True)
class McpTestView:
    """The optional test after an installation: which installations, the offer, and its answer.

    `installations` are exactly the MCP installations the committed transaction made. `plan` is
    filled once the test is prepared and `results` once it ran; neither is part of the install.
    """

    installations: tuple[str, ...]
    plan: tuple[McpTestEntryView, ...] = ()
    results: tuple[McpTestResultView, ...] | None = None


#: The controls of accepted screen 28, in the order the Product Specification lists them. They are
#: row identities rather than labels so a rename of what is drawn never rewrites what was stored.
SETTING_ROWS: tuple[str, ...] = (
    "detail-level",
    "default-scope",
    "python-installer",
    "show-updates",
    "maintainer-mode",
)

#: Screen 28's rows for the Default path's harnesses, one per detected harness, each on or off.
DEFAULT_HARNESS_ROW_PREFIX = "default-harness:"


def _is_harness_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and all(character.isalnum() or character in "-_." for character in value)
    )


def default_harness_row(harness: str) -> str:
    if not _is_harness_name(harness):
        raise ValueError("a default harness row needs a harness name")
    return f"{DEFAULT_HARNESS_ROW_PREFIX}{harness}"


def default_harness_from_row(row: str) -> str | None:
    if not row.startswith(DEFAULT_HARNESS_ROW_PREFIX):
        return None
    harness = row[len(DEFAULT_HARNESS_ROW_PREFIX) :]
    return harness if _is_harness_name(harness) else None


def setting_rows(harnesses: tuple[str, ...]) -> tuple[str, ...]:
    """Screen 28's rows: the fixed controls, then one Default-path harness row per harness.

    The harness rows come last, under their own heading, so the fixed controls keep their places
    however many harnesses this machine has.
    """

    return (*SETTING_ROWS, *(default_harness_row(item) for item in harnesses))


SETTING_PURPOSE: dict[str, str] = {
    "detail-level": "How much every screen says: Fast hides the per-row explanations, "
    "Verbose shows them.",
    "default-scope": "Where an install lands when nothing asks for somewhere else: "
    "Project writes into this checkout, User writes into your home.",
    "python-installer": "Which backend resolves Python dependencies when an artifact's "
    "contract and this machine allow either: pip is universally present, uv is faster.",
    "show-updates": "Whether the Dashboard counts the installed artifacts a registry "
    "offers a newer version of.",
    "maintainer-mode": "Whether this installation authors artifacts as well as installing "
    "them, which is what puts Sources, Candidates and Registry Workspace on the Dashboard.",
}
"""What each setting changes, for the block `[v]` opens (`QA-097`).

Every row a cursor can sit on describes itself, the way the rebuild stages have since `QA-089`.
Every row that changes behaviour says what it changes; a row that did not left the reader toggling
a setting to find out what it did.
"""


def setting_purpose(row: str) -> str | None:
    """What the Settings row under the cursor changes, a Default-path harness row included."""

    harness = default_harness_from_row(row)
    if harness is not None:
        return (
            f"Whether the Default install path installs into {harness} when it is detected and "
            "can host the artifact. With no harness on, Default uses every one that can."
        )
    return SETTING_PURPOSE.get(row)


#: Screen 05p's rows (§173.7). Default is first: it is the path that asks least.
INSTALL_PATH_DEFAULT = "default"
INSTALL_PATH_CUSTOM = "custom"
INSTALL_PATH_ROWS: tuple[str, ...] = (INSTALL_PATH_DEFAULT, INSTALL_PATH_CUSTOM)
INSTALL_PATH_PURPOSE: dict[str, str] = {
    INSTALL_PATH_DEFAULT: "Installs with the harnesses, scope and Python installer from Settings, "
    "and asks only what still needs entering.",
    INSTALL_PATH_CUSTOM: "Chooses the harnesses, the scope and the Python installer for this "
    "install, then asks what needs entering.",
}


def settings_to_data(view: ConsumerSettings) -> dict[str, object]:
    """One consumer's preferences as plain data. No machine state, and nothing secret."""

    if not isinstance(view, ConsumerSettings):
        raise ValueError("settings serialization needs consumer settings")
    return {
        "detail_level": view.profile.value,
        "default_scope": view.default_scope,
        "python_installer": view.python_installer,
        "show_updates": view.show_updates,
        "maintainer_mode": view.maintainer_mode,
        "default_harnesses": list(view.default_harnesses),
    }


def settings_from_data(data: object) -> Result[ConsumerSettings]:
    """Read back preferences somebody chose, refusing anything this cannot mean.

    A stored preference is read strictly rather than repaired: silently falling back to Fast after
    somebody chose Verbose would be the frontend deciding a detail level for them, and silently
    falling back on Registry Maintainer Mode is a mode boundary answering itself.
    """

    if not isinstance(data, dict):
        return Err((_settings_invalid("stored consumer settings must be a JSON object"),))
    known = {
        "detail_level",
        "default_scope",
        "python_installer",
        "show_updates",
        "maintainer_mode",
        "default_harnesses",
    }
    unknown = sorted(set(data) - known)
    if unknown:
        return Err(
            (_settings_invalid(f"stored consumer settings name {unknown[0]}, which AART does not"),)
        )
    detail = data.get("detail_level", PresentationProfile.LESS_INFO.value)
    if detail not in {item.value for item in PresentationProfile}:
        return Err((_settings_invalid("stored detail level must be less-info or more-info"),))
    scope = data.get("default_scope", "project")
    if scope not in {"project", "user"}:
        return Err((_settings_invalid("stored default scope must be project or user"),))
    installer = data.get("python_installer", "pip")
    if installer not in set(_PYTHON_INSTALLERS):
        return Err((_settings_invalid("stored Python installer must be pip or uv"),))
    updates = data.get("show_updates", True)
    maintainer = data.get("maintainer_mode", False)
    if not isinstance(updates, bool) or not isinstance(maintainer, bool):
        return Err(
            (
                _settings_invalid(
                    "stored update visibility and Registry Maintainer Mode must be true or false"
                ),
            )
        )
    harnesses = data.get("default_harnesses", [])
    if (
        not isinstance(harnesses, list)
        or any(not _is_harness_name(item) for item in harnesses)
        or len(set(harnesses)) != len(harnesses)
    ):
        return Err((_settings_invalid("stored default harnesses must be distinct harness names"),))
    return Ok(
        ConsumerSettings(
            PresentationProfile(detail),
            cast(str, scope),
            updates,
            maintainer,
            cast(str, installer),
            tuple(harnesses),
        )
    )


def _settings_invalid(message: str) -> Diagnostic:
    return Diagnostic(CONSUMER_SETTINGS_INVALID, Severity.ERROR, message)


@dataclass(frozen=True, slots=True)
class RegistryView:
    """One configured Registry connection as screen 21 shows it.

    Authoring Sources belong to Maintainer screen 31. Under 161.7 and INV-199, projecting one here
    would make a discovery subscription look like a consumer availability boundary.
    """

    alias: str
    availability: str
    health: str
    artifact_count: int
    last_sync_age_seconds: int | None
    kind: str
    origin: str
    ref: str | None
    revision: str | None
    snapshot_digest: str | None
    trust: tuple[str, ...]
    actions: tuple[str, ...] = ("details", "sync")
    is_registry: bool = True


def project_registries(catalog: MarketplaceCatalog) -> tuple[RegistryView, ...]:
    if not isinstance(catalog, MarketplaceCatalog):
        raise ValueError("registry projection needs a marketplace catalog")
    rows = []
    for source in catalog.sources:
        # Either transport (D-350): a local Registry is synced and disconnected from here too.
        if source.kind not in {SourceKind.REGISTRY_GIT, SourceKind.REGISTRY_LOCAL}:
            continue
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
                source.ref,
                source.resolved_revision,
                None if source.snapshot_digest is None else str(source.snapshot_digest),
                tuple(sorted({item.trust.kind.value for item in source_items})),
                ("details", "sync"),
                True,
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
    artifacts: tuple[InstalledArtifactView, ...] = ()
    collections: tuple[InstalledCollectionView, ...] = ()


def project_doctor(
    artifacts: tuple[InstalledArtifactView, ...],
    collections: tuple[InstalledCollectionView, ...] = (),
) -> DoctorView:
    if any(not isinstance(item, InstalledArtifactView) for item in artifacts):
        raise ValueError("Doctor projection needs installed artifact views")
    if any(not isinstance(item, InstalledCollectionView) for item in collections):
        raise ValueError("Doctor projection needs installed Collection views")
    # An issue is an installation, as Installed and repair address it: one artifact installed into
    # two harnesses is two issues, and keyed by coordinate they were one row twice (§169.3).
    issues = tuple(item.row for item in artifacts if item.health in {"attention", "broken"})
    repairable = tuple(
        item.row
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
        artifacts,
        collections,
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
                        (None if "source_revision" not in row else _string(row, "source_revision")),
                    )
                    for row in _rows(data, "artifacts")
                ),
            )
        )
    except ValueError as error:
        return _view_error(str(error))
