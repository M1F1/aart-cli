"""The one adapter a public command or the persistent shell calls to install what is configured.

`prepare_installation_action` and `complete_installation_action` are the application operation
(D-074), and everything they need is an explicit port: resolution, placement, inspection,
observation, interpreters, the lease, the receipt store and the clock. Somebody has to supply those
from this machine, and until now that somebody would have been each caller -- the shell's action
handler and every one of `install`/`update`/`uninstall`. Two copies of that composition disagree the
first time one of them changes, and the disagreement does not announce itself, because both copies
install something.

This module is that composition, once. It owns no policy of its own: what may be installed is still
decided by the configured approved registry snapshot, what is answered is still decided by the
screen-07 form, and what is confirmed is still the review digest the caller passes back.

Two properties are load-bearing and are tested rather than asserted here. Preparation touches
nothing on the target machine -- it may synchronize an immutable object into the store, which is
content-addressed and cannot change what is installed, but it writes no artifact tree and registers
no harness. And completion hands back a machine that was read from disk afterwards, never one
assembled from what the install believed it did: an install that half-worked has to be visible as
what it left behind, not as what it intended.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date

from agent_artifacts.application.consumer_session import ConsumerMachine
from agent_artifacts.application.installation_action import (
    CompletedInstallationAction,
    PreparedInstallationAction,
    complete_installation_action,
    prepare_installation_action,
)
from agent_artifacts.application.marketplace_resolution import ResolutionPolicy
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import Scope
from agent_artifacts.domain.identifiers import ArtifactCoordinate, ObjectDigest
from agent_artifacts.domain.inputs import InputValueSource
from agent_artifacts.domain.inspection import (
    EnvironmentFacts,
    RemediationCapability,
    RemediationCapabilityKind,
)
from agent_artifacts.domain.policies import EffectivePolicy
from agent_artifacts.domain.python_runtime import PythonInstaller
from agent_artifacts.domain.receipts import ArtifactReceipt
from agent_artifacts.domain.reconciliation import CurrentState, DesiredState
from agent_artifacts.domain.remediations import Remediation
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ArtifactSelection

from .configured_installation import (
    ConfiguredInstallationDraft,
    prepare_configured_installation_draft,
)
from .consumer_machine import read_consumer_machine
from .credentials import CredentialProviderPort
from .environment_inspection import LocalEnvironmentInspector, platform_name
from .execution import LocalMutationLock
from .harness import LocalHarnessRegistry
from .installation_execution import interpreters_for
from .installation_observation import (
    observe_planned_installation,
    observe_recorded_installation,
)
from .python_runtime import observe_python_installers
from .receipt_store import LocalReceiptStore

__all__ = [
    "CONFIGURED_ACTION_INVALID",
    "CompletedConfiguredInstallation",
    "InstallationHost",
    "PreparedConfiguredInstallation",
    "complete_configured_installation",
    "local_remediation_capabilities",
    "prepare_configured_installation",
]

CONFIGURED_ACTION_INVALID = DiagnosticCode("configured-installation-action-invalid")


def _error(message: str) -> Err:
    return Err((Diagnostic(CONFIGURED_ACTION_INVALID, Severity.ERROR, message),))


@dataclass(frozen=True, slots=True)
class InstallationHost:
    """Where one configured install reads, writes and registers on this machine.

    The state and harness roots are derived rather than supplied. Preparation and completion are two
    calls that have to act on the same machine, and a pair of roots passed twice is a pair of roots
    that can be passed differently -- an install prepared against one scope and completed against
    another would take the wrong lease and record into the wrong store.
    """

    data_root: str
    project_root: str
    user_home: str
    scope: Scope
    profiles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, label in (
            (self.data_root, "data root"),
            (self.project_root, "project root"),
            (self.user_home, "user home"),
        ):
            if not isinstance(value, str) or not os.path.isabs(value):
                raise ValueError(f"an installation host needs an absolute {label}")
        if not isinstance(self.scope, Scope):
            raise ValueError("an installation host needs an installation scope")
        if not isinstance(self.profiles, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.profiles
        ):
            raise ValueError("installation host profiles are invalid")

    @property
    def state_root(self) -> str:
        return os.path.join(self.data_root, "state")

    @property
    def harness_root(self) -> str:
        """The root a harness's settings file is resolved against, which is the scope's own root."""

        return self.project_root if self.scope is Scope.PROJECT else self.user_home

    @property
    def lock_scope(self) -> str:
        return f"{self.scope.value}:{self.harness_root}"


def local_remediation_capabilities(
    host: InstallationHost,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    *,
    interpreter: str | None = None,
) -> tuple[RemediationCapability, ...]:
    """What this machine could actually do about a requirement it fails to meet.

    These decide which remediations a plan may offer, so every one of them is measured or supplied:
    a dependency backend is reported only when this interpreter can run it, a credential provider
    only when an adapter for it was handed in, and a harness only when it is a profile this install
    is targeting. Nothing is assumed to exist because it usually does.
    """

    return (
        *observe_python_installers(interpreter=interpreter),
        *(
            RemediationCapability(RemediationCapabilityKind.CREDENTIAL_PROVIDER, item.provider)
            for item in credential_providers
        ),
        *(
            RemediationCapability(RemediationCapabilityKind.HARNESS_CONFIGURATION, profile)
            for profile in host.profiles
        ),
    )


@dataclass(frozen=True, slots=True)
class PreparedConfiguredInstallation:
    """A reviewable action, or the form that is still missing an answer.

    `action` is `None` exactly while the draft is not ready. Unanswered inputs are not a refusal --
    screen 07 exists because the answer is "not yet" -- so the form comes back rather than an error,
    and the caller collects what is missing and prepares again.
    """

    draft: ConfiguredInstallationDraft
    action: PreparedInstallationAction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.draft, ConfiguredInstallationDraft) or (
            self.action is not None and not isinstance(self.action, PreparedInstallationAction)
        ):
            raise ValueError("a prepared configured installation is invalid")
        if self.draft.ready is not (self.action is not None):
            raise ValueError("a prepared configured installation contradicts its own form state")

    @property
    def ready(self) -> bool:
        return self.action is not None

    @property
    def review_digest(self) -> ObjectDigest | None:
        return None if self.action is None else self.action.review_digest


@dataclass(frozen=True, slots=True)
class CompletedConfiguredInstallation:
    """What ran and was recorded, beside the machine as it stands afterwards."""

    action: CompletedInstallationAction
    machine: ConsumerMachine

    def __post_init__(self) -> None:
        if not isinstance(self.action, CompletedInstallationAction) or not isinstance(
            self.machine, ConsumerMachine
        ):
            raise ValueError("a completed configured installation is invalid")


def prepare_configured_installation(
    effective: object,
    selection: ArtifactSelection,
    *,
    host: InstallationHost,
    sources: tuple[InputValueSource, ...],
    policy: EffectivePolicy,
    selected_remediations: tuple[Remediation, ...] | None,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    resolvers: tuple[object, ...] = (),
    base_interpreter: str | None = None,
    resolution_policy: ResolutionPolicy | None = None,
    preferred_installer: PythonInstaller | None = None,
    previous: tuple[tuple[ArtifactCoordinate, DesiredState], ...] = (),
) -> Result[PreparedConfiguredInstallation]:
    """Resolve, place and offer one configured Selection without mutating the target machine.

    `previous` is how a caller says this Selection replaces versions already installed here. It
    comes from the receipts on this machine rather than from anything resolved, which is why it is
    the caller's to supply: this module composes the install, and what is already installed is a
    fact about the machine that was read before the composition began.
    """

    if not isinstance(host, InstallationHost):
        return _error("preparing a configured installation needs an installation host")
    drafted = prepare_configured_installation_draft(
        effective,  # type: ignore[arg-type]
        selection,
        data_root=host.data_root,
        project_root=host.project_root,
        scope=host.scope,
        profiles=host.profiles,
        sources=sources,
        policy=policy,
        harness_root=host.harness_root,
        resolution_policy=resolution_policy,
        preferred_installer=preferred_installer,
    )
    if isinstance(drafted, Err):
        return drafted
    draft = drafted.value
    if not draft.ready:
        return Ok(PreparedConfiguredInstallation(draft))

    placements = draft.prepared_placements()
    if isinstance(placements, Err):
        return placements
    capabilities = local_remediation_capabilities(
        host, credential_providers, interpreter=base_interpreter
    )
    registry = LocalHarnessRegistry(host.harness_root)
    prepared = prepare_installation_action(
        draft.selection,
        placements.value,
        policy=policy,
        facts=EnvironmentFacts(platform_name(), remediation_capabilities=capabilities),
        inspect=LocalEnvironmentInspector(capabilities),
        observe=lambda planned: observe_planned_installation(
            planned, registry=registry, credential_providers=credential_providers
        ),
        selected_remediations=selected_remediations,
        base_interpreter=base_interpreter or sys.executable,
        resolvers=resolvers,  # type: ignore[arg-type]
        previous=previous,
    )
    if isinstance(prepared, Err):
        return prepared
    try:
        return Ok(PreparedConfiguredInstallation(draft, prepared.value))
    except ValueError as error:
        return _error(f"this configured installation cannot be prepared: {error}")


def complete_configured_installation(
    prepared: PreparedConfiguredInstallation,
    *,
    expected_review_digest: ObjectDigest | None,
    host: InstallationHost,
    policy: EffectivePolicy,
    recorded_at: str,
    today: date,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
    previous_receipts: tuple[tuple[ArtifactCoordinate, ArtifactReceipt], ...] = (),
    timeout_seconds: float = 900.0,
    offline: bool = False,
) -> Result[CompletedConfiguredInstallation]:
    """Execute the confirmed review, record it, and re-read the machine it left behind.

    `previous_receipts` are what an update is leaving. The executor asks for the previous state
    when it has to put a failed update back, and that state can only be measured against the
    receipt the version being replaced wrote -- so a caller that supplies `previous` states to
    preparation supplies the matching receipts here.
    """

    if not isinstance(prepared, PreparedConfiguredInstallation) or not isinstance(
        host, InstallationHost
    ):
        return _error("completing a configured installation needs a prepared action and a host")
    action = prepared.action
    if action is None:
        names = ", ".join(item.input.id.value for item in prepared.draft.inputs.unanswered)
        return _error(f"this installation is still waiting for its inputs: {names}")
    if not isinstance(expected_review_digest, ObjectDigest):
        return _error("completing a configured installation needs the confirmed review digest")

    registry = LocalHarnessRegistry(host.harness_root)
    interpreters = interpreters_for(
        action.installations,
        registry=registry,
        credential_providers=credential_providers,
        timeout_seconds=timeout_seconds,
        offline=offline,
    )
    if isinstance(interpreters, Err):
        return interpreters

    planned = {installation.coordinate: installation for installation in action.installations}
    recorded = dict(previous_receipts)

    def inspect(desired: DesiredState) -> CurrentState:
        # Two vocabularies, and which one applies is decided by the state being asked about. A
        # coordinate this action planned is measured against the plan. The version an update is
        # leaving was never planned here, so it is measured against the receipt it wrote -- and a
        # state that is neither is a bug in this composition rather than a fact about the machine,
        # which is why it refuses instead of measuring something adjacent and calling it the answer.
        installation = planned.get(desired.artifact)
        if installation is not None:
            return observe_planned_installation(
                installation,
                registry=registry,
                credential_providers=credential_providers,
            )
        receipt = recorded.get(desired.artifact)
        if receipt is None:
            raise ValueError(
                f"{desired.artifact} is neither planned by this action nor recorded as the "
                "version it replaces, so nothing here can measure it"
            )
        return observe_recorded_installation(
            desired,
            receipt,
            registry=registry,
            credential_providers=credential_providers,
        )

    completed = complete_installation_action(
        action,
        expected_review_digest=expected_review_digest,
        policy=policy,
        interpreters=interpreters.value,
        inspect=inspect,
        lock=LocalMutationLock(host.state_root, host.lock_scope),
        store=LocalReceiptStore(host.state_root),
        recorded_at=recorded_at,
    )
    if isinstance(completed, Err):
        return completed

    machine = read_consumer_machine(
        state_root=host.state_root,
        harness_root=host.harness_root,
        today=today,
        project_root=host.project_root,
        user_home=host.user_home,
        data_root=host.data_root,
        credential_providers=credential_providers,
    )
    if isinstance(machine, Err):
        return machine
    try:
        return Ok(CompletedConfiguredInstallation(completed.value, machine.value))
    except ValueError as error:
        return _error(f"this configured installation cannot be completed: {error}")
