from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from coding_agent_harness.agent.orchestrator import AgentOrchestrator
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.domain.models import Task
from coding_agent_harness.governance.paths import PathGuard
from coding_agent_harness.governance.policy import PolicyContext, PolicyEngine
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.providers.base import LLMRequest, LLMResponse
from coding_agent_harness.providers.mock import ScriptedMockProvider
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.tools.models import ToolContext, VerificationApproval
from coding_agent_harness.tools.registry import ToolRegistry
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.models import RepositoryMap
from coding_agent_harness.workspace.processes import CommandResult, ProcessRequest


class SourceAwareRunner:
    def __init__(self, worktree: Path, wrong_source: str, fixed_source: str) -> None:
        self._worktree = worktree
        self._wrong_source = wrong_source
        self._fixed_source = fixed_source
        self.calls: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.calls.append(request)
        assert request.cwd == self._worktree
        assert request.argv == ("python", "-m", "pytest")
        current = (self._worktree / "src" / "add.py").read_text(encoding="utf-8")
        if current == self._wrong_source:
            return CommandResult(returncode=1, stdout=b"1 failed\nAssertionError: add(1, 2) == 4\n", stderr=b"")
        assert current == self._fixed_source
        return CommandResult(returncode=0, stdout=b"1 passed\n", stderr=b"")


class UntrackedBeforeCompleteProvider(ScriptedMockProvider):
    def __init__(self, script: list[str], untracked_path: Path) -> None:
        super().__init__(script)
        self._untracked_path = untracked_path

    async def complete(self, request):
        response = await super().complete(request)
        if '"kind": "complete"' in response.content:
            self._untracked_path.write_bytes(b"external change\n")
        return response


class ObservationDrivenProvider:
    def __init__(self, wrong_source: str, fixed_source: str) -> None:
        self._wrong_source = wrong_source
        self._fixed_source = fixed_source
        self._step = 0
        self.requests: list[LLMRequest] = []
        self.patch_contents: list[str] = []
        self.read_observation: dict[str, object] | None = None

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        step = self._step
        self._step += 1
        if step == 0:
            return LLMResponse(content="修复计划")
        if step == 1:
            return LLMResponse(
                content=_tool("read_file", {"path": "src/add.py"}, "read-current")
            )
        if step == 2:
            observation = _latest_tool_observation(request)
            assert observation["tool"] == "read_file"
            assert observation["kind"] == "file"
            assert observation["path"] == "src/add.py"
            assert isinstance(observation.get("content"), str)
            assert "def add" in str(observation["content"])
            assert isinstance(observation.get("sha256"), str)
            self.read_observation = observation
            self.patch_contents.append(self._wrong_source)
            return LLMResponse(
                content=_tool(
                    "apply_patch",
                    {
                        "path": "src/add.py",
                        "expected_sha256": observation["sha256"],
                        "content": self._wrong_source,
                    },
                    "patch-wrong",
                )
            )
        if step == 3:
            return LLMResponse(
                content=_tool(
                    "run_verification", {"name": "test"}, "verify-wrong"
                )
            )
        if step == 4:
            assert "1 failed" in str(request.messages)
            previous_content = self.patch_contents[-1]
            self.patch_contents.append(self._fixed_source)
            return LLMResponse(
                content=_tool(
                    "apply_patch",
                    {
                        "path": "src/add.py",
                        "expected_sha256": sha256(
                            previous_content.encode("utf-8")
                        ).hexdigest(),
                        "content": self._fixed_source,
                    },
                    "patch-fixed",
                )
            )
        if step == 5:
            return LLMResponse(
                content=_tool(
                    "run_verification", {"name": "test"}, "verify-fixed"
                )
            )
        if step == 6:
            return LLMResponse(
                content=json.dumps(
                    {"kind": "complete", "summary": "add 已修复并通过测试"}
                )
            )
        raise AssertionError("观察驱动 Mock 收到多余请求")


