from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4

import pytest

from coding_agent_harness.agent.orchestrator import AgentOrchestrator
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.domain.models import Task
from coding_agent_harness.providers.mock import ScriptedMockProvider, ScriptExhaustedError
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.tools.models import ToolResult
from coding_agent_harness.tools.models import ToolContext, VerificationEvidence
from coding_agent_harness.tools.registry import ToolRegistry


class ScriptedTools:
    def __init__(self, results: list[ToolResult]) -> None:
        self._results = iter(results)
        self._evidence = VerificationEvidence(
            name="test",
            config_version="scripted-v1",
            trust_fingerprint="a" * 64,
            worktree_fingerprint="b" * 64,
            required_checks=("test",),
        )

    async def execute(self, action: ToolAction) -> ToolResult:
        result = next(self._results)
        if action.tool != "run_verification" or not result.ok or result.verification is not None:
            return result
        return result.model_copy(
            update={"verification": self._evidence.model_copy(update={"name": action.arguments["name"]})}
        )

    async def current_verification_evidence(self) -> VerificationEvidence:
        return self._evidence


class EvidenceTools(ScriptedTools):
    def __init__(self, results: list[ToolResult], current: VerificationEvidence) -> None:
        super().__init__(results)
        self._current = current

    async def current_verification_evidence(self) -> VerificationEvidence:
        return self._current


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
    assert "VERIFICATION_FAILED" in str(provider.requests[3].messages)
    assert "UNTRUSTED_RUNNER_OUTPUT" in str(provider.requests[3].messages)
    events = await EventStore(database).list_for_task(task.id)
    assert any(
        event.event_type == "FINAL_SUMMARY_RECORDED"
        and event.payload["content_bytes"] > 0
        and "summary" not in event.payload
        for event in events
    )
    assert (await orchestrator.task(task.id)).state is TaskState.WAITING_FINAL_REVIEW


async def test_verification_failure_pauses_for_learning_when_enabled(harness) -> None:
    _, provider, task, database = harness
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"apply_patch", "run_verification", "delete_file"}),
        tools=ScriptedTools([
            ToolResult(ok=True, code="OK", changed_paths=("src/add.py",)),
            ToolResult(ok=False, code="VERIFICATION_FAILED", output="1 failed"),
        ]),
        event_store=EventStore(database),
        tasks=TaskRepository(database),
        pause_on_verification_failure=True,
    )

    await orchestrator.propose_plan(task.id)
    await orchestrator.approve_plan(task.id)

    assert (await orchestrator.run_until_wait(task.id)).state is TaskState.WAITING_USER
    assert (await EventStore(database).list_for_task(task.id))[-1].payload == {
        "reason_code": "LEARNING_CHECKPOINT"
    }


async def test_runtime_failure_is_recorded_once_through_legal_event(harness) -> None:
    _, _, task, database = harness
    orchestrator = AgentOrchestrator(
        provider=ScriptedMockProvider([]),
        parser=ActionParser(()),
        tools=ScriptedTools([]),
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )

    with pytest.raises(ScriptExhaustedError):
        await orchestrator.propose_plan(task.id)

    waiting = await orchestrator.record_runtime_failure(
        task.id,
        "PROVIDER_UNAVAILABLE token=must-not-persist",
    )
    repeated = await orchestrator.record_runtime_failure(
        task.id,
        "PROVIDER_UNAVAILABLE token=must-not-persist",
    )
    events = await EventStore(database).list_for_task(task.id)

    assert waiting.state is repeated.state is TaskState.WAITING_USER
    assert [event.sequence for event in events] == [1, 2, 3, 4]
    assert events[-1].event_type == "USER_INPUT_REQUIRED"
    assert events[-1].payload["reason_code"].startswith("PROVIDER_UNAVAILABLE")
    assert "must-not-persist" not in str(events[-1].payload)


