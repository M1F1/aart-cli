"""The bridge from one installed artifact to the states a reconciler compares.

CP-10 produced a receipt and an observation of a real installation. This turns both into the
component algebra, so a launcher somebody edited becomes a launcher repair and a harness entry
somebody deleted becomes a harness repair -- and neither becomes a reinstall.

Desired state is derived from the receipt plus the things a receipt deliberately does not hold: the
base interpreter an environment is built from, the dependency descriptor, and where the payload is
copied from. Those come from the plan, which is where §158 says they belong. A receipt records what
happened, not what should.

The same builder serves an installation that has not happened yet, from the receipt that
installation intends to leave. That is deliberate: the state an install converges to has to be the
state a repair afterwards keeps, and two builders would be free to disagree about it.
"""

from __future__ import annotations

from agent_artifacts.domain.credentials import CredentialReference
from agent_artifacts.domain.effects import (
    ConfigureHarness,
    CopyTree,
    CreatePythonEnvironment,
    DeleteCredential,
    DeliverArtifact,
    InstallPythonDependencies,
    RemoveOwnedPath,
    ReplaceCredential,
    StoreCredential,
    UnconfigureHarness,
    WithdrawArtifact,
    WriteFile,
)
from agent_artifacts.domain.identifiers import ArtifactCoordinate
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import InstallationReceipt, PlacedArtifactReceipt
from agent_artifacts.domain.reconciliation import (
    Component,
    ComponentId,
    ComponentState,
    CurrentState,
    DesiredComponent,
    DesiredState,
    ObservedComponent,
)

from .installation_verification import (
    InstallationObservation,
    PlacementObservation,
    VerificationFinding,
)

__all__ = [
    "current_state_from_observation",
    "current_state_from_placement",
    "desired_state_from_placement",
    "desired_state_from_receipt",
    "removal_state_from_placement",
    "removal_state_from_receipt",
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
    payload_source: str | None = None,
) -> DesiredState:
    """The component-level desired state this receipt describes.

    `base_interpreter`, `dependencies` and `payload_source` are optional because they are plan
    knowledge, not receipt knowledge. Omitting them omits those components rather than inventing
    them: a reconciler that guessed which interpreter an environment was built from would repair it
    into something else, and one that guessed where a payload came from would overwrite it from
    somewhere nobody chose.
    """

    if not isinstance(receipt, InstallationReceipt):
        raise ValueError("desired state needs an installation receipt")

    environment = ArtifactEnvironment(receipt.artifact, receipt.root)
    components: list[DesiredComponent] = []

    if payload_source is not None:
        components.append(
            DesiredComponent(
                ComponentId(Component.PAYLOAD),
                (CopyTree(payload_source, environment.payload),),
            )
        )
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


def removal_state_from_receipt(
    coordinate: ArtifactCoordinate,
    receipt: InstallationReceipt,
    *,
    delete_credentials: bool = False,
) -> DesiredState:
    """The absent desired state used by uninstall reconciliation.

    Credentials are deliberately omitted by default. The final dependant disappearing is not
    authority to delete a credential; callers have to request that separate mutation explicitly.
    """

    if not isinstance(receipt, InstallationReceipt):
        raise ValueError("removal state needs an installation receipt")
    environment = ArtifactEnvironment(receipt.artifact, receipt.root)
    absent = ComponentState.ABSENT
    components: list[DesiredComponent] = [
        DesiredComponent(
            ComponentId(Component.PAYLOAD),
            (RemoveOwnedPath(environment.root, recursive=True),),
            target=absent,
        ),
        DesiredComponent(
            ComponentId(Component.RUNTIME_ENVIRONMENT),
            (RemoveOwnedPath(environment.environment, recursive=True),),
            target=absent,
        ),
        DesiredComponent(
            ComponentId(Component.LAUNCHER),
            (RemoveOwnedPath(receipt.launcher),),
            target=absent,
        ),
    ]
    components.extend(
        DesiredComponent(
            ComponentId(Component.HARNESS, registration.target.harness),
            (
                UnconfigureHarness(
                    registration.target.harness,
                    registration.server,
                    registration.target.settings_file,
                ),
            ),
            target=absent,
        )
        for registration in receipt.registrations
    )
    if delete_credentials:
        components.extend(
            DesiredComponent(
                ComponentId(Component.CREDENTIAL, str(reference.input)),
                (DeleteCredential(str(reference), reference.provider.provider),),
                target=absent,
            )
            for reference in receipt.credentials
        )
    return DesiredState(coordinate, tuple(components))


def desired_state_from_placement(
    coordinate: ArtifactCoordinate,
    receipt: PlacedArtifactReceipt,
    *,
    payload_source: str | None = None,
) -> DesiredState:
    """The component-level desired state an artifact a harness reads converges to.

    A placed artifact is a payload and one delivery per harness, and that is the whole of it. There
    is no launcher, no environment and no dependency component -- not omitted as an unknown, but
    absent because the artifact starts no process. INV-010 keeps kind separate from runtime
    protocol, and a LAUNCHER component here would have a reconciler report the absence of a process
    nobody installed as drift and then repair it into existence.

    `payload_source` is plan knowledge for the same reason it is on the MCP builder: omitting it
    omits the payload component rather than guessing where the tree should be copied from.
    """

    if not isinstance(receipt, PlacedArtifactReceipt):
        raise ValueError("desired state needs a placed artifact receipt")

    environment = ArtifactEnvironment(receipt.artifact, receipt.root)
    components: list[DesiredComponent] = []
    if payload_source is not None:
        components.append(
            DesiredComponent(
                ComponentId(Component.PAYLOAD),
                (CopyTree(payload_source, environment.payload),),
            )
        )
    components.extend(
        DesiredComponent(
            ComponentId(Component.DELIVERY, delivery.harness),
            (
                DeliverArtifact(
                    delivery.harness,
                    receipt.artifact,
                    delivery.source,
                    delivery.destination,
                    delivery.kind,
                ),
            ),
        )
        for delivery in receipt.deliveries
    )
    return DesiredState(coordinate, tuple(components))


