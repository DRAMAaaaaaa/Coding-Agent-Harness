import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.domain.models import Task
from coding_agent_harness.governance.approvals import (
    ApprovalContext,
    ApprovalDecision,
    ApprovalManager,
    ApprovalRecord,
)
from coding_agent_harness.governance.paths import PathGuard
from coding_agent_harness.governance.policy import (
    PolicyContext,
    PolicyEngine,
    normalized_delete_scope,
)
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.tools import files
from coding_agent_harness.tools.models import ToolContext, ToolResult
from coding_agent_harness.tools.registry import ToolRegistry


NOW = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
CONFIG_VERSION = "v1"
ACTION_ID = "delete-1"
ORIGINAL_CONTENT = b"original\n"
_TIMEOUT_SECONDS = 2.0


class _Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@dataclass(frozen=True)
class _DeleteHarness:
    database: Database
    root: Path
    task: Task
    clock: _Clock
    manager: ApprovalManager
    policy_context: PolicyContext
    target: Path
    digest: str

    def registry(
        self,
        *,
        database: Database | None = None,
        task_id: UUID | None = None,
        policy_context: PolicyContext | None = None,
    ) -> ToolRegistry:
        active_database = database or self.database
        return ToolRegistry(
            ToolContext(
                workspace_root=self.root,
                policy=PolicyEngine(PathGuard(self.root), Redactor()),
                policy_context=policy_context or self.policy_context,
                approval_manager=ApprovalManager(active_database, self.clock, uuid4),
                approval_task_id=task_id or self.task.id,
            )
        )


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    value = await asyncio.wait_for(
        Database.open(tmp_path / "approval.sqlite3"), timeout=_TIMEOUT_SECONDS
    )
    try:
        yield value
    finally:
        await asyncio.wait_for(value.close(), timeout=_TIMEOUT_SECONDS)


@pytest.fixture
async def delete_harness(tmp_path: Path, database: Database) -> _DeleteHarness:
    task = await _create_task(database)
    target = tmp_path / "victim.py"
    target.write_bytes(ORIGINAL_CONTENT)
    clock = _Clock()
    return _DeleteHarness(
        database=database,
        root=tmp_path,
        task=task,
        clock=clock,
        manager=ApprovalManager(database, clock, uuid4),
        policy_context=PolicyContext(
            workspace_root=tmp_path,
            task_state=TaskState.WAITING_ACTION_APPROVAL,
            event_sequence=0,
            config_version=CONFIG_VERSION,
            llm_api_authorized=False,
        ),
        target=target,
        digest=files.digest(target),
    )


@asynccontextmanager
async def _open_database(path: Path) -> AsyncIterator[Database]:
    database = await asyncio.wait_for(Database.open(path), timeout=_TIMEOUT_SECONDS)
    try:
        yield database
    finally:
        await asyncio.wait_for(database.close(), timeout=_TIMEOUT_SECONDS)


async def _create_task(database: Database) -> Task:
    workspace_id = uuid4()
    await database.connection.execute(
        "INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),)
    )
    await database.connection.commit()
    return await TaskRepository(database).create(
        Task(
            id=uuid4(),
            workspace_id=workspace_id,
            requirement="删除已批准文件",
            state=TaskState.WAITING_ACTION_APPROVAL,
            step_budget=1,
            time_budget_seconds=60.0,
            created_at=NOW,
            deadline_at=None,
        )
    )


def _approval_context(
    harness: _DeleteHarness,
    *,
    normalized_scope: str | None = None,
) -> ApprovalContext:
    return ApprovalContext(
        action_id=ACTION_ID,
        event_sequence=0,
        normalized_scope=normalized_scope
        or normalized_delete_scope(harness.root, harness.target, harness.digest),
        task_state=TaskState.WAITING_ACTION_APPROVAL,
        config_version=CONFIG_VERSION,
    )


async def _request_approval(
    harness: _DeleteHarness,
    *,
    decision: ApprovalDecision | None = ApprovalDecision.APPROVED,
    normalized_scope: str | None = None,
    expires_at: datetime | None = None,
) -> ApprovalRecord:
    context = _approval_context(harness, normalized_scope=normalized_scope)
    approval = await harness.manager.request(
        harness.task.id,
        "DELETE_PATH",
        context,
        expires_at or NOW + timedelta(minutes=1),
    )
    if decision is not None:
        await harness.manager.decide(approval.id, decision, "user", context)
    return approval


