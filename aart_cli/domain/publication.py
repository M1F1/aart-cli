"""Where a reviewed registry commit may be pushed, and the one place it may never go (`D-228`).

Publication is not somebody else's problem (164.7).  The push is an action inside AART,
and what keeps approval separate from publication is the *branch*: a registry publishes to a branch
the maintainer configures, and never to the branch a consumer reads.  Only the merge makes reviewed
bytes the registry, and AART never merges.

That makes the refusal a domain rule rather than a policy setting or a forge configuration.  It is
decided here, from two strings, with no repository and no network: what was asked for, and what a
subscriber would read.  Adapters ask this before they touch a remote, so the attempt is refused by
name rather than attempted and rejected somewhere with less to say about why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .diagnostics import Diagnostic, DiagnosticCode, Severity
from .result import Err, Ok, Result

#: The requested target resolves to the branch consumers read, so publishing to it would merge
#: without review.  This is the refusal 164.7 asks AART to make itself.
DEFAULT_BRANCH_PUBLICATION = DiagnosticCode("registry-default-branch-publication")
#: The requested target is not a name Git would carry, so no remote could hold it.
PUBLICATION_BRANCH_INVALID = DiagnosticCode("registry-publication-branch-invalid")

PUBLICATION_BRANCH_NAMESPACE = "aart-cli"
DEFAULT_PUBLICATION_BRANCH = f"{PUBLICATION_BRANCH_NAMESPACE}/registry-update"


class RegistryCommitOrigin(str, Enum):
    """The local action that produced the commit now eligible for a review branch."""

    INIT_REGISTRY = "init-registry"
    REBUILD_REGISTRY = "rebuild-registry"
    PROMOTE = "promote"
    BULK_PROMOTE = "bulk-promote"


_HEADS_PREFIX = "refs/heads/"
#: `git check-ref-format --branch` in the shape this product needs: one or more slash-separated
#: components, each starting with an ordinary character, none of them a `.lock` and none of them
#: empty.  The excluded characters are Git's own, plus whitespace, which no branch may carry.
_COMPONENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]*$")
_FORBIDDEN = frozenset(" \t\r\n~^:?*[\\\"'`$;&|<>()")


@dataclass(frozen=True, slots=True)
class PublicationBranch:
    """A remote branch a registry may publish to, named the way `git push` would name it."""

    value: str

    def __post_init__(self) -> None:
        if not _is_usable_branch_name(self.value):
            raise ValueError("a publication branch must be a usable Git branch name")


def _short_name(value: str) -> str:
    """Answer what `git push` would move, so `refs/heads/main` cannot pass as something else."""

    return value[len(_HEADS_PREFIX) :] if value.startswith(_HEADS_PREFIX) else value


def _is_usable_branch_name(value: str) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if any(character in _FORBIDDEN for character in value):
        return False
    if value in {"HEAD", "@"} or ".." in value or "@{" in value or "//" in value:
        return False
    if value.startswith("/") or value.endswith("/") or value.endswith("."):
        return False
    components = value.split("/")
    return all(
        component and component.endswith(".lock") is False and _COMPONENT.match(component)
        for component in components
    )


def _refuse(code: DiagnosticCode, message: str, *remedy: str) -> Err:
    return Err(
        (
            Diagnostic(
                code,
                Severity.ERROR,
                message,
                remediation=tuple(f"aart-cli {item}" for item in remedy) if remedy else (),
                interactive=remedy,
            ),
        )
    )


def suggested_publication_branch(
    origin: RegistryCommitOrigin | None,
    *,
    subject: str = "",
) -> PublicationBranch:
    """Name the review branch after the producing action, falling back on unusable input."""

    suffix = (
        None
        if origin is None
        else {
            RegistryCommitOrigin.INIT_REGISTRY: "init-registry",
            RegistryCommitOrigin.REBUILD_REGISTRY: "rebuild-registry",
            RegistryCommitOrigin.BULK_PROMOTE: "bulk-promote",
            RegistryCommitOrigin.PROMOTE: f"promote-{subject}" if subject else None,
        }[origin]
    )
    candidate = (
        DEFAULT_PUBLICATION_BRANCH if suffix is None else f"{PUBLICATION_BRANCH_NAMESPACE}/{suffix}"
    )
    if not _is_usable_branch_name(candidate):
        candidate = DEFAULT_PUBLICATION_BRANCH
    return PublicationBranch(candidate)


def resolve_publication_branch(*, requested: str, default_branch: str) -> Result[PublicationBranch]:
    """Answer which branch a registry publishes to, refusing the branch consumers read (`D-228`).

    `default_branch` is what a subscriber resolves the registry at — the branch a merge lands on.
    Both names are compared as `git push` would move them, so `refs/heads/main` and `HEAD` are
    the default branch under other spellings rather than three separate targets.  Case is folded
    for the comparison alone: Git distinguishes `Main` from `main`, but a maintainer who typed the
    second meaning the first is asking for exactly what this refuses.
    """

    if not _is_usable_branch_name(
        default_branch.strip() if isinstance(default_branch, str) else ""
    ):
        return _refuse(
            PUBLICATION_BRANCH_INVALID,
            "the registry's default branch is not a usable Git branch name, "
            "so nothing can be checked against it",
            "Reconnect the registry with the branch its subscribers read.",
        )
    short_default = _short_name(default_branch)
    if isinstance(requested, str) and requested.strip() in {"HEAD", "@"}:
        return _refuse(
            DEFAULT_BRANCH_PUBLICATION,
            f"HEAD resolves to {short_default}, the branch this registry's subscribers read, "
            "and AART never publishes there",
            f"Name a branch to publish to; {short_default} is not one of them.",
        )
    if not isinstance(requested, str) or not _is_usable_branch_name(requested.strip()):
        return _refuse(
            PUBLICATION_BRANCH_INVALID,
            "a publication branch must be a usable Git branch name",
            "Type a branch name Git would accept, such as registry-update.",
        )
    short_requested = _short_name(requested.strip())
    if short_requested.casefold() == short_default.casefold():
        return _refuse(
            DEFAULT_BRANCH_PUBLICATION,
            f"{short_default} is the branch this registry's subscribers read; "
            "AART publishes to a branch and never to that one",
            f"Publish to a different branch and open a pull request into {short_default}.",
        )
    return Ok(PublicationBranch(short_requested))


__all__ = [
    "DEFAULT_PUBLICATION_BRANCH",
    "DEFAULT_BRANCH_PUBLICATION",
    "PUBLICATION_BRANCH_NAMESPACE",
    "PUBLICATION_BRANCH_INVALID",
    "PublicationBranch",
    "RegistryCommitOrigin",
    "resolve_publication_branch",
    "suggested_publication_branch",
]
