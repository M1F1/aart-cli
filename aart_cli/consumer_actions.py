"""The imperative boundary the persistent consumer application acts through.

`run_consumer_shell` reduces a keystroke into a typed command and refuses to act on one without an
injected handler (D-069). This is that handler on a real machine: it prepares, executes, records
and re-reads, and hands back a new immutable screen snapshot beside the event saying what the
action established. Nothing here decides product policy. What may be installed is still the
approved registry snapshot, what is removed is still what the receipts record, and what is carried
out is still the review digest somebody confirmed on screen.

Three things are load-bearing.

Preparation mutates nothing. Every action's first half only reads -- the machine, the receipts, the
configured snapshot -- so somebody can open a review, look at it and walk away having changed
nothing.

The machine it hands back was read afterwards, never assembled from what the action believed it
did. A half-applied install has to appear as what it left behind.

And a refusal is drawn rather than raised. The shell has already moved to the screen the action
was requested from, so a handler that threw would take the terminal down over an artifact that
failed to resolve. The refusal comes back as a notice on that screen, under an event the reducer
reads as "nothing was established", which leaves the session exactly where it was.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol

from aart_cli.application.consumer_session import ConsumerMachine, InstalledInspection
from aart_cli.application.consumer_ui import (
    AUTHORING_SOURCE_KINDS,
    REGISTRY_SOURCE_KINDS,
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    InstallationConfigDraft,
    InstallationConfigField,
    RegistryDraft,
    RegistryInitDraft,
    RepositoryScanDraft,
    SourceDraft,
    installation_is_mcp,
)
from aart_cli.application.consumer_views import (
    ConfigInputView,
    ConsumerPlanView,
    ConsumerScreen,
    ConsumerSettings,
    DefaultPathMismatch,
    HarnessTargetView,
    InputView,
    InstallScopeChoiceView,
    InstallSecretView,
    LifecyclePlanView,
    McpTestEntryView,
    McpTestResultView,
    McpTestStageView,
    McpTestView,
    PythonInstallerChoiceView,
    RunningInstallationView,
    default_pair_scopes,
    default_pairs,
    default_path_mismatches,
    harness_choice_problems,
    offer_install_scopes,
    offer_python_installers,
    pair_choice_problems,
    pair_from_key,
    pair_key,
    pair_scope_from_key,
    pair_scope_key,
    pairs_harnesses,
    project_lifecycle_plan,
    project_running_installation,
    scope_matrix_rows,
    secrets_to_ask,
    settings_pairs,
    target_choice_problems,
)
from aart_cli.application.credential_guidance import (
    CredentialGuidance,
    gather_credential_guidance,
)
from aart_cli.application.credential_lifecycle import (
    CredentialPlan,
    credential_plan_to_data,
    plan_credential_mutation,
)
from aart_cli.application.execution import StepProgress
from aart_cli.application.installation_inputs import (
    ArtifactAnswer,
    OwnedInputSource,
    artifact_answer_key,
    copy_artifact_answers,
)
from aart_cli.application.installed_setup import DeclaredArtifactSetup
from aart_cli.application.maintainer_promotion import (
    CandidatePromotionExecutionResult,
    PreparedCandidatePromotionTransaction,
)
from aart_cli.application.maintainer_sync import PreparedSourceSync
from aart_cli.application.maintainer_views import (
    REGISTRY_MAINTENANCE_STAGES,
    REGISTRY_REBUILD_EVERYTHING,
    REGISTRY_STAGE_PURPOSE,
    MaintainerAdoptedArtifactView,
    MaintainerAdoptionReviewView,
    MaintainerAdoptionUpstreamView,
    MaintainerRepositoryArtifactView,
    MaintainerRepositoryScanView,
    MaintainerViews,
    parse_collection_row,
    parse_validation_row,
    project_maintainer_registry_commit,
    project_maintainer_registry_validation,
    project_source_sync_result,
    project_source_sync_review,
)
from aart_cli.authoring.check import AuthorCheckReport
from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.configuration.policy import EffectiveConfiguration, redact_text
from aart_cli.configuration.schema import configured_source_from_input
from aart_cli.domain.candidates import CandidateId
from aart_cli.domain.credentials import (
    CredentialIntent,
    CredentialLength,
    CredentialReference,
    CredentialState,
    ProviderState,
    checked_observation,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.effects import ReplaceCredential, StoreCredential, VerifyCredential
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import (
    ArtifactCoordinate,
    ArtifactIdentity,
    InputId,
    SourceAlias,
)
from aart_cli.domain.inputs import (
    ConfigInput,
    InputGuidance,
    RuntimeInput,
    SecretInput,
    SecretProviderReference,
    is_skipped_value,
)
from aart_cli.domain.installation_owner import (
    credential_address,
    describe_installation,
    installation_key,
)
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.python_runtime import PythonInstaller
from aart_cli.domain.receipts import ArtifactReceipt, InstallationReceipt, InstalledRecord
from aart_cli.domain.reconciliation import DesiredState
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.selection import (
    ArtifactRequest,
    ArtifactSelection,
    OwnershipKind,
    OwnershipReason,
    VersionConstraint,
)
from aart_cli.io.author_operations import check_workspace, new_artifact, select_workspace
from aart_cli.io.configured_configuration_action import (
    PreparedConfiguredConfiguration,
    complete_configured_configuration,
    prepare_configured_configuration,
)
from aart_cli.io.configured_installation import InstallationAssignment
from aart_cli.io.configured_installation_action import (
    CompletedConfiguredInstallation,
    InstallationHost,
    PreparedConfiguredInstallation,
    complete_configured_installation,
    prepare_configured_installation,
)
from aart_cli.io.configured_repair_action import (
    PreparedConfiguredRepair,
    complete_configured_repair,
    prepare_configured_repair,
)
from aart_cli.io.configured_uninstall_action import (
    PreparedConfiguredUninstall,
    complete_configured_uninstall,
    prepare_configured_uninstall,
)
from aart_cli.io.consumer_machine import read_consumer_machine, read_installed_inspections
from aart_cli.io.consumer_settings import write_consumer_settings
from aart_cli.io.credential_entry import CredentialEntryFallback
from aart_cli.io.credentials import CredentialProviderPort
from aart_cli.io.execution import CredentialEffectInterpreter, TerminalHandover
from aart_cli.io.harness import ScopedHarnessRegistry
from aart_cli.io.installation_execution import interpreters_for
from aart_cli.io.installed_smoke import LocalMcpTest, SmokePlanEntry, SmokeTargetResult
from aart_cli.io.maintainer_promotion import (
    PreparedConfiguredCandidatePromotion,
    complete_configured_candidate_promotion,
    prepare_configured_bulk_promotion,
    prepare_configured_candidate_promotion,
    prepare_configured_collection,
)
from aart_cli.io.maintainer_sync import (
    complete_configured_source_sync,
    prepare_configured_source_sync,
)
from aart_cli.io.maintainer_views import read_maintainer_views
from aart_cli.io.object_store import read_object
from aart_cli.io.registry_adoption import (
    AdoptedArtifact,
    AdoptionUpstreamCheck,
    PreparedAdoption,
    RepositoryScan,
)
from aart_cli.io.registry_bootstrap import (
    RegistryBootstrapReport,
    registry_absent_refusal,
    registry_identity_refusal,
)
from aart_cli.io.registry_publication import publish_registry_commit
from aart_cli.io.registry_workspace import read_registry_workspace
from aart_cli.protocol.authoring import read_package_description
from aart_cli.protocol.hashing import parse_sha256
from aart_cli.registry_commands.publication_state import (
    RegistryPublicationCommand,
    RegistryPublicationReceipt,
    prepare_registry_publication,
    publication_summary,
)
from aart_cli.store.model import ObjectReadRequest, object_store_paths
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    ConsumerActionCompletion,
    ConsumerActionUpdate,
    ConsumerOffers,
    MarketplaceEntry,
    screens_from,
)

__all__ = [
    "CONSUMER_ACTION_NOT_INSTALLED",
    "CONSUMER_ACTION_NOT_OFFERED",
    "ConsumerActionContext",
    "LocalConsumerActions",
    "RegistryBootstrapCompletion",
    "RegistryConnectionSnapshot",
    "RepositoryAdoptionPort",
]

#: What a command names is not among the artifacts the configured sources currently offer.
CONSUMER_ACTION_NOT_OFFERED = DiagnosticCode("consumer-action-not-offered")

#: What a command names has no canonical record on this machine, so nothing here can act on it.
CONSUMER_ACTION_NOT_INSTALLED = DiagnosticCode("consumer-action-not-installed")

#: What a command names was installed into another project. Its harness files are resolved against
#: that project's root, so acting on it from here would write into this one (D-479).
CONSUMER_ACTION_ELSEWHERE = DiagnosticCode("consumer-action-elsewhere")

#: What a command names holds installations of both scopes. Each scope's harness paths resolve
#: against its own root, and one plan is prepared for one of them (D-479).
CONSUMER_ACTION_MIXED_SCOPES = DiagnosticCode("consumer-action-mixed-scopes")


def _installation_of(record: InstalledRecord) -> str:
    owner = record.receipt.owner
    assert owner is not None
    return installation_key(record.coordinate, owner)


def _why(error: BaseException) -> str:
    """An exception as one bounded line a screen can draw, so a failure says what failed (D-491)."""

    said = " ".join(str(error).split())
    named = f"{type(error).__name__}: {said}" if said else type(error).__name__
    return named if len(named) <= 200 else named[:199] + "…"


def _lines(*messages: str) -> tuple[str, ...]:
    """One drawable line per message, because a terminal row cannot hold a newline."""

    return tuple(
        part.strip()
        for message in messages
        for part in str(message).replace("\r", "\n").split("\n")
        if part.strip()
    )


#: `QA-017`/`B-091`: the net under the typed projection, not the projection itself. A producer that
#: has not been given `interactive` prose yet degrades to showing the steps that name no command,
#: rather than to printing shell syntax into a frame that cannot run it.
_COMMAND_MARKERS = ("aart-cli ", "`", "$ ", "git ")


def _names_a_command(step: str) -> bool:
    return any(marker in step for marker in _COMMAND_MARKERS)


_ELSEWHERE = "The next step for this is not available on this screen yet."


def _config_placeholders(prepared: PreparedConfiguredInstallation) -> tuple[str, ...]:
    """The ordinary inputs a skip left as `AART_NOT_SET`, once per artifact, for Ready (§172.3)."""

    return tuple(
        sorted(
            {
                f"{artifact_answer_key(owner)}\t{item.input.id.value}"
                for owner, bound in prepared.draft.inputs.bound
                for item in bound.inputs
                if not isinstance(item.input, SecretInput)
                and not isinstance(item.source, SecretProviderReference)
                and is_skipped_value(item.source.value)
            }
        )
    )


def _refusal(diagnostics: tuple[Diagnostic, ...]) -> tuple[str, ...]:
    """What a refusal reads like inside the application, never as something to go and type.

    `Diagnostic.interactive` is the projection: prose for somebody already here. Without it the
    command-free remediation steps are shown, and when a diagnostic had nothing but commands the
    refusal still says that a next step exists elsewhere -- a refusal that names no next step is
    the dead end `QA-019` removed one boundary over.
    """

    lines: list[str] = [item.message for item in diagnostics]
    steps: list[str] = []
    withheld = False
    for item in diagnostics:
        if item.interactive:
            steps.extend(item.interactive)
            continue
        for step in item.remediation:
            if _names_a_command(step):
                withheld = True
            else:
                steps.append(step)
    if withheld and not steps:
        steps.append(_ELSEWHERE)
    # `QA-096`: a refusal is a list of statements, not a paragraph. The blank line is what the
    # notice block reads to tell one from the next, so a reason and its next step are separated
    # here rather than run together into a single wrapped sentence.
    said = _lines(*lines, *steps)
    return tuple(
        line for index, item in enumerate(said) for line in (("",) if index else ()) + (item,)
    )


def _rebuild_stages(focus: str) -> tuple[str, ...]:
    """Which stages the chosen row means, or none at all when the row names no run.

    Deriving both answers from `REGISTRY_MAINTENANCE_STAGES` is what keeps "everything" honest: a
    stage added to the sequence is in the whole run without anybody remembering to add it here.
    """

    if focus == REGISTRY_REBUILD_EVERYTHING:
        return REGISTRY_MAINTENANCE_STAGES
    return (focus,) if focus in REGISTRY_MAINTENANCE_STAGES else ()


def _project_repository_scan(scan: RepositoryScan) -> MaintainerRepositoryScanView:
    """Cross the I/O-to-view boundary once; renderers never receive the acquired snapshot."""

    return MaintainerRepositoryScanView(
        scan.url,
        scan.ref,
        scan.commit,
        scan.manifest_count,
        tuple(
            MaintainerRepositoryArtifactView(
                item.coordinate,
                item.kind,
                item.name,
                item.version,
                item.summary,
                item.manifest_path,
                item.state,
                item.payload_paths,
                item.adoptable,
                item.held_by,
            )
            for item in scan.artifacts
        ),
    )


def _project_adopted_artifact(artifact: AdoptedArtifact) -> MaintainerAdoptedArtifactView:
    return MaintainerAdoptedArtifactView(
        artifact.coordinate,
        artifact.url,
        artifact.ref,
        artifact.recorded_commit,
        artifact.manifest_path,
        artifact.input_digest,
    )


def _project_adoption_upstream(check: AdoptionUpstreamCheck) -> MaintainerAdoptionUpstreamView:
    return MaintainerAdoptionUpstreamView(
        _project_adopted_artifact(check.adopted),
        check.disposition.value,
        check.resolved_commit,
        check.observed_coordinate,
        check.proposal is not None,
        check.details,
    )


@dataclass(frozen=True, slots=True)
class ConsumerActionContext:
    """Everything one machine's actions are composed from, read once before the shell starts."""

    host: InstallationHost
    effective: EffectiveConfiguration
    machine: ConsumerMachine
    offers: ConsumerOffers = ConsumerOffers()
    settings: ConsumerSettings = ConsumerSettings()
    maintainer: MaintainerViews | None = None
    policy: EffectivePolicy = EffectivePolicy()
    credential_providers: tuple[CredentialProviderPort, ...] = ()
    offline: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.host, InstallationHost)
            or not isinstance(self.machine, ConsumerMachine)
            or not isinstance(self.offers, ConsumerOffers)
            or not isinstance(self.settings, ConsumerSettings)
            or not (self.maintainer is None or isinstance(self.maintainer, MaintainerViews))
            or not isinstance(self.policy, EffectivePolicy)
        ):
            raise ValueError("a consumer action context is invalid")


@dataclass(frozen=True, slots=True)
class _PendingInstall:
    prepared: PreparedConfiguredInstallation
    previous_receipts: tuple[tuple[ArtifactCoordinate, ArtifactReceipt], ...] = ()
    targets: tuple[HarnessTargetView, ...] = ()
    chosen_targets: tuple[str, ...] = ()
    chosen_pairs: tuple[str, ...] = ()
    chosen_pair_scopes: tuple[str, ...] = ()


def _assignments(
    pairs: tuple[str, ...], pair_scopes: tuple[str, ...], scope: Scope
) -> tuple[InstallationAssignment, ...]:
    """Screen 05's ticked pairs as the installations they become (§172.2).

    Each pair goes to the scope 07a put it on (§172.5); one 07a has not reached yet goes to
    `scope`, the scope the session prepares for.
    """

    chosen = dict(parsed for parsed in map(pair_scope_from_key, pair_scopes) if parsed is not None)
    return tuple(
        InstallationAssignment(
            artifact,
            harness,
            Scope(chosen.get(pair_key(artifact, harness), scope.value)),
        )
        for artifact, harness in (
            parsed for parsed in map(pair_from_key, pairs) if parsed is not None
        )
    )


def _kept_assignments(
    resolved: tuple[ArtifactCoordinate, ...],
    receipts: tuple[tuple[ArtifactCoordinate, ArtifactReceipt], ...],
) -> tuple[InstallationAssignment, ...]:
    """The installations an update replaces, as the pairs placement puts the new version into.

    An update replaces what is installed and adds nothing (§169.3, D-479). Left to the session's
    harnesses, the newer version of a Skill installed in one harness was placed into every harness
    the machine has. A receipt naming no owner records no harness to keep, so it contributes none.
    """

    by_artifact = {(item.source, item.artifact): str(item) for item in resolved}
    return tuple(
        dict.fromkeys(
            InstallationAssignment(
                by_artifact[(owner.source, owner.artifact)], owner.harness, owner.scope
            )
            for _, receipt in receipts
            if (owner := receipt.owner) is not None
            and (owner.source, owner.artifact) in by_artifact
        )
    )