class MutatingVerificationRunner:
    def __init__(self, worktree: Path, mutation: str) -> None:
        self._worktree = worktree
        self._mutation = mutation
        self.calls: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.calls.append(request)
        assert request.argv == ("python", "-m", "pytest")
        assert request.cwd == self._worktree
        if self._mutation == "tracked":
            (self._worktree / "src" / "add.py").write_text(
                "def add(a, b):\n    return a - b\n", encoding="utf-8"
            )
        elif self._mutation == "untracked":
            (self._worktree / "external.py").write_text(
                "external\n", encoding="utf-8"
            )
        else:
            (self._worktree / ".harness.yml").write_text(
                "test:\n  - python\n  - -m\n  - pytest\n", encoding="utf-8"
            )
        return CommandResult(returncode=0, stdout=b"1 passed\n", stderr=b"")


class VerificationRaceProvider:
    def __init__(self) -> None:
        self._step = 0
        self.requests: list[LLMRequest] = []
        self.followup: LLMRequest | None = None

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        step = self._step
        self._step += 1
        if step == 0:
            return LLMResponse(content="计划")
        if step == 1:
            return LLMResponse(
                content=_tool(
                    "run_verification", {"name": "test"}, "racing-verification"
                )
            )
        if step == 2:
            serialized = str(request.messages)
            observation = _latest_tool_observation(request)
            assert "UNTRUSTED_TOOL_OBSERVATION" in serialized
            assert "WORKTREE_CHANGED_DURING_VERIFICATION" in serialized
            assert "UNTRUSTED_RUNNER_OUTPUT" in serialized
            assert "1 passed" in serialized
            assert observation["kind"] == "failure"
            assert observation["code"] == "WORKTREE_CHANGED_DURING_VERIFICATION"
            self.followup = request
            return LLMResponse(
                content=json.dumps(
                    {"kind": "complete", "summary": "不应进入最终审查"}
                )
            )
        raise AssertionError("验证竞态 Mock 收到多余请求")


