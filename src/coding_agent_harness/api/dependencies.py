"""API 的显式依赖容器。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypeVar
from uuid import UUID

from anyio import CapacityLimiter, to_thread

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.models import Task
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.storage.workspaces import WorkspaceRepository
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.scanner import WorkspaceScanner
from coding_agent_harness.workspace.models import Workspace
from coding_agent_harness.workspace.worktrees import WorktreeManager
from coding_agent_harness.workspace.git import SafeGit
from coding_agent_harness.workspace.processes import CommandResult


_ResultT = TypeVar("_ResultT")


class BlockingWorker:
    """所有 API 阻塞端口共享的有界 worker-thread 依赖。"""

    def __init__(self, limiter: CapacityLimiter | None = None) -> None:
        self._limiter = limiter or CapacityLimiter(4)

    @property
    def limiter(self) -> CapacityLimiter:
        return self._limiter

    async def run(
        self,
        function: Callable[..., _ResultT],
        *args: object,
    ) -> _ResultT:
        return await to_thread.run_sync(
            function,
            *args,
            abandon_on_cancel=False,
            limiter=self._limiter,
        )


class OrchestratorPort(Protocol):
    async def propose_plan(self, task_id: UUID) -> Task: ...
    async def record_runtime_failure(self, task_id: UUID, reason_code: str) -> Task: ...
    async def approve_plan(self, task_id: UUID) -> Task: ...
    async def run_until_wait(self, task_id: UUID) -> Task: ...
    async def approve_final(self, task_id: UUID) -> Task: ...


OrchestratorFactory = Callable[[], OrchestratorPort]


class RuntimeUnavailableError(RuntimeError):
    """当前 API 依赖中没有可用的 Agent 运行时。"""


class TaskStorageUnavailableError(RuntimeError):
    """任务未能落盘，但已确定清理本次工作树。"""


class DefaultBranchError(ValueError):
    """Git 默认分支无法作为 Workspace 的明确领域错误。"""


class BranchResolver(Protocol):
    def default_branch(self, root: Path) -> str: ...


class TaskRunner(Protocol):
    async def create(self, workspace: Workspace, task_id: UUID, requirement: str) -> Task: ...


@dataclass(slots=True)
class ApiDependencies:
    workspaces: WorkspaceRepository
    tasks: TaskRepository
    event_store: EventStore
    detector: ProjectDetector
    scanner: WorkspaceScanner
    state_root: Path
    private_roots: tuple[Path, ...]
    orchestrator_factory: OrchestratorFactory | None
    task_runner: TaskRunner
    branch_resolver: BranchResolver
    worker: BlockingWorker


class PlanGateOrchestrator:
    """离线默认编排器，仅通过公开 API 形成计划审批门。"""

    def __init__(self, tasks: TaskRepository) -> None:
        self._tasks = tasks

    async def propose_plan(self, task_id: UUID) -> Task:
        from coding_agent_harness.domain.actions import TaskState

        return await self._tasks.update_state(task_id, TaskState.WAITING_PLAN_APPROVAL)

    async def approve_plan(self, task_id: UUID) -> Task:
        from coding_agent_harness.domain.actions import TaskState

        return await self._tasks.update_state(task_id, TaskState.DECIDING)

    async def record_runtime_failure(self, task_id: UUID, reason_code: str) -> Task:
        raise RuntimeUnavailableError("离线计划门不支持运行时故障事件")

    async def run_until_wait(self, task_id: UUID) -> Task:
        return await self._tasks.get(task_id) or (_raise_task_not_found())

    async def approve_final(self, task_id: UUID) -> Task:
        from coding_agent_harness.domain.actions import TaskState

        return await self._tasks.update_state(task_id, TaskState.COMPLETED)


def _raise_task_not_found() -> Task:
    raise KeyError("任务不存在")


class LocalTaskRunner:
    """创建真实隔离 worktree 后，持久化尚未执行的任务。"""

    def __init__(
        self,
        tasks: TaskRepository,
        state_root: Path,
        *,
        step_budget: int,
        time_budget_seconds: float,
        worker: BlockingWorker | None = None,
    ) -> None:
        self._tasks = tasks
        self._state_root = state_root
        self._step_budget = step_budget
        self._time_budget_seconds = time_budget_seconds
        self._worker = worker or BlockingWorker()

    async def create(self, workspace: Workspace, task_id: UUID, requirement: str) -> Task:
        prepared_requirement = self._tasks.prepare_requirement(requirement)

        def create_worktree() -> WorktreeManager:
            manager = WorktreeManager(workspace, self._state_root)
            manager.create(task_id, "HEAD")
            return manager

        async def create_and_persist() -> Task:
            manager = await self._worker.run(create_worktree)
            task = Task(
                id=task_id,
                workspace_id=workspace.id,
                requirement=requirement,
                state=TaskState.CREATED,
                step_budget=self._step_budget,
                time_budget_seconds=self._time_budget_seconds,
                created_at=datetime.now(UTC),
                deadline_at=None,
            )
            try:
                return await self._tasks.create_prepared(task, prepared_requirement)
            except Exception:
                try:
                    await self._worker.run(manager.release, task_id)
                except Exception:
                    from coding_agent_harness.workspace.worktrees import (
                        WorktreeUncertainError,
                    )

                    raise WorktreeUncertainError(
                        "任务工作树补偿结果不确定，需要人工检查"
                    ) from None
                raise TaskStorageUnavailableError("任务存储暂时不可用") from None

        operation = asyncio.create_task(create_and_persist())
        try:
            return await asyncio.shield(operation)
        except asyncio.CancelledError as cancellation:
            await _settle_task(operation)
            raise cancellation from None


class SafeBranchResolver:
    def __init__(self, safe_git: SafeGit) -> None:
        self._git = safe_git

    def default_branch(self, root: Path) -> str:
        result: CommandResult = self._git.run(root, ["branch", "--show-current"])
        try:
            branch = result.stdout.decode("utf-8").strip()
        except UnicodeDecodeError:
            branch = ""
        if result.returncode != 0 or not branch:
            raise DefaultBranchError("Git 默认分支不可用")
        return branch


class UnavailableTaskRunner:
    async def create(self, workspace: Workspace, task_id: UUID, requirement: str) -> Task:
        raise RuntimeUnavailableError("Agent 运行时未配置")


async def _settle_task(operation: asyncio.Task[Task]) -> Task:
    """忽略宿主取消直到副作用任务产生已观察的确定结果。"""

    while not operation.done():
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None:
                current.uncancel()
    if operation.cancelled():
        from coding_agent_harness.workspace.worktrees import WorktreeUncertainError

        raise WorktreeUncertainError("任务工作树结果不确定，需要人工检查")
    return operation.result()
