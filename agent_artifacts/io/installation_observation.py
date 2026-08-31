"""What is on this machine right now, for an installation that has not happened yet.

Planning an install has to know what is already at the paths it would occupy. Not as a formality:
something already there is drift somebody reviews, not a file to quietly overwrite, and an install
planned against an assumption that nothing is there is exactly how a machine loses work nobody knew
about (D-029).

The receipt observed is the *intended* one -- what this install would leave behind if it ran. That
is the right thing to look for before a first install, because it names the paths in question, and
it is the same value the executor compares against afterwards, so before and after are measured in
one vocabulary rather than two.

Nothing here reads a secret value. A credential is inspected through its provider, which answers
present, absent, invalid or unknown about a reference and never with what it holds. A provider that
was not supplied leaves the reference unknown rather than absent, for the same reason it does
everywhere else: nobody looked is not the same fact as nothing is there.
"""

from __future__ import annotations

from agent_artifacts.application.installation_proposal import (
    PlannedArtifact,
    PlannedInstallation,
    PlannedPlacement,
    artifact_desired_state,
    intended_placement_receipt,
    intended_receipt,
)
from agent_artifacts.application.installed_state import (
    current_state_from_observation,
    current_state_from_placement,
)
from agent_artifacts.domain.credentials import CredentialReference, CredentialState
from agent_artifacts.domain.reconciliation import ComponentState, CurrentState
from agent_artifacts.domain.result import Err

from .credentials import CredentialProviderPort
from .harness import LocalHarnessRegistry
from .runtime_projection import observe_installation, observe_placement

__all__ = ["COMPONENT_STATE", "credential_component_states", "observe_planned_installation"]


#: How a credential's answer becomes a reconciliation component's. `UNKNOWN` maps to `UNKNOWN`
#: rather than collapsing into `ABSENT`, which is what keeps an uninspectable credential from
#: reading as a missing one and planning a store nobody asked for.
COMPONENT_STATE: dict[CredentialState, ComponentState] = {
    CredentialState.PRESENT: ComponentState.MATCHED,
    CredentialState.ABSENT: ComponentState.ABSENT,
    CredentialState.INVALID: ComponentState.DIVERGENT,
    CredentialState.UNKNOWN: ComponentState.UNKNOWN,
}


def credential_component_states(
    references: tuple[CredentialReference, ...],
    providers: tuple[CredentialProviderPort, ...] = (),
) -> tuple[tuple[str, ComponentState], ...]:
    """Ask each reference's provider about it, and say unknown where there is nobody to ask.

    A provider that was supplied and then failed also answers unknown here, which is a weaker
    response than :func:`read_consumer_machine` gives -- it refuses. The difference is what the two
    are for. Reading a machine reports what is true, and a credential nobody could inspect is a
    problem worth surfacing before somebody acts on the report. Planning asks a narrower question:
    is there anything to do about this credential? Unknown answers it correctly and conservatively
    -- the plan offers to store and verify the value -- while refusing would make one flaky provider
    block an install of artifacts that do not depend on it.
    """

    by_provider = {item.provider: item for item in providers}
    states: list[tuple[str, ComponentState]] = []
    for reference in references:
        provider = by_provider.get(reference.provider.provider)
        if provider is None:
            states.append((reference.input.value, ComponentState.UNKNOWN))
            continue
        observed = provider.inspect(reference)
        states.append(
            (
                reference.input.value,
                ComponentState.UNKNOWN
                if isinstance(observed, Err)
                else COMPONENT_STATE[observed.value.state],
            )
        )
    return tuple(states)


def observe_planned_installation(
    planned: PlannedArtifact,
    *,
    registry: LocalHarnessRegistry,
    credential_providers: tuple[CredentialProviderPort, ...] = (),
) -> CurrentState:
    """Measure the machine where `planned` would install, in the vocabulary it will be judged in.

    An artifact a harness reads is measured at the paths it would be delivered to, and nowhere
    else. There is no harness registry entry to look up and no credential to ask a provider about,
    so neither is consulted -- asking would report an absent launcher for something that was never
    going to have one.
    """

    if isinstance(planned, PlannedPlacement):
        placed = intended_placement_receipt(planned)
        return current_state_from_placement(
            artifact_desired_state(planned), placed, observe_placement(placed)
        )
    if not isinstance(planned, PlannedInstallation):
        raise ValueError("observing a planned installation needs a planned installation")
    desired = artifact_desired_state(planned)
    receipt = intended_receipt(planned)
    return current_state_from_observation(
        desired,
        receipt,
        observe_installation(receipt, registry=registry),
        credentials=credential_component_states(receipt.credentials, credential_providers),
    )
