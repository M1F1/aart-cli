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

from aart_cli.application.installation_offer import ArtifactPlacement
from aart_cli.application.skill_projection import SKILL_DOCUMENT, project_skill_document
from aart_cli.compiler.graph import supported_label
from aart_cli.domain.artifacts import ArtifactKind
from aart_cli.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from aart_cli.domain.harness import (
    Scope,
    delivery_destination,
    delivery_target,
    hook_event_path,
    hook_target,
    mcp_target,
    measured_harnesses,
    memory_target,
)
from aart_cli.domain.hooks import HookEntry
from aart_cli.domain.identifiers import ArtifactCoordinate, ArtifactIdentity
from aart_cli.domain.inputs import InputValueSource
from aart_cli.domain.install_description import InstallDescription
from aart_cli.domain.installation_owner import installed_name_for
from aart_cli.domain.managed_blocks import is_block_name
from aart_cli.domain.placement import artifact_root
from aart_cli.domain.python_runtime import ArtifactEnvironment, PythonInstaller
from aart_cli.domain.receipts import (
    ArtifactDelivery,
    ArtifactMerge,
    ArtifactSettingsEntry,
)
from aart_cli.domain.result import Err, Ok, Result
from aart_cli.domain.selection import ResolvedArtifact
from aart_cli.protocol.authoring import (
    package_delivery,
    package_hook,
    package_merge,
    package_payload_root,
    read_package_description,
)
from aart_cli.protocol.native_models import ArtifactManifest
from aart_cli.protocol.native_tree import compile_native_package
from aart_cli.store.model import ObjectReadRequest, ObjectStorePaths

from .environment_inspection import platform_name
from .object_store import read_object

__all__ = ["PLACEMENT_UNAVAILABLE", "placement_for"]

#: The artifact is selected and this machine cannot place it -- its package is not in the store, or
#: a requested harness is one nobody has measured.
PLACEMENT_UNAVAILABLE = DiagnosticCode("artifact-placement-unavailable")


def _error(message: str, *remediation: str) -> Err:
    return Err(
        (Diagnostic(PLACEMENT_UNAVAILABLE, Severity.ERROR, message, remediation=remediation),)
    )


#: The kinds a harness reads out of a file somebody else owns rather than off a path of their own.
#: A hook is absent because it is not one or the other: its script is delivered like a Skill's tree
#: and an entry in a settings file is what makes the harness run it, so it goes through both.
_MERGED_KINDS = frozenset({ArtifactKind.MEMORY})


def _skippable(profile: str, *, requested: bool) -> bool:
    """Whether a harness with no measured target for this artifact may be left out of the plan.

    `aart-cli marketplace install` refuses without `--profile`, so a profile that reaches it was typed
    by somebody, and dropping one would leave the harness they asked for with nothing to read and
    no way to start a server. The persistent shell names no profiles: it installs into every
    harness whose tables this build measured, which is a capability set rather than a request, and
    a harness that cannot host this kind at this scope is not a mistake in it.

    So the skip is narrow on both sides. A harness nobody measured is a refusal however the
    profiles arrived -- that is somebody naming a harness this build has never looked at, and the
    machine's own set can never contain one. And `placement_for` still refuses a Selection that
    every profile left out, because an install with no effect anywhere is not a successful one.
    """

    return not requested and profile in measured_harnesses()