def _delete_action(
    harness: _DeleteHarness,
    *,
    path: Path | None = None,
    expected_sha256: str | None = None,
    approval_id: UUID | None = None,
) -> ToolAction:
    arguments = {
        "path": (path or harness.target).relative_to(harness.root).as_posix(),
        "expected_sha256": expected_sha256 or harness.digest,
    }
    if approval_id is not None:
        arguments["approval_id"] = str(approval_id)
    return ActionParser({"delete_file"}).parse(
        json.dumps(
            {
                "kind": "tool",
                "tool": "delete_file",
                "arguments": arguments,
                "idempotency_key": ACTION_ID,
            }
        )
    )


async def _consumed_at(database: Database, approval_id: UUID) -> str | None:
    cursor = await database.connection.execute(
        "SELECT consumed_at FROM approvals WHERE id = ?", (str(approval_id),)
    )
    try:
        row = await cursor.fetchone()
    finally:
        await cursor.close()
    assert row is not None
    return None if row[0] is None else str(row[0])


async def _all_consumed_at(database: Database) -> list[str | None]:
    cursor = await database.connection.execute(
        "SELECT consumed_at FROM approvals ORDER BY id"
    )
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    return [None if row[0] is None else str(row[0]) for row in rows]


def _assert_unchanged(path: Path, expected: bytes = ORIGINAL_CONTENT) -> None:
    assert path.exists()
    assert path.read_bytes() == expected


async def test_delete_without_approval_keeps_real_file_and_has_no_consumption(
    delete_harness: _DeleteHarness,
) -> None:
    result = await delete_harness.registry().execute(_delete_action(delete_harness))

    assert result.code == "APPROVAL_REQUIRED"
    _assert_unchanged(delete_harness.target)
    assert await _all_consumed_at(delete_harness.database) == []


@pytest.mark.parametrize(
    ("approval_state", "expected_code"),
    [
        pytest.param("pending", "NOT_APPROVED", id="pending"),
        pytest.param("rejected", "DENIED", id="rejected"),
        pytest.param("expired", "EXPIRED", id="expired"),
    ],
)
async def test_unavailable_approval_never_deletes_or_consumes(
    delete_harness: _DeleteHarness,
    approval_state: str,
    expected_code: str,
) -> None:
    decision = (
        None if approval_state == "pending" else ApprovalDecision.APPROVED
    )
    if approval_state == "rejected":
        decision = ApprovalDecision.DENIED
    approval = await _request_approval(
        delete_harness,
        decision=decision,
        expires_at=NOW + timedelta(seconds=1),
    )
    if approval_state == "expired":
        delete_harness.clock.now = NOW + timedelta(seconds=2)

    result = await delete_harness.registry().execute(
        _delete_action(delete_harness, approval_id=approval.id)
    )

    assert result.code == expected_code
    _assert_unchanged(delete_harness.target)
    assert await _consumed_at(delete_harness.database, approval.id) is None


@pytest.mark.parametrize(
    ("mismatch", "expected_code"),
    [
        pytest.param("scope", "STALE_SCOPE", id="stale-scope"),
        pytest.param("event_sequence", "STALE_EVENT", id="stale-event-sequence"),
        pytest.param("config_version", "STALE_CONFIG", id="stale-config-version"),
        pytest.param("task", "STALE_ACTION", id="cross-task"),
    ],
)
async def test_stale_approval_binding_never_deletes_or_consumes(
    delete_harness: _DeleteHarness,
    mismatch: str,
    expected_code: str,
) -> None:
    scope = '{"stale":true}' if mismatch == "scope" else None
    approval = await _request_approval(delete_harness, normalized_scope=scope)
    policy_context = delete_harness.policy_context
    task_id = delete_harness.task.id
    if mismatch == "event_sequence":
        policy_context = policy_context.model_copy(update={"event_sequence": 1})
    elif mismatch == "config_version":
        policy_context = policy_context.model_copy(
            update={"config_version": "stale-config"}
        )
    elif mismatch == "task":
        task_id = (await _create_task(delete_harness.database)).id

    result = await delete_harness.registry(
        task_id=task_id, policy_context=policy_context
    ).execute(_delete_action(delete_harness, approval_id=approval.id))

    assert result.code == expected_code
    _assert_unchanged(delete_harness.target)
    assert await _consumed_at(delete_harness.database, approval.id) is None