async def test_request_cancellation_can_recover_created_task_through_legal_event(
    harness,
) -> None:
    _, _, task, database = harness
    orchestrator = AgentOrchestrator(
        provider=ScriptedMockProvider([]),
        parser=ActionParser(()),
        tools=ScriptedTools([]),
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )

    waiting = await orchestrator.record_runtime_failure(task.id, "REQUEST_CANCELLED")
    repeated = await orchestrator.record_runtime_failure(task.id, "REQUEST_CANCELLED")
    events = await EventStore(database).list_for_task(task.id)

    assert waiting.state is repeated.state is TaskState.WAITING_USER
    assert [event.event_type for event in events] == ["USER_INPUT_REQUIRED"]
    assert events[0].payload == {"reason_code": "REQUEST_CANCELLED"}


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


@pytest.mark.parametrize("absolute_path", [False, True])
async def test_loop_persists_each_decision_and_blocks_dangerous_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    absolute_path: bool,
) -> None:
    worktree = tmp_path / "target-worktree"
    worktree.mkdir()
    (worktree / "src").mkdir()
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    requested_path = str(worktree / "src" / ".." / "old.py") if absolute_path else "src/../old.py"
    database = await Database.open(tmp_path / "dangerous.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="清理", state=TaskState.CREATED, step_budget=2, time_budget_seconds=60, created_at=now, deadline_at=now + timedelta(minutes=1))
    )
    provider = ScriptedMockProvider(["计划", json.dumps({"kind": "tool", "tool": "delete_file", "arguments": {"path": requested_path, "expected_sha256": "A" * 64}, "idempotency_key": "delete"})])
    orchestrator = AgentOrchestrator(provider=provider, parser=ActionParser({"delete_file"}), tools=ToolRegistry(ToolContext(workspace_root=worktree)), event_store=EventStore(database), tasks=TaskRepository(database))
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)
        await orchestrator.run_until_wait(task.id)
        events = await EventStore(database).list_for_task(task.id)
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
        blocked = next(event for event in events if event.event_type == "GOVERNANCE_BLOCKED")
        assert blocked.payload["normalized_scope"] == '{"expected_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","path":"old.py","tool":"delete_file"}'
        assert not any(event.event_type == "TOOL_EXECUTION_STARTED" for event in events)
    finally:
        await database.close()


async def test_governance_scope_redacts_sensitive_action_path(harness, tmp_path: Path) -> None:
    orchestrator, _, _, _ = harness
    root = tmp_path / "scope-root"
    root.mkdir()
    orchestrator._tools = ToolRegistry(ToolContext(workspace_root=root))

    scope = orchestrator._governance_scope({
        "kind": "tool",
        "tool": "delete_file",
        "arguments": {"path": "token=secret-value", "expected_sha256": "a" * 64},
        "idempotency_key": "sensitive-scope",
    })

    assert "secret-value" not in scope
    assert "[REDACTED]" in scope


async def test_complete_requires_every_current_configured_check(tmp_path) -> None:
    database = await Database.open(tmp_path / "missing-check.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="完整验证", state=TaskState.CREATED, step_budget=3, time_budget_seconds=60, created_at=now, deadline_at=now + timedelta(minutes=1))
    )
    evidence = VerificationEvidence(
        name="lint",
        config_version="v1",
        trust_fingerprint="a" * 64,
        worktree_fingerprint="b" * 64,
        required_checks=("test", "lint"),
    )
    provider = ScriptedMockProvider([
        "计划",
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"lint"},"idempotency_key":"lint"}',
        '{"kind":"complete","summary":"只跑 lint"}',
    ])
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"run_verification"}),
        tools=EvidenceTools([ToolResult(ok=True, code="OK", verification=evidence)], evidence),
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)

        assert (await orchestrator.run_until_wait(task.id)).state is TaskState.WAITING_USER
    finally:
        await database.close()


