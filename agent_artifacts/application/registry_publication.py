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
    "RegistryPublicationReceipt",
    "prepare_registry_publication",
    "publication_summary",
]