def _run_git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _real_temporary_worktree(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _run_git(repository, "init")
    _run_git(repository, "config", "user.email", "harness@example.test")
    _run_git(repository, "config", "user.name", "Harness Test")
    (repository / "src").mkdir()
    (repository / "src" / "add.py").write_bytes(b"def add(a, b):\n    return a + b\n")
    (repository / "pyproject.toml").write_bytes(b"[project]\nname='loop'\n")
    _run_git(repository, "add", ".")
    _run_git(repository, "commit", "-m", "baseline")
    worktree = tmp_path / "task-worktree"
    _run_git(repository, "worktree", "add", "-b", "task-loop", str(worktree), "HEAD")
    return worktree


def _tool(tool: str, arguments: dict[str, object], key: str) -> str:
    return json.dumps(
        {"kind": "tool", "tool": tool, "arguments": arguments, "idempotency_key": key}
    )


def _latest_tool_observation(request: LLMRequest) -> dict[str, object]:
    prefix = (
        "UNTRUSTED_TOOL_OBSERVATION\n"
        "BEGIN_UNTRUSTED_DATA\n"
    )
    suffix = "\nEND_UNTRUSTED_DATA"
    for message in reversed(request.messages):
        content = message.get("content")
        if not isinstance(content, str) or not content.startswith(prefix):
            continue
        assert content.endswith(suffix)
        decoded = json.loads(content[len(prefix) : -len(suffix)])
        assert isinstance(decoded, dict)
        return decoded
    raise AssertionError("后续 LLMRequest 缺少工具观察")


async def test_real_registry_mock_loop_repairs_file_after_feedback(tmp_path: Path) -> None:
    worktree = _real_temporary_worktree(tmp_path)
    secret = "read-secret-123"
    (worktree / "src" / "add.py").write_text(
        f"TOKEN = '{secret}'\ndef add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    wrong = "def add(a, b):\n    return a - b\n"
    fixed = "def add(a, b):\n    return a + b\n"
    runner = SourceAwareRunner(worktree, wrong, fixed)
    profile = ProjectDetector().detect(worktree)
    policy_context = PolicyContext(
        workspace_root=worktree,
        task_state=TaskState.EXECUTING,
        event_sequence=1,
        config_version="test-v1",
        llm_api_authorized=False,
    )
    registry = ToolRegistry(
        ToolContext(
            workspace_root=worktree,
            repository_map=RepositoryMap(
                root=worktree,
                tracked_files=("pyproject.toml", "src/add.py"),
                documents=(),
                test_paths=(),
                recent_commits=(),
                dirty_paths=(),
            ),
            profile=profile,
            runner=runner,
            policy=PolicyEngine(PathGuard(worktree), Redactor()),
            policy_context=policy_context,
            verification_config_version="test-v1",
            verification_approval=VerificationApproval(
                approval_id="integration-test",
                config_version="test-v1",
                trust_fingerprint=profile.trust_fingerprint,
            ),
        )
    )
    database = await Database.open(tmp_path / "loop.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(
            id=uuid4(),
            workspace_id=workspace_id,
            requirement="修复 add 函数",
            state=TaskState.CREATED,
            step_budget=8,
            time_budget_seconds=60,
            created_at=now,
            deadline_at=now + timedelta(minutes=1),
        )
    )
    provider = ObservationDrivenProvider(wrong, fixed)
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"read_file", "apply_patch", "run_verification"}),
        tools=registry,
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)
        final_task = await orchestrator.run_until_wait(task.id)

        assert final_task.state is TaskState.WAITING_FINAL_REVIEW
        assert (worktree / "src" / "add.py").read_text(encoding="utf-8") == fixed
        assert [request.argv for request in runner.calls] == [
            ("python", "-m", "pytest"),
            ("python", "-m", "pytest"),
        ]
        events = await EventStore(database).list_for_task(task.id)
        feedback = [event for event in events if event.event_type == "FEEDBACK_RECORDED"]
        assert feedback, "\n".join(event.event_type for event in events)
        feedback_diagnostic = str(feedback[0].payload["diagnostic"])
        assert "RESULT_CODE: VERIFICATION_FAILED" in feedback_diagnostic
        assert "UNTRUSTED_RUNNER_OUTPUT" in feedback_diagnostic
        assert "1 failed" in feedback_diagnostic
        assert "AssertionError: add(1, 2) == 4" in feedback_diagnostic
        assert "1 failed" in str(provider.requests[4].messages)
        assert provider.read_observation is not None
        assert provider.read_observation["sha256"]
        assert "def add" in str(provider.read_observation["content"])
        assert provider.patch_contents == [wrong, fixed]
        assert any(event.event_type == "READ_TOOL_COMPLETED" for event in events)
        assert any(event.event_type == "FINAL_SUMMARY_RECORDED" for event in events)
        serialized_events = str([event.model_dump(mode="json") for event in events])
        serialized_requests = str(provider.requests)
        assert secret not in serialized_events
        assert secret not in serialized_requests
        assert wrong not in serialized_events
        assert fixed not in serialized_events

        delete = await registry.execute(
            ToolAction.model_validate(
                {
                    "kind": "tool",
                    "tool": "delete_file",
                    "arguments": {"path": "src/add.py", "expected_sha256": sha256(fixed.encode()).hexdigest()},
                    "idempotency_key": "must-not-delete",
                }
            )
        )
        assert delete.code == "APPROVAL_REQUIRED"
        assert (worktree / "src" / "add.py").exists()
    finally:
        await database.close()