def _per_artifact(views: tuple[InputView, ...], artifacts: dict[str, str]) -> tuple[InputView, ...]:
    """07's ordinary fields, one per artifact and input rather than one per installation (§172.4).

    `artifacts` maps each installation owner to its artifact's answer key. Secret rows are left
    per installation; asking them once per artifact is 07b's.
    """

    seen: set[str] = set()
    projected: list[InputView] = []
    for view in views:
        if isinstance(view, ConfigInputView) and view.owner in artifacts:
            view = replace(view, owner=artifacts[view.owner])
            if view.row in seen:
                continue
            seen.add(view.row)
        projected.append(view)
    return tuple(projected)


def _after_inputs(plan: ConsumerPlanView, *, default_path: bool = False) -> ConsumerScreen:
    """Where a reviewed install goes once its form was submitted (D-380, §161.5, §209).

    05 again only while the plan still offers a real choice of backend; otherwise 07b or Ready.
    07a was passed before the form (§209). The Default path has its backend from Settings
    (§173.7), so only the secrets are left.
    """

    if default_path:
        return ConsumerScreen.INSTALL_CREDENTIALS if secrets_to_ask(plan) else ConsumerScreen.READY
    if plan.installer_choice is not None and plan.installer_choice.is_a_choice:
        return ConsumerScreen.REVIEW_SELECTION
    if secrets_to_ask(plan):
        return ConsumerScreen.INSTALL_CREDENTIALS
    return ConsumerScreen.READY


def _installation_targets(
    prepared: PreparedConfiguredInstallation, profiles: tuple[str, ...]
) -> tuple[HarnessTargetView, ...]:
    """Project the draft's measured placement capability in host order.

    The draft is the authority even while inputs remain unanswered: each MCP registration target,
    tree delivery and managed merge names both its harness and its artifact. Policy, compatibility,
    platform and scope have already narrowed these placements (D-260).
    """

    hosted: dict[str, list[str]] = {profile: [] for profile in profiles}
    for placement in prepared.draft.placements:
        coordinate = str(placement.coordinate)
        harnesses = {item.harness for item in placement.targets}
        harnesses.update(item.harness for item in placement.deliveries)
        harnesses.update(item.harness for item in placement.merges)
        harnesses.update(item.harness for item in placement.settings)
        for profile in profiles:
            if profile in harnesses and coordinate not in hosted[profile]:
                hosted[profile].append(coordinate)
    return tuple(
        HarnessTargetView(profile, tuple(hosted[profile]))
        for profile in profiles
        if hosted[profile]
    )


def _grouped_targets(
    targets: tuple[HarnessTargetView, ...],
    groups: dict[str, tuple[str, ...]],
    profiles: tuple[str, ...],
) -> tuple[tuple[HarnessTargetView, ...], tuple[str, ...]]:
    """05's harnesses with each Collection standing as one artifact (§173.5, D-422).

    A harness is offered a Collection only when it hosts every member, and then the Collection
    replaces its members on that row; the members are never offered one by one. Each harness that
    cannot host a Collection is said to, naming the first member it cannot host.
    """

    if not groups:
        return targets, ()
    member_of = {member: key for key, members in groups.items() for member in members}
    hosted = {item.harness: item.artifacts for item in targets}
    grouped: list[HarnessTargetView] = []
    unhosted: list[str] = []
    for profile in profiles:
        artifacts = hosted.get(profile, ())
        row: list[str] = []
        for artifact in artifacts:
            key = member_of.get(artifact)
            if key is None:
                row.append(artifact)
            elif key not in row and all(member in artifacts for member in groups[key]):
                row.append(key)
        for key, members in groups.items():
            missing = next((member for member in members if member not in artifacts), None)
            if missing is not None:
                unhosted.append(f"{profile} is not offered for {key}: it cannot host {missing}.")
        if row:
            grouped.append(HarnessTargetView(profile, tuple(row)))
    return tuple(grouped), tuple(unhosted)


