"""`QA-016`/`B-090`: bringing one registry workspace into existence, as a single reviewed run.

Creating a registry is five separate canonical actions -- init, lock, build, validate, audit --
that only mean anything in that order: a lock over an uninitialized workspace has nothing to lock,
and an index built before the lock describes a registry that was never pinned.  The CLI leaves the
ordering to the operator because a terminal can.  A screen cannot: `B-090` exists because the
Maintainer had to leave the TUI and run all five by hand.

This module is the ordering, and nothing else.  Every stage is the same authority the CLI runs --
`LocalCurationService` for the three that write, and the same two planning gates for the two that
read -- so there is no second implementation of what a registry is.  What it adds is fail-fast
sequencing, a per-stage record of what happened, and one boundary the CLI states in prose and this
has to state in code: the run is local.  It may create a commit when the operator asked for one,
and it never pushes and never merges, because publishing a registry is a decision made through the
repository's own review process rather than by a key press (161.7).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from agent_artifacts.curation.model import (
    DEFAULT_MAXIMUM_AART,
    DEFAULT_MINIMUM_AART,
    CurationAction,
    CurationOutcome,
    CurationRequest,
)
from agent_artifacts.curation.runtime import load_local_curation_service
from agent_artifacts.domain.diagnostics import Diagnostic, DiagnosticCode, Severity
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.io.registry_workspace import FilesystemRegistryWorkspace
from agent_artifacts.protocol.semver import parse_semver
from agent_artifacts.registry_commands.model import RegistryInitOptions, RegistryQualityReport
from agent_artifacts.registry_commands.planning import (
    audit_registry_workspace,
    validate_registry_workspace,
)
from agent_artifacts.runtime_contract import EXECUTABLE_CAPABILITIES, EXECUTABLE_VERSION

__all__ = [
    "REGISTRY_BOOTSTRAP_REFUSED",
    "REGISTRY_BOOTSTRAP_STAGES",
    "RegistryBootstrapReport",
    "RegistryBootstrapStage",
    "bootstrap_registry_workspace",
    "registry_identity_refusal",
]

#: A bootstrap that never started, as opposed to one whose stage refused.
REGISTRY_BOOTSTRAP_REFUSED = DiagnosticCode("registry-bootstrap-refused")

#: The order, which is the whole product decision this module encodes.
REGISTRY_BOOTSTRAP_STAGES: tuple[str, ...] = ("init", "lock", "build", "validate", "audit")

_WRITING = (CurationAction.INIT, CurationAction.LOCK, CurationAction.BUILD)


@dataclass(frozen=True, slots=True)
class RegistryBootstrapStage:
    """One stage of the run: what it was, whether it passed, and what it did or refused."""

    name: str
    passed: bool
    lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name
            or not isinstance(self.passed, bool)
            or any(
                not isinstance(line, str) or any(char in line for char in "\r\n")
                for line in self.lines
            )
        ):
            raise ValueError("registry bootstrap stage is invalid")


@dataclass(frozen=True, slots=True)
class RegistryBootstrapReport:
    """What the run actually did, stage by stage, in the order it did it.

    A refused stage stops the run, so the report is a prefix of `REGISTRY_BOOTSTRAP_STAGES` rather
    than always all five: the screen has to be able to say which stage stopped, and saying so is
    only honest if the ones after it never ran.
    """

    stages: tuple[RegistryBootstrapStage, ...] = ()
    #: The short revision of the local commit, when one was asked for and made.  Never pushed.
    revision: str = ""

    def __post_init__(self) -> None:
        if any(not isinstance(item, RegistryBootstrapStage) for item in self.stages) or not (
            isinstance(self.revision, str) and not any(char in self.revision for char in "\r\n")
        ):
            raise ValueError("registry bootstrap report is invalid")

    @property
    def passed(self) -> bool:
        return bool(self.stages) and all(stage.passed for stage in self.stages)


def _refusal(message: str, *interactive: str) -> Err:
    return Err(
        (
            Diagnostic(
                REGISTRY_BOOTSTRAP_REFUSED,
                Severity.ERROR,
                message,
                interactive=interactive,
            ),
        )
    )


def registry_identity_refusal(
    *,
    registry_id: str,
    display_name: str,
    usage_reporting_repository: str | None = None,
) -> Err | None:
    """Whether these three answers can name a registry at all, before any of them is acted on.

    The same options object `init` builds is the judge, so a form cannot accept an identity the
    canonical action would go on to refuse -- and the refusal is prose, because the screen that
    reads it has no command line (`QA-017`).
    """

    minimum = parse_semver(DEFAULT_MINIMUM_AART)
    maximum = parse_semver(DEFAULT_MAXIMUM_AART)
    if isinstance(minimum, Err):
        return minimum
    if isinstance(maximum, Err):
        return maximum
    try:
        RegistryInitOptions(
            registry_id,
            display_name,
            minimum.value,
            maximum.value,
            usage_reporting_repository,
        )
    except ValueError:
        return _refusal(
            "this is not a usable registry identity",
            "The identifier is lowercase words joined by dashes, like acme-registry. "
            "The display name is one line of text. "
            "Leave usage reporting empty unless you have an owner/repository to send to.",
        )
    return None


def _git(root: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", root, *arguments),
        text=True,
        capture_output=True,
        check=False,
    )


def _outcome_lines(outcome: CurationOutcome) -> tuple[str, ...]:
    """What one writing stage did, without the follow-up commands the CLI prints (`QA-017`)."""

    if outcome.status == "no-op":
        return ("nothing needed changing",)
    plural = "" if outcome.changed_paths == 1 else "s"
    return (f"wrote {outcome.changed_paths} managed path{plural}",)


def _report_lines(report: RegistryQualityReport) -> tuple[str, ...]:
    """Only what failed. `QA-014`: a stage that passed has already said so by passing."""

    return tuple(
        f"{check.name}: {item.message}"
        for check in report.checks
        if not check.passed
        for item in check.diagnostics
        if item.severity is Severity.ERROR
    )


def bootstrap_registry_workspace(
    *,
    root: str,
    registry_id: str,
    display_name: str,
    usage_reporting_repository: str | None = None,
    commit: bool = False,
) -> Result[RegistryBootstrapReport]:
    """Run init, lock, build, validate and audit over `root`, stopping at the first refusal.

    `Err` means nothing was attempted; `Ok` with a report that has not passed means some of it was,
    and the report says exactly how far it got.
    """

    if not os.path.isabs(root) or os.path.normpath(root) != root:
        return _refusal("a registry is initialized in an absolute project path")
    if commit and _git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        # Checked before anything is written: the operator asked for a commit, and a run that
        # created the files and then could not commit them would have answered a different
        # question than the one on the form.
        return _refusal(
            "this project is not a Git checkout, so the run cannot make a commit",
            "Turn the local-commit choice off to write the registry files without a commit, "
            "or make this project a Git repository first.",
        )
    identity = registry_identity_refusal(
        registry_id=registry_id,
        display_name=display_name,
        usage_reporting_repository=usage_reporting_repository,
    )
    if identity is not None:
        return Ok(
            RegistryBootstrapReport(
                (
                    RegistryBootstrapStage(
                        "init", False, tuple(item.message for item in identity.diagnostics)
                    ),
                )
            )
        )
    service = load_local_curation_service(root)
    if isinstance(service, Err):
        return service

    stages: list[RegistryBootstrapStage] = []
    for action in _WRITING:
        try:
            request = CurationRequest(
                action,
                root,
                source_id=registry_id if action is CurationAction.INIT else None,
                display_name=display_name if action is CurationAction.INIT else None,
                usage_reporting_repository=(
                    usage_reporting_repository if action is CurationAction.INIT else None
                ),
            )
        except ValueError as error:
            stages.append(RegistryBootstrapStage(action.value, False, (str(error),)))
            return Ok(RegistryBootstrapReport(tuple(stages)))
        prepared = service.value.prepare(request)
        if isinstance(prepared, Err):
            stages.append(
                RegistryBootstrapStage(
                    action.value, False, tuple(item.message for item in prepared.diagnostics)
                )
            )
            return Ok(RegistryBootstrapReport(tuple(stages)))
        finalized = service.value.finalize(prepared.value, prepared.value.review.review_digest)
        if isinstance(finalized, Err):
            stages.append(
                RegistryBootstrapStage(
                    action.value, False, tuple(item.message for item in finalized.diagnostics)
                )
            )
            return Ok(RegistryBootstrapReport(tuple(stages)))
        if finalized.value.status == "failed":
            stages.append(RegistryBootstrapStage(action.value, False, ("the stage did not apply",)))
            return Ok(RegistryBootstrapReport(tuple(stages)))
        stages.append(RegistryBootstrapStage(action.value, True, _outcome_lines(finalized.value)))

    workspace = FilesystemRegistryWorkspace(root)
    for name in ("validate", "audit"):
        snapshot = workspace.snapshot()
        if isinstance(snapshot, Err):
            stages.append(
                RegistryBootstrapStage(
                    name, False, tuple(item.message for item in snapshot.diagnostics)
                )
            )
            return Ok(RegistryBootstrapReport(tuple(stages)))
        checked = (
            validate_registry_workspace(
                snapshot.value,
                executable_version=EXECUTABLE_VERSION,
                available_capabilities=EXECUTABLE_CAPABILITIES,
            )
            if name == "validate"
            else audit_registry_workspace(
                snapshot.value,
                executable_version=EXECUTABLE_VERSION,
                available_capabilities=EXECUTABLE_CAPABILITIES,
            )
        )
        if isinstance(checked, Err):
            stages.append(
                RegistryBootstrapStage(
                    name, False, tuple(item.message for item in checked.diagnostics)
                )
            )
            return Ok(RegistryBootstrapReport(tuple(stages)))
        stages.append(
            RegistryBootstrapStage(name, checked.value.passed, _report_lines(checked.value))
        )
        if not checked.value.passed:
            return Ok(RegistryBootstrapReport(tuple(stages)))

    if not commit:
        return Ok(RegistryBootstrapReport(tuple(stages)))
    added = _git(root, "add", "-A")
    if added.returncode != 0:
        stages.append(
            RegistryBootstrapStage("commit", False, (added.stderr.strip() or "git add failed",))
        )
        return Ok(RegistryBootstrapReport(tuple(stages)))
    subject = f"Initialize AART registry: {display_name}"
    committed = _git(root, "commit", "-m", subject)
    if committed.returncode != 0:
        stages.append(
            RegistryBootstrapStage(
                "commit",
                False,
                (committed.stderr.strip() or committed.stdout.strip() or "git commit failed",),
            )
        )
        return Ok(RegistryBootstrapReport(tuple(stages)))
    revision = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    # Stated rather than implied: the commit is where this run stops.
    stages.append(
        RegistryBootstrapStage(
            "commit", True, (f"committed {revision} locally; not pushed and not merged",)
        )
    )
    return Ok(RegistryBootstrapReport(tuple(stages), revision))
