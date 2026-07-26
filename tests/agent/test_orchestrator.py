from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from coding_agent_harness.agent.orchestrator import AgentOrchestrator
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.models import Task
from coding_agent_harness.providers.mock import ScriptedMockProvider
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.tools.models import ToolResult


class ScriptedTools:
    def __init__(self, results: list[ToolResult]) -> None:
        self._results = iter(results)

    async def execute(self, _action: object) -> ToolResult:
        return next(self._results)


@pytest.fixture
async def harness(tmp_path):
    database = await Database.open(tmp_path / "agent-loop.sqlite3")
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
            "修复 add 函数的计划",
            '{"kind":"tool","tool":"apply_patch","arguments":{"path":"src/add.py","expected_sha256":null,"content":"def add(a, b): return a - b\\n"},"idempotency_key":"patch-broken"}',
            '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"test-before"}',
            '{"kind":"tool","tool":"apply_patch","arguments":{"path":"src/add.py","expected_sha256":null,"content":"def add(a, b): return a + b\\n"},"idempotency_key":"patch-fixed"}',
            '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"test-after"}',
            '{"kind":"complete","summary":"add 已修复并通过测试"}',
        ]
    )
    tools = ScriptedTools(
        [
            ToolResult(ok=True, code="OK", changed_paths=("src/add.py",)),
            ToolResult(ok=False, code="VERIFICATION_FAILED", output="1 failed\nAssertionError: add(1, 2) == 4"),
            ToolResult(ok=True, code="OK", changed_paths=("src/add.py",)),
            ToolResult(ok=True, code="OK", output="1 passed"),
        ]
    )
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"apply_patch", "run_verification", "delete_file"}),
        tools=tools,
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )
    try:
        yield orchestrator, provider, task, database
    finally:
        await database.close()


async def test_feedback_changes_next_action_after_injected_failure(harness) -> None:
    orchestrator, provider, task, database = harness

    await orchestrator.propose_plan(task.id)
    await orchestrator.approve_plan(task.id)
    await orchestrator.run_until_wait(task.id)

    patches = [action for action in orchestrator.actions if action.tool == "apply_patch"]
    assert [patch.arguments["content"] for patch in patches] == [
        "def add(a, b): return a - b\n",
        "def add(a, b): return a + b\n",
    ]
    assert patches[0].idempotency_key != patches[1].idempotency_key
    assert "AssertionError: add(1, 2) == 4" in str(provider.requests[3].messages)
    events = await EventStore(database).list_for_task(task.id)
    assert any(
        event.event_type == "FINAL_SUMMARY_RECORDED"
        and event.payload["summary"] == "add 已修复并通过测试"
        for event in events
    )
    assert (await orchestrator.task(task.id)).state is TaskState.WAITING_FINAL_REVIEW


async def test_distinct_unreliable_failures_do_not_trigger_no_progress(tmp_path) -> None:
    database = await Database.open(tmp_path / "unreliable-count.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="修复", state=TaskState.CREATED, step_budget=3, time_budget_seconds=60, created_at=now, deadline_at=now + timedelta(minutes=1))
    )
    provider = ScriptedMockProvider([
        "计划",
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"first"}',
        '{"kind":"tool","tool":"apply_patch","arguments":{"path":"src/add.py","expected_sha256":null,"content":"first"},"idempotency_key":"patch"}',
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"second"}',
    ])
    orchestrator = AgentOrchestrator(provider=provider, parser=ActionParser({"apply_patch", "run_verification"}), tools=ScriptedTools([
        ToolResult(ok=False, code="VERIFICATION_FAILED", output="AssertionError: first"),
        ToolResult(ok=True, code="OK", changed_paths=("src/add.py",)),
        ToolResult(ok=False, code="VERIFICATION_FAILED", output="AssertionError: second"),
    ]), event_store=EventStore(database), tasks=TaskRepository(database))
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)
        await orchestrator.run_until_wait(task.id)
        decisions = [event.payload["reason_code"] for event in await EventStore(database).list_for_task(task.id) if event.event_type == "FEEDBACK_RECORDED"]
        assert decisions == ["CORRECTION_REQUIRED", "CORRECTION_REQUIRED"]
    finally:
        await database.close()