@pytest.mark.parametrize("mutation", ["tracked", "untracked", "config"])
async def test_verification_race_never_reaches_final_review(
    tmp_path: Path, mutation: str
) -> None:
    worktree = _real_temporary_worktree(tmp_path)
    runner = MutatingVerificationRunner(worktree, mutation)
    profile = ProjectDetector().detect(worktree)
    registry = ToolRegistry(
        ToolContext(
            workspace_root=worktree,
            repository_map=RepositoryMap(
                root=worktree,
                tracked_files=("pyproject.toml", "src/add.py"),
                documents=(),
                test_paths=(),
                recent_commits=(),
                dirty_paths=(),
            ),
            profile=profile,
            runner=runner,
            policy=PolicyEngine(PathGuard(worktree), Redactor()),
            policy_context=PolicyContext(
                workspace_root=worktree,
                task_state=TaskState.EXECUTING,
                event_sequence=1,
                config_version="test-v1",
                llm_api_authorized=False,
            ),
            verification_config_version="test-v1",
            verification_approval=VerificationApproval(
                approval_id=f"race-{mutation}",
                config_version="test-v1",
                trust_fingerprint=profile.trust_fingerprint,
            ),
        )
    )
    database = await Database.open(tmp_path / f"race-{mutation}.sqlite3")
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
            requirement="验证期间变化必须拒绝完成",
            state=TaskState.CREATED,
            step_budget=2,
            time_budget_seconds=60,
            created_at=now,
            deadline_at=now + timedelta(minutes=1),
        )
    )
    provider = VerificationRaceProvider()
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"run_verification"}),
        tools=registry,
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)

        final_task = await orchestrator.run_until_wait(task.id)

        events = await EventStore(database).list_for_task(task.id)
        assert final_task.state is TaskState.WAITING_USER
        assert events[-1].payload["reason_code"] == "VERIFICATION_REQUIRED"
        assert not any(
            event.event_type == "VERIFICATION_SUCCEEDED" for event in events
        )
        assert any(
            event.event_type == "TOOL_EXECUTION_FAILED"
            and event.payload["result"]["code"]
            == "WORKTREE_CHANGED_DURING_VERIFICATION"
            for event in events
        )
        assert len(runner.calls) == 1
        assert provider.followup is not None
    finally:
        await database.close()


async def test_real_registry_rejects_completion_after_untracked_file_appears(tmp_path: Path) -> None:
    worktree = _real_temporary_worktree(tmp_path)
    fixed = "def add(a, b):\n    return a + b\n"
    runner = SourceAwareRunner(
        worktree,
        "def add(a, b):\n    return a - b\n",
        fixed,
    )
    profile = ProjectDetector().detect(worktree)
    registry = ToolRegistry(
        ToolContext(
            workspace_root=worktree,
            repository_map=RepositoryMap(
                root=worktree,
                tracked_files=("pyproject.toml", "src/add.py"),
                documents=(),
                test_paths=(),
                recent_commits=(),
                dirty_paths=(),
            ),
            profile=profile,
            runner=runner,
            policy=PolicyEngine(PathGuard(worktree), Redactor()),
            policy_context=PolicyContext(
                workspace_root=worktree,
                task_state=TaskState.EXECUTING,
                event_sequence=1,
                config_version="test-v1",
                llm_api_authorized=False,
            ),
            verification_config_version="test-v1",
            verification_approval=VerificationApproval(
                approval_id="untracked-test",
                config_version="test-v1",
                trust_fingerprint=profile.trust_fingerprint,
            ),
        )
    )
    database = await Database.open(tmp_path / "untracked.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(
            id=uuid4(),
            workspace_id=workspace_id,
            requirement="拒绝验证后的外部未跟踪文件",
            state=TaskState.CREATED,
            step_budget=3,
            time_budget_seconds=60,
            created_at=now,
            deadline_at=now + timedelta(minutes=1),
        )
    )
    provider = UntrackedBeforeCompleteProvider(
        [
            "计划",
            _tool("run_verification", {"name": "test"}, "verified"),
            json.dumps({"kind": "complete", "summary": "不应完成"}),
        ],
        worktree / "external.py",
    )
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"run_verification"}),
        tools=registry,
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)

        assert (await orchestrator.run_until_wait(task.id)).state is TaskState.WAITING_USER
        events = await EventStore(database).list_for_task(task.id)
        assert events[-1].payload["reason_code"] == "VERIFICATION_REQUIRED"
        assert runner.calls
    finally:
        await database.close()
