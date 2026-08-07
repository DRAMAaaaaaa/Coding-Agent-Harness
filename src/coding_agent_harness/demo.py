"""完全离线的确定性 Harness 机制演示。"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import cast
from uuid import UUID, uuid4

from coding_agent_harness.agent.orchestrator import AgentOrchestrator
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.domain.models import Task
from coding_agent_harness.providers.mock import ScriptedMockProvider
from coding_agent_harness.providers.registry import ProviderRegistry
from coding_agent_harness.learning.cards import ProjectLearningService
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.storage.workspaces import WorkspaceRepository
from coding_agent_harness.tools.models import (
    ToolContext,
    ToolResult,
    VerificationApproval,
    VerificationEvidence,
)
from coding_agent_harness.tools.registry import ToolRegistry
from coding_agent_harness.governance.paths import PathGuard
from coding_agent_harness.governance.policy import PolicyContext, PolicyEngine
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.git import SafeGit
from coding_agent_harness.workspace.models import RepositoryMap, Workspace
from coding_agent_harness.workspace.processes import (
    CommandResult,
    ProcessRequest,
    ProcessRunner,
    SubprocessGitRunner,
)
from coding_agent_harness.workspace.worktrees import WorktreeManager


class DemoProviderRegistry:
    """按任务返回隔离的离线脚本，并保留父任务的问答上下文。"""

    def __init__(self, initial: ScriptedMockProvider) -> None:
        self._initial = initial
        self._providers: dict[UUID, ScriptedMockProvider] = {}
        self._initial_task: UUID | None = None
        self._learning_tasks: set[UUID] = set()

    def mark_learning(self, task_id: UUID) -> None:
        self._learning_tasks.add(task_id)

    async def build_for_task(self, task: Task) -> ScriptedMockProvider:
        provider = self._providers.get(task.id)
        if provider is not None:
            return provider
        if task.id in self._learning_tasks:
            provider = ScriptedMockProvider(learning_demo_script())
        elif "纠正：" in task.requirement:
            provider = ScriptedMockProvider(correction_demo_script())
        elif self._initial_task is None:
            self._initial_task = task.id
            provider = self._initial
        else:
            provider = ScriptedMockProvider(demo_script())
        self._providers[task.id] = provider
        return provider


@dataclass(frozen=True, slots=True)
class GovernanceEvidence:
    blocked_event: bool
    tool_calls: int
    final_state: str


@dataclass(frozen=True, slots=True)
class FeedbackEvidence:
    feedback_in_second_request: bool
    actions: tuple[str, ...]
    final_state: str


@dataclass(frozen=True, slots=True)
class StopEvidence:
    same_fingerprint_count: int
    final_state: str


@dataclass(frozen=True, slots=True)
class DemoReport:
    governance_guard: GovernanceEvidence
    feedback_changed_action: FeedbackEvidence
    deterministic_stop: StopEvidence

    @property
    def passed(self) -> bool:
        return (
            self.governance_guard.blocked_event
            and self.governance_guard.tool_calls == 0
            and self.governance_guard.final_state == TaskState.WAITING_USER.value
            and self.feedback_changed_action.feedback_in_second_request
            and self.feedback_changed_action.actions
            == ("run_verification", "apply_patch", "run_verification", "git_diff")
            and self.feedback_changed_action.final_state
            == TaskState.WAITING_FINAL_REVIEW.value
            and self.deterministic_stop.same_fingerprint_count == 2
            and self.deterministic_stop.final_state == TaskState.WAITING_USER.value
        )


class _QueuedTools:
    def __init__(
        self,
        results: list[ToolResult],
        evidence: VerificationEvidence | None = None,
    ) -> None:
        self._results = deque(results)
        self._evidence = evidence
        self.calls: list[ToolAction] = []

    async def execute(self, action: ToolAction) -> ToolResult:
        self.calls.append(action)
        if not self._results:
            raise AssertionError("演示工具结果序列已耗尽")
        return self._results.popleft()

    def normalized_governance_scope(self, action: ToolAction) -> str | None:
        if action.tool != "delete_file":
            return None
        return '{"path":"old.py","tool":"delete_file"}'

    async def current_verification_evidence(self) -> VerificationEvidence | None:
        return self._evidence


async def _new_task(root: Path, name: str, *, step_budget: int = 8) -> tuple[Database, Task]:
    database = await Database.open(root / f"{name}.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute(
        "INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),)
    )
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(
            id=uuid4(),
            workspace_id=workspace_id,
            requirement="执行确定性离线演示",
            state=TaskState.CREATED,
            step_budget=step_budget,
            time_budget_seconds=60,
            created_at=now,
            deadline_at=now + timedelta(minutes=1),
        )
    )
    return database, task


async def _prepare(
    database: Database,
    task: Task,
    provider: ScriptedMockProvider,
    tools: _QueuedTools,
    allowed_tools: tuple[str, ...],
) -> AgentOrchestrator:
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser(allowed_tools),
        tools=tools,
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )
    await orchestrator.propose_plan(task.id)
    await orchestrator.approve_plan(task.id)
    return orchestrator


async def _governance_scenario(root: Path) -> GovernanceEvidence:
    database, task = await _new_task(root, "governance", step_budget=2)
    provider = ScriptedMockProvider(
        [
            "只尝试危险删除。",
            '{"kind":"tool","tool":"delete_file","arguments":{"path":"old.py",'
            '"expected_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
            '"idempotency_key":"delete-old"}',
        ]
    )
    tools = _QueuedTools([])
    try:
        orchestrator = await _prepare(database, task, provider, tools, ("delete_file",))
        final = await orchestrator.run_until_wait(task.id)
        events = await EventStore(database).list_for_task(task.id)
        return GovernanceEvidence(
            blocked_event=any(event.event_type == "GOVERNANCE_BLOCKED" for event in events),
            tool_calls=len(tools.calls),
            final_state=final.state.value,
        )
    finally:
        await database.close()


def _evidence() -> VerificationEvidence:
    return VerificationEvidence(
        name="test",
        config_version="demo-v1",
        trust_fingerprint="a" * 64,
        worktree_fingerprint="b" * 64,
        required_checks=("test",),
    )


async def _feedback_scenario(root: Path) -> FeedbackEvidence:
    database, task = await _new_task(root, "feedback")
    evidence = _evidence()
    provider = ScriptedMockProvider(
        [
            "先验证失败，再修改并重新验证，最后展示差异。",
            '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},'
            '"idempotency_key":"verify-before"}',
            '{"kind":"tool","tool":"apply_patch","arguments":{"path":"demo.py",'
            '"expected_sha256":null,"content":"VALUE = 2\\n"},"idempotency_key":"fix"}',
            '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},'
            '"idempotency_key":"verify-after"}',
            '{"kind":"tool","tool":"git_diff","arguments":{},"idempotency_key":"diff"}',
            '{"kind":"complete","summary":"修改完成，测试通过。"}',
        ]
    )
    tools = _QueuedTools(
        [
            ToolResult(ok=False, code="VERIFICATION_FAILED", output="1 failed: VALUE != 2"),
            ToolResult(ok=True, code="OK", changed_paths=("demo.py",)),
            ToolResult(ok=True, code="OK", output="1 passed", verification=evidence),
            ToolResult(ok=True, code="OK", output="-VALUE = 1\n+VALUE = 2"),
        ],
        evidence,
    )
    try:
        orchestrator = await _prepare(
            database,
            task,
            provider,
            tools,
            ("run_verification", "apply_patch", "git_diff"),
        )
        final = await orchestrator.run_until_wait(task.id)
        feedback_request = provider.requests[2]
        return FeedbackEvidence(
            feedback_in_second_request="VALUE != 2" in str(feedback_request.messages),
            actions=tuple(action.tool for action in tools.calls),
            final_state=final.state.value,
        )
    finally:
        await database.close()


async def _stop_scenario(root: Path) -> StopEvidence:
    database, task = await _new_task(root, "stop", step_budget=3)
    provider = ScriptedMockProvider(
        [
            "重复验证以证明无进展停止。",
            '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},'
            '"idempotency_key":"same-1"}',
            '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},'
            '"idempotency_key":"same-2"}',
        ]
    )
    tools = _QueuedTools(
        [
            ToolResult(ok=False, code="VERIFICATION_FAILED", output="1 failed: stable error"),
            ToolResult(ok=False, code="VERIFICATION_FAILED", output="1 failed: stable error"),
        ]
    )
    try:
        orchestrator = await _prepare(
            database, task, provider, tools, ("run_verification",)
        )
        final = await orchestrator.run_until_wait(task.id)
        events = await EventStore(database).list_for_task(task.id)
        fingerprints: list[object] = []
        for event in events:
            observation = event.payload.get("observation")
            if event.event_type == "FEEDBACK_RECORDED" and isinstance(
                observation, dict
            ):
                fingerprints.append(observation.get("fingerprint"))
        stable = fingerprints[0] if fingerprints else None
        return StopEvidence(
            same_fingerprint_count=sum(value == stable for value in fingerprints),
            final_state=final.state.value,
        )
    finally:
        await database.close()


async def run_mechanism_demo() -> DemoReport:
    """执行三个独立场景，仅返回结构化证据，不输出内部内容。"""

    with TemporaryDirectory(prefix="harness-mechanism-demo-") as directory:
        root = Path(directory)
        return DemoReport(
            governance_guard=await _governance_scenario(root),
            feedback_changed_action=await _feedback_scenario(root),
            deterministic_stop=await _stop_scenario(root),
        )


def task_worktree_path(state_root: Path, workspace_id: UUID, task_id: UUID) -> Path:
    """返回 LocalTaskRunner 与 WorktreeManager 的确定性任务目录。"""

    return state_root / "worktrees" / str(workspace_id) / str(task_id)


class DemoProcessRunner:
    """仅把 fixture 声明的通用 python 解析到当前固定解释器。"""

    def __init__(self, delegate: ProcessRunner | None = None) -> None:
        self._delegate = delegate or SubprocessGitRunner()

    def run(self, request: ProcessRequest) -> CommandResult:
        argv = request.argv
        if argv and argv[0].casefold() in {"python", "python.exe"}:
            argv = (sys.executable, *argv[1:])
        return self._delegate.run(
            ProcessRequest(argv=argv, cwd=request.cwd, env=request.env, stdin=request.stdin)
        )


class DemoOrchestratorRouter:
    """按 task_id 缓存真实 AgentOrchestrator，并管理演示工作树生命周期。"""

    def __init__(
        self,
        *,
        provider: ScriptedMockProvider,
        tasks: TaskRepository,
        workspaces: WorkspaceRepository,
        event_store: EventStore,
        state_root: Path,
        project_learning: ProjectLearningService | None = None,
        on_completed: Callable[[], None] | None = None,
    ) -> None:
        self._provider = provider
        self._providers = DemoProviderRegistry(provider)
        self._tasks = tasks
        self._workspaces = workspaces
        self._event_store = event_store
        self._state_root = state_root
        self._project_learning = project_learning
        self._on_completed = on_completed
        self._orchestrators: dict[UUID, AgentOrchestrator] = {}
        self._workspaces_by_task: dict[UUID, Workspace] = {}

    async def _for(self, task_id: UUID) -> AgentOrchestrator:
        cached = self._orchestrators.get(task_id)
        if cached is not None:
            return cached
        task = await self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"任务不存在：{task_id}")
        stored = await self._workspaces.get(task.workspace_id)
        if stored is None:
            raise KeyError(f"Workspace 不存在：{task.workspace_id}")
        workspace = stored.workspace
        worktree = task_worktree_path(self._state_root, workspace.id, task.id)
        profile = ProjectDetector().detect(worktree)
        safe_git = SafeGit(self._state_root)
        safe_git.trust_linked_worktree(worktree, workspace.git_root)
        tracked_result = safe_git.run(worktree, ["ls-files", "-z"])
        if tracked_result.returncode != 0:
            raise RuntimeError("演示工作树无法读取跟踪文件")
        tracked = tuple(
            path for path in tracked_result.stdout.decode("utf-8").split("\0") if path
        )
        repository_map = RepositoryMap(
            root=worktree,
            tracked_files=tracked,
            documents=(),
            test_paths=tuple(path for path in tracked if path.startswith("tests/")),
            recent_commits=(),
            dirty_paths=(),
        )
        assert profile.trust_fingerprint is not None
        config_version = "demo-verification-v1"
        tools = ToolRegistry(
            ToolContext(
                workspace_root=worktree,
                state_root=self._state_root,
                repository_map=repository_map,
                profile=profile,
                policy=PolicyEngine(PathGuard(worktree), Redactor()),
                policy_context=PolicyContext(
                    workspace_root=worktree,
                    task_state=TaskState.EXECUTING,
                    event_sequence=1,
                    config_version=config_version,
                    llm_api_authorized=False,
                ),
                safe_git=safe_git,
                runner=DemoProcessRunner(),
                verification_config_version=config_version,
                verification_approval=VerificationApproval(
                    approval_id="demo-approved-test",
                    config_version=config_version,
                    trust_fingerprint=profile.trust_fingerprint,
                ),
            )
        )
        learning = None
        if self._project_learning is not None:
            learning = await self._project_learning.latest_for_workspace(task.workspace_id)
            if learning is not None:
                self._providers.mark_learning(task.id)
        orchestrator = AgentOrchestrator(
            provider=await self._providers.build_for_task(task),
            parser=ActionParser(("apply_patch", "run_verification", "git_diff")),
            tools=tools,
            event_store=self._event_store,
            tasks=self._tasks,
            pause_on_verification_failure=True,
            project_learning=learning,
        )
        self._orchestrators[task_id] = orchestrator
        self._workspaces_by_task[task_id] = workspace
        return orchestrator

    async def propose_plan(self, task_id: UUID) -> Task:
        return await (await self._for(task_id)).propose_plan(task_id)

    async def record_runtime_failure(self, task_id: UUID, reason_code: str) -> Task:
        return await (await self._for(task_id)).record_runtime_failure(task_id, reason_code)

    async def approve_plan(self, task_id: UUID) -> Task:
        return await (await self._for(task_id)).approve_plan(task_id)

    async def run_until_wait(self, task_id: UUID) -> Task:
        return await (await self._for(task_id)).run_until_wait(task_id)

    async def approve_final(self, task_id: UUID) -> Task:
        task = await self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"任务不存在：{task_id}")
        stored = await self._workspaces.get(task.workspace_id)
        if stored is None:
            raise KeyError(f"Workspace 不存在：{task.workspace_id}")
        workspace = stored.workspace
        await asyncio.to_thread(WorktreeManager(workspace, self._state_root).freeze, task_id)
        if task.state is TaskState.COMPLETED:
            return task
        orchestrator = await self._for(task_id)
        completed = await orchestrator.approve_final(task_id)
        if self._on_completed is not None:
            self._on_completed()
        return completed

    async def provider_for_task(self, task: Task) -> ScriptedMockProvider:
        return await self._providers.build_for_task(task)

    @property
    def provider_registry(self) -> ProviderRegistry:
        return cast(ProviderRegistry, self._providers)

    def cleanup(self, *, timeout_seconds: float = 10.0) -> None:
        for task_id, workspace in tuple(self._workspaces_by_task.items()):
            worktree = task_worktree_path(self._state_root, workspace.id, task_id)
            demo_file = worktree / "demo.py"
            if demo_file.is_file():
                demo_file.write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
            cleanup_git = SafeGit(
                self._state_root,
                runner=SubprocessGitRunner(timeout_seconds=timeout_seconds),
            )
            manager = WorktreeManager(
                workspace,
                self._state_root,
                safe_git=cleanup_git,
            )
            manager.release(task_id)


def demo_script() -> list[str]:
    """构造只用于临时 fixture 的固定 Scripted Mock 响应。"""

    initial_digest = digest_bytes(b"VALUE = 1\n")
    return [
        "先验证失败，再修改并重新验证，最后展示差异。",
        '{"kind":"tool","tool":"apply_patch","arguments":{"path":"demo.py",'
        f'"expected_sha256":"{initial_digest}","content":"VALUE = 3\\n"}},'
        '"idempotency_key":"e2e-wrong-fix"}',
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},'
        '"idempotency_key":"e2e-verify-before"}',
        "VALUE 仍为 1，因此验证失败。",
    ]


def correction_demo_script() -> list[str]:
    """纠正分支只消费自己的脚本，不会重放父任务的失败问答。"""

    initial_digest = digest_bytes(b"VALUE = 3\n")
    return [
        "纠正分支：将 VALUE 改为 2 后重新验证。",
        '{"kind":"tool","tool":"apply_patch","arguments":{"path":"demo.py",'
        f'"expected_sha256":"{initial_digest}","content":"VALUE = 2\\n"}},'
        '"idempotency_key":"e2e-fix"}',
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},'
        '"idempotency_key":"e2e-verify-after"}',
        '{"kind":"tool","tool":"git_diff","arguments":{},"idempotency_key":"e2e-diff"}',
        '{"kind":"complete","summary":"VALUE 已修改为 2，离线测试通过，差异已生成。"}',
    ]


def learning_demo_script() -> list[str]:
    """已应用经验的下一任务以可观察的首个验证动作开始。"""

    return [
        "已应用项目经验，先运行验证。",
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},'
        '"idempotency_key":"learning-first-verification"}',
    ]


def digest_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()
