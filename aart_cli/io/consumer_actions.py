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
)
from aart_cli.application.consumer_views import (
    ConsumerPlanView,
    ConsumerSettings,
    HarnessTargetView,
    InstallScopeChoiceView,
    LifecyclePlanView,
    PythonInstallerChoiceView,
    RunningInstallationView,
    offer_install_scopes,
    offer_python_installers,
    project_lifecycle_plan,
    project_running_installation,
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
from aart_cli.application.installation_inputs import OwnedInputSource
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
    parse_validation_row,
    project_maintainer_registry_commit,
    project_maintainer_registry_validation,
    project_source_sync_result,
    project_source_sync_review,
)
from aart_cli.application.registry_publication import (
    RegistryPublicationCommand,
    RegistryPublicationReceipt,
    prepare_registry_publication,
    publication_summary,
)
from aart_cli.configuration.model import ConfiguredSource, SourceKind
from aart_cli.configuration.policy import EffectiveConfiguration, redact_text
from aart_cli.configuration.schema import configured_source_from_input
from aart_cli.domain.candidates import CandidateId
from aart_cli.domain.credentials import (
    CredentialIntent,
    CredentialState,
    ProviderState,
)
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.effects import VerifyCredential
from aart_cli.domain.harness import Scope
from aart_cli.domain.identifiers import ArtifactCoordinate, InputId, SourceAlias
from aart_cli.domain.inputs import (
    ConfigInput,
    InputGuidance,
    PromptedConfigValue,
    RuntimeInput,
    SecretInput,
    SecretProviderReference,
)
from aart_cli.domain.installation_owner import InstallationOwner, credential_address
from aart_cli.domain.policies import EffectivePolicy
from aart_cli.domain.python_runtime import PythonInstaller
from aart_cli.domain.receipts import ArtifactReceipt, InstallationReceipt, InstalledRecord
from aart_cli.domain.reconciliation import DesiredState
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.selection import ArtifactRequest, ArtifactSelection, VersionConstraint
from aart_cli.protocol.authoring import read_package_description
from aart_cli.protocol.hashing import parse_sha256
from aart_cli.store.model import ObjectReadRequest, object_store_paths
from aart_cli.tui_consumer import (
    CanonicalScreenSource,
    ConsumerActionCompletion,
    ConsumerActionUpdate,
    ConsumerOffers,
    MarketplaceEntry,
    screens_from,
)