async def test_time_budget_applies_when_deadline_is_none(tmp_path) -> None:
    database = await Database.open(tmp_path / "time-budget.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="超时", state=TaskState.CREATED, step_budget=3, time_budget_seconds=1, created_at=datetime.now(UTC) - timedelta(seconds=2), deadline_at=None)
    )
    provider = ScriptedMockProvider(["计划"])
    orchestrator = AgentOrchestrator(provider=provider, parser=ActionParser({"run_verification"}), tools=ScriptedTools([]), event_store=EventStore(database), tasks=TaskRepository(database))
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)
        assert (await orchestrator.run_until_wait(task.id)).state is TaskState.WAITING_USER
        assert len(provider.requests) == 1
    finally:
        await database.close()


async def test_complete_action_rejects_verification_invalidated_by_patch(tmp_path) -> None:
    database = await Database.open(tmp_path / "stale-verification.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="修复", state=TaskState.CREATED, step_budget=4, time_budget_seconds=60, created_at=now, deadline_at=now + timedelta(minutes=1))
    )
    provider = ScriptedMockProvider([
        "计划",
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"verified"}',
        '{"kind":"tool","tool":"apply_patch","arguments":{"path":"src/add.py","expected_sha256":null,"content":"changed"},"idempotency_key":"changed-after-verify"}',
        '{"kind":"complete","summary":"过期摘要"}',
    ])
    orchestrator = AgentOrchestrator(provider=provider, parser=ActionParser({"apply_patch", "run_verification"}), tools=ScriptedTools([
        ToolResult(ok=True, code="OK", output="1 passed"),
        ToolResult(ok=True, code="OK", changed_paths=("src/add.py",)),
    ]), event_store=EventStore(database), tasks=TaskRepository(database))
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)
        assert (await orchestrator.run_until_wait(task.id)).state is TaskState.WAITING_USER
        events = await EventStore(database).list_for_task(task.id)
        assert not any(event.event_type == "FINAL_SUMMARY_RECORDED" for event in events)
        assert events[-1].payload["reason_code"] == "VERIFICATION_REQUIRED"
    finally:
        await database.close()


async def test_read_only_action_keeps_successful_verification_fresh(tmp_path) -> None:
    database = await Database.open(tmp_path / "read-after-verification.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="检查", state=TaskState.CREATED, step_budget=4, time_budget_seconds=60, created_at=now, deadline_at=now + timedelta(minutes=1))
    )
    provider = ScriptedMockProvider([
        "计划",
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"verified"}',
        '{"kind":"tool","tool":"search","arguments":{"query":"add"},"idempotency_key":"read-only"}',
        '{"kind":"complete","summary":"只读后摘要"}',
    ])
    orchestrator = AgentOrchestrator(provider=provider, parser=ActionParser({"run_verification", "search"}), tools=ScriptedTools([
        ToolResult(ok=True, code="OK", output="1 passed"),
        ToolResult(ok=True, code="OK", output="src/add.py"),
    ]), event_store=EventStore(database), tasks=TaskRepository(database))
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)
        assert (await orchestrator.run_until_wait(task.id)).state is TaskState.WAITING_FINAL_REVIEW
    finally:
        await database.close()


async def test_loop_persists_each_decision_and_blocks_dangerous_action(tmp_path) -> None:
    database = await Database.open(tmp_path / "dangerous.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="清理", state=TaskState.CREATED, step_budget=2, time_budget_seconds=60, created_at=now, deadline_at=now + timedelta(minutes=1))
    )
    provider = ScriptedMockProvider(["计划", '{"kind":"tool","tool":"delete_file","arguments":{"path":"old.py","expected_sha256":"0000000000000000000000000000000000000000000000000000000000000000"},"idempotency_key":"delete"}'])
    orchestrator = AgentOrchestrator(provider=provider, parser=ActionParser({"delete_file"}), tools=ScriptedTools([]), event_store=EventStore(database), tasks=TaskRepository(database))
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)
        await orchestrator.run_until_wait(task.id)
        events = await EventStore(database).list_for_task(task.id)
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
        assert any(event.event_type == "GOVERNANCE_BLOCKED" for event in events)
        assert not any(event.event_type == "TOOL_EXECUTION_STARTED" for event in events)
    finally:
        await database.close()
