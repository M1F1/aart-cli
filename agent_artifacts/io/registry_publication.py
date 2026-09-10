"""The one adapter that moves a reviewed registry commit to a remote (`QA-082`, `D-228`).

Everything about this is deliberately narrow.  It pushes one commit the checkout already holds, to
one branch the command already named, on one remote the checkout already has, with a refspec that
spells the revision out — so what reaches the remote is the reviewed commit rather than whatever
`HEAD` has become since.  `--force`, `--force-with-lease`, `--delete` and `--mirror` are not options
that are refused: they are never constructed, so a rewritten history is a failed push rather than a
lost one.

The default-branch refusal is made twice on purpose.  `domain.publication` makes it from the
configured ref, which is what a subscriber reads; this makes it again from the remote's own `HEAD`,
because a configuration can disagree with the remote it names, and the branch that must never move
is the one the *remote* calls default.
"""

from __future__ import annotations

import os

from agent_artifacts.application.registry_publication import (
    PublicationOutcome,
    RegistryPublicationCommand,
    RegistryPublicationReceipt,
)
from agent_artifacts.configuration.policy import redact_text
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.publication import DEFAULT_BRANCH_PUBLICATION
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.git import GitProcessReceipt, GitProcessRequest, run_git_process

REGISTRY_PUBLICATION_FAILED = DiagnosticCode("registry-publication-failed")

_TIMEOUT_SECONDS = 120.0


def _error(code: DiagnosticCode, message: str, *remediation: str) -> Err:
    return Err(
        (
            Diagnostic(
                code,
                Severity.ERROR,
                redact_text(message),
                remediation=tuple(redact_text(item) for item in remediation),
                interactive=tuple(redact_text(item) for item in remediation),
            ),
        )
    )


def _git(
    root: str, *arguments: str, max_output_bytes: int = 64 * 1024
) -> Result[GitProcessReceipt]:
    return run_git_process(
        GitProcessRequest(("git", "-C", root, *arguments), root, _TIMEOUT_SECONDS, max_output_bytes)
    )


def _text(receipt: GitProcessReceipt) -> str:
    return receipt.stdout.decode("utf-8", errors="replace").strip()


def _remote_default_branch(root: str, remote: str) -> str | None:
    """What the remote itself calls default, read from its advertised `HEAD` rather than config."""

    shown = _git(root, "ls-remote", "--symref", "--", remote, "HEAD")
    if isinstance(shown, Err):
        return None
    for line in _text(shown.value).splitlines():
        if line.startswith("ref:"):
            target = line[4:].strip().split()[0]
            if target.startswith("refs/heads/"):
                return target[len("refs/heads/") :]
    return None


def publish_registry_commit(
    root: str,
    command: RegistryPublicationCommand,
) -> Result[RegistryPublicationReceipt]:
    """Push one reviewed revision to its publication branch, never to the remote's default."""

    if (
        not isinstance(root, str)
        or not os.path.isabs(root)
        or os.path.normpath(root) != root
        or not isinstance(command, RegistryPublicationCommand)
    ):
        return _error(
            REGISTRY_PUBLICATION_FAILED,
            "publishing needs a normalized absolute registry checkout and a prepared command",
        )
    branch = command.branch.value
    remotes = _git(root, "remote")
    if isinstance(remotes, Err):
        return remotes
    if command.remote not in _text(remotes.value).split():
        return _error(
            REGISTRY_PUBLICATION_FAILED,
            f"this registry checkout has no Git remote named {command.remote}",
            "Add the remote to the registry checkout, then publish again.",
        )
    default_branch = _remote_default_branch(root, command.remote)
    if default_branch is not None and default_branch.casefold() == branch.casefold():
        return _error(
            DEFAULT_BRANCH_PUBLICATION,
            f"{command.remote} calls {default_branch} its default branch; "
            "AART publishes to a branch and never to that one",
            f"Publish to a different branch and open a pull request into {default_branch}.",
        )
    held = _git(root, "cat-file", "-e", f"{command.revision}^{{commit}}", max_output_bytes=1024)
    if isinstance(held, Err):
        return _error(
            REGISTRY_PUBLICATION_FAILED,
            f"this registry checkout does not hold commit {command.revision[:12]}",
            "Create the registry commit here, then publish the revision it made.",
        )
    listed = _git(root, "ls-remote", "--heads", "--", command.remote, f"refs/heads/{branch}")
    if isinstance(listed, Err):
        return listed
    advertised = _text(listed.value)
    existing = advertised.split("\t")[0] if advertised else ""
    if existing == command.revision:
        return _receipt(command, PublicationOutcome.ALREADY_CURRENT)
    pushed = _git(root, "push", "--", command.remote, f"{command.revision}:refs/heads/{branch}")
    if isinstance(pushed, Err):
        return pushed
    return _receipt(
        command, PublicationOutcome.CREATED if not existing else PublicationOutcome.UPDATED
    )


def _receipt(
    command: RegistryPublicationCommand, outcome: PublicationOutcome
) -> Result[RegistryPublicationReceipt]:
    try:
        return Ok(
            RegistryPublicationReceipt(
                command.registry,
                command.remote,
                command.branch,
                command.revision,
                command.review_digest,
                outcome,
            )
        )
    except ValueError as error:
        return _error(REGISTRY_PUBLICATION_FAILED, f"publication receipt is invalid: {error}")


__all__ = ["REGISTRY_PUBLICATION_FAILED", "publish_registry_commit"]
