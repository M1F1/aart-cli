"""Publishing a reviewed registry commit: one push, one branch, and never a merge (`D-228`).

Ending the maintainer's work at the local commit and sending them to a terminal to move it would be
no safeguard — the same bytes were reviewed, validated and committed inside AART a
moment earlier, and typing `git push` afterwards records no decision the surface did not already
have.  What actually separates publication from approval is the branch: reviewed bytes land
somewhere other people can look at them, and only a merge makes them the registry.

So this module prepares exactly one thing and refuses everything adjacent to it.  There is no force,
no merge, no fast-forward and no delete, structurally rather than by convention, and the branch is
resolved through `domain.publication` so a push to the branch consumers read is refused here rather
than attempted and bounced by a forge that has less to say about why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.identifiers import (
    ObjectDigest,
    SourceAlias,
    source_revision_kind,
)
from agent_artifacts.domain.publication import PublicationBranch, resolve_publication_branch
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.capabilities import Capability
from agent_artifacts.protocol.native_tree import SnapshotEntryKind, SourceSnapshot
from agent_artifacts.protocol.registry_schema import parse_registry_manifest
from agent_artifacts.protocol.semver import SemVer
from agent_artifacts.registry_commands.model import RegistryWorkspacePlan
from agent_artifacts.registry_commands.planning import (
    audit_registry_workspace,
    plan_promoted_registry_build,
    plan_registry_format,
    project_registry_workspace_plan,
    test_registry_compatibility,
    validate_registry_workspace,
)
from agent_artifacts.registry_commands.publication import REGISTRY_PUBLICATION_GATES

REGISTRY_PUBLICATION_INVALID = DiagnosticCode("registry-publication-invalid")

#: A Git remote is one name, not a path and not an option: `origin`, `upstream`, `company`.
_REMOTE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


class PublicationOutcome(str, Enum):
    """What the remote branch did, which is the only thing a push can honestly report."""

    CREATED = "created"
    UPDATED = "updated"
    ALREADY_CURRENT = "already-current"


@dataclass(frozen=True, slots=True)
class RegistryPublicationCommand:
    """One already-made commit, one remote, one branch that is not the one consumers read."""

    registry: SourceAlias
    remote: str
    branch: PublicationBranch
    revision: str
    review_digest: ObjectDigest

    def __post_init__(self) -> None:
        if (
            not isinstance(self.registry, SourceAlias)
            or not self.registry.value
            or not _is_remote_name(self.remote)
            or not isinstance(self.branch, PublicationBranch)
            or source_revision_kind(self.revision) != "git"
            or not isinstance(self.review_digest, ObjectDigest)
        ):
            raise ValueError("registry publication command is invalid")


@dataclass(frozen=True, slots=True)
class RegistryPublicationReceipt:
    """What one push moved, said in the terms the maintainer reviewed it in."""

    registry: SourceAlias
    remote: str
    branch: PublicationBranch
    revision: str
    review_digest: ObjectDigest
    outcome: PublicationOutcome

    def __post_init__(self) -> None:
        if (
            not isinstance(self.registry, SourceAlias)
            or not self.registry.value
            or not _is_remote_name(self.remote)
            or not isinstance(self.branch, PublicationBranch)
            or source_revision_kind(self.revision) != "git"
            or not isinstance(self.review_digest, ObjectDigest)
            or not isinstance(self.outcome, PublicationOutcome)
        ):
            raise ValueError("registry publication receipt is invalid")


PublishRegistryPort = Callable[[RegistryPublicationCommand], Result[RegistryPublicationReceipt]]


@dataclass(frozen=True, slots=True)
class RegistryPublicationGate:
    """One mandatory check over the exact snapshot proposed for publication."""

    name: str
    passed: bool
    details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.name
            or not isinstance(self.passed, bool)
            or any(not item or "\n" in item or "\r" in item for item in self.details)
        ):
            raise ValueError("registry publication gate is invalid")


@dataclass(frozen=True, slots=True)
class RegistryPublicationPreparation:
    """The one build and gate result used by publish and Push readiness."""

    plan: RegistryWorkspacePlan
    snapshot: SourceSnapshot
    gates: tuple[RegistryPublicationGate, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.plan, RegistryWorkspacePlan)
            or not isinstance(self.snapshot, SourceSnapshot)
            or not self.gates
            or any(not isinstance(item, RegistryPublicationGate) for item in self.gates)
        ):
            raise ValueError("registry publication preparation is invalid")

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.gates)


def _gate(name: str, report) -> RegistryPublicationGate:
    diagnostics = tuple(
        f"{diagnostic.severity.value}: {diagnostic.message}"
        for check in report.checks
        for diagnostic in check.diagnostics
    )
    return RegistryPublicationGate(name, report.passed, diagnostics)


def _manifest(snapshot: SourceSnapshot):
    marker = next(
        (
            item
            for item in snapshot.entries
            if str(item.path) == "aart-registry.json" and item.kind is SnapshotEntryKind.FILE
        ),
        None,
    )
    return None if marker is None else parse_registry_manifest(marker.content)


def prepare_registry_publication_state(
    snapshot: SourceSnapshot,
    *,
    executable_version: SemVer,
    available_capabilities: tuple[Capability, ...],
) -> Result[RegistryPublicationPreparation]:
    """Prepare canonical outputs and run the complete publication contract once.

    ``registry publish`` may apply ``plan`` before making its local commit. Push readiness requires
    the same plan to be a no-op. Both consume the same named gates, so the CLI, screen 46 and the
    generated workflow cannot silently grow different definitions of publishable bytes.
    """

    if (
        not isinstance(snapshot, SourceSnapshot)
        or not isinstance(executable_version, SemVer)
        or any(not isinstance(item, Capability) for item in available_capabilities)
    ):
        return _refuse("publication preparation needs a Registry snapshot and runtime contract")
    formatted = plan_registry_format(snapshot)
    if isinstance(formatted, Err):
        return formatted
    format_gate = RegistryPublicationGate(
        "format",
        formatted.value.changed_paths == 0,
        (
            ()
            if formatted.value.changed_paths == 0
            else ("registry format would change managed files",)
        ),
    )
    built = plan_promoted_registry_build(snapshot)
    if isinstance(built, Err):
        return built
    projected = project_registry_workspace_plan(snapshot, built.value)
    if isinstance(projected, Err):
        return projected
    reproduced = plan_promoted_registry_build(projected.value)
    if isinstance(reproduced, Err):
        return reproduced
    validated = validate_registry_workspace(
        projected.value,
        executable_version=executable_version,
        available_capabilities=available_capabilities,
    )
    if isinstance(validated, Err):
        return validated
    audited = audit_registry_workspace(
        projected.value,
        executable_version=executable_version,
        available_capabilities=available_capabilities,
    )
    if isinstance(audited, Err):
        return audited
    manifest = _manifest(projected.value)
    if manifest is None or isinstance(manifest, Err):
        return _refuse("publication preparation cannot read the Registry compatibility window")
    minimum = manifest.value.requires_aart.min_inclusive
    if minimum is None:
        return _refuse("publication preparation needs a minimum compatible aart-cli version")
    compatible = test_registry_compatibility(
        projected.value,
        minimum=minimum,
        latest=executable_version,
        available_capabilities=available_capabilities,
    )
    if isinstance(compatible, Err):
        return compatible
    gates = (
        format_gate,
        RegistryPublicationGate(
            "lock",
            True,
            ("approved versions carry their canonical pins",),
        ),
        RegistryPublicationGate(
            "build",
            reproduced.value.changed_paths == 0,
            (
                ()
                if reproduced.value.changed_paths == 0
                else ("canonical generated outputs do not reproduce",)
            ),
        ),
        _gate("validate", validated.value),
        _gate("audit", audited.value),
        _gate("compatibility", compatible.value),
    )
    if tuple(item.name for item in gates) != tuple(
        item.name for item in REGISTRY_PUBLICATION_GATES
    ):
        return _refuse("publication gate implementation does not match the canonical gate contract")
    return Ok(RegistryPublicationPreparation(built.value, projected.value, gates))


def _is_remote_name(value: object) -> bool:
    return isinstance(value, str) and _REMOTE_RE.match(value) is not None


def _refuse(message: str, *remedy: str) -> Err:
    return Err(
        (
            Diagnostic(
                REGISTRY_PUBLICATION_INVALID,
                Severity.ERROR,
                message,
                remediation=remedy,
                interactive=remedy,
            ),
        )
    )


def prepare_registry_publication(
    *,
    registry: SourceAlias,
    remote: str,
    default_branch: str,
    requested_branch: str,
    revision: str,
    review_digest: ObjectDigest,
) -> Result[RegistryPublicationCommand]:
    """Bind one reviewed revision to one publication branch, or say why it cannot be published.

    `default_branch` is the ref the registry connection is read at, which is what a subscriber
    resolves — so the refusal needs no network to make.
    """

    if not isinstance(registry, SourceAlias) or not registry.value:
        return _refuse("publishing needs the registry it publishes")
    if not _is_remote_name(remote):
        return _refuse(
            "a publication remote must be one Git remote name",
            "Name the remote the registry checkout already has, such as origin.",
        )
    if source_revision_kind(revision) != "git":
        return _refuse(
            "publishing needs the exact commit that was reviewed, not a moving name",
            "Create the registry commit first, then publish the revision it made.",
        )
    if not isinstance(review_digest, ObjectDigest):
        return _refuse("publishing needs the review this commit was made under")
    branch = resolve_publication_branch(requested=requested_branch, default_branch=default_branch)
    if isinstance(branch, Err):
        return branch
    return Ok(RegistryPublicationCommand(registry, remote, branch.value, revision, review_digest))


def publication_summary(receipt: RegistryPublicationReceipt) -> tuple[str, ...]:
    """The lines a maintainer reads after a push, including the one about what it is not."""

    if not isinstance(receipt, RegistryPublicationReceipt):
        raise ValueError("a publication summary needs a receipt")
    moved = {
        PublicationOutcome.CREATED: f"created {receipt.remote}/{receipt.branch.value}",
        PublicationOutcome.UPDATED: f"updated {receipt.remote}/{receipt.branch.value}",
        PublicationOutcome.ALREADY_CURRENT: (
            f"{receipt.remote}/{receipt.branch.value} already held this revision"
        ),
    }[receipt.outcome]
    return (
        f"{receipt.registry.value}: {moved} at {receipt.revision[:12]}",
        "Nothing was merged. Open a pull request for the reviewer to merge it.",
    )


__all__ = [
    "REGISTRY_PUBLICATION_INVALID",
    "PublicationOutcome",
    "PublishRegistryPort",
    "RegistryPublicationCommand",
    "RegistryPublicationGate",
    "RegistryPublicationPreparation",
    "RegistryPublicationReceipt",
    "prepare_registry_publication",
    "prepare_registry_publication_state",
    "publication_summary",
]
