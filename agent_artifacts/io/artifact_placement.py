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

What the package declares also decides which of two answers "where" has. An artifact that names a
launch contract registers with a harness, so the answer is an MCP target. One that names none is
read off a path, so the answer is a delivery per harness -- measured from `DELIVERY_TARGETS`, made
from the copy this installation owns rather than from the shared store object, and digested from
the package so a later repair can tell an edited Skill from an intact one.
"""

from __future__ import annotations

import os

from agent_artifacts.application.installation_offer import ArtifactPlacement
from agent_artifacts.domain.artifacts import ArtifactKind
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.harness import (
    Scope,
    delivery_destination,
    delivery_target,
    mcp_target,
)
from agent_artifacts.domain.identifiers import ArtifactIdentity
from agent_artifacts.domain.inputs import InputValueSource
from agent_artifacts.domain.install_description import InstallDescription
from agent_artifacts.domain.placement import artifact_root
from agent_artifacts.domain.python_runtime import ArtifactEnvironment, PythonInstaller
from agent_artifacts.domain.receipts import ArtifactDelivery
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.domain.selection import ResolvedArtifact
from agent_artifacts.protocol.authoring import (
    package_delivery,
    package_payload_root,
    read_package_description,
)
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


def _delivered(description: InstallDescription) -> bool:
    """Whether this artifact is read off a path rather than started, as the package declares it."""

    return description.contract is None


def _deliveries(
    identity: ArtifactIdentity,
    entries: object,
    *,
    scope: Scope,
    profiles: tuple[str, ...],
    root: str,
    harness_root: str,
) -> Result[tuple[ArtifactDelivery, ...]]:
    """Where each requested harness would read this artifact from, and what it would find there.

    The source is inside `root` rather than inside the store, because that is the copy this
    installation owns: the store's object is shared with every other installation of the same
    version and may be pruned, so a repair copying from it would depend on somebody else's
    housekeeping.
    """

    # A coordinate's kind is a plain string; the measured tables are keyed by the enum. Coercing
    # here rather than indexing with the string keeps an unrecognized kind a named refusal instead
    # of a lookup that happens to miss.
    try:
        kind = ArtifactKind(identity.kind)
    except ValueError:
        return _error(f"{identity} names a kind this build does not know how to deliver")

    packaged = package_delivery(kind, entries)  # type: ignore[arg-type]
    if isinstance(packaged, Err):
        return packaged
    payload = ArtifactEnvironment(str(identity), root).payload
    source = payload if not packaged.value.source else f"{payload}/{packaged.value.source}"

    deliveries: list[ArtifactDelivery] = []
    for profile in profiles:
        try:
            target = delivery_target(profile, scope, kind)
        except KeyError as error:
            # Named rather than skipped, for the same reason a missing MCP target is: an install
            # that reports success and delivers nowhere leaves the harness somebody asked for with
            # nothing to read.
            return _error(str(error).strip("'"))
        if target.delivery is not packaged.value.delivery:
            # Two measured tables disagreeing about one kind. Delivering anyway would write a
            # directory where the harness reads a file, or the reverse.
            return _error(
                f"{profile} reads a {kind.value} as {target.delivery.value}, and this "
                f"package offers {packaged.value.delivery.value}"
            )
        try:
            destination = delivery_destination(target, identity.name)
        except ValueError as error:
            return _error(f"{identity} cannot be delivered to {profile}: {error}")
        deliveries.append(
            ArtifactDelivery(
                profile,
                source,
                os.path.join(harness_root, destination),
                target.delivery,
                packaged.value.digest,
            )
        )
    return Ok(tuple(deliveries))


def placement_for(
    artifact: ResolvedArtifact,
    *,
    scope: Scope,
    profiles: tuple[str, ...],
    project_root: str,
    data_root: str,
    store: ObjectStorePaths,
    harness_root: str | None = None,
    sources: tuple[InputValueSource, ...] = (),
    preferred_installer: PythonInstaller | None = None,
) -> Result[ArtifactPlacement]:
    """Read what this artifact declares, and decide where and into what it would be installed.

    `harness_root` is the scope's own root, the one a harness's paths are resolved against. It is
    needed only by an artifact a harness reads, which is why it is optional -- an MCP server names
    its settings file relative to that root and the registry adapter applies it later.
    """

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

    root = artifact_root(coordinate, scope, project_root=project_root, data_root=data_root)
    delivered = _delivered(described.value)

    targets = []
    if not delivered:
        for profile in profiles:
            try:
                targets.append(mcp_target(profile, scope))
            except KeyError as error:
                # Named rather than skipped. A profile quietly dropped is an install that reports
                # success and leaves the harness somebody asked for with no way to start the
                # server.
                return _error(str(error).strip("'"))

    deliveries: tuple[ArtifactDelivery, ...] = ()
    if delivered:
        if harness_root is None or not os.path.isabs(harness_root):
            return _error(
                f"{coordinate} is read off a path, so placing it needs the absolute root that "
                "path is resolved against",
                "supply the project root for a project install, or the user home for a user one",
            )
        made = _deliveries(
            coordinate.artifact,
            stored.value.candidate.entries,
            scope=scope,
            profiles=profiles,
            root=root,
            harness_root=harness_root,
        )
        if isinstance(made, Err):
            return made
        deliveries = made.value

    try:
        return Ok(
            ArtifactPlacement(
                artifact,
                described.value,
                root=root,
                payload_source=package_payload_root(stored.value.root),
                targets=tuple(targets),
                sources=sources,
                preferred_installer=preferred_installer,
                deliveries=deliveries,
                # The registry's attested digest of the payload, not one re-derived here. The
                # installing machine records what the approved version says it placed.
                payload_digest=artifact.version.payload_digest if delivered else None,
            )
        )
    except ValueError as error:
        return _error(f"{coordinate} cannot be placed here: {error}")