def removal_state_from_placement(
    coordinate: ArtifactCoordinate, receipt: PlacedArtifactReceipt
) -> DesiredState:
    """The absent desired state uninstalling a placed artifact converges to.

    The delivery is withdrawn rather than deleted as a path AART owns, because it is not one: it
    sits where the harness reads, and CP-12 teardown has to leave anything there this installation
    did not put there alone.
    """

    if not isinstance(receipt, PlacedArtifactReceipt):
        raise ValueError("removal state needs a placed artifact receipt")

    environment = ArtifactEnvironment(receipt.artifact, receipt.root)
    absent = ComponentState.ABSENT
    components: list[DesiredComponent] = [
        DesiredComponent(
            ComponentId(Component.PAYLOAD),
            (RemoveOwnedPath(environment.root, recursive=True),),
            target=absent,
        )
    ]
    components.extend(
        DesiredComponent(
            ComponentId(Component.DELIVERY, delivery.harness),
            (
                WithdrawArtifact(
                    delivery.harness,
                    receipt.artifact,
                    delivery.destination,
                    delivery.kind,
                ),
            ),
            target=absent,
        )
        for delivery in receipt.deliveries
    )
    return DesiredState(coordinate, tuple(components))


def _payload_state(
    receipt: PlacedArtifactReceipt, observation: PlacementObservation
) -> ComponentState:
    """Whether the artifact's own tree holds what the receipt says it holds.

    Presence is not the question. The tree an installation owns is version-independent -- an update
    converges in place -- so the payload of the version being replaced is present at exactly the
    path the new one wants. Judging that as matched skips the copy, and the delivery that follows
    then places the old content under the new version's name, reporting success.
    """

    if not observation.payload_present:
        return ComponentState.ABSENT
    if observation.payload_digest is None:
        return ComponentState.UNKNOWN
    return (
        ComponentState.MATCHED
        if observation.payload_digest == receipt.payload_digest
        else ComponentState.DIVERGENT
    )


def current_state_from_placement(
    desired: DesiredState,
    receipt: PlacedArtifactReceipt,
    observation: PlacementObservation,
) -> CurrentState:
    """What was actually found for an artifact a harness reads, in `desired`'s vocabulary.

    A delivery nobody looked at is left out entirely, so the comparison reports it as unobserved
    rather than as fine. A delivery somebody looked at and could not measure is `UNKNOWN`, which is
    a different fact again: reading either as absent would plan a delivery over whatever is there.
    """

    if not isinstance(desired, DesiredState):
        raise ValueError("current state must be paired with the desired state it answers")
    if not isinstance(receipt, PlacedArtifactReceipt) or not isinstance(
        observation, PlacementObservation
    ):
        raise ValueError("a placement's current state needs its receipt and observation")

    wanted = {component.id for component in desired.components}
    expected = {delivery.harness: delivery.digest for delivery in receipt.deliveries}
    components: list[ObservedComponent] = [
        ObservedComponent(ComponentId(Component.PAYLOAD), _payload_state(receipt, observation))
    ]
    for found in observation.deliveries:
        if not found.present:
            state = ComponentState.ABSENT
        elif found.digest is None:
            state = ComponentState.UNKNOWN
        elif found.digest == expected.get(found.harness):
            state = ComponentState.MATCHED
        else:
            state = ComponentState.DIVERGENT
        components.append(ObservedComponent(ComponentId(Component.DELIVERY, found.harness), state))
    return CurrentState(desired.artifact, tuple(item for item in components if item.id in wanted))


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
        ObservedComponent(
            ComponentId(Component.PAYLOAD),
            ComponentState.MATCHED if observation.payload_present else ComponentState.ABSENT,
        ),
        ObservedComponent(ComponentId(Component.LAUNCHER), _launcher_state(found)),
    ]
    if observation.interpreter_present:
        components.append(
            ObservedComponent(ComponentId(Component.RUNTIME_ENVIRONMENT), ComponentState.MATCHED)
        )
    elif VerificationFinding.INTERPRETER_MISSING in found:
        components.append(
            ObservedComponent(ComponentId(Component.RUNTIME_ENVIRONMENT), ComponentState.ABSENT)
        )

    # Dependencies are reported through the environment they were installed into, because that
    # environment is what installing them produces: when it is gone they are gone, and repairing
    # it reinstalls them. What is deliberately not claimed is that the packages inside it still
    # match the descriptor -- nothing here re-resolves that, and the detail says so rather than
    # letting a partial check read as a full one. Reporting nothing instead would leave the
    # component permanently unobserved, so every artifact with dependencies would ask for
    # attention forever while being perfectly healthy (B-029).
    components.append(
        ObservedComponent(
            ComponentId(Component.RUNTIME_DEPENDENCIES),
            ComponentState.MATCHED if observation.interpreter_present else ComponentState.ABSENT,
            "the environment they were installed into is present; not re-resolved"
            if observation.interpreter_present
            else "the environment they were installed into is gone",
        )
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
