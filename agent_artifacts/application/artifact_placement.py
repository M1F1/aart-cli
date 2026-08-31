"""What an artifact a harness reads declares, met with where this machine would put it.

The counterpart of `artifact_installation` for the four kinds that start no process. INV-010 keeps
artifact kind, package format and runtime protocol apart, and this is the seam where that becomes
real: a Skill, a guideline, a hook and a memory are installed by being delivered where a harness
looks, and there is nothing to launch, no environment to build and no input to resolve into a
command line.

The refusals carry most of the weight. An artifact that declares how it starts is an installation,
and planning it as a placement would silently drop its launcher -- the payload would land where the
harness reads and nothing would ever run it, with no step missing from the plan to say so. The same
goes for dependencies nothing would use and a secret with no launcher to resolve it into: each is
an author saying something this shape of installation cannot honour, and honouring it partly is
worse than refusing it.

Nothing here touches a filesystem or reads a secret value. Where each delivery comes from and goes
to is measured by the adapter that read the package and the profile, and arrives already resolved.
"""

from __future__ import annotations

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import ObjectDigest
from agent_artifacts.domain.inputs import SecretInput
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.python_runtime import ArtifactEnvironment
from agent_artifacts.domain.receipts import ArtifactDelivery
from agent_artifacts.domain.requirements import HarnessRequirement, Requirement, RequirementId
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ResolvedArtifact

from .installation_proposal import PlannedPlacement

__all__ = [
    "PLACEMENT_NOT_PLANNABLE",
    "placement_requirements_for",
    "plan_artifact_placement",
]

PLACEMENT_NOT_PLANNABLE = DiagnosticCode("placement-not-plannable")


def _error(message: str) -> Err:
    return Err((Diagnostic(PLACEMENT_NOT_PLANNABLE, Severity.ERROR, message),))


def placement_requirements_for(
    deliveries: tuple[ArtifactDelivery, ...],
) -> tuple[Requirement, ...]:
    """What has to be true of a machine before this artifact can be delivered to it.

    One requirement per harness that reads it, and nothing else. A placement declares no runtime,
    no dependencies and no credentials, so the harnesses are the whole of what a machine has to
    offer -- and they come from the request rather than the package, because an artifact declares
    what it is compatible with and a person chooses where it goes.
    """

    return tuple(
        HarnessRequirement(RequirementId(f"harness-{harness}"), harness)
        for harness in sorted({delivery.harness for delivery in deliveries})
    )


def plan_artifact_placement(
    artifact: ResolvedArtifact,
    description: InstallDescription,
    *,
    root: str,
    payload_source: str,
    payload_digest: ObjectDigest,
    deliveries: tuple[ArtifactDelivery, ...],
) -> Result[PlannedPlacement]:
    """Everything decided about placing `artifact` here, before anything is touched."""

    if not isinstance(artifact, ResolvedArtifact) or not isinstance(
        description, InstallDescription
    ):
        return _error("planning a placement needs a resolved artifact and its install description")

    coordinate = artifact.version.coordinate
    if description.contract is not None:
        return _error(
            f"{coordinate} declares how it starts, so it is an installation rather than a "
            "placement; planning it here would drop the launcher a harness has to run"
        )
    if description.dependencies is not None:
        return _error(
            f"{coordinate} declares dependencies but starts no process, so nothing would ever "
            "load them"
        )
    secrets = tuple(item.id for item in description.inputs if isinstance(item, SecretInput))
    if secrets:
        return _error(
            f"{coordinate} declares the secret {secrets[0]} but has no launcher to resolve it "
            "into, so the value would have nowhere to go"
        )

    try:
        environment = ArtifactEnvironment(str(coordinate.artifact), root)
    except ValueError as error:
        return _error(f"placement root is invalid: {error}")

    try:
        return Ok(
            PlannedPlacement(
                artifact,
                environment,
                payload_digest,
                tuple(deliveries),
                payload_source,
                placement_requirements_for(tuple(deliveries)),
            )
        )
    except ValueError as error:
        return _error(f"the placement is not plannable: {error}")