@pytest.mark.parametrize("change", ["path", "sha256"])
async def test_changed_delete_target_never_deletes_or_consumes(
    delete_harness: _DeleteHarness,
    change: str,
) -> None:
    approval = await _request_approval(delete_harness)
    action_path = delete_harness.target
    action_digest = delete_harness.digest
    unchanged_paths = [delete_harness.target]
    if change == "path":
        action_path = delete_harness.root / "other.py"
        action_path.write_bytes(ORIGINAL_CONTENT)
        unchanged_paths.append(action_path)
    else:
        action_digest = "0" * 64

    result = await delete_harness.registry().execute(
        _delete_action(
            delete_harness,
            path=action_path,
            expected_sha256=action_digest,
            approval_id=approval.id,
        )
    )

    assert result.code == "STALE_SCOPE"
    for path in unchanged_paths:
        _assert_unchanged(path)
    assert await _consumed_at(delete_harness.database, approval.id) is None


async def test_delete_consumes_approved_json_uuid_and_replay_has_one_side_effect(
    delete_harness: _DeleteHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval = await _request_approval(delete_harness)
    action = _delete_action(delete_harness, approval_id=approval.id)
    real_delete = files.delete_regular_file
    delete_calls: list[Path] = []

    def recording_delete(path: Path, expected_sha256: str) -> str:
        delete_calls.append(path)
        return real_delete(path, expected_sha256)

    monkeypatch.setattr(files, "delete_regular_file", recording_delete)

    result = await delete_harness.registry().execute(action)
    replay = await delete_harness.registry().execute(action)

    assert result.code == "OK"
    assert replay.code == "REPLAYED"
    assert not delete_harness.target.exists()
    assert delete_calls == [delete_harness.target]
    assert await _consumed_at(delete_harness.database, approval.id) is not None


async def test_two_connections_and_registries_race_to_one_real_delete(
    delete_harness: _DeleteHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval = await _request_approval(delete_harness)
    action = _delete_action(delete_harness, approval_id=approval.id)
    real_delete = files.delete_regular_file
    delete_calls: list[Path] = []

    def recording_delete(path: Path, expected_sha256: str) -> str:
        delete_calls.append(path)
        return real_delete(path, expected_sha256)

    monkeypatch.setattr(files, "delete_regular_file", recording_delete)
    barrier = asyncio.Barrier(2)

    async with _open_database(
        delete_harness.root / "approval.sqlite3"
    ) as second_database:
        registries = (
            delete_harness.registry(),
            delete_harness.registry(database=second_database),
        )

        async def execute_after_barrier(registry: ToolRegistry) -> ToolResult:
            await barrier.wait()
            return await registry.execute(action)

        contenders = [
            asyncio.create_task(execute_after_barrier(registry))
            for registry in registries
        ]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*contenders), timeout=_TIMEOUT_SECONDS
            )
        finally:
            for contender in contenders:
                if not contender.done():
                    contender.cancel()
            await asyncio.gather(*contenders, return_exceptions=True)

    assert sorted(result.code for result in results) == ["OK", "REPLAYED"]
    assert not delete_harness.target.exists()
    assert delete_calls == [delete_harness.target]
    assert await _consumed_at(delete_harness.database, approval.id) is not None


async def test_external_rewrite_after_consumption_is_stale_and_not_retryable(
    delete_harness: _DeleteHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval = await _request_approval(delete_harness)
    action = _delete_action(delete_harness, approval_id=approval.id)
    real_delete = files.delete_regular_file
    replacement = b"external replacement\n"
    delete_calls: list[Path] = []

    def rewrite_before_delete(path: Path, expected_sha256: str) -> str:
        delete_calls.append(path)
        path.write_bytes(replacement)
        return real_delete(path, expected_sha256)

    monkeypatch.setattr(files, "delete_regular_file", rewrite_before_delete)

    stale = await delete_harness.registry().execute(action)
    replay = await delete_harness.registry().execute(action)

    assert stale.code == "STALE_CONTENT"
    assert replay.code == "REPLAYED"
    _assert_unchanged(delete_harness.target, replacement)
    assert delete_calls == [delete_harness.target]
    assert await _consumed_at(delete_harness.database, approval.id) is not None
