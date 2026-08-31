"""Turning a resolved artifact into the placement this machine would install it at.

Between "somebody selected `public/mcp/github`" and "here is what installing it would do" sits one
read and three decisions: read the package out of the object store, take what it declares it needs,
decide where its tree goes, and decide which harnesses it registers with. Nothing did that, which
is why `offer_installation` had no production caller -- every one of its `ArtifactPlacement`s was
built by hand in a test.

The read is the only effect. An object the store does not hold is a refusal naming the digest, not
an empty description: a package nobody can read is not a package that declares nothing, and
installing the second as though it were the first produces an artifact that starts nothing and asks
for nothing, with no error anywhere.
"""

from __future__ import annotations

from agent_artifacts.application.installation_offer import ArtifactPlacement
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import Scope, mcp_target
from agent_artifacts.domain.inputs import InputValueSource
from agent_artifacts.domain.placement import artifact_root
from agent_artifacts.domain.python_runtime import PythonInstaller
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ResolvedArtifact
from agent_artifacts.protocol.authoring import package_payload_root, read_package_description
from agent_artifacts.store.model import ObjectReadRequest, ObjectStorePaths

from .object_store import read_object

__all__ = ["PLACEMENT_UNAVAILABLE", "placement_for"]

#: The artifact is selected and this machine cannot place it -- its package is not in the store, or
#: a requested harness is one nobody has measured.
PLACEMENT_UNAVAILABLE = DiagnosticCode("artifact-placement-unavailable")


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (Diagnostic(PLACEMENT_UNAVAILABLE, Severity.ERROR, message, remediation=remediation),)
    )


def placement_for(
    artifact: ResolvedArtifact,
    *,
    scope: Scope,
    profiles: tuple[str, ...],
    project_root: str,
    data_root: str,
    store: ObjectStorePaths,
    sources: tuple[InputValueSource, ...] = (),
    preferred_installer: PythonInstaller | None = None,
) -> Result[ArtifactPlacement]:
    """Read what this artifact declares, and decide where and into what it would be installed."""

    if not isinstance(artifact, ResolvedArtifact) or not isinstance(scope, Scope):
        return _error("placing an artifact needs a resolved artifact and a scope")
    if not profiles:
        return _error(
            "placing an artifact needs at least one harness profile",
            "name a profile, so the installation registers somewhere it can be started from",
        )

    coordinate = artifact.version.coordinate
    stored = read_object(ObjectReadRequest(store, artifact.version.object_digest))
    if isinstance(stored, Err):
        return stored
    if stored.value is None:
        return _error(
            f"{coordinate} resolves to object {artifact.version.object_digest}, which this "
            "machine's store does not hold",
            "synchronize the source that publishes it, then plan the install again",
        )

    described = read_package_description(stored.value.candidate.entries)
    if isinstance(described, Err):
        return described

    targets = []
    for profile in profiles:
        try:
            targets.append(mcp_target(profile, scope))
        except KeyError as error:
            # Named rather than skipped. A profile quietly dropped is an install that reports
            # success and leaves the harness somebody asked for with no way to start the server.
            return _error(str(error).strip("'"))

    try:
        return Ok(
            ArtifactPlacement(
                artifact,
                described.value,
                root=artifact_root(
                    coordinate, scope, project_root=project_root, data_root=data_root
                ),
                payload_source=package_payload_root(stored.value.root),
                targets=tuple(targets),
                sources=sources,
                preferred_installer=preferred_installer,
            )
        )
    except ValueError as error:
        return _error(f"{coordinate} cannot be placed here: {error}")