def _declared_narrowing(
    manifest: ArtifactManifest,
    identity: ArtifactIdentity,
    profiles: tuple[str, ...],
    *,
    profiles_requested: bool,
) -> Result[tuple[str, ...]]:
    """The harnesses left after the artifact's own declaration is applied to the asked-for set.

    An empty or absent `compatibility.harnesses` means unconstrained rather than "nowhere"
    (`D-231`): the schema parses both as `()`, so they cannot be given different meanings, and an
    author who wrote nothing did not say the artifact goes nowhere.

    A non-empty declaration narrows through the asymmetry that already governs a missing target
    (`_skippable`) rather than a second one of its own. A harness this build merely measured is
    left out, because the machine's capability set is not a request. A harness somebody typed is
    refused by name, because they asked for something the artifact says it does not support, and
    the message names the set they can choose from -- the same set Artifact Details showed them.
    """

    platforms = manifest.compatibility.platforms
    here = platform_name()
    # D-261: the platforms an artifact declares narrow exactly as Artifact Details reads them, and
    # by the same D-231 rule -- an empty declaration is unconstrained. A platform this machine is
    # not is no harness's fault, so it is refused whoever named the profiles.
    if platforms and here not in platforms:
        return _error(
            f"{identity} declares support for platforms {supported_label(platforms)}, and this "
            f"machine is {here}",
            "install it on a machine running one of those platforms",
        )
    declared = manifest.compatibility.profiles
    if not declared:
        return Ok(profiles)
    for profile in profiles:
        if profile in declared or _skippable(profile, requested=profiles_requested):
            continue
        return _error(
            f"profile {profile!r} is not supported; supported profiles: {supported_label(declared)}",
            "install it for a harness this artifact declares support for",
        )
    kept = tuple(profile for profile in profiles if profile in declared)
    if not kept:
        return _error(
            f"{identity} declares support for {supported_label(declared)}, and this machine measured "
            "none of them",
            "install it on a machine with one of those harnesses",
        )
    return Ok(kept)


def _delivered(description: InstallDescription) -> bool:
    """Whether this artifact is read off a path rather than started, as the package declares it."""

    return description.contract is None


def _merges(
    identity: ArtifactIdentity,
    entries: object,
    *,
    kind: ArtifactKind,
    scope: Scope,
    profiles: tuple[str, ...],
    profiles_requested: bool,
    root: str,
    harness_root: str,
) -> Result[tuple[ArtifactMerge, ...]]:
    """Which region of which shared file each requested harness would read this artifact from.

    The destination is a file the user writes in, so what is recorded is the region rather than the
    file, and the digest covers only the body that goes in it. The source is inside `root` for the
    same reason a delivery's is: the store's object is shared and may be pruned, and a repair has to
    re-merge from the copy this installation owns.
    """

    packaged = package_merge(kind, entries)  # type: ignore[arg-type]
    if isinstance(packaged, Err):
        return packaged
    payload = ArtifactEnvironment(str(identity), root).payload
    if not is_block_name(identity.name):
        return _error(f"{identity} cannot name a region of a file somebody else owns")

    merges: list[ArtifactMerge] = []
    for profile in profiles:
        try:
            target = memory_target(profile, scope)
        except KeyError as error:
            # Named rather than skipped, for the same reason a missing delivery target is: an
            # install that reports success and merges nowhere leaves the harness somebody asked for
            # with nothing to read. A harness nobody asked for is left out instead (`_skippable`).
            if _skippable(profile, requested=profiles_requested):
                continue
            return _error(str(error).strip("'"))
        merges.append(
            ArtifactMerge(
                profile,
                f"{payload}/{packaged.value.source}",
                os.path.join(harness_root, target.destination),
                identity.name,
                packaged.value.digest,
            )
        )
    return Ok(tuple(merges))


def _settings(
    identity: ArtifactIdentity,
    entries: object,
    deliveries: tuple[ArtifactDelivery, ...],
    *,
    scope: Scope,
    harness_root: str,
) -> Result[tuple[ArtifactSettingsEntry, ...]]:
    """What each requested harness would be told to run, and where it reads that from.

    The command is built from the delivery rather than from the package: an author writes
    `${SCRIPT_DIR}/run.sh` because they have never seen this machine, and the delivery is the only
    thing that knows where the script actually lands. Which slot the entry goes in comes from the
    harness's own measured table, so a `PreToolUse` hook reaches Tabnine's `BeforeTool` rather than
    being installed into an event that build never reads.
    """

    packaged = package_hook(ArtifactKind.HOOK, entries)  # type: ignore[arg-type]
    if isinstance(packaged, Err):
        return packaged

    settings: list[ArtifactSettingsEntry] = []
    for delivery in deliveries:
        try:
            target = hook_target(delivery.harness, scope)
            path = hook_event_path(target, packaged.value.event)
        except KeyError as error:
            # Named rather than skipped, for the same reason a missing delivery target is: a hook
            # whose script is placed and whose entry is not would install cleanly and never run.
            return _error(str(error).strip("'"))
        try:
            settings.append(
                ArtifactSettingsEntry(
                    delivery.harness,
                    os.path.join(harness_root, target.settings),
                    path,
                    HookEntry(
                        target.shape,
                        packaged.value.matcher,
                        os.path.join(delivery.destination, packaged.value.command),
                    ),
                )
            )
        except ValueError as error:
            return _error(f"{identity} cannot be registered with {delivery.harness}: {error}")
    return Ok(tuple(settings))


