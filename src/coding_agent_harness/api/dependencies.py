"""API 的显式依赖容器。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

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


class OrchestratorPort(Protocol):
    async def propose_plan(self, task_id: UUID) -> Task: ...
    async def approve_plan(self, task_id: UUID) -> Task: ...
    async def run_until_wait(self, task_id: UUID) -> Task: ...
    async def approve_final(self, task_id: UUID) -> Task: ...


OrchestratorFactory = Callable[[], OrchestratorPort]


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
    ) -> None:
        self._tasks = tasks
        self._state_root = state_root
        self._step_budget = step_budget
        self._time_budget_seconds = time_budget_seconds

    async def create(self, workspace: Workspace, task_id: UUID, requirement: str) -> Task:
        WorktreeManager(workspace, self._state_root).create(task_id, "HEAD")
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
        return await self._tasks.create(task)


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
            raise ValueError("Git 默认分支不可用")
        return branch


class UnavailableTaskRunner:
    async def create(self, workspace: Workspace, task_id: UUID, requirement: str) -> Task:
        raise RuntimeError("Agent 运行时未配置")
