from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from coding_agent_harness.agent.orchestrator import AgentOrchestrator
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.domain.models import Task
from coding_agent_harness.governance.paths import PathGuard
from coding_agent_harness.governance.policy import PolicyContext, PolicyEngine
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.providers.mock import ScriptedMockProvider
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.tools.models import ToolContext
from coding_agent_harness.tools.registry import ToolRegistry
from coding_agent_harness.workspace.detector import ProjectDetector
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
    (repository / "pyproject.toml").write_bytes(
        b"[build-system]\nrequires=[]\nbuild-backend='setuptools.build_meta'\n"
    )
    _run_git(repository, "add", ".")
    _run_git(repository, "commit", "-m", "baseline")
    worktree = tmp_path / "task-worktree"
    _run_git(repository, "worktree", "add", "-b", "task-loop", str(worktree), "HEAD")
    return worktree


def _tool(tool: str, arguments: dict[str, object], key: str) -> str:
    return json.dumps(
        {"kind": "tool", "tool": tool, "arguments": arguments, "idempotency_key": key}
    )


async def test_real_registry_mock_loop_repairs_file_after_feedback(tmp_path: Path) -> None:
    worktree = _real_temporary_worktree(tmp_path)
    wrong = "def add(a, b):\n    return a - b\n"
    fixed = "def add(a, b):\n    return a + b\n"
    original_sha = sha256((worktree / "src" / "add.py").read_bytes()).hexdigest()
    wrong_sha = sha256(wrong.encode()).hexdigest()
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
            profile=profile,
            runner=runner,
            policy=PolicyEngine(PathGuard(worktree), Redactor()),
            policy_context=policy_context,
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
    provider = ScriptedMockProvider(
        [
            "修复计划",
            _tool("read_file", {"path": "src/add.py"}, "read-current"),
            _tool(
                "apply_patch",
                {"path": "src/add.py", "expected_sha256": original_sha, "content": wrong},
                "patch-wrong",
            ),
            _tool("run_verification", {"name": "test"}, "verify-wrong"),
            _tool(
                "apply_patch",
                {"path": "src/add.py", "expected_sha256": wrong_sha, "content": fixed},
                "patch-fixed",
            ),
            _tool("run_verification", {"name": "test"}, "verify-fixed"),
            json.dumps({"kind": "complete", "summary": "add 已修复并通过测试"}),
        ]
    )
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
        assert feedback[0].payload["output"] == "1 failed\nAssertionError: add(1, 2) == 4\n"
        assert "1 failed" in str(provider.requests[4].messages)
        assert any(event.event_type == "READ_TOOL_COMPLETED" for event in events)
        assert any(event.event_type == "FINAL_SUMMARY_RECORDED" for event in events)

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
