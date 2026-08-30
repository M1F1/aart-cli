"""The bridge from one installed artifact to the states a reconciler compares.

CP-10 produced a receipt and an observation of a real installation. This turns both into the
component algebra, so a launcher somebody edited becomes a launcher repair and a harness entry
somebody deleted becomes a harness repair -- and neither becomes a reinstall.

Desired state is derived from the receipt plus the things a receipt deliberately does not hold: the
base interpreter an environment is built from, and the dependency descriptor. Those come from the
plan, which is where §158 says they belong. A receipt records what happened, not what should.
"""

from __future__ import annotations

from agent_artifacts.domain.credentials import CredentialReference
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CreatePythonEnvironment,
    InstallPythonDependencies,
    ReplaceCredential,
    StoreCredential,
    WriteFile,
)
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import InstallationReceipt
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    ObservedComponent,
)

from .installation_verification import InstallationObservation, VerificationFinding

__all__ = [
    "current_state_from_observation",
    "desired_state_from_receipt",
]


def _credential_component(reference: CredentialReference) -> DesiredComponent:
    name = str(reference.input)
    provider = reference.provider.provider
    return DesiredComponent(
        ComponentId(Component.CREDENTIAL, name),
        (StoreCredential(str(reference), provider),),
        (ReplaceCredential(str(reference), provider),),
    )


def desired_state_from_receipt(
    coordinate: ArtifactCoordinate,
    receipt: InstallationReceipt,
    *,
    base_interpreter: str | None = None,
    dependencies: tuple[str, str, str] | None = None,
) -> DesiredState:
    """The component-level desired state this receipt describes.

    `base_interpreter` and `dependencies` are optional because they are plan knowledge, not receipt
    knowledge. Omitting them omits those components rather than inventing them: a reconciler that
    guessed which interpreter an environment was built from would repair it into something else.
    """

    if not isinstance(receipt, InstallationReceipt):
        raise ValueError("desired state needs an installation receipt")

    environment = ArtifactEnvironment(receipt.artifact, receipt.root)
    components: list[DesiredComponent] = []

    if base_interpreter is not None:
        components.append(
            DesiredComponent(
                ComponentId(Component.RUNTIME_ENVIRONMENT),
                (
                    CreatePythonEnvironment(
                        receipt.artifact, environment.environment, base_interpreter
                    ),
                ),
            )
        )
    if dependencies is not None:
        descriptor, descriptor_kind, installer = dependencies
        components.append(
            DesiredComponent(
                ComponentId(Component.RUNTIME_DEPENDENCIES),
                (
                    InstallPythonDependencies(
                        environment.environment, descriptor, descriptor_kind, installer
                    ),
                ),
            )
        )

    components.append(
        DesiredComponent(
            ComponentId(Component.LAUNCHER),
            (WriteFile(receipt.launcher, str(receipt.launcher_digest), True),),
        )
    )
    components.extend(_credential_component(reference) for reference in receipt.credentials)
    components.extend(
        DesiredComponent(
            ComponentId(Component.HARNESS, registration.target.harness),
            (
                ConfigureHarness(
                    registration.target.harness,
                    receipt.artifact,
                    registration.target.settings_file,
                ),
            ),
        )
        for registration in receipt.registrations
    )
    return DesiredState(coordinate, tuple(components))


def _launcher_state(findings: frozenset[VerificationFinding]) -> ComponentState:
    if VerificationFinding.LAUNCHER_MISSING in findings:
        return ComponentState.ABSENT
    if (
        VerificationFinding.LAUNCHER_CHANGED in findings
        or VerificationFinding.LAUNCHER_NOT_EXECUTABLE in findings
    ):
        return ComponentState.DIVERGENT
    return ComponentState.MATCHED


def current_state_from_observation(
    desired: DesiredState,
    receipt: InstallationReceipt,
    observation: InstallationObservation,
    *,
    findings: tuple[VerificationFinding, ...] | None = None,
    credentials: tuple[tuple[str, ComponentState], ...] = (),
) -> CurrentState:
    """What was actually found, in the same vocabulary `desired` uses.

    The desired state is an argument rather than a coordinate because the two have to be paired.
    Only components `desired` describes are reported, so a partial desired state -- one built
    without a base interpreter, say -- does not turn a perfectly good environment into something
    unexpected. Unexpected means "installed and nothing wants it", and that claim is only honest
    against a complete description.

    A component `desired` names and this observation did not cover is simply left out, so the
    comparison reports it as unobserved rather than as fine. That is the point of having an
    unobserved kind at all.
    """

    from .installation_verification import verify_installation

    if not isinstance(desired, DesiredState):
        raise ValueError("current state must be paired with the desired state it answers")
    if findings is None:
        findings = verify_installation(receipt, observation)
    found = frozenset(findings)
    wanted = {component.id for component in desired.components}

    components: list[ObservedComponent] = [
        ObservedComponent(ComponentId(Component.LAUNCHER), _launcher_state(found))
    ]
    if observation.interpreter_present:
        components.append(
            ObservedComponent(ComponentId(Component.RUNTIME_ENVIRONMENT), ComponentState.MATCHED)
        )
    elif VerificationFinding.INTERPRETER_MISSING in found:
        components.append(
            ObservedComponent(ComponentId(Component.RUNTIME_ENVIRONMENT), ComponentState.ABSENT)
        )

    for harness, _server, command in observation.registered_commands:
        expected = next(
            (
                registration.command
                for registration in receipt.registrations
                if registration.target.harness == harness
            ),
            None,
        )
        if command is None:
            state = ComponentState.ABSENT
        elif expected is not None and command != expected:
            state = ComponentState.DIVERGENT
        else:
            state = ComponentState.MATCHED
        components.append(ObservedComponent(ComponentId(Component.HARNESS, harness), state))

    components.extend(
        ObservedComponent(ComponentId(Component.CREDENTIAL, name), state)
        for name, state in credentials
    )
    return CurrentState(desired.artifact, tuple(item for item in components if item.id in wanted))