from .configured_configuration_action import (
    PreparedConfiguredConfiguration,
    complete_configured_configuration,
    prepare_configured_configuration,
)
from .configured_installation_action import (
    CompletedConfiguredInstallation,
    InstallationHost,
    PreparedConfiguredInstallation,
    complete_configured_installation,
    prepare_configured_installation,
)
from .configured_repair_action import (
    PreparedConfiguredRepair,
    complete_configured_repair,
    prepare_configured_repair,
)
from .configured_uninstall_action import (
    PreparedConfiguredUninstall,
    complete_configured_uninstall,
    prepare_configured_uninstall,
)
from .consumer_machine import read_consumer_machine, read_installed_inspections
from .consumer_settings import write_consumer_settings
from .credentials import CredentialProviderPort
from .execution import CredentialEffectInterpreter, TerminalHandover
from .maintainer_promotion import (
    PreparedConfiguredCandidatePromotion,
    complete_configured_candidate_promotion,
    prepare_configured_bulk_promotion,
    prepare_configured_candidate_promotion,
)
from .maintainer_sync import (
    complete_configured_source_sync,
    prepare_configured_source_sync,
)
from .maintainer_views import read_maintainer_views
from .object_store import read_object
from .registry_adoption import (
    AdoptedArtifact,
    AdoptionUpstreamCheck,
    PreparedAdoption,
    RepositoryScan,
)
from .registry_bootstrap import (
    RegistryBootstrapReport,
    registry_absent_refusal,
    registry_identity_refusal,
)
from .registry_publication import publish_registry_commit
from .registry_workspace import read_registry_workspace

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
        check.new_version_required,
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
        for profile in profiles:
            if profile in harnesses and coordinate not in hosted[profile]:
                hosted[profile].append(coordinate)
    return tuple(
        HarnessTargetView(profile, tuple(hosted[profile]))
        for profile in profiles
        if hosted[profile]
    )


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
    authoring Source (screen 31a) change the same three derived things, so the value that carries
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
        self, scan: RepositoryScan, selected: tuple[str, ...]
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
    ) -> None:
        if not isinstance(context, ConsumerActionContext):
            raise ValueError("consumer actions need a composed action context")
        self._context = context
        self._machine = context.machine
        self._now = now if now is not None else (lambda: datetime.now(timezone.utc))
        self._pending: _Pending | None = None
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
        self._scanned_repository: RepositoryScan | None = None
        self._adoption_review: MaintainerAdoptionReviewView | None = None
        self._adoption_upstream: AdoptionUpstreamCheck | None = None
        self._promotion_transaction: PreparedCandidatePromotionTransaction | None = None
        self._promotion_result: CandidatePromotionExecutionResult | None = None

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
            )
        )

    # -- the injected boundary ----------------------------------------------- #

    def handle(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if not isinstance(command, ConsumerUiCommand) or command.action is None:
            raise ValueError("a consumer action handler needs a typed action command")
        if command.kind is ConsumerUiCommandKind.PREPARE_ACTION:
            return self._prepare(command)
        if command.kind is ConsumerUiCommandKind.EXECUTE_ACTION:
            return self._execute(command)
        raise ValueError(f"{command.kind.value} is not a consumer action")

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
        if action is ConsumerActionKind.SOURCE_SYNC:
            return self._prepare_source_sync(command)
        if action is ConsumerActionKind.CANDIDATE_PROMOTION:
            return self._prepare_candidate_promotion(command)
        if action is ConsumerActionKind.BULK_PROMOTION:
            return self._prepare_bulk_promotion(command)
        if action in _CREDENTIAL_INTENTS:
            return self._prepare_credential_action(command)
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
            for installation in inspected.value.inspections:
                if observation.reference not in installation.record.credential_references:
                    continue
                inputs = self._installed_inputs(installation.record)
                if isinstance(inputs, Err):
                    continue
                declared.extend(
                    (str(installation.record.coordinate), item.guidance)
                    for item in inputs.value
                    if isinstance(item, SecretInput) and item.id == observation.reference.input
                )
            guidance = gather_credential_guidance(
                observation.reference.input.value,
                declared,
            )
            self._pending = _PendingCredentialAction(
                planned.value,
                provider,
                review_digest,
                guidance,
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
        prepared = self._repository_adoption.prepare(self._scanned_repository, command.selection)
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
        parsed = configured_source_from_input(
            draft.alias,
            SourceKind.REGISTRY_GIT,
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
                    f"  URL: {parsed.value.location}",
                    f"  branch or tag: {parsed.value.ref}",
                    f"  make default: {default}",
                    "  next: download and validate a fresh snapshot, then save the subscription",
                )
            ),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                review_digest=review_digest,
            ),
        )

    def _prepare_source_addition(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        """Review one authoring Source subscription: screen 31a's confirmable value (B-083).

        The kind is checked here rather than only in the schema because this form's *purpose* is
        the 164.2 boundary: an approved registry is screen 21a's subject, and a Maintainer form
        that quietly accepted `registry-git` would be the widening B-083 says must not happen.
        """

        draft = command.source_draft
        if draft is None or self._source_connection is None:
            return self._declined(command, _lines("Source connection is unavailable"))
        if draft.kind not in AUTHORING_SOURCE_KINDS:
            return self._declined(
                command,
                _lines(
                    f"{draft.kind} is not an authoring Source kind",
                    "choose source-git or source-local; an approved registry is connected in "
                    "Registries",
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
                    "Source connection review:",
                    f"  alias: {parsed.value.alias.value}",
                    f"  kind: {parsed.value.kind.value}",
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
        if not raw_id or command.promotion_mode is None:
            return self._declined(
                command,
                _lines("Candidate promotion needs one focused Candidate and promotion mode"),
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
            mode=command.promotion_mode,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        shown = (
            None
            if self._context.maintainer is None
            else self._context.maintainer.registry_diff(raw_id, command.promotion_mode)
        )
        if (
            shown is None
            or shown.plan_digest is None
            or shown.plan_digest != str(prepared.value.review_digest)
        ):
            return self._declined(
                command,
                _lines(
                    "registry transaction changed after screen 43 was composed; review it again"
                ),
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
        if not command.selection or command.promotion_mode is None:
            return self._declined(
                command,
                _lines("bulk promotion needs a selection and a promotion mode"),
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
            mode=command.promotion_mode,
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
                _lines("the selection changed after screen 47 was composed; review it again"),
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

    def _prepare_source_sync(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        if self._data_root is None:
            return self._declined(
                command,
                _lines("Source Sync needs the configured durable data root"),
            )
        if not command.focus:
            return self._declined(command, _lines("Source Sync needs one focused authoring Source"))
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
        keys = self._targets(command)
        if not keys:
            return self._declined(command, _lines("nothing is selected to install"))
        offered = self._offered(keys)
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
                )
            )
        except ValueError as error:
            return self._declined(command, _lines(f"this selection cannot be installed: {error}"))
        return self._offer_installation(command, selection)

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
    ) -> ConsumerActionUpdate:
        context = self._context
        host = self._host(command.install_scope)
        preferred = PythonInstaller(command.python_installer or context.settings.python_installer)
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
            previous=previous,
            preferred_installer=preferred,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        fields_by_row = {
            f"{field.owner}\t{field.input.id.value}": field
            for field in prepared.value.draft.inputs.fields
        }
        sources = tuple(
            OwnedInputSource(
                fields_by_row[row].owner,
                PromptedConfigValue(fields_by_row[row].input.id, value),
            )
            for row, value in command.config_answers
            if row in fields_by_row
        )
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
                )
                if isinstance(prepared, Err):
                    return self._declined(command, _refusal(prepared.diagnostics))
        targets = (
            _installation_targets(prepared.value, host.profiles)
            if command.action is ConsumerActionKind.INSTALL
            else ()
        )
        if not prepared.value.ready:
            config_fields: tuple[tuple[InstallationOwner, ConfigInput], ...] = ()
            for field in prepared.value.draft.inputs.unanswered:
                runtime_input = field.input
                if isinstance(runtime_input, ConfigInput):
                    config_fields = (*config_fields, (field.owner, runtime_input))
            if config_fields:
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
                            owner=str(owner),
                        )
                        for owner, runtime_input in config_fields
                    )
                )
                return ConsumerActionUpdate(
                    self.source(
                        installation_inputs=prepared.value.draft.inputs.views(tuple(observations))
                    ),
                    ConsumerUiEvent(
                        ConsumerUiEventKind.ACTION_PREPARED,
                        action=command.action,
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
        chosen: tuple[str, ...] = ()
        reviewed = prepared.value
        reviewed_host = host
        if command.action is ConsumerActionKind.INSTALL:
            problems = target_choice_problems(plan, command.targets)
            if not problems:
                chosen = command.targets
            if chosen:
                reviewed_host = replace(host, profiles=chosen)
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
                    chosen_targets=chosen,
                )
        self._pending_host = reviewed_host
        self._pending = _PendingInstall(reviewed, previous_receipts, targets, chosen)
        self._pending_action = command.action
        return ConsumerActionUpdate(
            self.source(plan=plan),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_PREPARED,
                action=command.action,
                semantic_identity=plan.semantic_identity,
                selection_identity=plan.selection.semantic_identity,
                review_digest=plan.review_digest,
            ),
        )

    def _prepare_repair(self, command: ConsumerUiCommand) -> ConsumerActionUpdate:
        inspected = self._inspections(self._targets(command))
        if isinstance(inspected, Err):
            return self._declined(command, _refusal(inspected.diagnostics))
        if len(inspected.value) != 1:
            return self._declined(command, _lines("a repair acts on one installation at a time"))
        prepared = prepare_configured_repair(inspected.value[0], policy=self._context.policy)
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        self._pending_host = self._host()
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
        self._pending_host = self._host()
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
        inspected = self._inspections(self._targets(command))
        if isinstance(inspected, Err):
            return self._declined(command, _refusal(inspected.diagnostics))
        host = self._host()
        prepared = prepare_configured_uninstall(
            tuple(item.record for item in inspected.value),
            host=host,
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        self._pending_host = host
        self._pending = prepared.value
        self._pending_action = command.action
        # One artifact per removal review, because screen 18 renders one lifecycle plan. A
        # Collection removal is a transaction and reaches this seam when Collections do (B-031).
        return ConsumerActionUpdate(
            self.source(lifecycle=project_lifecycle_plan(prepared.value.proposal.lifecycle[0])),
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
        inspected = read_installed_inspections(
            state_root=host.state_root,
            harness_root=host.harness_root,
            credential_providers=self._context.credential_providers,
            scope=host.scope,
            profiles=host.profiles,
        )
        if isinstance(inspected, Err):
            return inspected
        by_coordinate = {item.coordinate: item for item in inspected.value.inspections}
        missing = [item for item in coordinates if item not in by_coordinate]
        if missing:
            return Err(
                (
                    Diagnostic(
                        CONSUMER_ACTION_NOT_INSTALLED,
                        Severity.ERROR,
                        "nothing canonical is installed here as " + ", ".join(sorted(missing)),
                        remediation=("open Installed and choose a recorded installation",),
                    ),
                )
            )
        return Ok(tuple(by_coordinate[item] for item in coordinates))

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

        The row has to be a registry.  An authoring Source holds Candidates that a maintainer
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
                    f"{alias} is an authoring Source, not a registry; "
                    "its Candidates are promoted in Maintainer Mode"
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
                if item.alias.value == command.focus and item.kind is SourceKind.REGISTRY_GIT
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
                f"Source {pending.draft.alias} added.",
                "",
                "Run Source Sync to discover artifacts and create or refresh Candidates, "
                "including new upstream versions. Adding a Source only connects it.",
                "",
                "Source Sync does not promote Candidates or update installed artifacts.",
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
        if (
            command.action is ConsumerActionKind.INSTALL
            and command.targets != pending.chosen_targets
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
            interactive_credentials=True,
            credential_handover=self._terminal_handover,
            observe=None if self._progress is None else observe,
        )
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        self._machine = completed.value.machine
        receipt = completed.value.action.flow.outcome
        assert receipt is not None
        completion = None
        if self._completion_factory is not None:
            completion = self._completion_factory(
                completed.value,
                "update" if command.action is ConsumerActionKind.UPDATE else "install",
                lambda remaining: self.source(
                    transaction=receipt,
                    pending_setup=remaining,
                ),
                self._reviewed_host(),
            )
        return self._recorded(
            command,
            receipt.recorded_at,
            completion=completion,
            transaction=receipt,
            pending_setup=completed.value.pending_setup,
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
