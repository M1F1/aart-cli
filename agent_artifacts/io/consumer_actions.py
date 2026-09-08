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

from agent_artifacts.application.consumer_session import ConsumerMachine, InstalledInspection
from agent_artifacts.application.consumer_ui import (
    AUTHORING_SOURCE_KINDS,
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
    RegistryDraft,
    RegistryInitDraft,
    RepositoryScanDraft,
    SourceDraft,
)
from agent_artifacts.application.consumer_views import (
    ConsumerSettings,
    LifecyclePlanView,
    project_lifecycle_plan,
)
from agent_artifacts.application.installed_setup import DeclaredArtifactSetup
from agent_artifacts.application.maintainer_sync import PreparedSourceSync
from agent_artifacts.application.maintainer_views import (
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
from agent_artifacts.configuration.model import ConfiguredSource, SourceKind
from agent_artifacts.configuration.policy import EffectiveConfiguration
from agent_artifacts.configuration.schema import configured_source_from_input
from agent_artifacts.domain.candidates import CandidateId
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ArtifactCoordinate, SourceAlias
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.receipts import ArtifactReceipt
from agent_artifacts.domain.reconciliation import DesiredState
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ArtifactRequest, ArtifactSelection, VersionConstraint
from agent_artifacts.tui_consumer import (
    CanonicalScreenSource,
    ConsumerActionCompletion,
    ConsumerActionUpdate,
    ConsumerOffers,
    MarketplaceEntry,
    screens_from,
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
from .consumer_machine import read_installed_inspections
from .consumer_settings import write_consumer_settings
from .credentials import CredentialProviderPort
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
from .registry_adoption import (
    AdoptedArtifact,
    AdoptionUpstreamCheck,
    PreparedAdoption,
    RepositoryScan,
)
from .registry_bootstrap import RegistryBootstrapReport, registry_identity_refusal

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
_COMMAND_MARKERS = ("aart ", "`", "$ ", "git ")


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
    return _lines(*lines, *steps)


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
SourceConnectionPort = Callable[[SourceDraft], Result[RegistryConnectionSnapshot]]
RegistryBootstrapPort = Callable[[RegistryInitDraft], Result[RegistryBootstrapCompletion]]
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
    | _PendingSourceAddition
    | _PendingRegistryInit
    | PreparedAdoption
)

ConfiguredCompletionFactory = Callable[
    [
        CompletedConfiguredInstallation,
        Literal["install", "update"],
        Callable[[tuple[DeclaredArtifactSetup, ...]], CanonicalScreenSource],
    ],
    ConsumerActionCompletion | None,
]


class LocalConsumerActions:
    """One machine's install, update, verify-and-repair and uninstall, behind `handle`.

    The prepared action is held between the two commands rather than recomputed, because what is
    executed has to be the plan somebody reviewed. The digest is checked on the way in regardless:
    holding it is a convenience, and the confirmation is the authority.
    """

    def __init__(
        self,
        context: ConsumerActionContext,
        *,
        now=None,
        data_root: str | None = None,
        completion_factory: ConfiguredCompletionFactory | None = None,
        registry_connection: RegistryConnectionPort | None = None,
        registry_refresh: RegistryRefreshPort | None = None,
        source_connection: SourceConnectionPort | None = None,
        registry_bootstrap: RegistryBootstrapPort | None = None,
        repository_scan: RepositoryScanPort | None = None,
        repository_adoption: RepositoryAdoptionPort | None = None,
        adopted_artifacts: tuple[AdoptedArtifact, ...] = (),
        repository_upstream_check: RepositoryUpstreamCheckPort | None = None,
        repository_adopted_list: RepositoryAdoptedListPort | None = None,
    ) -> None:
        if not isinstance(context, ConsumerActionContext):
            raise ValueError("consumer actions need a composed action context")
        self._context = context
        self._machine = context.machine
        self._now = now if now is not None else (lambda: datetime.now(timezone.utc))
        self._pending: _Pending | None = None
        self._pending_action: ConsumerActionKind | None = None
        self._data_root = data_root
        self._completion_factory = completion_factory
        self._registry_connection = registry_connection
        self._registry_refresh = registry_refresh
        self._source_connection = source_connection
        self._registry_bootstrap = registry_bootstrap
        self._repository_scan = repository_scan
        self._repository_adoption = repository_adoption
        self._adopted_artifacts = adopted_artifacts
        self._repository_upstream_check = repository_upstream_check
        self._repository_adopted_list = repository_adopted_list
        self._scanned_repository: RepositoryScan | None = None
        self._adoption_review: MaintainerAdoptionReviewView | None = None
        self._adoption_upstream: AdoptionUpstreamCheck | None = None

    # -- preferences --------------------------------------------------------- #

    @property
    def settings(self) -> ConsumerSettings:
        """What screen 28 was last told, which is what a session opens on."""

        return self._context.settings

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
    ) -> CanonicalScreenSource:
        """The screens for the machine as it currently stands, plus whatever a flow is holding."""

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
        if action is ConsumerActionKind.VERIFY_REPAIR:
            return self._prepare_repair(command)
        if action is ConsumerActionKind.REGISTRY_SYNC:
            return self._prepare_registry_refresh(command)
        if action is ConsumerActionKind.SOURCE_SYNC:
            return self._prepare_source_sync(command)
        if action is ConsumerActionKind.CANDIDATE_PROMOTION:
            return self._prepare_candidate_promotion(command)
        if action is ConsumerActionKind.BULK_PROMOTION:
            return self._prepare_bulk_promotion(command)
        return self._prepare_uninstall(command)

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
                    "  next: acquire a pinned snapshot, discover declared aart.yaml/aart.json "
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

        draft = command.registry_init_draft
        if draft is None or self._registry_bootstrap is None:
            return self._declined(command, _lines("registry initialization is unavailable"))
        refused = registry_identity_refusal(
            registry_id=draft.registry_id,
            display_name=draft.display_name,
            usage_reporting_repository=draft.usage_reporting or None,
        )
        if refused is not None:
            return self._declined(command, _refusal(refused.diagnostics))
        workspace = self._context.host.project_root
        identity = json.dumps(
            {
                "workspace": workspace,
                "registry_id": draft.registry_id,
                "display_name": draft.display_name,
                "usage_reporting": draft.usage_reporting,
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
                    f"  usage reporting: {draft.usage_reporting or 'not enabled'}",
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
            registry_root=self._context.host.harness_root,
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
            registry_root=self._context.host.harness_root,
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
        prepared = prepare_configured_installation(
            context.effective,
            selection,
            host=context.host,
            sources=(),
            policy=context.policy,
            selected_remediations=None,
            credential_providers=context.credential_providers,
            resolvers=context.credential_providers,
            previous=previous,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
        if not prepared.value.ready:
            # Unanswered inputs are not a refusal -- screen 07 exists because the answer is "not
            # yet" -- but this shell has no way to collect one, so it says what it is waiting for
            # rather than offering a plan that cannot be confirmed (B-036).
            waiting = ", ".join(
                item.input.id.value for item in prepared.value.draft.inputs.unanswered
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
        plan = action.flow.plan
        self._pending = _PendingInstall(prepared.value, previous_receipts)
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
        prepared = prepare_configured_uninstall(
            tuple(item.record for item in inspected.value),
            host=self._context.host,
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
        )
        if isinstance(prepared, Err):
            return self._declined(command, _refusal(prepared.diagnostics))
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
        host = self._context.host
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
        **views,
    ) -> ConsumerActionUpdate:
        self._pending, self._pending_action = None, None
        return ConsumerActionUpdate(
            self.source(**views),
            ConsumerUiEvent(
                ConsumerUiEventKind.ACTION_RECORDED,
                action=command.action,
                text=recorded_at,
            ),
            completion,
        )

    def _failed(self, command: ConsumerUiCommand, notice: tuple[str, ...]) -> ConsumerActionUpdate:
        """An execution that did not record anything, drawn on the screen it was run from.

        `text` is empty, which `_action_recorded` reads as nothing having been recorded, so the
        session stays on the running screen instead of opening a result that does not exist.
        """

        self._pending, self._pending_action = None, None
        return ConsumerActionUpdate(
            self.source(notice=notice),
            ConsumerUiEvent(ConsumerUiEventKind.ACTION_RECORDED, action=command.action),
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
        if isinstance(pending, _PendingSourceAddition):
            return self._execute_source_addition(command, pending)
        if isinstance(pending, _PendingRegistryInit):
            return self._execute_registry_init(command, pending)
        if isinstance(pending, PreparedAdoption):
            return self._execute_repository_adoption(command, pending)
        if isinstance(pending, PreparedConfiguredRepair):
            return self._execute_repair(command, pending)
        if isinstance(pending, PreparedSourceSync):
            return self._execute_source_sync(command, pending)
        if isinstance(pending, PreparedConfiguredCandidatePromotion):
            return self._execute_candidate_promotion(command, pending)
        assert isinstance(pending, PreparedConfiguredUninstall)
        return self._execute_uninstall(command, pending)

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
                registry_root=self._context.host.harness_root,
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
        recorded_at, _today = self._moment()
        return self._recorded(command, recorded_at)

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
            registry_root=self._context.host.harness_root,
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
            registry_root=self._context.host.harness_root,
        )
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        assert self._data_root is not None
        # The write just moved the registry checkout, so screen 46's working-tree observation and
        # every Candidate view planned against that tree are stale the moment the commit lands.
        refreshed = read_maintainer_views(
            self._context.effective,
            data_root=self._data_root,
            observed_at_epoch_seconds=int(self._now().timestamp()),
            registry_root=self._context.host.harness_root,
        )
        if isinstance(refreshed, Ok):
            self._context = replace(self._context, maintainer=refreshed.value)
        recorded_at, _today = self._moment()
        return self._recorded(
            command,
            recorded_at,
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
        recorded_at, today = self._moment()
        completed = complete_configured_installation(
            pending.prepared,
            expected_review_digest=pending.prepared.review_digest,
            host=self._context.host,
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
            previous_receipts=pending.previous_receipts,
            recorded_at=recorded_at,
            today=today,  # type: ignore[arg-type]
            offline=self._context.offline,
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
            )
        return self._recorded(
            command,
            receipt.recorded_at,
            completion=completion,
            transaction=receipt,
            pending_setup=completed.value.pending_setup,
        )

    def _execute_repair(
        self, command: ConsumerUiCommand, pending: PreparedConfiguredRepair
    ) -> ConsumerActionUpdate:
        recorded_at, today = self._moment()
        completed = complete_configured_repair(
            pending,
            expected_review_digest=pending.review_digest,
            host=self._context.host,
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
            host=self._context.host,
            policy=self._context.policy,
            credential_providers=self._context.credential_providers,
            recorded_at=recorded_at,
            today=today,  # type: ignore[arg-type]
        )
        if isinstance(completed, Err):
            return self._failed(command, _refusal(completed.diagnostics))
        self._machine = completed.value.machine
        return self._recorded(command, completed.value.recorded.receipt.recorded_at)
