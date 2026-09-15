"""Atomic filesystem interpreter for one reviewed Candidate promotion transaction."""

from __future__ import annotations

from agent_artifacts.application.promotion import (
    PromotionApplyCommand,
    PromotionApplyReceipt,
)
from agent_artifacts.domain.result import Err, Ok, Result
from agent_artifacts.protocol.native_tree import SourceSnapshot
from agent_artifacts.registry_commands.model import (
    RegistryApplyCommand,
    RegistryOperation,
    RegistryWorkspaceChange,
    RegistryWorkspacePlan,
    WorkspaceChangeKind,
    registry_workspace_review_digest,
)

from .registry_workspace import FilesystemRegistryWorkspace


class FilesystemPromotionOutput:
    """Adapt the existing rollback-capable registry writer; no Git push exists here."""

    def __init__(self, root: str):
        self._workspace = FilesystemRegistryWorkspace(root)

    def current(self) -> Result[SourceSnapshot]:
        return self._workspace.current()

    def apply(self, command: PromotionApplyCommand) -> Result[PromotionApplyReceipt]:
        promotion = command.plan
        changes = tuple(
            RegistryWorkspaceChange(
                item.path,
                WorkspaceChangeKind(item.kind.value),
                item.content,
                item.before_digest,
                item.after_digest,
                item.executable,
            )
            for item in promotion.changes
        )
        workspace_review = registry_workspace_review_digest(
            RegistryOperation.CANDIDATE_PROMOTION,
            promotion.expected_workspace_digest,
            promotion.next_workspace_digest,
            changes,
        )
        workspace_plan = RegistryWorkspacePlan(
            RegistryOperation.CANDIDATE_PROMOTION,
            promotion.expected_workspace_digest,
            promotion.next_workspace_digest,
            changes,
            workspace_review,
        )
        applied = self._workspace.apply(RegistryApplyCommand(workspace_plan))
        if isinstance(applied, Err):
            return applied
        return Ok(
            PromotionApplyReceipt(
                promotion.review_digest,
                applied.value.snapshot_digest,
                promotion.next_registry_snapshot,
                applied.value.changed_paths,
            )
        )