async def test_complete_rejects_changed_current_worktree_snapshot(tmp_path) -> None:
    database = await Database.open(tmp_path / "external-edit.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="外部编辑", state=TaskState.CREATED, step_budget=3, time_budget_seconds=60, created_at=now, deadline_at=now + timedelta(minutes=1))
    )
    succeeded = VerificationEvidence(
        name="test",
        config_version="v1",
        trust_fingerprint="a" * 64,
        worktree_fingerprint="b" * 64,
        required_checks=("test",),
    )
    current = succeeded.model_copy(update={"name": "current", "worktree_fingerprint": "c" * 64})
    provider = ScriptedMockProvider([
        "计划",
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"test"}',
        '{"kind":"complete","summary":"外部编辑后摘要"}',
    ])
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"run_verification"}),
        tools=EvidenceTools([ToolResult(ok=True, code="OK", verification=succeeded)], current),
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)

        assert (await orchestrator.run_until_wait(task.id)).state is TaskState.WAITING_USER
    finally:
        await database.close()


async def test_complete_accepts_all_current_checks_after_last_change(tmp_path) -> None:
    database = await Database.open(tmp_path / "all-checks.sqlite3")
    workspace_id = uuid4()
    await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    await database.connection.commit()
    now = datetime.now(UTC)
    task = await TaskRepository(database).create(
        Task(id=uuid4(), workspace_id=workspace_id, requirement="全部检查", state=TaskState.CREATED, step_budget=4, time_budget_seconds=60, created_at=now, deadline_at=now + timedelta(minutes=1))
    )
    test_evidence = VerificationEvidence(
        name="test",
        config_version="v1",
        trust_fingerprint="a" * 64,
        worktree_fingerprint="b" * 64,
        required_checks=("test", "lint"),
    )
    lint_evidence = test_evidence.model_copy(update={"name": "lint"})
    provider = ScriptedMockProvider([
        "计划",
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"test"}',
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"lint"},"idempotency_key":"lint"}',
        '{"kind":"complete","summary":"全部检查已通过"}',
    ])
    orchestrator = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"run_verification"}),
        tools=EvidenceTools(
            [
                ToolResult(ok=True, code="OK", verification=test_evidence),
                ToolResult(ok=True, code="OK", verification=lint_evidence),
            ],
            test_evidence,
        ),
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )
    try:
        await orchestrator.propose_plan(task.id)
        await orchestrator.approve_plan(task.id)

        assert (await orchestrator.run_until_wait(task.id)).state is TaskState.WAITING_FINAL_REVIEW
    finally:
        await database.close()


async def test_events_and_followup_requests_do_not_persist_or_replay_secrets(harness) -> None:
    orchestrator, provider, task, database = harness
    secret = "leak-me-123"
    private_key = "-----BEGIN PRIVATE KEY-----\nleak-key\n-----END PRIVATE KEY-----"
    await database.connection.execute(
        "UPDATE tasks SET requirement = ? WHERE id = ?",
        (f"fix token={secret} {private_key}", str(task.id)),
    )
    await database.connection.commit()
    provider._script.clear()
    provider._script.extend(
        [
            "plan token=leak-me-123",
            '{"kind":"tool","tool":"run_verification","arguments":{"name":"test"},"idempotency_key":"secret-action"}',
            '{"kind":"complete","summary":"Bearer leak-me-123"}',
        ]
    )
    orchestrator._tools = ScriptedTools(
        [ToolResult(ok=False, code="VERIFICATION_FAILED", output=f"token={secret}\n{private_key}")]
    )

    await orchestrator.propose_plan(task.id)
    await orchestrator.approve_plan(task.id)
    await orchestrator.run_until_wait(task.id)

    events = await EventStore(database).list_for_task(task.id)
    serialized = str([event.model_dump(mode="json") for event in events])
    requests = str(provider.requests)
    assert secret not in serialized
    assert "leak-key" not in serialized
    assert secret not in requests
    assert "leak-key" not in requests


