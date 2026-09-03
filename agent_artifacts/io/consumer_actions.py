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

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Literal

from agent_artifacts.application.consumer_session import ConsumerMachine, InstalledInspection
from agent_artifacts.application.consumer_ui import (
    ConsumerActionKind,
    ConsumerUiCommand,
    ConsumerUiCommandKind,
    ConsumerUiEvent,
    ConsumerUiEventKind,
)
from agent_artifacts.application.consumer_views import (
    ConsumerSettings,
    LifecyclePlanView,
    project_lifecycle_plan,
)
from agent_artifacts.application.installed_setup import DeclaredArtifactSetup
from agent_artifacts.application.maintainer_sync import PreparedSourceSync
from agent_artifacts.application.maintainer_views import (
    MaintainerViews,
    parse_validation_row,
    project_maintainer_registry_commit,
    project_maintainer_registry_validation,
    project_source_sync_result,
    project_source_sync_review,
)
from agent_artifacts.configuration.policy import EffectiveConfiguration
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

__all__ = [
    "CONSUMER_ACTION_NOT_INSTALLED",
    "CONSUMER_ACTION_NOT_OFFERED",
    "ConsumerActionContext",
    "LocalConsumerActions",
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


def _refusal(diagnostics: tuple[Diagnostic, ...]) -> tuple[str, ...]:
    return _lines(
        *(item.message for item in diagnostics),
        *(remediation for item in diagnostics for remediation in item.remediation),
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


#: What one reviewed-but-unconfirmed action is holding. Each carries the review digest the
#: confirmation has to name, so nothing runs against a plan nobody read.
_Pending = (
    _PendingInstall
    | PreparedConfiguredRepair
    | PreparedConfiguredUninstall
    | PreparedSourceSync
    | PreparedConfiguredCandidatePromotion
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
        if action is ConsumerActionKind.UPDATE:
            return self._prepare_update(command)
        if action is ConsumerActionKind.VERIFY_REPAIR:
            return self._prepare_repair(command)
        if action is ConsumerActionKind.SOURCE_SYNC:
            return self._prepare_source_sync(command)
        if action is ConsumerActionKind.CANDIDATE_PROMOTION:
            return self._prepare_candidate_promotion(command)
        if action is ConsumerActionKind.BULK_PROMOTION:
            return self._prepare_bulk_promotion(command)
        return self._prepare_uninstall(command)

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
        if isinstance(pending, _PendingInstall):
            expected = pending.prepared.review_digest
        else:
            expected = pending.review_digest
        if command.review_digest != str(expected):
            return self._failed(
                command,
                _lines(
                    "this confirmation names a different plan than the one prepared; "
                    "review it again"
                ),
            )
        if isinstance(pending, _PendingInstall):
            return self._execute_installation(command, pending)
        if isinstance(pending, PreparedConfiguredRepair):
            return self._execute_repair(command, pending)
        if isinstance(pending, PreparedSourceSync):
            return self._execute_source_sync(command, pending)
        if isinstance(pending, PreparedConfiguredCandidatePromotion):
            return self._execute_candidate_promotion(command, pending)
        assert isinstance(pending, PreparedConfiguredUninstall)
        return self._execute_uninstall(command, pending)

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
