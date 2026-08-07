"""单级纠正分支：先预留、后副作用，失败绝不重放。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel

from coding_agent_harness.api.dependencies import BlockingWorker, TaskRunner
from coding_agent_harness.domain.models import Task
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.providers.registry import ProviderRegistry
from coding_agent_harness.replay.checkpoints import capture_patch, write_checkpoint
from coding_agent_harness.storage.correction_branches import CorrectionBranchRepository, StoredCorrectionBranch
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.storage.workspaces import WorkspaceRepository
from coding_agent_harness.workspace.worktrees import WorktreeManager
from coding_agent_harness.workspace.git import SafeGit


class CorrectionBranch(BaseModel):
    id: UUID
    workspace_id: UUID
    parent_task_id: UUID
    source_event_sequence: int
    child_task_id: UUID | None
    status: Literal["CREATING", "READY", "UNCERTAIN"]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BranchComparison:
    branch_id: UUID
    parent_state: str
    child_state: str | None
    parent_verification: str | None
    child_verification: str | None
    parent_diff: str
    child_diff: str | None


class CorrectionBranchError(RuntimeError):
    pass


class CorrectionBranchService:
    def __init__(
        self, *, branches: CorrectionBranchRepository, tasks: TaskRepository,
        events: EventStore, workspaces: WorkspaceRepository, runner: TaskRunner,
        providers: ProviderRegistry, state_root: Path, worker: BlockingWorker,
    ) -> None:
        self._branches, self._tasks, self._events = branches, tasks, events
        self._workspaces, self._runner, self._providers = workspaces, runner, providers
        self._state_root, self._worker = state_root, worker

    async def create(self, parent_task_id: UUID, source_event_sequence: int, correction: str) -> CorrectionBranch:
        sanitized = Redactor().sanitize(correction).value
        if not isinstance(sanitized, str) or not sanitized.strip() or len(sanitized.encode("utf-8")) > 8192:
            raise CorrectionBranchError("INVALID_CORRECTION")
        parent = await self._require_parent(parent_task_id, source_event_sequence)
        if await self._branches.is_child_task(parent_task_id):
            raise CorrectionBranchError("NESTED_CORRECTION_UNSUPPORTED")
        workspace = await self._workspaces.get(parent.workspace_id)
        if workspace is None:
            raise CorrectionBranchError("BRANCH_CREATION_UNCERTAIN")
        # 授权必须早于预留后的任何本地副作用。
        await self._providers.build_for_task(parent)
        parent_root = self._state_root / "worktrees" / str(parent.workspace_id) / str(parent.id)
        checkpoint_git = SafeGit(self._state_root)
        checkpoint_git.trust_linked_worktree(parent_root, workspace.workspace.git_root)
        base_commit, patch = await self._worker.run(
            capture_patch, parent_root, self._state_root, source_event_sequence, checkpoint_git
        )
        import hashlib
        branch_id = uuid4()
        child_task_id = uuid4()
        branch, owner = await self._branches.reserve(
            branch_id, parent.workspace_id, parent.id, source_event_sequence, base_commit,
            hashlib.sha256(patch).hexdigest(), len(patch), f"{branch_id}.patch", child_task_id,
        )
        if not owner:
            if branch.status == "CREATING":
                raise CorrectionBranchError("BRANCH_CREATION_UNCERTAIN")
            return _model(branch)
        manager = WorktreeManager(workspace.workspace, self._state_root)
        frozen = False
        try:
            await self._worker.run(manager.freeze, parent.id)
            frozen = True
            await self._worker.run(write_checkpoint, self._state_root, branch.id, parent.id, source_event_sequence, base_commit, patch)
            child = await self._runner.create(
                workspace.workspace, child_task_id, f"{parent.requirement}\n\n纠正：{sanitized}",
                provider_profile_id=parent.provider_profile_id,
                provider_profile_version=parent.provider_profile_version,
                llm_api_authorized_at=parent.llm_api_authorized_at,
                base_commit=base_commit, initial_patch=patch,
            )
            return _model(await self._branches.mark_ready(branch.id, child.id))
        except BaseException:
            await self._branches.mark_uncertain(branch.id)
            if frozen:
                try:
                    await self._worker.run(manager.restore_writer, parent.id)
                except BaseException:
                    pass
            raise

    async def compare(self, branch_id: UUID) -> BranchComparison:
        branch = await self._branches.get(branch_id)
        if branch is None:
            raise KeyError(branch_id)
        parent = await self._tasks.get(branch.parent_task_id)
        child = await self._tasks.get(branch.child_task_id) if branch.child_task_id else None
        if parent is None:
            raise CorrectionBranchError("BRANCH_CREATION_UNCERTAIN")
        return BranchComparison(branch.id, parent.state.value, child.state.value if child else None,
            await _last_verification(self._events, parent.id),
            await _last_verification(self._events, child.id) if child else None,
            (self._state_root / "checkpoints" / branch.checkpoint_file_name).read_text(encoding="utf-8"),
            await self._child_diff(child))

    async def _require_parent(self, task_id: UUID, sequence: int) -> Task:
        task = await self._tasks.get(task_id)
        events = await self._events.list_for_task(task_id)
        if task is None or not any(event.sequence == sequence and event.event_type == "VERIFICATION_FAILED" for event in events):
            raise CorrectionBranchError("INVALID_CHECKPOINT")
        return task

    async def _child_diff(self, child: Task | None) -> str | None:
        if child is None:
            return None
        workspace = await self._workspaces.get(child.workspace_id)
        if workspace is None:
            return None
        root = self._state_root / "worktrees" / str(child.workspace_id) / str(child.id)
        git = SafeGit(self._state_root)
        git.trust_linked_worktree(root, workspace.workspace.git_root)
        result = await self._worker.run(
            git.run, root, ["diff", "--no-ext-diff", "--no-color", "HEAD", "--"]
        )
        if result.returncode != 0:
            return None
        try:
            return result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            return None


def _model(branch: StoredCorrectionBranch) -> CorrectionBranch:
    return CorrectionBranch(id=branch.id, workspace_id=branch.workspace_id, parent_task_id=branch.parent_task_id,
        source_event_sequence=branch.source_event_sequence, child_task_id=branch.child_task_id,
        status=branch.status, created_at=branch.created_at)


async def _last_verification(events: EventStore, task_id: UUID) -> str | None:
    for event in reversed(await events.list_for_task(task_id)):
        if event.event_type == "VERIFICATION_RECORDED":
            return str(event.payload.get("diagnostic", ""))
    return None