async def test_recovery_persists_uncertain_execution_and_requires_explicit_resume(harness) -> None:
    orchestrator, provider, task, database = harness
    await orchestrator.propose_plan(task.id)
    task = await orchestrator.approve_plan(task.id)
    task = await orchestrator._emit(task, "ACTION_PROPOSED", {"action": {"tool": "apply_patch"}})
    await orchestrator._emit(
        task,
        "TOOL_EXECUTION_STARTED",
        {"execution_id": "unfinished-1", "action": {"tool": "apply_patch"}},
    )
    restarted = AgentOrchestrator(
        provider=provider,
        parser=ActionParser({"apply_patch"}),
        tools=ScriptedTools([]),
        event_store=EventStore(database),
        tasks=TaskRepository(database),
    )

    waiting = await restarted.task(task.id)
    events = await EventStore(database).list_for_task(task.id)
    assert waiting.state is TaskState.WAITING_USER
    assert events[-1].event_type == "UNCERTAIN_SIDE_EFFECT_DETECTED"
    assert events[-1].payload["reason_code"] == "UNCERTAIN_SIDE_EFFECT"
    assert events[-1].payload["execution_id"] == "unfinished-1"
    assert len(await EventStore(database).list_for_task(task.id)) == len(events)
    resumed = await restarted.resume_after_uncertain(task.id, "continue")
    assert resumed.state is TaskState.DECIDING
    assert (await restarted.task(task.id)).state is TaskState.DECIDING


async def test_verification_event_bounds_long_sanitized_output(harness) -> None:
    orchestrator, _, task, _ = harness
    await orchestrator.propose_plan(task.id)
    task = await orchestrator.approve_plan(task.id)
    payload = {"run": {"name": "test", "ok": False, "failure_count": None, "output": "token=low-entropy-secret\n" + "x" * 70_000}}
    await orchestrator._emit(task, "VERIFICATION_RECORDED", payload)
    event = (await orchestrator._event_store.list_for_task(task.id))[-1]
    encoded = str(event.payload).encode("utf-8")
    assert len(encoded) < 65_536
    assert "low-entropy-secret" not in str(event.payload)
    assert "output" not in event.payload["run"]


async def test_tool_observation_redacts_and_bounds_each_field_without_losing_shape(
    harness,
) -> None:
    orchestrator, _, _, _ = harness
    payload = orchestrator._safe_payload(
        "TOOL_EXECUTION_COMPLETED",
        {
            "observation": {
                "tool": "read_file",
                "kind": "file",
                "code": "OK",
                "path": "src/app.py",
                "sha256": "a" * 64,
                "content": "token=observation-secret\n" + "x" * 70_000,
            }
        },
    )

    assert "observation" in payload
    observation = payload["observation"]
    assert isinstance(observation, dict)
    assert observation["sha256"] == "a" * 64
    assert "observation-secret" not in str(observation)
    assert "OUTPUT_LIMIT" in str(observation["content"])
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) < 65_536


async def test_recent_failed_tool_observation_reaches_next_request_boundary(
    harness,
) -> None:
    orchestrator, _, task, _ = harness
    await orchestrator.propose_plan(task.id)
    task = await orchestrator.approve_plan(task.id)
    task = await orchestrator._emit(
        task, "ACTION_PROPOSED", {"action": {"tool": "search"}}
    )
    task = await orchestrator._emit(
        task,
        "TOOL_EXECUTION_STARTED",
        {"execution_id": "failed-search", "action": {"tool": "search"}},
    )
    task = await orchestrator._emit(
        task,
        "TOOL_EXECUTION_FAILED",
        {
            "execution_id": "failed-search",
            "result": {"ok": False, "code": "REPOSITORY_MAP_REQUIRED"},
            "observation": {
                "tool": "search",
                "kind": "failure",
                "code": "REPOSITORY_MAP_REQUIRED",
                "diagnostic": "REPOSITORY_MAP_REQUIRED",
            },
        },
    )
    task = await orchestrator._emit(task, "TOOL_COMPLETED", {"tool": "search"})
    task = await orchestrator._emit(
        task, "VERIFICATION_READY", {"source": "orchestrator"}
    )

    messages = await orchestrator._messages(task)

    assert "UNTRUSTED_TOOL_OBSERVATION" in str(messages)
    assert "REPOSITORY_MAP_REQUIRED" in str(messages)