def _member_pairs(pairs: tuple[str, ...], groups: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """A Collection×harness choice as the member installations it applies to (§173.5)."""

    expanded: list[str] = []
    for pair in pairs:
        parsed = pair_from_key(pair)
        if parsed is None or parsed[0] not in groups:
            expanded.append(pair)
            continue
        expanded.extend(pair_key(member, parsed[1]) for member in groups[parsed[0]])
    return tuple(dict.fromkeys(expanded))


def _member_pair_scopes(
    pair_scopes: tuple[str, ...], groups: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """The scope chosen for a Collection and harness, given to every member there (§173.5)."""

    expanded: list[str] = []
    for chosen in pair_scopes:
        parsed = pair_scope_from_key(chosen)
        pair = None if parsed is None else pair_from_key(parsed[0])
        if parsed is None or pair is None or pair[0] not in groups:
            expanded.append(chosen)
            continue
        expanded.extend(
            pair_scope_key(pair_key(member, pair[1]), parsed[1]) for member in groups[pair[0]]
        )
    return tuple(expanded)


@dataclass(frozen=True, slots=True)
class _PendingRegistryAddition:
    draft: RegistryDraft
    source: ConfiguredSource
    review_digest: str


@dataclass(frozen=True, slots=True)
class _PendingRegistryRefresh:
    """One reviewed refresh of an already-connected registry (B-084).

    It holds only the alias, because that is the whole decision: a refresh changes no
    configuration and asks the origin the configured question again.
    """

    alias: str
    review_digest: str


@dataclass(frozen=True, slots=True)
class _PendingRegistryRemoval:
    """The complete Registry identity shown before its connection is removed."""

    source: ConfiguredSource
    review_digest: str


@dataclass(frozen=True, slots=True)
class _PendingCredentialAction:
    """One reviewed replacement or deletion: the plan, the provider it runs on, and its identity.

    The plan holds a reference and effects and no value (INV-056); the provider is the one whose
    observation the plan was made from, so confirmation cannot land on a different adapter.
    """

    plan: CredentialPlan
    provider: CredentialProviderPort
    review_digest: str
    guidance: tuple[CredentialGuidance, ...] = ()
    #: The length an artifact needing it declares, judged once the value is stored (§204).
    length: CredentialLength | None = None


class McpTestPort(Protocol):
    """The optional post-installation test (§170.4): which installations, what it calls, the run."""

    def installations(
        self,
        *,
        scope: Scope,
        root: str,
        harnesses: frozenset[str],
        coordinates: frozenset[str],
    ) -> tuple[InstalledRecord, ...]: ...

    def plan(self, records: tuple[InstalledRecord, ...]) -> tuple[SmokePlanEntry, ...]: ...

    def run(self, records: tuple[InstalledRecord, ...]) -> tuple[SmokeTargetResult, ...]: ...


@dataclass(frozen=True, slots=True)
class _AfterInstall:
    """A committed install as Success shows it, and the MCP installations it made.

    Kept so that the optional test can be offered, reviewed and answered without Success losing
    what it reports: the test is drawn beside the install, never in place of it (§170.4).
    """

    transaction: object
    pending_setup: tuple[DeclaredArtifactSetup, ...]
    records: tuple[InstalledRecord, ...]
    test: McpTestView | None


@dataclass(frozen=True, slots=True)
class _PendingMcpTest:
    records: tuple[InstalledRecord, ...]
    review_digest: str
    #: The test as it was asked for from Installed (D-395); `None` for the one after an install,
    #: which is drawn beside that install's Success instead.
    installed: McpTestView | None = None


#: Member statuses whose installation was made, so the test may be offered for it.
_INSTALLED_MEMBER = frozenset({"completed", "completed-with-attention"})


#: The credential intent each of screen 24's rows asks for (CP-23 task 12, D-262).
_CREDENTIAL_INTENTS: dict[ConsumerActionKind, CredentialIntent] = {
    ConsumerActionKind.CREDENTIAL_VERIFY: CredentialIntent.VERIFY,
    ConsumerActionKind.CREDENTIAL_SET: CredentialIntent.STORE,
    ConsumerActionKind.CREDENTIAL_REPLACE: CredentialIntent.REPLACE,
    ConsumerActionKind.CREDENTIAL_DELETE: CredentialIntent.DELETE,
}


@dataclass(frozen=True, slots=True)
class _PendingSourceAddition:
    draft: SourceDraft
    source: ConfiguredSource
    review_digest: str


@dataclass(frozen=True, slots=True)
class _PendingRegistryInit:
    """One reviewed run of init -> lock -> build -> validate -> audit (B-090)."""

    draft: RegistryInitDraft
    workspace: str
    review_digest: str


@dataclass(frozen=True, slots=True)
class _PendingRegistryRebuild:
    """One reviewed re-run of some or all of lock -> build -> validate -> audit (`B-099`)."""

    stages: tuple[str, ...]
    workspace: str
    review_digest: str


@dataclass(frozen=True, slots=True)
class _PendingRegistryPush:
    command: RegistryPublicationCommand
    root: str
    content_digest: str

    @property
    def review_digest(self):
        return self.command.review_digest


@dataclass(frozen=True, slots=True)
class RegistryConnectionSnapshot:
    """Configuration-derived views re-read after a subscription succeeds.

    Both subscriptions land here: connecting an approved registry (screen 21a) and connecting an
    upstream repository (screen 31a) change the same three derived things, so the value that carries
    them back is one value rather than two identical ones.
    """

    effective: EffectiveConfiguration
    offers: ConsumerOffers
    maintainer: MaintainerViews | None = None


@dataclass(frozen=True, slots=True)
class RegistryBootstrapCompletion:
    """What one bootstrap run established: the stages it ran, and what they changed here.

    The connection is separate and optional because the two are not the same claim.  The stages are
    what happened in the checkout; the snapshot is what this machine can now see, which only exists
    when the run got far enough for there to be a registry to re-read.
    """

    report: RegistryBootstrapReport
    connection: RegistryConnectionSnapshot | None = None


RegistryConnectionPort = Callable[[RegistryDraft], Result[RegistryConnectionSnapshot]]
RegistryRefreshPort = Callable[[str], Result[RegistryConnectionSnapshot]]
RegistryRemovalPort = Callable[[ConfiguredSource], Result[RegistryConnectionSnapshot]]
SourceConnectionPort = Callable[[SourceDraft], Result[RegistryConnectionSnapshot]]
RegistryBootstrapPort = Callable[[RegistryInitDraft], Result[RegistryBootstrapCompletion]]
RegistryRebuildPort = Callable[[tuple[str, ...]], Result[RegistryBootstrapCompletion]]
RegistryPublicationPort = Callable[
    [str, RegistryPublicationCommand], Result[RegistryPublicationReceipt]
]
RepositoryScanPort = Callable[[RepositoryScanDraft], Result[RepositoryScan]]
RepositoryUpstreamCheckPort = Callable[[str], Result[AdoptionUpstreamCheck]]
RepositoryAdoptedListPort = Callable[[], Result[tuple[AdoptedArtifact, ...]]]


class RepositoryAdoptionPort(Protocol):
    """The two halves of one reviewed adoption, already bound to a registry checkout."""

    def prepare(
        self,
        scan: RepositoryScan,
        selected: tuple[str, ...],
        renames: tuple[tuple[str, str], ...] = (),
    ) -> Result[PreparedAdoption]: ...

    def apply(self, prepared: PreparedAdoption, review_digest: str) -> Result[PreparedAdoption]: ...


#: What one reviewed-but-unconfirmed action is holding. Each carries the review digest the
#: confirmation has to name, so nothing runs against a plan nobody read.
_Pending = (
    _PendingInstall
    | PreparedConfiguredRepair
    | PreparedConfiguredUninstall
    | PreparedSourceSync
    | PreparedConfiguredCandidatePromotion
    | _PendingRegistryAddition
    | _PendingRegistryRefresh
    | _PendingRegistryRemoval
    | _PendingSourceAddition
    | _PendingRegistryInit
    | _PendingRegistryRebuild
    | _PendingRegistryPush
    | PreparedAdoption
    | _PendingCredentialAction
    | PreparedConfiguredConfiguration
    | _PendingMcpTest
)

#: The host is passed rather than closed over: setup describes the installation that just happened,
#: and it happened at whichever scope the review was prepared against.
ConfiguredCompletionFactory = Callable[
    [
        CompletedConfiguredInstallation,
        Literal["install", "update"],
        Callable[[tuple[DeclaredArtifactSetup, ...]], CanonicalScreenSource],
        InstallationHost,
    ],
    ConsumerActionCompletion | None,
]


class LocalConsumerActions:
    """One machine's install, update, verify-and-repair and uninstall, behind `handle`.

    The prepared action is held between the two commands rather than recomputed, because what is
    executed has to be the plan somebody reviewed. The digest is checked on the way in regardless:
    holding it is a convenience, and the confirmation is the authority.
    """

    #: Where to say a running plan has got to, while one is running. Bound by whoever draws, for
    #: the duration of one execution, and None the rest of the time -- a route with no screen (the
    #: CLI, a test) never asks for one and never pays for one. Declared on the class so that every
    #: instance has an answer, however it was constructed.
    _progress: Callable[[RunningInstallationView], None] | None = None

    def __init__(
        self,
        context: ConsumerActionContext,
        *,
        now=None,
        data_root: str | None = None,
        completion_factory: ConfiguredCompletionFactory | None = None,
        registry_connection: RegistryConnectionPort | None = None,
        registry_refresh: RegistryRefreshPort | None = None,
        registry_removal: RegistryRemovalPort | None = None,
        source_connection: SourceConnectionPort | None = None,
        registry_bootstrap: RegistryBootstrapPort | None = None,
        registry_rebuild: RegistryRebuildPort | None = None,
        registry_publication: RegistryPublicationPort = publish_registry_commit,
        repository_scan: RepositoryScanPort | None = None,
        repository_adoption: RepositoryAdoptionPort | None = None,
        adopted_artifacts: tuple[AdoptedArtifact, ...] = (),
        repository_upstream_check: RepositoryUpstreamCheckPort | None = None,
        repository_adopted_list: RepositoryAdoptedListPort | None = None,
        terminal_handover: TerminalHandover | None = None,
        mcp_test: McpTestPort | None = None,
        credential_entry: tuple[CredentialEntryFallback, ...] = (),
    ) -> None:
        if not isinstance(context, ConsumerActionContext):
            raise ValueError("consumer actions need a composed action context")
        self._context = context
        self._machine = context.machine
        self._now = now if now is not None else (lambda: datetime.now(timezone.utc))
        self._pending: _Pending | None = None
        #: Why 05 offers a harness no Collection of the prepared install (§173.5).
        self._unhosted: tuple[str, ...] = ()
        self._pending_action: ConsumerActionKind | None = None
        #: The machine the held action was prepared against, so a preference changed between the
        #: review and its confirmation cannot execute a project plan as a user install.
        self._pending_host: InstallationHost | None = None
        self._data_root = data_root
        self._completion_factory = completion_factory
        self._registry_connection = registry_connection
        self._registry_refresh = registry_refresh
        self._registry_removal = registry_removal
        self._source_connection = source_connection
        self._registry_bootstrap = registry_bootstrap
        self._registry_rebuild = registry_rebuild
        self._registry_publication = registry_publication
        self._repository_scan = repository_scan
        self._repository_adoption = repository_adoption
        self._adopted_artifacts = adopted_artifacts
        self._repository_upstream_check = repository_upstream_check
        self._repository_adopted_list = repository_adopted_list
        #: How the terminal adapter lends its screen to an effect that needs a person at the
        #: keyboard.  A credential prompt belongs to the provider, not to AART (161.8/161.9), and
        #: under the TUI it would otherwise be spoken over a drawn frame (`QA-081`).
        self._terminal_handover = terminal_handover
        #: Other ways to enter a credential when what the store's prompt kept is not it (§204).
        self._credential_entry = tuple(credential_entry)
        #: What the store's own prompt took on 07b for the review held now, by reference (§207).
        #: References only: no value of a credential is ever held in this process. They are
        #: deleted when that review is abandoned or its install fails.
        self._entered: dict[str, CredentialReference] = {}
        #: The command the held install review was prepared from, to prepare it again after 07b
        #: stored something, because the machine it measured has changed (§207).
        self._install_command: ConsumerUiCommand | None = None
        #: The plan 07b redraws after each choice; it says what is asked, never a value.
        self._pending_plan: ConsumerPlanView | None = None
        #: What each 07b row answers: the references it fills, what the artifact says about the
        #: credential, and the provider that will keep it. References and guidance only.
        self._secret_rows: dict[
            str, tuple[tuple[CredentialReference, ...], tuple[CredentialGuidance, ...], str]
        ] = {}
        self._scanned_repository: RepositoryScan | None = None
        self._adoption_review: MaintainerAdoptionReviewView | None = None
        self._adoption_upstream: AdoptionUpstreamCheck | None = None
        self._promotion_transaction: PreparedCandidatePromotionTransaction | None = None
        self._promotion_result: CandidatePromotionExecutionResult | None = None
        self._mcp_test = mcp_test
        self._after_install: _AfterInstall | None = None
        self._author_report: AuthorCheckReport | None = None

    def observe_progress(self, report: Callable[[RunningInstallationView], None] | None) -> None:
        """Take the screen's progress reporter for one execution, or give it back (None)."""

        self._progress = report

    # -- preferences --------------------------------------------------------- #

    @property
    def terminal_handover(self) -> TerminalHandover | None:
        """The screen loan this was composed with, for whoever draws the screen to bind (`QA-081`).

        Composition happens before any terminal exists, so the loan is handed over here inert and
        the adapter that draws claims it.  A route with no drawn screen never looks.
        """

        return self._terminal_handover

    @property
    def settings(self) -> ConsumerSettings:
        """What screen 28 was last told, which is what a session opens on."""

        return self._context.settings

    def _host(self, chosen: str = "") -> InstallationHost:
        """The machine as this operation addresses it: a chosen scope, else the preference.

        `chosen` is what one installation decided for itself on the way past (issue #11a, D-295).
        It is deliberately not written back to the preference: a one-off choice is an answer about
        this operation, not a new default, and silently rewriting Settings from it would make the
        preference mean whatever the last install happened to need.

        Screen 28 offers `Default scope: Project/User`, and until this read it was a preference the
        application drew and then ignored: composition fixed the host at project scope, so a User
        install landed in the project anyway. A preference that is displayed and not honoured is
        worse than one that was never offered, because the operator reads it as a statement about
        where their files went.

        Only the scope moves. `harness_root` follows from it, and everything else about this
        machine -- its state, its project checkout, its home, the harnesses it measured -- is the
        same machine either way. The registry a maintainer curates is addressed as
        `project_root` for that reason: it is the checkout this session was opened in, whatever
        scope installations are going to.
        """

        host = self._context.host
        if chosen not in ("", "project", "user"):
            raise ValueError("an installation scope must be project or user")
        named = chosen or self._context.settings.default_scope
        scope = Scope.USER if named == "user" else Scope.PROJECT
        return host if host.scope is scope else replace(host, scope=scope)

    def _installer_choice(
        self, prepared: PreparedConfiguredInstallation, preferred: PythonInstaller
    ) -> PythonInstallerChoiceView | None:
        """Which Python backends this prepared installation could be resolved by.

        The usable sets come back from the preparation that measured this machine, so the offer and
        the plan are the same measurement rather than two that can drift. `None` means the question
        does not arise: nothing in the selection declares Python dependencies (issue #11b).
        """

        offered = offer_python_installers(prepared.python_installers, preferred=preferred.value)
        return offered.value if isinstance(offered, Ok) else None

    def _scope_choice(self, plan: ConsumerPlanView, chosen: str) -> InstallScopeChoiceView | None:
        """Which scopes this selection may install into, seeded by the preference.

        The declared sets come from the Marketplace rows the composition is already holding, so
        this reads no index and touches no disk. A selection whose members share no scope, or an
        artifact this composition has no row for, yields `None`: the screen then offers nothing
        rather than an offer it cannot stand behind (issue #11a).
        """

        declared = {
            entry.row.key: entry.row.declared_scopes for entry in self._context.offers.artifacts
        }
        sets = tuple(declared[key] for key in plan.selection.resolved if key in declared)
        if len(sets) != len(plan.selection.resolved):
            return None
        offered = offer_install_scopes(
            sets,
            project_available=bool(self._context.host.project_root),
            preferred=chosen or self._context.settings.default_scope,
        )
        return offered.value if isinstance(offered, Ok) else None

    def _pair_scope_offers(
        self, pairs: tuple[str, ...], groups: dict[str, tuple[str, ...]] | None = None
    ) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Which scopes each ticked pair may go to on this machine (§172.5).

        A pair is offered what its artifact declares, less project when this session has no
        project to install into. An artifact this composition holds no row for is offered nothing,
        so 07a never claims a scope it cannot stand behind. A Collection is offered only the scopes
        every member declares (§173.5).
        """

        declared = {
            entry.row.key: entry.row.declared_scopes for entry in self._context.offers.artifacts
        }
        for key, members in (groups or {}).items():
            if all(member in declared for member in members):
                declared[key] = tuple(
                    scope
                    for scope in ("project", "user")
                    if all(scope in declared[member] for member in members)
                )
        project = bool(self._context.host.project_root)
        offers: list[tuple[str, tuple[str, ...]]] = []
        # Sorted, so 07a lists the installations in one order however 05 ticked them.
        for pair in sorted(pairs):
            parsed = pair_from_key(pair)
            if parsed is None or parsed[0] not in declared:
                continue
            offered = tuple(
                scope
                for scope in ("project", "user")
                if scope in declared[parsed[0]] and (project or scope != "project")
            )
            if offered:
                offers.append((pair, offered))
        return tuple(offers)

    def _reviewed_host(self) -> InstallationHost:
        """The machine the held review was prepared against, not the one preferences name now.

        What is executed has to be what somebody reviewed, and a scope toggled between the two
        would otherwise record a project plan as a user installation.
        """

        return self._pending_host if self._pending_host is not None else self._host()

    def save_settings(self, settings: ConsumerSettings) -> None:
        """Keep a changed preference, and keep drawing it, for the rest of this session too.

        A composition with no data root can still change a preference; it just cannot outlive the
        session, which is what a caller that supplied no place to write asked for.
        """

        self._context = replace(self._context, settings=settings)
        if self._data_root is None:
            return
        written = write_consumer_settings(settings, data_root=self._data_root)
        if isinstance(written, Err):
            raise ValueError(written.diagnostics[0].message)

    # -- what the shell draws ------------------------------------------------ #

    def source(
        self,
        *,
        plan=None,
        lifecycle: LifecyclePlanView | None = None,
        outcome=None,
        transaction=None,
        source_sync_review=None,
        source_sync_result=None,
        promotion_validation=None,
        promotion_commit=None,
        notice: tuple[str, ...] = (),
        pending_setup: tuple[DeclaredArtifactSetup, ...] = (),
        installation_inputs=(),
        install_targets: tuple[HarnessTargetView, ...] = (),
        mcp_test: McpTestView | None = None,
        install_scope_offers: tuple[str, ...] = (),
    ) -> CanonicalScreenSource:
        """The screens for the machine as it currently stands, plus whatever a flow is holding."""

        if promotion_commit is None and self._promotion_transaction is not None:
            promotion_commit = project_maintainer_registry_commit(
                self._promotion_transaction,
                result=self._promotion_result,
            )

        return CanonicalScreenSource(
            screens_from(
                self._machine,
                marketplace=self._context.offers.artifacts,
                collections=self._context.offers.collections,
                registries=self._context.offers.registries,
                settings=self._context.settings,
                maintainer=self._context.maintainer,
                plan=plan,
                lifecycle=lifecycle,
                outcome=outcome,
                transaction=transaction,
                source_sync_review=source_sync_review,
                source_sync_result=source_sync_result,
                promotion_validation=promotion_validation,
                promotion_commit=promotion_commit,
                notice=notice,
                pending_setup=pending_setup,
                repository_scan=(
                    None
                    if self._scanned_repository is None
                    else _project_repository_scan(self._scanned_repository)
                ),
                adoption_review=self._adoption_review,
                adopted_artifacts=tuple(
                    _project_adopted_artifact(item) for item in self._adopted_artifacts
                ),
                adoption_upstream=(
                    None
                    if self._adoption_upstream is None
                    else _project_adoption_upstream(self._adoption_upstream)
                ),
                installation_inputs=installation_inputs,
                install_targets=install_targets,
                install_unhosted=self._unhosted,
                mcp_test=mcp_test,
                harnesses=self._context.host.profiles,
                author_report=self._author_report,
                install_scope_offers=install_scope_offers,
                project_root=self._context.host.project_root,
            )
        )

    # -- the injected boundary ----------------------------------------------- #

    def handle(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if not isinstance(command, ConsumerUiCommand) or command.action is None:
            raise ValueError("a consumer action handler needs a typed action command")
        if command.kind is ConsumerUiCommandKind.RUN_AUTHOR:
            return self._run_author(command)
        if command.kind is ConsumerUiCommandKind.PREPARE_ACTION:
            return self._prepare(command)
        if command.kind is ConsumerUiCommandKind.EXECUTE_ACTION:
            return self._execute(command)
        if command.kind is ConsumerUiCommandKind.ASK_SECRET:
            return self._ask_secret(command)
        raise ValueError(f"{command.kind.value} is not a consumer action")

    def _run_author(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        def failed(diagnostics: tuple[Diagnostic, ...]) -> ConsumerActionUpdate:
            return ConsumerActionUpdate(
                self.source(notice=_refusal(diagnostics)),
                ConsumerUiEvent(ConsumerUiEventKind.ACTION_FAILED, action=command.action),
            )

        if not self.settings.author_mode or command.author_draft is None:
            return ConsumerActionUpdate(
                self.source(notice=("Enable Author Mode in Settings first.",)),
                ConsumerUiEvent(ConsumerUiEventKind.ACTION_FAILED, action=command.action),
            )
        draft = command.author_draft
        value = (
            draft.workspace
            if command.action is ConsumerActionKind.AUTHOR_WORKSPACE
            else self.settings.author_workspace
        )
        selected = select_workspace(value, application_home=self._data_root)
        if isinstance(selected, Err):
            if command.action is ConsumerActionKind.AUTHOR_CHECK:
                self._author_report = None
            return failed(selected.diagnostics)
        root = selected.value
        if command.action is ConsumerActionKind.AUTHOR_WORKSPACE:
            self.save_settings(replace(self.settings, author_workspace=root))
            self._author_report = None
            return ConsumerActionUpdate(
                self.source(notice=("Author workspace saved.",)),
                ConsumerUiEvent(
                    ConsumerUiEventKind.ACTION_RECORDED, action=command.action, text=root
                ),
            )
        focus = "checked"
        if command.action is ConsumerActionKind.AUTHOR_INIT:
            created = new_artifact(
                root,
                kind=draft.kind,
                name=draft.name,
                into=draft.into,
                application_home=self._data_root,
            )
            if isinstance(created, Err):
                return failed(created.diagnostics)
            focus = created.value
        elif command.action is not ConsumerActionKind.AUTHOR_CHECK:
            raise ValueError("unknown author operation")
        checked = check_workspace(root)
        if isinstance(checked, Err):
            self._author_report = None
            if command.action is ConsumerActionKind.AUTHOR_INIT:
                return ConsumerActionUpdate(
                    self.source(
                        notice=(
                            f"Wrote {focus}. Check could not read the workspace:",
                            *_refusal(checked.diagnostics),
                        )
                    ),
                    ConsumerUiEvent(
                        ConsumerUiEventKind.ACTION_RECORDED, action=command.action, text=focus
                    ),
                )
            return failed(checked.diagnostics)
        self._author_report = checked.value
        return ConsumerActionUpdate(
            self.source(),
            ConsumerUiEvent(ConsumerUiEventKind.ACTION_RECORDED, action=command.action, text=focus),
        )

    def discard_secrets(self) -> None:
        """Delete what 07b entered: the session left the review it was entered for (§207)."""

        self._forget_entered(tuple(self._entered))

    def _forget_entered(self, references: tuple[str, ...]) -> None:
        """Delete these items 07b stored, and stop holding them."""

        for raw in references:
            reference = self._entered.pop(raw, None)
            if reference is None:
                continue
            keeper = next(
                (
                    item
                    for item in self._context.credential_providers
                    if item.provider == reference.provider.provider
                ),
                None,
            )
            if keeper is not None:
                # A deletion that fails leaves an item Credentials and variables still lists, so
                # it can be deleted there; nothing here could say more about it.
                keeper.delete(reference)

    def _ask_secret(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Let the credential store take one 07b row's value now, then prepare the install again.

        Each installation the row reaches has its own item (D-334), so the store's own prompt asks
        once for each, on the lent terminal after its briefing, and the macOS dialog follows only
        when what the prompt kept is not the credential (§204). aart-cli never sees a value. An
        item somebody stored before this review is left alone. Storing changes the machine the
        review measured, so the install is prepared again from the same command, or its preflight
        would refuse it as changed after Review (§207).
        """

        row = command.focus
        pending = self._pending
        held = self._secret_rows.get(row)

        def refused(reason: tuple[str, ...]) -> ConsumerActionUpdate:
            return ConsumerActionUpdate(
                self.source(plan=self._pending_plan, notice=reason),
                ConsumerUiEvent(
                    ConsumerUiEventKind.SECRET_ASKED,
                    action=ConsumerActionKind.INSTALL,
                    key=row,
                    accepted=False,
                ),
            )

        if (
            held is None
            or not isinstance(pending, _PendingInstall)
            or pending.prepared.action is None
            or self._install_command is None
        ):
            return refused(_lines("this credential is not part of the reviewed install"))
        references = held[0]
        interpreters = interpreters_for(
            pending.prepared.action.installations,
            registry=ScopedHarnessRegistry(self._reviewed_host().scope_roots),
            credential_providers=self._context.credential_providers,
            interactive_credentials=True,
            credential_handover=self._terminal_handover,
            prompted_credentials=frozenset(str(reference) for reference in references),
            credential_entry=self._credential_entry,
        )
        if isinstance(interpreters, Err):
            return refused(_refusal(interpreters.diagnostics))
        keepers = tuple(
            item for item in interpreters.value if isinstance(item, CredentialEffectInterpreter)
        )
        why: tuple[str, ...] = ()
        for reference in references:
            raw, name = str(reference), reference.provider.provider
            keeper = next(
                (item for item in keepers if item.supports(StoreCredential(raw, name))), None
            )
            if keeper is None:
                why = _lines(f"nothing here can store {reference.input}")
                break
            if raw not in self._entered:
                before = keeper.provider.inspect(reference)
                if isinstance(before, Ok) and before.value.state is CredentialState.PRESENT:
                    continue
            replacing = raw in self._entered
            # Whatever the prompt leaves behind is this review's, to delete if it is abandoned.
            self._entered[raw] = reference
            applied = keeper.apply(
                ReplaceCredential(raw, name) if replacing else StoreCredential(raw, name)
            )
            if isinstance(applied, Err):
                why = _refusal(applied.diagnostics)
                break
            observed = keeper.provider.inspect(reference)
            unfit = (
                "nothing was stored"
                if not isinstance(observed, Ok)
                or observed.value.state is not CredentialState.PRESENT
                else keeper.unfit(raw, observed.value)
            )
            if unfit is not None:
                why = _lines(f"{reference.input} is not configured: {unfit}")
                break
        if why:
            # A row is stored whole or not at all: what it left is deleted, and 07b says why.
            self._forget_entered(tuple(str(reference) for reference in references))
            return refused(why)
        prepared = self._prepare_install(self._install_command)
        event = prepared.event
        if event.kind is not ConsumerUiEventKind.ACTION_PREPARED or not event.review_digest:
            self._forget_entered(tuple(str(reference) for reference in references))
            return ConsumerActionUpdate(
                prepared.source,
                ConsumerUiEvent(
                    ConsumerUiEventKind.SECRET_ASKED,
                    action=ConsumerActionKind.INSTALL,
                    key=row,
                    accepted=False,
                ),
            )
        return ConsumerActionUpdate(
            prepared.source,
            ConsumerUiEvent(
                ConsumerUiEventKind.SECRET_ASKED,
                action=ConsumerActionKind.INSTALL,
                key=row,
                accepted=True,
                semantic_identity=event.semantic_identity,
                selection_identity=event.selection_identity,
                review_digest=event.review_digest,
            ),
        )

    def _install_secrets(
        self, prepared: PreparedConfiguredInstallation
    ) -> tuple[InstallSecretView, ...]:
        """07b's rows: each secret input once per artifact, over every installation it reaches.

        A row is "Configured securely" when every installation already holds a value -- the
        provider says so; nothing is read back (§172.6).
        """

        grouped: dict[str, list[tuple[str, SecretInput, CredentialReference]]] = {}
        for owner, bound in prepared.draft.inputs.bound:
            for item in bound.inputs:
                if isinstance(item.input, SecretInput) and isinstance(
                    item.source, SecretProviderReference
                ):
                    row = f"{artifact_answer_key(owner)}\t{item.input.id.value}"
                    grouped.setdefault(row, []).append(
                        (str(owner), item.input, item.source.reference)
                    )
        views = []
        for row in sorted(grouped):
            members = grouped[row]
            references = tuple(dict.fromkeys(reference for _, _, reference in members))
            configured = True
            for reference in references:
                keeper = next(
                    (
                        item
                        for item in self._context.credential_providers
                        if item.provider == reference.provider.provider
                    ),
                    None,
                )
                observed = None if keeper is None else keeper.inspect(reference)
                if (
                    not isinstance(observed, Ok)
                    or observed.value.state is not CredentialState.PRESENT
                    # What 07b stored for this review is still its question, answered (§207).
                    or str(reference) in self._entered
                ):
                    configured = False
            first = members[0][1]
            label = first.guidance.label if first.guidance is not None else first.id.value
            guidance = gather_credential_guidance(
                first.id.value,
                ((name, declared.guidance) for name, declared, _ in members),
            )
            self._secret_rows[row] = (references, guidance, references[0].provider.provider)
            views.append(InstallSecretView(row, label, configured=configured))
        return tuple(views)

    # -- preparation --------------------------------------------------------- #

    def _declined(
        self, command: ConsumerUiCommand, notice: tuple[str, ...]
    ) -> ConsumerActionUpdate:
        """A refusal the reducer reads as "nothing was established", drawn where it was asked.

        The event carries no review digest, which is exactly what `_action_prepared` requires
        before it will move a session onto a plan -- so the screen keeps its previous content and
        gains the reason underneath it.
        """

        self._pending, self._pending_action = None, None
        return ConsumerActionUpdate(
            self.source(notice=notice),
            ConsumerUiEvent(ConsumerUiEventKind.ACTION_PREPARED, action=command.action),
        )

    def _default_path_unfit(
        self, command: ConsumerUiCommand, unfit: tuple[DefaultPathMismatch, ...]
    ) -> ConsumerActionUpdate:
        """§176: Default does not fit Settings, so nothing is pending and 05p says why."""

        self._pending, self._pending_action = None, None
        return ConsumerActionUpdate(
            self.source(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                default_path_mismatches=unfit,
            ),
        )

    def _prepare(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        self._pending, self._pending_action = None, None
        action = command.action
        if action is ConsumerActionKind.INSTALL:
            return self._prepare_install(command)
        if action is ConsumerActionKind.REGISTRY_ADD:
            return self._prepare_registry_addition(command)
        if action is ConsumerActionKind.SOURCE_ADD:
            return self._prepare_source_addition(command)
        if action is ConsumerActionKind.REGISTRY_INIT:
            return self._prepare_registry_init(command)
        if action is ConsumerActionKind.REGISTRY_REBUILD:
            return self._prepare_registry_rebuild(command)
        if action is ConsumerActionKind.REGISTRY_PUSH:
            return self._prepare_registry_push(command)
        if action is ConsumerActionKind.REPOSITORY_SCAN:
            return self._prepare_repository_scan(command)
        if action is ConsumerActionKind.REPOSITORY_ADOPT:
            return self._prepare_repository_adoption(command)
        if action is ConsumerActionKind.REPOSITORY_UPSTREAM_CHECK:
            return self._prepare_repository_upstream_check(command)
        if action is ConsumerActionKind.REPOSITORY_ADOPT_UPDATE:
            return self._prepare_repository_adoption_update(command)
        if action is ConsumerActionKind.UPDATE:
            return self._prepare_update(command)
        if action is ConsumerActionKind.CONFIGURE:
            return self._prepare_configuration(command)
        if action is ConsumerActionKind.VERIFY_REPAIR:
            return self._prepare_repair(command)
        if action is ConsumerActionKind.REGISTRY_SYNC:
            return self._prepare_registry_refresh(command)
        if action is ConsumerActionKind.REGISTRY_REMOVE:
            return self._prepare_registry_removal(command)
        if action is ConsumerActionKind.SOURCE_REMOVE:
            return self._prepare_source_removal(command)
        if action is ConsumerActionKind.SOURCE_SYNC:
            return self._prepare_source_sync(command)
        if action is ConsumerActionKind.CANDIDATE_PROMOTION:
            return self._prepare_candidate_promotion(command)
        if action is ConsumerActionKind.BULK_PROMOTION:
            return self._prepare_bulk_promotion(command)
        if action is ConsumerActionKind.COLLECTION_DEFINE:
            return self._prepare_collection_definition(command)
        if action in _CREDENTIAL_INTENTS:
            return self._prepare_credential_action(command)
        if action is ConsumerActionKind.MCP_TEST:
            return self._prepare_mcp_test(command)
        return self._prepare_uninstall(command)

    def _prepare_registry_push(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Re-read screen 46's exact workspace and bind its eligible commit to one target."""

        root = self._context.host.project_root
        workspace = read_registry_workspace(root) if root else None
        if workspace is None:
            return self._declined(
                command, _lines("Push requires the canonical Registry worktree root")
            )
        if not workspace.push_ready:
            return self._declined(command, _lines(*workspace.push_blockers))
        if (
            workspace.root is None
            or workspace.revision is None
            or workspace.content_digest is None
            or workspace.publication_review_digest is None
        ):
            return self._declined(command, _lines("Push has no exact reviewed Registry state"))
        digest = parse_sha256(workspace.publication_review_digest)
        if isinstance(digest, Err):
            return self._declined(command, _refusal(digest.diagnostics))
        # A checkout already on a branch of its own pushes that branch; one standing where
        # subscribers read pushes the reviewed name instead. `needs_a_new_branch` is the same
        # question screen 46j asked, so the answer cannot drift between the review and the push.
        branch = (
            workspace.branch
            if not workspace.needs_a_new_branch and workspace.branch is not None
            else (
                command.publication_branch or command.suggested_branch or workspace.suggested_branch
            )
        )
        current_is_target = not workspace.needs_a_new_branch
        if current_is_target and command.publication_branch not in {"", workspace.branch}:
            return self._declined(
                command,
                _lines(f"this Registry commit belongs to its current branch {workspace.branch}"),
            )
        prepared = prepare_registry_publication(
            registry=SourceAlias(workspace.name),
            remote=workspace.remote,
            default_branch=workspace.default_branch,
            requested_branch=branch,
            revision=workspace.revision,
            review_digest=digest.value,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        self._pending = _PendingRegistryPush(
            prepared.value, workspace.root, workspace.content_digest
        )
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                text=branch,
                review_digest=str(prepared.value.review_digest),
            ),
        )

    def _prepare_credential_action(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Plan one credential action against what the provider says now (CP-23 task 12, D-262).

        The observation and its dependants are read live rather than taken from the drawn list:
        that list is as old as the session, and the plan has to be about the reference as it stands
        and about every installation that uses it (INV-057). Planning is
        `plan_credential_mutation`, so policy, provider availability and the in-use deletion rule
        are the lifecycle's own. Verify is answered here -- asking the provider is all it is -- so
        it leaves nothing pending.
        """

        assert command.action is not None
        intent = _CREDENTIAL_INTENTS[command.action]
        host = self._host()
        providers = self._context.credential_providers
        inspected = read_installed_inspections(
            state_root=host.state_root,
            harness_root=host.harness_root,
            credential_providers=providers,
        )
        if isinstance(inspected, Err):
            return self._declined(command, _refusal(inspected.diagnostics))
        observation = next(
            (item for item in inspected.value.credentials if str(item.reference) == command.focus),
            None,
        )
        if observation is None:
            return self._declined(
                command, _lines(f"nothing installed here uses the credential {command.focus}")
            )
        named = observation.reference.provider.provider
        provider = next((item for item in providers if item.provider == named), None)
        if provider is None:
            return self._declined(
                command, _lines(f"nothing here can reach the credential provider {named}")
            )
        dependants = tuple(
            item.record.coordinate
            for item in inspected.value.inspections
            if observation.reference in item.record.credential_references
        )
        planned = plan_credential_mutation(
            intent,
            observation,
            dependants,
            policy=self._context.policy,
            # The review names every dependant before a replacement can be confirmed, so the
            # confirmation is the acknowledgement. A deletion is never acknowledged from here,
            # which is what keeps a credential something uses from being removed (INV-057).
            acknowledged_dependants=dependants if intent is CredentialIntent.REPLACE else (),
        )
        if isinstance(planned, Err):
            return self._declined(command, _refusal(planned.diagnostics))
        identity = json.dumps(
            credential_plan_to_data(planned.value), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        review_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        if intent is CredentialIntent.VERIFY:
            refreshed = self._reread_machine(host)
            if refreshed:
                return self._declined(command, refreshed)
        else:
            declared: list[tuple[str, InputGuidance | None]] = []
            lengths: list[CredentialLength] = []
            for installation in inspected.value.inspections:
                if observation.reference not in installation.record.credential_references:
                    continue
                inputs = self._installed_inputs(installation.record)
                if isinstance(inputs, Err):
                    continue
                needing = tuple(
                    item
                    for item in inputs.value
                    if isinstance(item, SecretInput) and item.id == observation.reference.input
                )
                declared.extend(
                    (str(installation.record.coordinate), item.guidance) for item in needing
                )
                lengths.extend(item.validation for item in needing if item.validation is not None)
            guidance = gather_credential_guidance(
                observation.reference.input.value,
                declared,
            )
            self._pending = _PendingCredentialAction(
                planned.value,
                provider,
                review_digest,
                guidance,
                lengths[0] if lengths else None,
            )
            self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _reread_machine(self, host: InstallationHost) -> tuple[str, ...]:
        """Draw the machine as it is now; what stopped the read, or nothing when it worked."""

        machine = read_consumer_machine(
            state_root=host.state_root,
            harness_root=host.harness_root,
            today=self._now().date(),
            project_root=host.project_root,
            user_home=host.user_home,
            data_root=host.data_root,
            credential_providers=self._context.credential_providers,
        )
        if isinstance(machine, Err):
            return _refusal(machine.diagnostics)
        self._machine = machine.value
        return ()

    def _prepare_repository_scan(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        draft = command.repository_scan_draft
        if draft is None or self._repository_scan is None:
            return self._declined(command, _lines("repository scan is unavailable"))
        scanned = self._repository_scan(draft)
        if isinstance(scanned, Err):
            return self._declined(command, _refusal(scanned.diagnostics))
        self._scanned_repository = scanned.value
        self._adoption_review = None
        identity = json.dumps(
            {
                "url": scanned.value.url,
                "ref": scanned.value.ref,
                "commit": scanned.value.commit,
                "artifacts": [item.coordinate for item in scanned.value.artifacts],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        scan_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        return ConsumerActionUpdate(
            self.source(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=scan_digest,
            ),
        )

    def _prepare_repository_adoption(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if self._scanned_repository is None or self._repository_adoption is None:
            return self._declined(
                command,
                _lines("scan a repository before choosing artifacts to adopt"),
            )
        # Typed against the scanned coordinate; adoption names the artifact by kind/name (INV-279).
        scanned = {
            item.coordinate: f"{item.kind}/{item.name}"
            for item in self._scanned_repository.artifacts
        }
        prepared = self._repository_adoption.prepare(
            self._scanned_repository,
            command.selection,
            tuple(
                (scanned[coordinate], name)
                for coordinate, name in command.adoption_names
                if coordinate in scanned
            ),
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        self._pending = prepared.value
        self._pending_action = command.action
        self._adoption_review = MaintainerAdoptionReviewView(
            prepared.value.url,
            prepared.value.commit,
            prepared.value.selected,
            prepared.value.changed_paths,
            prepared.value.review_digest,
        )
        return ConsumerActionUpdate(
            self.source(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=prepared.value.review_digest,
            ),
        )

    def _prepare_repository_upstream_check(
        self, command: ConsumerUiCommand
    ) -> ConsumerActionUpdate:
        if self._repository_upstream_check is None:
            return self._declined(command, _lines("upstream checking is unavailable"))
        checked = self._repository_upstream_check(command.focus)
        if isinstance(checked, Err):
            return self._declined(command, _refusal(checked.diagnostics))
        self._adoption_upstream = checked.value
        identity = json.dumps(
            {
                "coordinate": checked.value.adopted.coordinate,
                "disposition": checked.value.disposition.value,
                "recorded_commit": checked.value.recorded_commit,
                "resolved_commit": checked.value.resolved_commit,
                "observed_coordinate": checked.value.observed_coordinate,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        check_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        return ConsumerActionUpdate(
            self.source(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=check_digest,
            ),
        )

    def _prepare_repository_adoption_update(
        self, command: ConsumerUiCommand
    ) -> ConsumerActionUpdate:
        check = self._adoption_upstream
        if check is None or check.adopted.coordinate != command.focus or check.proposal is None:
            return self._declined(
                command,
                _lines("this upstream check has no new version ready to review"),
            )
        prepared = check.proposal
        self._pending = prepared
        self._pending_action = command.action
        self._adoption_review = MaintainerAdoptionReviewView(
            prepared.url,
            prepared.commit,
            prepared.selected,
            prepared.changed_paths,
            prepared.review_digest,
        )
        return ConsumerActionUpdate(
            self.source(),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=prepared.review_digest,
            ),
        )

    def _prepare_registry_addition(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        draft = command.registry_draft
        if draft is None or self._registry_connection is None:
            return self._declined(command, _lines("registry connection is unavailable"))
        if draft.kind not in REGISTRY_SOURCE_KINDS:
            return self._declined(command, _lines(f"{draft.kind} is not a registry transport"))
        parsed = configured_source_from_input(
            draft.alias,
            SourceKind(draft.kind),
            draft.location,
            draft.ref or None,
        )
        if isinstance(parsed, Err):
            return self._declined(command, _refusal(parsed.diagnostics))
        identity = json.dumps(
            {
                "alias": parsed.value.alias.value,
                "kind": parsed.value.kind.value,
                "location": parsed.value.location,
                "ref": parsed.value.ref,
                "make_default": draft.make_default,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        review_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        self._pending = _PendingRegistryAddition(draft, parsed.value, review_digest)
        self._pending_action = command.action
        default = "yes" if draft.make_default else "no"
        return ConsumerActionUpdate(
            self.source(
                notice=(
                    "Registry connection review:",
                    f"  alias: {parsed.value.alias.value}",
                    f"  repository path: {parsed.value.location}"
                    if parsed.value.is_local_checkout
                    else f"  URL: {parsed.value.location}",
                    f"  branch: {parsed.value.ref}"
                    if parsed.value.is_local_checkout
                    else f"  branch or tag: {parsed.value.ref}",
                    f"  make default: {default}",
                    "  next: read and validate a fresh snapshot of that branch, then save the "
                    "subscription"
                    if parsed.value.is_local_checkout
                    else "  next: download and validate a fresh snapshot, then save the "
                    "subscription",
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _prepare_source_addition(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Review one upstream repository subscription: screen 31a's confirmable value (B-083).

        The kind is checked here rather than only in the schema because this form's *purpose* is
        the 164.2 boundary: an approved registry is screen 21a's subject, and a Maintainer form
        that quietly accepted `registry-git` would be the widening B-083 says must not happen.
        """

        draft = command.source_draft
        if draft is None or self._source_connection is None:
            return self._declined(command, _lines("Upstream connection is unavailable"))
        if draft.kind not in AUTHORING_SOURCE_KINDS:
            return self._declined(
                command,
                _lines(
                    f"{draft.kind} is not an upstream repository kind",
                    "choose git or local; an approved registry is connected in Registries",
                ),
            )
        kind = SourceKind(draft.kind)
        parsed = configured_source_from_input(
            draft.alias,
            kind,
            draft.location,
            (draft.ref or None) if kind is SourceKind.SOURCE_GIT else None,
        )
        if isinstance(parsed, Err):
            return self._declined(command, _refusal(parsed.diagnostics))
        identity = json.dumps(
            {
                "alias": parsed.value.alias.value,
                "kind": parsed.value.kind.value,
                "location": parsed.value.location,
                "ref": parsed.value.ref,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        review_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        self._pending = _PendingSourceAddition(draft, parsed.value, review_digest)
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(
                notice=(
                    "Upstream connection review:",
                    f"  alias: {parsed.value.alias.value}",
                    f"  kind: {parsed.value.kind.value.removeprefix('source-')}",
                    f"  location: {parsed.value.location}",
                    f"  branch or tag: {parsed.value.ref or 'not applicable'}",
                    "  next: acquire a pinned snapshot, discover declared aart-cli.yaml/aart-cli.json "
                    "manifests, then save the subscription",
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _prepare_registry_init(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Review creating this project's registry: what it will be, and what it will not do.

        The review names all five stages because they are one decision rather than five: the
        operator is agreeing to a registry existing here, not to `init` in isolation. It also
        states the two things the run will never do, since a maintainer reading a screen has no
        other way to know that confirming it cannot publish anything (B-090).
        """

        if command.registry_init_draft is None or self._registry_bootstrap is None:
            return self._declined(command, _lines("registry initialization is unavailable"))
        # `QA-058`: judged, reviewed, digested and run as the operator named it, without the
        # spaces a `[Space] Toggle` press leaves in a text row.
        draft = command.registry_init_draft.settled()
        refused = registry_identity_refusal(
            registry_id=draft.registry_id,
            display_name=draft.display_name,
        )
        if refused is not None:
            return self._declined(command, _refusal(refused.diagnostics))
        workspace = self._context.host.project_root
        identity = json.dumps(
            {
                "workspace": workspace,
                "registry_id": draft.registry_id,
                "display_name": draft.display_name,
                "commit": draft.commit,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        review_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        self._pending = _PendingRegistryInit(draft, workspace, review_digest)
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(
                notice=(
                    "Registry initialization review:",
                    f"  project: {workspace}",
                    f"  registry ID: {draft.registry_id}",
                    f"  display name: {draft.display_name}",
                    f"  local commit: {'yes' if draft.commit else 'no'}",
                    "  next: init writes the registry skeleton, lock pins what it references,",
                    "        build writes its index, then validate and audit check the result",
                    "  nothing is pushed and nothing is merged: publishing this registry stays a "
                    "decision you make in the repository",
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _prepare_registry_rebuild(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Review re-running the generated files of the registry that is already here (`B-099`).

        The stages are named because they are the plan: confirming "everything" and confirming
        "validate" are two different runs over the same checkout, and a review that said only
        "rebuild" would let one be confirmed into the other (`D-069`).
        """

        if self._registry_rebuild is None:
            return self._declined(command, _lines("registry rebuilding is unavailable"))
        stages = _rebuild_stages(command.focus)
        if not stages:
            return self._declined(
                command,
                _lines("a rebuild runs the whole sequence or one of its stages"),
            )
        workspace = self._context.host.project_root
        absent = registry_absent_refusal(workspace)
        if absent is not None:
            return self._declined(command, _refusal(absent.diagnostics))
        identity = json.dumps(
            {"workspace": workspace, "stages": list(stages)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        review_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        self._pending = _PendingRegistryRebuild(stages, workspace, review_digest)
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(
                notice=(
                    "Registry rebuild review:",
                    f"  registry: {workspace}",
                    f"  stages: {', '.join(stages)}",
                    *(f"    {stage} will {REGISTRY_STAGE_PURPOSE[stage]}" for stage in stages),
                    "  nothing is pushed and nothing is merged: what this writes is reviewed in "
                    "the repository like any other change",
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _prepare_candidate_promotion(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if self._data_root is None:
            return self._declined(
                command,
                _lines("Candidate promotion needs the configured durable data root"),
            )
        row = parse_validation_row(command.focus)
        raw_id = command.focus if row is None else row.candidate_id
        if not raw_id or command.content_mode is None:
            return self._declined(
                command,
                _lines("Candidate promotion needs one focused Candidate and content mode"),
            )
        try:
            candidate_id = CandidateId(raw_id)
        except ValueError as error:
            return self._declined(command, _lines(str(error)))
        prepared = prepare_configured_candidate_promotion(
            self._context.effective,
            candidate_id,
            data_root=self._data_root,
            registry_root=self._context.host.project_root,
            policy=self._context.policy,
            mode=command.content_mode,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        shown = (
            None
            if self._context.maintainer is None
            else self._context.maintainer.registry_diff(raw_id, command.content_mode)
        )
        if (
            shown is None
            or shown.plan_digest is None
            or shown.plan_digest != str(prepared.value.review_digest)
        ):
            return self._declined(
                command,
                _lines("the Registry change differs from the one reviewed; review it again"),
            )
        self._pending = prepared.value
        self._pending_action = command.action
        transaction = prepared.value.transaction
        self._promotion_transaction = transaction
        self._promotion_result = None
        return ConsumerActionUpdate(
            self.source(
                promotion_validation=project_maintainer_registry_validation(transaction),
                promotion_commit=project_maintainer_registry_commit(transaction),
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=str(prepared.value.review_digest),
            ),
        )

    def _prepare_bulk_promotion(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if self._data_root is None:
            return self._declined(
                command,
                _lines("bulk promotion needs the configured durable data root"),
            )
        if not command.selection or command.content_mode is None:
            return self._declined(
                command,
                _lines("bulk promotion needs a selection and a content mode"),
            )
        try:
            selected = tuple(CandidateId(item) for item in command.selection)
        except ValueError as error:
            return self._declined(command, _lines(str(error)))
        prepared = prepare_configured_bulk_promotion(
            self._context.effective,
            selected,
            data_root=self._data_root,
            registry_root=self._context.host.project_root,
            policy=self._context.policy,
            mode=command.content_mode,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        # Screen 47 offered the selection; what is promoted must still be exactly what it offered,
        # so the prepared set is checked against the composed selectable set rather than assumed.
        offered = (
            None
            if self._context.maintainer is None
            else self._context.maintainer.bulk_promotion(
                prepared.value.transaction.target_registry.value
            )
        )
        if offered is None or not set(command.selection) <= {
            item.candidate_id for item in offered.candidates
        }:
            return self._declined(
                command,
                _lines("the selection changed after Bulk Promotion showed it; review it again"),
            )
        self._pending = prepared.value
        self._pending_action = command.action
        transaction = prepared.value.transaction
        self._promotion_transaction = transaction
        self._promotion_result = None
        return ConsumerActionUpdate(
            self.source(
                promotion_validation=project_maintainer_registry_validation(transaction),
                promotion_commit=project_maintainer_registry_commit(transaction),
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=str(prepared.value.review_digest),
            ),
        )

    def _prepare_collection_definition(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Screen 52's Collection version, prepared as the transaction 44 and 45 review (D-430)."""

        if self._data_root is None:
            return self._declined(
                command, _lines("a Collection needs the configured durable data root")
            )
        opened = parse_collection_row(command.focus)
        draft = command.collection_draft
        if opened is None or draft is None:
            return self._declined(
                command, _lines("a Collection is defined in the Collection Editor")
            )
        alias, existing = opened
        name = existing if existing is not None else draft.name.strip()
        if not name:
            return self._declined(command, _lines("a new Collection needs a name"))
        summary = draft.summary.strip()
        if not command.selection:
            return self._declined(command, _lines(f"Collection {name} needs at least one member"))
        members: list[ArtifactIdentity] = []
        for row in command.selection:
            kind, _, member = row.partition("/")
            try:
                members.append(ArtifactIdentity(kind, member))  # type: ignore[arg-type]
            except ValueError as error:
                return self._declined(command, _lines(str(error)))
        prepared = prepare_configured_collection(
            self._context.effective,
            SourceAlias(alias),
            name=name,
            summary=summary or None,
            members=tuple(members),
            data_root=self._data_root,
            registry_root=self._context.host.project_root,
            policy=self._context.policy,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        self._pending = prepared.value
        self._pending_action = command.action
        transaction = prepared.value.transaction
        self._promotion_transaction = transaction
        self._promotion_result = None
        return ConsumerActionUpdate(
            self.source(
                promotion_validation=project_maintainer_registry_validation(transaction),
                promotion_commit=project_maintainer_registry_commit(transaction),
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=str(prepared.value.review_digest),
            ),
        )

    def _prepare_source_sync(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if self._data_root is None:
            return self._declined(
                command,
                _lines("Upstream sync needs the configured durable data root"),
            )
        if not command.focus:
            return self._declined(
                command, _lines("Upstream sync needs one focused upstream repository")
            )
        prepared = prepare_configured_source_sync(
            self._context.effective,
            SourceAlias(command.focus),
            data_root=self._data_root,
            observed_at_epoch_seconds=int(self._now().timestamp()),
            offline=self._context.offline,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        self._pending = prepared.value
        self._pending_action = command.action
        review = project_source_sync_review(prepared.value)
        return ConsumerActionUpdate(
            self.source(source_sync_review=review),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review.review_digest,
            ),
        )

    def _targets(self, command: ConsumerUiCommand) -> tuple[str, ...]:
        """What this command is about: what was ticked, or the row it was requested from."""

        return command.selection or ((command.focus,) if command.focus else ())

    def _offered(self, keys: tuple[str, ...]) -> Result[tuple[MarketplaceEntry, ...]]:
        entries = []
        for key in keys:
            entry = next((item for item in self._context.offers.artifacts if item.key == key), None)
            if entry is None:
                return Err(
                    (
                        Diagnostic(
                            CONSUMER_ACTION_NOT_OFFERED,
                            Severity.ERROR,
                            f"nothing offered here is {key}",
                            remediation=("re-open the Marketplace and choose an offered version",),
                        ),
                    )
                )
            entries.append(entry)
        return Ok(tuple(entries))

    def _prepare_install(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        self._install_command = command
        keys = self._targets(command)
        if not keys:
            return self._declined(command, _lines("nothing is selected to install"))
        # A Collection with every member ticked is installed as the Collection (D-422); untick one
        # and what remains is a custom selection of artifacts (§161.4).
        collections = {item.key: item for item in self._context.offers.collections}
        # The focus is the Collection while its preview is open; a later screen re-prepares with
        # its own row focused, and then the pairs 05 chose for the Collection still name it.
        named = (parsed[0] for parsed in map(pair_from_key, command.pairs) if parsed is not None)
        focused = collections.get(command.focus) or next(
            (collections[key] for key in named if key in collections), None
        )
        if focused is not None and set(keys) == set(focused.members):
            keys = (focused.key,)
        chosen = tuple(collections[key] for key in keys if key in collections)
        offered = self._offered(tuple(key for key in keys if key not in collections))
        if isinstance(offered, Err):
            return self._declined(command, _refusal(offered.diagnostics))
        try:
            selection = ArtifactSelection(
                tuple(
                    ArtifactRequest(
                        entry.row.identity,
                        VersionConstraint(entry.row.version),
                        entry.row.source_alias,
                    )
                    for entry in offered.value
                ),
                tuple(item.collection.coordinate for item in chosen),
            )
        except ValueError as error:
            return self._declined(command, _lines(f"this selection cannot be installed: {error}"))
        return self._offer_installation(
            command, selection, groups={item.key: item.members for item in chosen}
        )

    def _prepare_update(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        coordinates = self._targets(command)
        if not coordinates:
            return self._declined(command, _lines("nothing is selected to update"))
        inspected = self._inspections(coordinates)
        if isinstance(inspected, Err):
            return self._declined(command, _refusal(inspected.diagnostics))
        installed = inspected.value
        try:
            selection = ArtifactSelection(
                tuple(
                    ArtifactRequest(
                        item.record.coordinate.artifact,
                        VersionConstraint("*"),
                        item.record.coordinate.source,
                    )
                    for item in installed
                )
            )
        except ValueError as error:
            return self._declined(command, _lines(f"this selection cannot be updated: {error}"))
        # What an update replaces is what is installed, measured against the receipt that version
        # wrote. The version is dropped from the previous coordinate for the same reason the
        # public command drops it: the state being left is this artifact's, whatever it was on.
        previous = tuple(
            (replace(item.record.coordinate, version=None), item.desired) for item in installed
        )
        return self._offer_installation(
            command,
            selection,
            previous=previous,
            previous_receipts=tuple(
                (item.record.coordinate, item.record.receipt) for item in installed
            ),
        )

    def _offer_installation(
        self,
        command: ConsumerUiCommand,
        selection: ArtifactSelection,
        *,
        previous: tuple[tuple[ArtifactCoordinate, DesiredState], ...] = (),
        previous_receipts: tuple[tuple[ArtifactCoordinate, ArtifactReceipt], ...] = (),
        groups: dict[str, tuple[str, ...]] | None = None,
    ) -> ConsumerActionUpdate:
        context = self._context
        groups = groups or {}
        if command.action is ConsumerActionKind.INSTALL:
            # A new review is a new set of questions. What 07b entered stays held: it is deleted
            # when the session leaves the screens of this review (§207).
            self._secret_rows = {}
        host = self._host(command.install_scope)
        preferred = PythonInstaller(command.python_installer or context.settings.python_installer)
        # Until screen 05 has been answered there are no pairs, and placement measures every harness.
        assignments: tuple[InstallationAssignment, ...] = ()
        # Every installation this selection would create has to be known before an answer can be
        # addressed to one (D-353), and only placement knows which harnesses an artifact reaches.
        # The draft is therefore built once with nothing answered. Each owner-qualified screen row
        # then resolves to exactly that field; an answer is never broadcast to another installation.
        prepared = prepare_configured_installation(
            context.effective,
            selection,
            host=host,
            sources=(),
            policy=context.policy,
            selected_remediations=None,
            credential_providers=context.credential_providers,
            resolvers=context.credential_providers,
            # For an update this draft only resolves the versions. What it replaces is matched
            # once the installations it replaces are placed below, not against the session's scope.
            previous=() if previous_receipts else previous,
            preferred_installer=preferred,
            assignments=assignments,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        if previous_receipts:
            # An update goes into exactly the installations it replaces, each at its own scope and
            # root, and into no harness that did not have it (§169.3, D-479).
            assignments = _kept_assignments(
                tuple(item.version.coordinate for item in prepared.value.draft.selection.artifacts),
                previous_receipts,
            )
            if not assignments:
                return self._declined(
                    command,
                    _lines(
                        "this installation does not record which harness it is",
                        "uninstall it and install it again",
                    ),
                )
            host = replace(
                host, profiles=tuple(dict.fromkeys(item.harness for item in assignments))
            )
            prepared = prepare_configured_installation(
                context.effective,
                selection,
                host=host,
                sources=(),
                policy=context.policy,
                selected_remediations=None,
                credential_providers=context.credential_providers,
                resolvers=context.credential_providers,
                previous=previous,
                preferred_installer=preferred,
                assignments=assignments,
            )
            if isinstance(prepared, Err):
                return self._declined(command, _refusal(prepared.diagnostics))
        # Eligibility is measured over every profile, before anything is narrowed: it is what the
        # harness rows offer, and a choice is judged against it rather than against itself.
        targets = (
            _installation_targets(prepared.value, host.profiles)
            if command.action is ConsumerActionKind.INSTALL
            else ()
        )
        targets, self._unhosted = _grouped_targets(targets, groups, host.profiles)
        # §172.2: until 05 is answered, an artifact only one harness can host has it ticked.
        # §173.7: the Default path takes its harnesses from Settings rather than from 05.
        pairs = command.pairs or (
            settings_pairs(targets, context.settings.default_harnesses)
            if command.default_path
            else default_pairs(targets)
            if not command.targets
            else ()
        )
        chosen_targets = command.targets or pairs_harnesses(pairs)
        # §172.5: each pair starts on the Settings scope when it may go there and keeps what 07a
        # chose for it; a pair no longer ticked has no scope to keep.
        scope_offers = self._pair_scope_offers(pairs, groups)
        pair_scopes = default_pair_scopes(
            scope_offers,
            command.install_scope or context.settings.default_scope,
            command.pair_scopes,
        )
        if command.default_path:
            # §176: Default applies Settings or says which value does not fit; it never narrows.
            unfit = default_path_mismatches(
                targets,
                detected=context.host.profiles,
                harnesses=context.settings.default_harnesses,
                scope_offers=scope_offers,
                scope=context.settings.default_scope,
            )
            if unfit:
                return self._default_path_unfit(command, unfit)
        if targets and not prepared.value.ready:
            # #50: configuration is per installation and an installation is a harness, so nothing
            # is asked until the harness is chosen. Before then the answer is the choice itself; a
            # field for a harness nobody picked is a question with no installation behind it.
            eligible_artifacts = tuple(
                dict.fromkeys(artifact for item in targets for artifact in item.artifacts)
            )
            if (
                pair_choice_problems(targets, pairs)
                if pairs
                else harness_choice_problems(targets, eligible_artifacts, chosen_targets)
            ):
                return ConsumerActionUpdate(
                    self.source(install_targets=targets),
                    ConsumerUiEvent(
                        ConsumerUiEventKind.ACTION_PREPARED,
                        action=command.action,
                        pairs=pairs,
                        config_draft=InstallationConfigDraft(),
                    ),
                )
            host = replace(host, profiles=chosen_targets)
            assignments = _assignments(
                _member_pairs(pairs, groups), _member_pair_scopes(pair_scopes, groups), host.scope
            )
            prepared = prepare_configured_installation(
                context.effective,
                selection,
                host=host,
                sources=(),
                policy=context.policy,
                selected_remediations=None,
                credential_providers=context.credential_providers,
                resolvers=context.credential_providers,
                previous=previous,
                preferred_installer=preferred,
                assignments=assignments,
            )
            if isinstance(prepared, Err):
                return self._declined(command, _refusal(prepared.diagnostics))
        # §172.4: 07 asks each ordinary input once per artifact. The answer is copied into every
        # installation of that artifact this operation creates, and into no other (INV-259).
        artifacts = {
            artifact_answer_key(field.owner): field.owner
            for field in prepared.value.draft.inputs.fields
        }
        answers = []
        for row, value in command.config_answers:
            key, _, identifier = row.rpartition("\t")
            if key in artifacts and identifier:
                held_by = artifacts[key]
                answers.append(
                    ArtifactAnswer(held_by.source, held_by.artifact, InputId(identifier), value)
                )
        sources = copy_artifact_answers(prepared.value.draft.inputs.fields, answers)
        if sources:
            prepared = prepare_configured_installation(
                context.effective,
                selection,
                host=host,
                sources=sources,
                policy=context.policy,
                selected_remediations=None,
                credential_providers=context.credential_providers,
                resolvers=context.credential_providers,
                previous=previous,
                preferred_installer=preferred,
                assignments=assignments,
            )
            if isinstance(prepared, Err):
                return self._declined(command, _refusal(prepared.diagnostics))
        if not prepared.value.ready:
            unanswered = prepared.value.draft.inputs.unanswered
            provider = next(
                (
                    item
                    for item in context.credential_providers
                    if item.available() is ProviderState.AVAILABLE
                ),
                None,
            )
            secret_fields = tuple(
                field for field in unanswered if isinstance(field.input, SecretInput)
            )
            if provider is not None and secret_fields:
                # The reference is safe application state, never a value. Each installation
                # addresses its own item (§169.4-6): the address carries the Registry alias, the
                # artifact, the scope, the root and the harness, so two harnesses of one artifact
                # no longer read one secret, and two homes never collide. The launcher composes
                # the harness half of it at start rather than carrying one (D-355).
                sources = (
                    *sources,
                    *(
                        OwnedInputSource(
                            field.owner,
                            SecretProviderReference(
                                field.input.id,
                                credential_address(
                                    field.owner,
                                    field.input.id,
                                    provider=provider.provider,
                                ),
                            ),
                        )
                        for field in secret_fields
                    ),
                )
                prepared = prepare_configured_installation(
                    context.effective,
                    selection,
                    host=host,
                    sources=sources,
                    policy=context.policy,
                    selected_remediations=None,
                    credential_providers=context.credential_providers,
                    resolvers=context.credential_providers,
                    previous=previous,
                    preferred_installer=preferred,
                    assignments=assignments,
                )
                if isinstance(prepared, Err):
                    return self._declined(command, _refusal(prepared.diagnostics))
        if not prepared.value.ready:
            # §187: an artifact that 07 asks about shows its optional inputs too, so they can be
            # given at all; one left empty stays unbound.
            unanswered_keys = {field.key for field in prepared.value.draft.inputs.unanswered}
            asked = {
                artifact_answer_key(field.owner)
                for field in prepared.value.draft.inputs.unanswered
                if isinstance(field.input, ConfigInput)
            }
            config_fields: dict[tuple[str, str], ConfigInput] = {}
            for field in prepared.value.draft.inputs.fields:
                runtime_input = field.input
                artifact = artifact_answer_key(field.owner)
                if isinstance(runtime_input, ConfigInput) and (
                    field.key in unanswered_keys
                    or (not runtime_input.required and artifact in asked)
                ):
                    config_fields.setdefault((artifact, runtime_input.id.value), runtime_input)
            if config_fields:
                order = {
                    artifact: index
                    for index, artifact in enumerate(dict.fromkeys(key for key, _ in config_fields))
                }
                observations = []
                for reference in prepared.value.draft.inputs.credential_references:
                    owner = next(
                        (
                            item
                            for item in context.credential_providers
                            if item.provider == reference.provider.provider
                        ),
                        None,
                    )
                    if owner is None:
                        continue
                    observed = owner.inspect(reference)
                    if isinstance(observed, Ok):
                        observations.append(observed.value)
                draft = InstallationConfigDraft(
                    tuple(
                        InstallationConfigField(
                            runtime_input.id.value,
                            runtime_input.default or "",
                            runtime_input.validation,
                            owner=artifact,
                            required=runtime_input.required,
                        )
                        # Within each artifact the required inputs come first (§187).
                        for (artifact, _), runtime_input in sorted(
                            config_fields.items(),
                            key=lambda item: (order[item[0][0]], not item[1].required),
                        )
                    )
                )
                return ConsumerActionUpdate(
                    self.source(
                        installation_inputs=_per_artifact(
                            prepared.value.draft.inputs.views(tuple(observations)),
                            {
                                str(field.owner): artifact_answer_key(field.owner)
                                for field in prepared.value.draft.inputs.fields
                            },
                        ),
                        install_targets=targets,
                        # §209: 07a is drawn from these before the form, while no plan exists.
                        install_scope_offers=scope_matrix_rows(scope_offers),
                    ),
                    ConsumerUiEvent(
                        ConsumerUiEventKind.ACTION_PREPARED,
                        action=command.action,
                        pairs=pairs,
                        pair_scopes=pair_scopes,
                        config_draft=draft,
                    ),
                )
            waiting = ", ".join(
                sorted({item.input.id.value for item in prepared.value.draft.inputs.unanswered})
            )
            return self._declined(
                command,
                _lines(
                    "this installation is waiting for answers this screen cannot collect yet: "
                    + waiting
                ),
            )
        action = prepared.value.action
        assert action is not None
        plan = replace(
            action.flow.plan,
            targets=targets,
            scope_choice=self._scope_choice(action.flow.plan, command.install_scope),
            installer_choice=self._installer_choice(prepared.value, preferred),
        )
        if command.default_path:
            # The installer offer exists only once the plan is ready, so it is checked here.
            unfit = default_path_mismatches(
                (),
                detected=(),
                harnesses=(),
                installer=plan.installer_choice,
                python_installer=preferred.value,
            )
            if unfit:
                return self._default_path_unfit(command, unfit)
        chosen: tuple[str, ...] = ()
        reviewed = prepared.value
        reviewed_host = host
        if command.action is ConsumerActionKind.INSTALL:
            problems = (
                pair_choice_problems(plan.targets, pairs)
                if pairs
                else target_choice_problems(plan, chosen_targets)
            )
            if not problems:
                chosen = chosen_targets
            if chosen:
                reviewed_host = replace(host, profiles=chosen)
                assignments = _assignments(
                    _member_pairs(pairs, groups),
                    _member_pair_scopes(pair_scopes, groups),
                    host.scope,
                )
                narrowed = prepare_configured_installation(
                    context.effective,
                    selection,
                    host=reviewed_host,
                    sources=sources,
                    policy=context.policy,
                    selected_remediations=None,
                    credential_providers=context.credential_providers,
                    resolvers=context.credential_providers,
                    previous=previous,
                    preferred_installer=preferred,
                    assignments=assignments,
                )
                if isinstance(narrowed, Err):
                    return self._declined(command, _refusal(narrowed.diagnostics))
                if not narrowed.value.ready:
                    return self._declined(
                        command,
                        _lines("the chosen harness plan still needs installation inputs"),
                    )
                reviewed = narrowed.value
                narrowed_action = reviewed.action
                assert narrowed_action is not None
                plan = replace(
                    narrowed_action.flow.plan,
                    targets=targets,
                    scope_choice=plan.scope_choice,
                    installer_choice=plan.installer_choice,
                    chosen_targets=chosen,
                    chosen_pairs=pairs,
                    scope_offers=scope_matrix_rows(scope_offers),
                    chosen_pair_scopes=pair_scopes,
                    secrets=self._install_secrets(reviewed),
                    config_placeholders=_config_placeholders(reviewed),
                )
        self._pending_host = reviewed_host
        self._pending_plan = plan
        self._pending = _PendingInstall(
            reviewed,
            previous_receipts,
            targets,
            chosen,
            pairs if chosen else (),
            pair_scopes if chosen else (),
        )
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(plan=plan),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                pairs=pairs,
                pair_scopes=pair_scopes,
                semantic_identity=plan.semantic_identity,
                selection_identity=plan.selection.semantic_identity,
                review_digest=plan.review_digest,
                # A Default plan that left some artifact without a harness goes to 05 for it.
                screen=(
                    _after_inputs(plan, default_path=command.default_path)
                    if chosen or not command.default_path
                    else ConsumerScreen.REVIEW_SELECTION
                ),
            ),
        )

    def _prepare_repair(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        inspected = self._inspections(self._targets(command))
        if isinstance(inspected, Err):
            return self._declined(command, _refusal(inspected.diagnostics))
        if len(inspected.value) != 1:
            return self._declined(command, _lines("a repair acts on one installation at a time"))
        host = self._host_of(inspected.value)
        if isinstance(host, Err):
            return self._declined(command, _refusal(host.diagnostics))
        prepared = prepare_configured_repair(inspected.value[0], policy=self._context.policy)
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        self._pending_host = host.value
        self._pending = prepared.value
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(lifecycle=project_lifecycle_plan(prepared.value.plan)),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=str(prepared.value.review_digest),
            ),
        )

    def _installed_inputs(self, record: InstalledRecord) -> Result[tuple[RuntimeInput, ...]]:
        """Read an installed artifact's approved input declarations from its immutable object."""

        receipt = record.receipt
        if not isinstance(receipt, InstallationReceipt) or receipt.object_digest is None:
            return Err(
                (
                    Diagnostic(
                        CONSUMER_ACTION_NOT_INSTALLED,
                        Severity.ERROR,
                        f"{record.coordinate} has no retained approved input description",
                    ),
                )
            )
        loaded = read_object(
            ObjectReadRequest(
                object_store_paths(self._context.host.data_root), receipt.object_digest
            )
        )
        if isinstance(loaded, Err):
            return loaded
        if loaded.value is None:
            return Err(
                (
                    Diagnostic(
                        CONSUMER_ACTION_NOT_INSTALLED,
                        Severity.ERROR,
                        f"{record.coordinate}'s approved object is no longer available",
                    ),
                )
            )
        described = read_package_description(loaded.value.candidate.entries)
        if isinstance(described, Err):
            return described
        return Ok(described.value.inputs)

    def _prepare_configuration(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        inspected = self._inspections((command.focus,) if command.focus else ())
        if isinstance(inspected, Err):
            return self._declined(command, _refusal(inspected.diagnostics))
        if len(inspected.value) != 1 or len(command.config_answers) != 1:
            return self._declined(
                command,
                _lines("a configuration edit needs one installed artifact and one ordinary input"),
            )
        identifier, value = command.config_answers[0]
        try:
            input_id = InputId(identifier)
        except ValueError:
            return self._declined(command, _lines("the chosen configuration input is invalid"))
        declarations = self._installed_inputs(inspected.value[0].record)
        if isinstance(declarations, Err):
            return self._declined(command, _refusal(declarations.diagnostics))
        declared = tuple(
            item
            for item in declarations.value
            if isinstance(item, ConfigInput) and item.id == input_id
        )
        if len(declared) != 1:
            return self._declined(
                command,
                _lines("the approved artifact no longer declares this configuration input"),
            )
        prepared = prepare_configured_configuration(
            inspected.value[0],
            input_id=input_id,
            harnesses=command.targets,
            value=value,
            policy=self._context.policy,
            validation=declared[0].validation,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        host = self._host_of(inspected.value)
        if isinstance(host, Err):
            return self._declined(command, _refusal(host.diagnostics))
        self._pending_host = host.value
        self._pending = prepared.value
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(lifecycle=project_lifecycle_plan(prepared.value.plan)),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=str(prepared.value.review_digest),
            ),
        )

    def _prepare_uninstall(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        targets = self._targets(command)
        collections = {
            item.collection: item for item in self.source().screens.installed_collections
        }
        if len(targets) > 1 and collections.keys() & set(targets):
            return self._declined(
                command,
                _lines(
                    "a Collection is uninstalled on its own, not ticked with artifacts",
                    "untick the Collection, or untick everything else",
                ),
            )
        # A Collection is its member installations, and uninstalling it gives up only its own
        # claim on each: a member something else still owns stays installed (INV-215).
        group = collections.get(targets[0]) if len(targets) == 1 else None
        release = (
            None
            if group is None
            else (OwnershipReason(OwnershipKind.COLLECTION, group.collection),)
        )
        inspected = self._inspections(
            targets if group is None else tuple(item.artifact for item in group.members)
        )
        if isinstance(inspected, Err):
            return self._declined(command, _refusal(inspected.diagnostics))
        chosen = self._host_of(inspected.value)
        if isinstance(chosen, Err):
            return self._declined(command, _refusal(chosen.diagnostics))
        host = chosen.value
        prepared = prepare_configured_uninstall(
            tuple(item.record for item in inspected.value),
            host=host,
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
            release=release,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        self._pending_host = host
        self._pending = prepared.value
        self._pending_action = command.action
        # Several ticked on Installed are one removal: one review, one confirmation (D-393).
        first, *rest = (project_lifecycle_plan(item) for item in prepared.value.proposal.lifecycle)
        return ConsumerActionUpdate(
            self.source(lifecycle=replace(first, also=tuple(rest))),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=str(prepared.value.review_digest),
            ),
        )

    def _inspections(self, coordinates: tuple[str, ...]) -> Result[tuple[InstalledInspection, ...]]:
        """Measure the named installations now, rather than trusting a projection from before.

        A lifecycle action is judged against the machine, and the screens were assembled when the
        shell started. Re-reading here is what keeps a repair from planning against drift that has
        since been fixed by hand.
        """

        if not coordinates:
            return Err(
                (
                    Diagnostic(
                        CONSUMER_ACTION_NOT_INSTALLED,
                        Severity.ERROR,
                        "nothing is selected to act on",
                    ),
                )
            )
        host = self._host()
        # Every installation on the machine, not only those of the scope Settings prefer: a row is
        # one installation's key, so the key alone picks it out, and narrowed to one scope the
        # user's installations read as missing from a project and another project's Skill did too.
        inspected = read_installed_inspections(
            state_root=host.state_root,
            harness_root=host.harness_root,
            credential_providers=self._context.credential_providers,
            scope_roots=host.scope_roots,
        )
        if isinstance(inspected, Err):
            return inspected
        # Keyed by installation. Addressed by coordinate alone, an action on an artifact that is
        # installed into two harnesses would reach whichever inspection this dictionary kept
        # (§169.3), so the key is what the row carries.
        by_installation = {item.installation: item for item in inspected.value.inspections}
        missing = [item for item in coordinates if item not in by_installation]
        if missing:
            return Err(
                (
                    Diagnostic(
                        CONSUMER_ACTION_NOT_INSTALLED,
                        Severity.ERROR,
                        "nothing canonical is installed here as "
                        + ", ".join(describe_installation(item) for item in sorted(missing)),
                        remediation=("open Installed and choose a recorded installation",),
                    ),
                )
            )
        # Every action below resolves harness paths against this session's root for the scope, so
        # an installation another project owns is refused rather than repaired, reconfigured,
        # updated or removed in this one (§169.3, D-479).
        elsewhere = sorted(
            item
            for item in coordinates
            if (owner := by_installation[item].record.receipt.owner) is not None
            and owner.root != host.root_for(owner.scope)
        )
        if elsewhere:
            roots = sorted(
                {
                    owner.root
                    for item in elsewhere
                    if (owner := by_installation[item].record.receipt.owner) is not None
                }
            )
            return Err(
                (
                    Diagnostic(
                        CONSUMER_ACTION_ELSEWHERE,
                        Severity.ERROR,
                        "installed in another project: "
                        + ", ".join(describe_installation(item) for item in elsewhere)
                        + "; open aart-cli in "
                        + " or ".join(roots)
                        + " to change it",
                    ),
                )
            )
        return Ok(tuple(by_installation[item] for item in coordinates))

    def _host_of(self, inspected: tuple[InstalledInspection, ...]) -> Result[InstallationHost]:
        """The host at the scope these installations were made at, whatever Settings prefer.

        Repair, configuration and removal resolve harness paths against the host's scope, so a
        user installation acted on from a project is planned at user scope rather than looked for
        in the project (§169.3, D-479).
        """

        scopes = {
            owner.scope for item in inspected if (owner := item.record.receipt.owner) is not None
        }
        if len(scopes) > 1:
            return Err(
                (
                    Diagnostic(
                        CONSUMER_ACTION_MIXED_SCOPES,
                        Severity.ERROR,
                        "user and project installations are changed one scope at a time",
                        remediation=("tick only user rows, or only project rows",),
                    ),
                )
            )
        return Ok(self._host(scopes.pop().value if scopes else ""))

    # -- execution ------------------------------------------------------------ #

    def _recorded(
        self,
        command: ConsumerUiCommand,
        recorded_at: str,
        *,
        completion: ConsumerActionCompletion | None = None,
        registry_commit_subject: str = "",
        **views,
    ) -> ConsumerActionUpdate:
        self._pending, self._pending_action = None, None
        return ConsumerActionUpdate(
            self.source(**views),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=command.action,
                text=recorded_at,
                registry_commit_subject=registry_commit_subject,
            ),
            completion,
        )

    def _failed(self, command: ConsumerUiCommand, notice: tuple[str, ...]) -> ConsumerActionUpdate:
        """An execution that did not record anything, drawn on the screen it was run from.

        The screen stays where it is: the refusal answers a question asked here, and no result
        screen exists for a run that produced nothing. But the attempt is over -- the pending plan
        is discarded on the line above -- so this says the run failed rather than saying nothing
        was recorded. They are two events: a review told "nothing was recorded" cannot tell an attempt
        that stopped from a confirmation that never happened, and would go on advertising a key whose
        only answer is that nothing was prepared (`QA-033`).
        """

        self._pending, self._pending_action = None, None
        return ConsumerActionUpdate(
            self.source(notice=notice),
            ConsumerUiEvent(ConsumerUiEventKind.ACTION_FAILED, action=command.action),
        )

    def _execute(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        pending = self._pending
        if pending is None or self._pending_action is not command.action:
            return self._failed(
                command, _lines("nothing was prepared for this action; review it again")
            )
        expected = (
            str(pending.prepared.review_digest)
            if isinstance(pending, _PendingInstall)
            else str(pending.review_digest)
        )
        if command.review_digest != expected:
            return self._failed(
                command,
                _lines(
                    "this confirmation names a different plan than the one prepared; "
                    "review it again"
                ),
            )
        if isinstance(pending, _PendingInstall):
            return self._execute_installation(command, pending)
        if isinstance(pending, _PendingRegistryAddition):
            return self._execute_registry_addition(command, pending)
        if isinstance(pending, _PendingRegistryRefresh):
            return self._execute_registry_refresh(command, pending)
        if isinstance(pending, _PendingRegistryRemoval):
            return self._execute_registry_removal(command, pending)
        if isinstance(pending, _PendingSourceAddition):
            return self._execute_source_addition(command, pending)
        if isinstance(pending, _PendingRegistryInit):
            return self._execute_registry_init(command, pending)
        if isinstance(pending, _PendingRegistryRebuild):
            return self._execute_registry_rebuild(command, pending)
        if isinstance(pending, _PendingRegistryPush):
            return self._execute_registry_push(command, pending)
        if isinstance(pending, PreparedAdoption):
            return self._execute_repository_adoption(command, pending)
        if isinstance(pending, PreparedConfiguredRepair):
            return self._execute_repair(command, pending)
        if isinstance(pending, PreparedConfiguredConfiguration):
            return self._execute_configuration(command, pending)
        if isinstance(pending, PreparedSourceSync):
            return self._execute_source_sync(command, pending)
        if isinstance(pending, PreparedConfiguredCandidatePromotion):
            return self._execute_candidate_promotion(command, pending)
        if isinstance(pending, _PendingCredentialAction):
            return self._execute_credential_action(command, pending)
        if isinstance(pending, _PendingMcpTest):
            return self._execute_mcp_test(command, pending)
        assert isinstance(pending, PreparedConfiguredUninstall)
        return self._execute_uninstall(command, pending)

    def _execute_registry_push(
        self, command: ConsumerUiCommand, pending: _PendingRegistryPush
    ) -> ConsumerActionUpdate:
        """Fail closed if any reviewed workspace or gate evidence changed, then push once."""

        workspace = read_registry_workspace(pending.root)
        if (
            workspace is None
            or not workspace.push_ready
            or workspace.root != pending.root
            or workspace.revision != pending.command.revision
            or workspace.content_digest != pending.content_digest
            or workspace.publication_review_digest != str(pending.command.review_digest)
        ):
            blockers = () if workspace is None else workspace.push_blockers
            return self._failed(
                command,
                _lines(
                    "Registry Push readiness changed after review",
                    *blockers,
                    "Review the current Registry state and prepare Push again.",
                ),
            )
        published = self._registry_publication(pending.root, pending.command)
        if isinstance(published, Err):
            return self._failed(command, _refusal(published.diagnostics))
        if self._data_root is not None:
            refreshed = read_maintainer_views(
                self._context.effective,
                data_root=self._data_root,
                observed_at_epoch_seconds=int(self._now().timestamp()),
                registry_root=self._context.host.project_root,
            )
            if isinstance(refreshed, Ok):
                self._context = replace(self._context, maintainer=refreshed.value)
        recorded_at, _today = self._moment()
        return self._recorded(
            command,
            recorded_at,
            notice=publication_summary(published.value),
        )

    def _execute_repository_adoption(
        self,
        command: ConsumerUiCommand,
        pending: PreparedAdoption,
    ) -> ConsumerActionUpdate:
        assert self._repository_adoption is not None
        applied = self._repository_adoption.apply(pending, command.review_digest)
        if isinstance(applied, Err):
            return self._failed(command, _refusal(applied.diagnostics))
        if self._repository_adopted_list is not None:
            listed = self._repository_adopted_list()
            if isinstance(listed, Ok):
                self._adopted_artifacts = listed.value
        if self._data_root is not None:
            refreshed = read_maintainer_views(
                self._context.effective,
                data_root=self._data_root,
                observed_at_epoch_seconds=int(self._now().timestamp()),
                registry_root=self._context.host.project_root,
            )
            if isinstance(refreshed, Ok):
                self._context = replace(self._context, maintainer=refreshed.value)
        recorded_at, _today = self._moment()
        return self._recorded(command, recorded_at)

    def _execute_registry_addition(
        self,
        command: ConsumerUiCommand,
        pending: _PendingRegistryAddition,
    ) -> ConsumerActionUpdate:
        assert self._registry_connection is not None
        connected = self._registry_connection(pending.draft)
        if isinstance(connected, Err):
            return self._failed(command, _refusal(connected.diagnostics))
        self._context = replace(
            self._context,
            effective=connected.value.effective,
            offers=connected.value.offers,
            maintainer=connected.value.maintainer,
        )
        recorded_at, _today = self._moment()
        return self._recorded(command, recorded_at)

    def _prepare_registry_refresh(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Review refreshing one connected registry: which subscription, and what it is not.

        The row has to be a registry.  An upstream repository holds Candidates that a maintainer
        promotes, so "refresh what Marketplace can offer" is an effect it cannot have (INV-199),
        and offering the action there would advertise a result that never arrives.
        """

        if self._registry_refresh is None:
            return self._declined(command, _lines("registry refresh is unavailable"))
        alias = command.focus
        row = next(
            (item for item in self._context.offers.registries if item.alias == alias),
            None,
        )
        if row is None:
            return self._declined(command, _lines(f"no connected registry here is {alias}"))
        if not row.is_registry:
            return self._declined(
                command,
                _lines(
                    f"{alias} is an upstream repository, not a registry; "
                    "its Candidates are promoted in Registry Maintainer Mode"
                ),
            )
        identity = json.dumps(
            {"alias": alias, "operation": "registry-sync"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        review_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        self._pending = _PendingRegistryRefresh(alias, review_digest)
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(
                notice=(
                    f"Registry refresh review: {alias} from {row.origin}",
                    f"  branch or tag: {row.ref or 'repository default'}",
                    "  installed artifacts are not changed by this",
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _execute_registry_refresh(
        self,
        command: ConsumerUiCommand,
        pending: _PendingRegistryRefresh,
    ) -> ConsumerActionUpdate:
        assert self._registry_refresh is not None
        refreshed = self._registry_refresh(pending.alias)
        if isinstance(refreshed, Err):
            # Last known good: the fetch failed, so the context keeps the snapshot it already had
            # and the Marketplace goes on offering what is already approved.
            return self._failed(command, _refusal(refreshed.diagnostics))
        self._context = replace(
            self._context,
            effective=refreshed.value.effective,
            offers=refreshed.value.offers,
            maintainer=refreshed.value.maintainer,
        )
        recorded_at, _today = self._moment()
        return self._recorded(command, recorded_at)

    def _prepare_registry_removal(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if self._registry_removal is None:
            return self._declined(command, _lines("Registry disconnection is unavailable"))
        source = next(
            (
                item
                for item in self._context.effective.configuration.sources
                if item.alias.value == command.focus and item.is_registry
            ),
            None,
        )
        if source is None:
            return self._declined(command, _lines(f"no connected Registry here is {command.focus}"))
        cleared_default = self._context.effective.configuration.default_registry == source.alias
        identity = json.dumps(
            {
                "alias": source.alias.value,
                "location": source.location,
                "ref": source.ref,
                "cleared_default": cleared_default,
                "operation": "registry-remove",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        review_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        self._pending = _PendingRegistryRemoval(source, review_digest)
        self._pending_action = command.action
        default_effect = (
            "  default Registry: cleared; no replacement is selected"
            if cleared_default
            else "  default Registry: unchanged"
        )
        return ConsumerActionUpdate(
            self.source(
                notice=(
                    "Disconnect Registry review:",
                    f"  Registry: {source.alias}",
                    f"  origin: {redact_text(source.location)}",
                    f"  branch or tag: {source.ref or 'repository default'}",
                    "  removes: this connection and its AART-managed snapshot",
                    default_effect,
                    "  keeps: all installed artifacts and receipts",
                    "  Marketplace will be reloaded from the Registries that remain connected.",
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _prepare_source_removal(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Review removing one upstream repository: the same unsubscribe as `aart-cli maintain upstream remove`.

        Removing is how a Source whose origin, branch or kind was entered wrong is corrected:
        removed here, then added again from Add upstream (D-391). The port is the Registry one,
        because the transaction is one; only the subject it is offered for differs.
        """

        if self._registry_removal is None:
            return self._declined(command, _lines("Upstream removal is unavailable"))
        source = next(
            (
                item
                for item in self._context.effective.configuration.sources
                if item.alias.value == command.focus and not item.is_registry
            ),
            None,
        )
        if source is None:
            return self._declined(
                command, _lines(f"no upstream repository here is {command.focus}")
            )
        identity = json.dumps(
            {
                "alias": source.alias.value,
                "kind": source.kind.value,
                "location": source.location,
                "ref": source.ref,
                "operation": "source-remove",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        review_digest = "sha256:" + hashlib.sha256(identity).hexdigest()
        self._pending = _PendingRegistryRemoval(source, review_digest)
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(
                notice=(
                    "Remove upstream review:",
                    f"  Upstream: {source.alias}",
                    f"  kind: {source.kind.value.removeprefix('source-')}",
                    f"  origin: {redact_text(source.location)}",
                    f"  branch or tag: {source.ref or 'repository default'}",
                    "  removes: this upstream, its AART-managed snapshot and its Candidates",
                    "  keeps: every version already promoted into a Registry",
                    "  Add it again from Add upstream; Upstream sync then rebuilds its Candidates.",
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _execute_registry_removal(
        self,
        command: ConsumerUiCommand,
        pending: _PendingRegistryRemoval,
    ) -> ConsumerActionUpdate:
        assert self._registry_removal is not None
        removed = self._registry_removal(pending.source)
        if isinstance(removed, Err):
            return self._failed(command, _refusal(removed.diagnostics))
        self._context = replace(
            self._context,
            effective=removed.value.effective,
            offers=removed.value.offers,
            maintainer=removed.value.maintainer,
        )
        recorded_at, _today = self._moment()
        return self._recorded(command, recorded_at)

    def _execute_source_addition(
        self,
        command: ConsumerUiCommand,
        pending: _PendingSourceAddition,
    ) -> ConsumerActionUpdate:
        assert self._source_connection is not None
        connected = self._source_connection(pending.draft)
        if isinstance(connected, Err):
            return self._failed(command, _refusal(connected.diagnostics))
        self._context = replace(
            self._context,
            effective=connected.value.effective,
            offers=connected.value.offers,
            maintainer=connected.value.maintainer,
        )
        return self._recorded(
            command,
            pending.draft.alias,
            notice=(
                f"Upstream {pending.draft.alias} added.",
                "",
                "Run Upstream sync to discover artifacts and create or refresh Candidates, "
                "including new upstream versions. Adding an upstream only connects it.",
                "",
                "Upstream sync does not promote Candidates or update installed artifacts.",
            ),
        )

    def _execute_registry_init(
        self,
        command: ConsumerUiCommand,
        pending: _PendingRegistryInit,
    ) -> ConsumerActionUpdate:
        """Run the five stages and draw what each one did, including the one that stopped it.

        A refused stage is not a silent failure and not an exception: the stages before it really
        did write to the checkout, so the result says how far the run got rather than only that it
        failed. Nothing is recorded in that case, which leaves the session on the review.
        """

        assert self._registry_bootstrap is not None
        completed = self._registry_bootstrap(pending.draft)
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        report = completed.value.report
        if completed.value.connection is not None:
            self._context = replace(
                self._context,
                effective=completed.value.connection.effective,
                offers=completed.value.connection.offers,
                maintainer=completed.value.connection.maintainer,
            )
        lines: list[str] = ["Registry initialization:"]
        for stage in report.stages:
            lines.append(f"  {stage.name}: {'done' if stage.passed else 'refused'}")
            lines.extend(f"    {line}" for line in stage.lines)
        if not report.passed:
            lines.append("  the run stopped there; the stages after it did not run")
            # Not through `_lines`: the indentation is what makes a stage's own detail read as
            # belonging to that stage rather than as another stage.
            return self._failed(command, tuple(lines))
        recorded_at, _today = self._moment()
        return self._recorded(command, recorded_at, notice=tuple(lines))

    def _execute_registry_rebuild(
        self,
        command: ConsumerUiCommand,
        pending: _PendingRegistryRebuild,
    ) -> ConsumerActionUpdate:
        """Run the reviewed stages and draw what each one did, including the one that stopped it."""

        assert self._registry_rebuild is not None
        completed = self._registry_rebuild(pending.stages)
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        report = completed.value.report
        if completed.value.connection is not None:
            self._context = replace(
                self._context,
                effective=completed.value.connection.effective,
                offers=completed.value.connection.offers,
                maintainer=completed.value.connection.maintainer,
            )
        lines: list[str] = ["Registry rebuild:"]
        for stage in report.stages:
            lines.append(f"  {stage.name}: {'done' if stage.passed else 'refused'}")
            lines.extend(f"    {line}" for line in stage.lines)
        if not report.passed:
            lines.append("  the run stopped there; the stages after it did not run")
            # Not through `_lines`, for the same reason the initialization result is not: the
            # indentation is what makes a stage's detail read as belonging to that stage.
            return self._failed(command, tuple(lines))
        recorded_at, _today = self._moment()
        return self._recorded(command, recorded_at, notice=tuple(lines))

    def _execute_source_sync(
        self,
        command: ConsumerUiCommand,
        pending: PreparedSourceSync,
    ) -> ConsumerActionUpdate:
        completed = complete_configured_source_sync(
            self._context.effective,
            pending,
            reviewed_digest=pending.review_digest,
        )
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        assert self._data_root is not None
        refreshed = read_maintainer_views(
            self._context.effective,
            data_root=self._data_root,
            observed_at_epoch_seconds=int(self._now().timestamp()),
            registry_root=self._context.host.project_root,
        )
        if isinstance(refreshed, Err):
            return self._failed(command, _refusal(refreshed.diagnostics))
        self._context = replace(self._context, maintainer=refreshed.value)
        recorded_at, _today = self._moment()
        return self._recorded(
            command,
            recorded_at,
            source_sync_result=project_source_sync_result(
                completed.value,
                target_registry=pending.target_registry,
            ),
        )

    def _execute_candidate_promotion(
        self,
        command: ConsumerUiCommand,
        pending: PreparedConfiguredCandidatePromotion,
    ) -> ConsumerActionUpdate:
        completed = complete_configured_candidate_promotion(
            self._context.effective,
            pending,
            reviewed_digest=pending.review_digest,
            registry_root=self._context.host.project_root,
        )
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        self._promotion_transaction = pending.transaction
        self._promotion_result = completed.value
        assert self._data_root is not None
        # The write just moved the registry checkout, so screen 46's working-tree observation and
        # every Candidate view planned against that tree are stale the moment the commit lands.
        refreshed = read_maintainer_views(
            self._context.effective,
            data_root=self._data_root,
            observed_at_epoch_seconds=int(self._now().timestamp()),
            registry_root=self._context.host.project_root,
        )
        if isinstance(refreshed, Ok):
            self._context = replace(self._context, maintainer=refreshed.value)
        recorded_at, _today = self._moment()
        versions = pending.transaction.plan.versions
        registry_commit_subject = (
            f"{versions[0].coordinate.artifact.name}-{versions[0].coordinate.version}"
            if len(versions) == 1
            else ""
        )
        return self._recorded(
            command,
            recorded_at,
            registry_commit_subject=registry_commit_subject,
            promotion_validation=project_maintainer_registry_validation(pending.transaction),
            promotion_commit=project_maintainer_registry_commit(
                pending.transaction,
                result=completed.value,
            ),
        )

    def _moment(self) -> tuple[str, object]:
        now = self._now()
        return now.isoformat(), now.date()

    def _execute_installation(
        self, command: ConsumerUiCommand, pending: _PendingInstall
    ) -> ConsumerActionUpdate:
        if pending.targets and not pending.chosen_targets:
            return self._failed(
                command,
                _lines(
                    "no installation harness was chosen; choose at least one eligible harness "
                    "and review the installation again"
                ),
            )
        if command.action is ConsumerActionKind.INSTALL and (
            command.targets != pending.chosen_targets
            or set(command.pairs) != set(pending.chosen_pairs)
            or set(command.pair_scopes) != set(pending.chosen_pair_scopes)
        ):
            return self._failed(
                command,
                _lines(
                    "this confirmation names different harness targets than the reviewed plan; "
                    "review the installation again"
                ),
            )
        recorded_at, today = self._moment()
        reports: list[StepProgress] = []

        def observe(progress: StepProgress) -> None:
            # Accumulated here rather than in the projection so the screen is a fold of everything
            # said so far, not just the latest step.
            reports.append(progress)
            report = self._progress
            if report is not None:
                report(project_running_installation(tuple(reports)))

        completed = complete_configured_installation(
            pending.prepared,
            expected_review_digest=pending.prepared.review_digest,
            host=self._reviewed_host(),
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
            previous_receipts=pending.previous_receipts,
            recorded_at=recorded_at,
            today=today,  # type: ignore[arg-type]
            offline=self._context.offline,
            # 07b's store prompts already ran (§207); every secret not entered there is stored as
            # the AART_NOT_SET placeholder, so the install asks nobody anything.
            skipped_secrets_as_placeholders=True,
            observe=None if self._progress is None else observe,
            credential_entry=self._credential_entry,
        )
        if isinstance(completed, Err):
            # The values were entered for this install, and it did not happen (§207).
            self._forget_entered(tuple(self._entered))
            return self._failed(command, _refusal(completed.diagnostics))
        # They belong to the installations now, and leave with them (§208).
        self._entered = {}
        self._machine = completed.value.machine
        receipt = completed.value.action.flow.outcome
        assert receipt is not None
        host = self._reviewed_host()
        # Read after the commit and only to offer something: whatever it finds, or fails to find,
        # the install above is already recorded and reported as it is (§170.4, INV-251).
        after = _AfterInstall(
            receipt,
            completed.value.pending_setup,
            (
                self._installed_mcps(host, pending.chosen_targets, receipt)
                if command.action is ConsumerActionKind.INSTALL
                else ()
            ),
            None,
        )
        if after.records:
            after = replace(
                after,
                test=McpTestView(tuple(_installation_of(record) for record in after.records)),
            )
        self._after_install = after
        completion = None
        if self._completion_factory is not None:

            def remaining_source(remaining: tuple[DeclaredArtifactSetup, ...]):
                if self._after_install is not None:
                    self._after_install = replace(self._after_install, pending_setup=remaining)
                return self.source(
                    transaction=receipt,
                    pending_setup=remaining,
                    mcp_test=None if self._after_install is None else self._after_install.test,
                )

            completion = self._completion_factory(
                completed.value,
                "update" if command.action is ConsumerActionKind.UPDATE else "install",
                remaining_source,
                host,
            )
        return self._recorded(
            command,
            receipt.recorded_at,
            completion=completion,
            transaction=receipt,
            pending_setup=completed.value.pending_setup,
            mcp_test=after.test,
        )

    # -- the optional test after an installation (§170.4) ------------------- #

    def _mcp_tester(self, host: InstallationHost) -> McpTestPort:
        return self._mcp_test if self._mcp_test is not None else LocalMcpTest(host.data_root)

    def _installed_mcps(
        self, host: InstallationHost, harnesses: tuple[str, ...], receipt
    ) -> tuple[InstalledRecord, ...]:
        """The MCP installations this committed transaction made, or none when unreadable.

        A failure here can only withhold the offer. It never reaches the install's outcome,
        because the install is already recorded and somebody is about to be told it succeeded.
        """

        members = frozenset(
            item.coordinate
            for item in getattr(receipt, "artifacts", ())
            if item.status in _INSTALLED_MEMBER
        )
        try:
            return self._mcp_tester(host).installations(
                scope=host.scope,
                root=host.harness_root,
                harnesses=frozenset(harnesses),
                coordinates=members,
            )
        except Exception:  # noqa: BLE001 - an offer that cannot be made is simply not made
            return ()

    def _after_install_source(
        self, test: McpTestView | None, notice: tuple[str, ...] = ()
    ) -> CanonicalScreenSource:
        after = self._after_install
        if after is None:
            return self.source(notice=notice)
        return self.source(
            transaction=after.transaction,
            pending_setup=after.pending_setup,
            mcp_test=test,
            notice=notice,
        )

    def _prepare_mcp_test(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if command.screen in (
            ConsumerScreen.INSTALLED,
            ConsumerScreen.INSTALLED_ARTIFACT_DETAILS,
        ):
            return self._prepare_installed_mcp_test(command)
        after = self._after_install
        if after is None or not after.records or after.test is None:
            return ConsumerActionUpdate(
                self._after_install_source(
                    None if after is None else after.test,
                    _lines("this install made no MCP installation to test"),
                ),
                ConsumerUiEvent(ConsumerUiEventKind.ACTION_PREPARED, action=command.action),
            )
        try:
            planned = self._mcp_tester(self._reviewed_host()).plan(after.records)
        except Exception as error:  # noqa: BLE001 - the offer is withheld, the install is untouched
            return ConsumerActionUpdate(
                self._after_install_source(
                    after.test,
                    _lines(f"the installed MCPs could not be read for a test: {_why(error)}"),
                ),
                ConsumerUiEvent(ConsumerUiEventKind.ACTION_PREPARED, action=command.action),
            )
        plan = tuple(
            McpTestEntryView(item.installation, item.tool, item.arguments) for item in planned
        )
        digest = hashlib.sha256(
            json.dumps(
                [[item.installation, item.tool, item.arguments] for item in plan],
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self._pending, self._pending_action = _PendingMcpTest(after.records, digest), command.action
        return ConsumerActionUpdate(
            self._after_install_source(replace(after.test, plan=plan, results=None)),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=digest,
            ),
        )

    def _prepare_installed_mcp_test(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Review the test of installations chosen on Installed, or the one a details screen is.

        Selection is installation-qualified exactly as `aart-cli consume mcp test` makes it (§170.1,
        INV-254): each key is one installation in one harness, read back from the receipts now.
        A chosen row that is not an MCP is refused by name rather than dropped, because a test
        that quietly covers less than was ticked reads as a pass for what it skipped.
        """

        targets = self._targets(command)
        if not targets:
            return self._declined(command, _lines("select an installed MCP to test"))
        others = tuple(key for key in targets if not installation_is_mcp(key))
        if others:
            return self._declined(
                command,
                _lines(
                    *(
                        f"{describe_installation(key)} is not an MCP; only MCP installations are tested"
                        for key in others
                    ),
                    "untick it and test the MCPs alone",
                ),
            )
        host = self._host()
        views = {item.row: item for item in self.source().screens.installed}
        # Each key says where its installation is: an MCP installed for the user is tested from a
        # project too, so the records are read in the key's scope and root, never the session's.
        places: dict[tuple[str, str], list[str]] = {}
        for key in targets:
            _, _, scope, root = (key.split("#", 3) + ["", "", ""])[:4]
            places.setdefault((scope, root), []).append(key)
        try:
            records = tuple(
                record
                for (scope, root), keys in sorted(places.items())
                if scope in (Scope.PROJECT.value, Scope.USER.value)
                for record in self._mcp_tester(host).installations(
                    scope=Scope(scope),
                    root=root,
                    harnesses=frozenset(
                        views[key].harness.partition("+")[0] for key in keys if key in views
                    ),
                    coordinates=frozenset(key.partition("#")[0] for key in keys),
                )
            )
            chosen = tuple(record for record in records if _installation_of(record) in targets)
            missing = tuple(
                key for key in targets if key not in {_installation_of(item) for item in chosen}
            )
            if missing:
                return self._declined(
                    command,
                    _lines(*(f"{key} has no recorded MCP installation to test" for key in missing)),
                )
            planned = self._mcp_tester(host).plan(chosen)
        except Exception as error:  # noqa: BLE001 - a test that cannot be prepared changes nothing
            return self._declined(
                command,
                _lines(f"the installed MCPs could not be read for a test: {_why(error)}"),
            )
        plan = tuple(
            McpTestEntryView(item.installation, item.tool, item.arguments) for item in planned
        )
        digest = hashlib.sha256(
            json.dumps(
                [[item.installation, item.tool, item.arguments] for item in plan],
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        test = McpTestView(tuple(_installation_of(item) for item in chosen), plan=plan)
        self._pending_host = host
        self._pending = _PendingMcpTest(chosen, digest, installed=test)
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(mcp_test=test),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=digest,
            ),
        )

    def _execute_mcp_test(
        self, command: ConsumerUiCommand, pending: _PendingMcpTest
    ) -> ConsumerActionUpdate:
        """Run the reviewed test once. Its outcome is an answer, never a change to the install."""

        self._pending, self._pending_action = None, None
        test = pending.installed
        if test is None:
            after = self._after_install
            assert after is not None and after.test is not None
            test = after.test

        def drawn(view: McpTestView, notice: tuple[str, ...] = ()) -> CanonicalScreenSource:
            if pending.installed is not None:
                return self.source(mcp_test=view, notice=notice)
            return self._after_install_source(view, notice)

        try:
            ran = self._mcp_tester(self._reviewed_host()).run(pending.records)
        except Exception as error:  # noqa: BLE001 - a test that cannot run is reported, not escalated
            return ConsumerActionUpdate(
                drawn(
                    test,
                    _lines(
                        f"the MCP test could not be run: {_why(error)}",
                        "the installation is unchanged",
                    ),
                ),
                ConsumerUiEvent(ConsumerUiEventKind.ACTION_FAILED, action=command.action),
            )
        results = tuple(
            McpTestResultView(
                item.installation,
                tuple(
                    McpTestStageView(stage.stage.value, stage.outcome.value, stage.reason)
                    for stage in item.stages
                ),
            )
            for item in ran
        )
        recorded_at, _ = self._moment()
        return ConsumerActionUpdate(
            drawn(replace(test, results=results)),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED, action=command.action, text=recorded_at
            ),
        )

    def _execute_credential_action(
        self, command: ConsumerUiCommand, pending: _PendingCredentialAction
    ) -> ConsumerActionUpdate:
        """Run a reviewed replacement or deletion, then ask the provider what it now holds.

        The effects go through `CredentialEffectInterpreter`, the interpreter repair uses, so a
        replacement lends the terminal to the provider's own prompt and AART never holds a value,
        old or new (INV-056, `QA-081`). The plan's verify effect is the reading taken afterwards:
        it is the one whose answer decides whether the action did what the review said (INV-176).
        """

        plan = pending.plan
        reference = plan.observation.reference
        interpreter = CredentialEffectInterpreter(
            pending.provider,
            (reference,),
            interactive_store=True,
            terminal_handover=self._terminal_handover,
            guidance={str(reference): pending.guidance} if pending.guidance else None,
            lengths=None if pending.length is None else {str(reference): pending.length},
            fallbacks=self._credential_entry,
        )
        for effect in plan.effects:
            if isinstance(effect, VerifyCredential):
                continue
            applied = interpreter.apply(effect)
            if isinstance(applied, Err):
                self._reread_machine(self._host())
                return self._failed(command, _refusal(applied.diagnostics))
        observed = pending.provider.inspect(reference)
        unread = self._reread_machine(self._host())
        if isinstance(observed, Err):
            return self._failed(command, _refusal(observed.diagnostics))
        provider = reference.provider.provider
        if plan.intent is CredentialIntent.DELETE:
            expected, done = CredentialState.ABSENT, f"Deleted {reference.input} from {provider}."
        elif plan.intent is CredentialIntent.STORE:
            expected, done = CredentialState.PRESENT, f"Set {reference.input} in {provider}."
        else:
            expected, done = CredentialState.PRESENT, f"Replaced {reference.input} in {provider}."
        if observed.value.state is not expected:
            return self._failed(
                command,
                _lines(
                    f"{provider} reports {reference.input} as {observed.value.state.value} "
                    f"after the {plan.intent.value}",
                    "choose Verify to ask it again",
                ),
            )
        if expected is CredentialState.PRESENT:
            checked = checked_observation(observed.value, pending.length)
            if checked.state is CredentialState.INVALID:
                # Stored, and still not the credential: said as a failure, with why (§204).
                return self._failed(
                    command,
                    _lines(
                        f"{reference.input} is not configured: {checked.detail}",
                        "set it again and paste the whole value",
                    ),
                )
            if pending.length is None and observed.value.clipped:
                done = f"{done} {observed.value.detail}; if it is longer, set it again."
        return self._recorded(command, str(reference), notice=(done, *unread))

    def _execute_repair(
        self, command: ConsumerUiCommand, pending: PreparedConfiguredRepair
    ) -> ConsumerActionUpdate:
        recorded_at, today = self._moment()
        completed = complete_configured_repair(
            pending,
            expected_review_digest=pending.review_digest,
            host=self._reviewed_host(),
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
            recorded_at=recorded_at,
            today=today,  # type: ignore[arg-type]
            offline=self._context.offline,
        )
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        self._machine = completed.value.machine
        return self._recorded(command, completed.value.recorded.receipt.recorded_at)

    def _execute_configuration(
        self, command: ConsumerUiCommand, pending: PreparedConfiguredConfiguration
    ) -> ConsumerActionUpdate:
        recorded_at, today = self._moment()
        completed = complete_configured_configuration(
            pending,
            expected_review_digest=pending.review_digest,
            host=self._reviewed_host(),
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
            recorded_at=recorded_at,
            today=today,  # type: ignore[arg-type]
            offline=self._context.offline,
        )
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        self._machine = completed.value.machine
        return self._recorded(command, completed.value.recorded.receipt.recorded_at)

    def _execute_uninstall(
        self, command: ConsumerUiCommand, pending: PreparedConfiguredUninstall
    ) -> ConsumerActionUpdate:
        recorded_at, today = self._moment()
        completed = complete_configured_uninstall(
            pending,
            expected_review_digest=pending.review_digest,
            host=self._reviewed_host(),
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
            recorded_at=recorded_at,
            today=today,  # type: ignore[arg-type]
        )
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        self._machine = completed.value.machine
        return self._recorded(command, completed.value.recorded.receipt.recorded_at)