def _deliveries(
    coordinate: ArtifactCoordinate,
    entries: object,
    *,
    summary: str,
    scope: Scope,
    profiles: tuple[str, ...],
    profiles_requested: bool,
    root: str,
    harness_root: str,
) -> Result[tuple[ArtifactDelivery, ...]]:
    """Where each requested harness would read this artifact from, and what it would find there.

    The source is inside `root` rather than inside the store, because that is the copy this
    installation owns: the store's object is shared with every other installation of the same
    version and may be pruned, so a repair copying from it would depend on somebody else's
    housekeeping.

    What the harness reads it under is the installed name, not the authored one (`§169.7`,
    `D-349`): the same artifact taken from two Registries, or installed at two scopes, reaches two
    directories rather than overwriting one. The name is composed here from the coordinate and the
    scope, because this is where the destination is built, and the delivery carries it so the
    executor writes the same spelling into the Skill's own document.
    """

    identity = coordinate.artifact
    # A coordinate's kind is a plain string; the measured tables are keyed by the enum. Coercing
    # here rather than indexing with the string keeps an unrecognized kind a named refusal instead
    # of a lookup that happens to miss.
    try:
        kind = ArtifactKind(identity.kind)
    except ValueError:
        return _error(f"{identity} names a kind this build does not know how to deliver")

    named = installed_name_for(coordinate, scope)
    if isinstance(named, Err):
        return named
    name = named.value
    # Only a Skill carries its identity inside its own text; a hook's script and a guideline's
    # document name nothing, so nothing in them is rewritten and the delivery records no document.
    document = SKILL_DOCUMENT if kind is ArtifactKind.SKILL else None

    def project(relative: str, content: bytes) -> Result[bytes]:
        if relative != document:
            return Ok(content)
        return project_skill_document(content, installed_name=name, summary=summary)

    packaged = package_delivery(kind, entries, projection=project)  # type: ignore[arg-type]
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
            # nothing to read. A harness nobody asked for is left out instead (`_skippable`).
            if _skippable(profile, requested=profiles_requested):
                continue
            return _error(str(error).strip("'"))
        if target.delivery is not packaged.value.delivery:
            # Two measured tables disagreeing about one kind. Delivering anyway would write a
            # directory where the harness reads a file, or the reverse.
            return _error(
                f"{profile} reads a {kind.value} as {target.delivery.value}, and this "
                f"package offers {packaged.value.delivery.value}"
            )
        try:
            destination = delivery_destination(target, name)
        except ValueError as error:
            return _error(f"{identity} cannot be delivered to {profile}: {error}")
        deliveries.append(
            ArtifactDelivery(
                profile,
                source,
                os.path.join(harness_root, destination),
                target.delivery,
                packaged.value.digest,
                name,
                summary,
                document,
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
    profiles_requested: bool = True,
    harness_root: str | None = None,
    sources: tuple[InputValueSource, ...] = (),
    preferred_installer: PythonInstaller | None = None,
) -> Result[ArtifactPlacement]:
    """Read what this artifact declares, and decide where and into what it would be installed.

    `harness_root` is the scope's own root, the one a harness's paths are resolved against. It is
    needed only by an artifact a harness reads, which is why it is optional -- an MCP server names
    its settings file relative to that root and the registry adapter applies it later.

    `profiles_requested` says where the profiles came from. The default is the honest one for a
    command: somebody typed them, so a harness that cannot host this artifact is a refusal naming
    it. The persistent shell passes `False`, because its profiles are every harness this build
    measured rather than a list anybody asked for -- see `_skippable`.
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

    # One compilation, read for two separate answers: what the artifact declares it supports, and
    # the summary the harness is given for it. Compiling twice would let the two disagree.
    package = compile_native_package(
        stored.value.candidate.entries, expected_identity=coordinate.artifact
    )
    if isinstance(package, Err):
        return package
    summary = package.value.manifest.summary

    # `QA-078`/`D-231`: what the artifact declares it supports and what it is installed into are
    # one answer. Narrowing happens here, once, rather than inside each per-profile loop, so the
    # two screens read the same set.
    narrowed = _declared_narrowing(
        package.value.manifest,
        coordinate.artifact,
        profiles,
        profiles_requested=profiles_requested,
    )
    if isinstance(narrowed, Err):
        return narrowed
    profiles = narrowed.value

    root = artifact_root(coordinate, scope, project_root=project_root, data_root=data_root)
    delivered = _delivered(described.value)
    # A coordinate's kind is a plain string; the measured tables are keyed by the enum. An
    # unrecognized kind is left as `None` here and named by whichever branch needs it, rather than
    # becoming a lookup that happens to miss.
    try:
        kind: ArtifactKind | None = ArtifactKind(coordinate.artifact.kind)
    except ValueError:
        kind = None

    targets = []
    if not delivered:
        for profile in profiles:
            try:
                targets.append(mcp_target(profile, scope))
            except KeyError as error:
                # Named rather than skipped. A profile quietly dropped is an install that reports
                # success and leaves the harness somebody asked for with no way to start the
                # server. A harness nobody asked for is left out instead (`_skippable`).
                if _skippable(profile, requested=profiles_requested):
                    continue
                return _error(str(error).strip("'"))
        if not targets:
            return _error(
                f"{coordinate} registers with none of {', '.join(profiles)} at {scope.value} scope",
                "install it at a scope one of these harnesses starts servers from",
            )

    deliveries: tuple[ArtifactDelivery, ...] = ()
    merges: tuple[ArtifactMerge, ...] = ()
    settings: tuple[ArtifactSettingsEntry, ...] = ()
    if delivered:
        if harness_root is None or not os.path.isabs(harness_root):
            return _error(
                f"{coordinate} is read off a path, so placing it needs the absolute root that "
                "path is resolved against",
                "supply the project root for a project install, or the user home for a user one",
            )
        if kind in _MERGED_KINDS:
            assert kind is not None
            blocks = _merges(
                coordinate.artifact,
                stored.value.candidate.entries,
                kind=kind,
                scope=scope,
                profiles=profiles,
                profiles_requested=profiles_requested,
                root=root,
                harness_root=harness_root,
            )
            if isinstance(blocks, Err):
                return blocks
            merges = blocks.value
            if not merges:
                return _error(
                    f"{coordinate} merges into no file of {', '.join(profiles)} at "
                    f"{scope.value} scope",
                    "install it at a scope one of these harnesses reads that file at",
                )
        else:
            made = _deliveries(
                coordinate,
                stored.value.candidate.entries,
                summary=summary,
                scope=scope,
                profiles=profiles,
                profiles_requested=profiles_requested,
                root=root,
                harness_root=harness_root,
            )
            if isinstance(made, Err):
                return made
            deliveries = made.value
            if not deliveries:
                return _error(
                    f"{coordinate} is read by none of {', '.join(profiles)} at {scope.value} scope",
                    "install it at a scope one of these harnesses reads it at",
                )
            if kind is ArtifactKind.HOOK:
                # Both halves, from one read of one package. A hook whose script is delivered and
                # whose entry is not is installed and inert, which is worse than not installed.
                told = _settings(
                    coordinate.artifact,
                    stored.value.candidate.entries,
                    deliveries,
                    scope=scope,
                    harness_root=harness_root,
                )
                if isinstance(told, Err):
                    return told
                settings = told.value

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
                merges=merges,
                settings=settings,
                # The registry's attested digest of the payload, not one re-derived here. The
                # installing machine records what the approved version says it placed.
                payload_digest=artifact.version.payload_digest if delivered else None,
            )
        )
    except ValueError as error:
        return _error(f"{coordinate} cannot be placed here: {error}")
