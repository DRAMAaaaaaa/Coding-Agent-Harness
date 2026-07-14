import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.governance.approvals import (
    ApprovalContext,
    ApprovalDecision,
    ApprovalError,
    ApprovalManager,
    ApprovalRecord,
)
from coding_agent_harness.storage.database import Database


NOW = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def _seed_task(database: Database, task_id: UUID) -> None:
    workspace_id = uuid4()
    await database.connection.execute(
        "INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),)
    )
    await database.connection.execute(
        """
        INSERT INTO tasks (
            id, workspace_id, requirement, state, step_budget,
            time_budget_seconds, created_at, deadline_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(task_id),
            str(workspace_id),
            "测试审批",
            TaskState.WAITING_ACTION_APPROVAL.value,
            4,
            60.0,
            NOW.isoformat(),
            None,
        ),
    )
    await database.connection.commit()


def _context(**updates: object) -> ApprovalContext:
    values: dict[str, object] = {
        "action_id": "action-1",
        "event_sequence": 8,
        "normalized_scope": "shell:[pytest,-q]",
        "task_state": TaskState.WAITING_ACTION_APPROVAL,
        "config_version": "cfg-4",
    }
    values.update(updates)
    return ApprovalContext.model_validate(values, strict=True)


async def _manager(
    path: Path,
    *,
    clock: _Clock | None = None,
    uuid_factory: Callable[[], UUID] = uuid4,
) -> tuple[Database, ApprovalManager, UUID]:
    database = await Database.open(path)
    task_id = uuid4()
    await _seed_task(database, task_id)
    manager = ApprovalManager(database, clock or _Clock(), uuid_factory)
    return database, manager, task_id


async def test_database_migrates_v1_legacy_approval_and_reopen_is_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    migration = (
        Path(__file__).parents[2]
        / "src"
        / "coding_agent_harness"
        / "storage"
        / "migrations"
        / "001_initial.sql"
    ).read_text(encoding="utf-8")
    connection.executescript(migration)
    connection.execute("PRAGMA user_version=1")
    connection.execute("INSERT INTO workspaces (id) VALUES (?)", ("workspace-1",))
    connection.execute(
        """
        INSERT INTO tasks (
            id, workspace_id, requirement, state, step_budget,
            time_budget_seconds, created_at, deadline_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "task-1",
            "workspace-1",
            "legacy",
            TaskState.CANCELLED.value,
            1,
            1.0,
            NOW.isoformat(),
            None,
        ),
    )
    connection.execute(
        "INSERT INTO approvals (id, task_id, decision, created_at) VALUES (?, ?, ?, ?)",
        ("approval-1", "task-1", "APPROVED", NOW.isoformat()),
    )
    connection.commit()
    connection.close()

    first = await Database.open(path)
    version = await (await first.connection.execute("PRAGMA user_version")).fetchone()
    columns = await (
        await first.connection.execute("PRAGMA table_info(approvals)")
    ).fetchall()
    legacy = await (
        await first.connection.execute(
            "SELECT decision, consumed_at, expires_at FROM approvals WHERE id = ?",
            ("approval-1",),
        )
    ).fetchone()
    await first.close()

    second = await Database.open(path)
    try:
        count = await (
            await second.connection.execute(
                "SELECT COUNT(*) FROM approvals WHERE id = ?", ("approval-1",)
            )
        ).fetchone()
        assert version == (2,)
        assert {
            "action_id",
            "reason_code",
            "event_sequence",
            "normalized_scope",
            "task_state",
            "config_version",
            "decided_by",
            "expires_at",
            "decided_at",
            "consumed_at",
        } <= {str(row[1]) for row in columns}
        assert legacy is not None
        assert legacy[0] == ApprovalDecision.DENIED.value
        assert legacy[1] is not None and legacy[2] is not None
        assert count == (1,)
    finally:
        await second.close()


async def test_database_rejects_newer_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version=99")
    connection.close()

    with pytest.raises(RuntimeError, match="^数据库版本高于代码支持版本$"):
        await Database.open(path)


async def test_request_decide_consume_round_trip_is_persistent(tmp_path: Path) -> None:
    path = tmp_path / "approval.sqlite3"
    approval_id = UUID("00000000-0000-0000-0000-000000000041")
    database, manager, task_id = await _manager(
        path, uuid_factory=lambda: approval_id
    )
    context = _context()
    requested = await manager.request(task_id, "TOOL_NETWORK", context, NOW + timedelta(minutes=5))
    decided = await manager.decide(
        requested.id, ApprovalDecision.APPROVED, "human-reviewer", context
    )
    await database.close()

    reopened = await Database.open(path)
    try:
        consumed = await ApprovalManager(reopened, _Clock(), uuid4).consume(
            approval_id, context
        )
        assert isinstance(requested, ApprovalRecord)
        assert requested.decision is ApprovalDecision.PENDING
        assert decided.decision is ApprovalDecision.APPROVED
        assert consumed.consumed_at == NOW
        with pytest.raises(ApprovalError) as replayed:
            await ApprovalManager(reopened, _Clock(), uuid4).consume(approval_id, context)
        assert replayed.value.reason_code == "REPLAYED"
        assert str(replayed.value) == "审批已被消费"
    finally:
        await reopened.close()


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"action_id": "other-action"}, "STALE_ACTION"),
        ({"event_sequence": 9}, "STALE_EVENT"),
        ({"normalized_scope": "different"}, "STALE_SCOPE"),
        ({"task_state": TaskState.EXECUTING}, "STALE_STATE"),
        ({"config_version": "cfg-5"}, "STALE_CONFIG"),
    ],
)
async def test_decide_rejects_any_context_mismatch(
    tmp_path: Path,
    updates: dict[str, object],
    reason_code: str,
) -> None:
    database, manager, task_id = await _manager(tmp_path / f"{reason_code}.sqlite3")
    try:
        requested = await manager.request(
            task_id, "DANGEROUS", _context(), NOW + timedelta(minutes=1)
        )
        with pytest.raises(ApprovalError) as captured:
            await manager.decide(
                requested.id,
                ApprovalDecision.APPROVED,
                "reviewer-secret-name",
                _context(**updates),
            )
        assert captured.value.reason_code == reason_code
        assert "reviewer-secret-name" not in str(captured.value)
    finally:
        await database.close()


async def test_denied_expired_cancelled_and_invalid_requests_never_execute(
    tmp_path: Path,
) -> None:
    database, manager, task_id = await _manager(tmp_path / "reject.sqlite3")
    context = _context()
    try:
        denied = await manager.request(
            task_id, "DANGEROUS", context, NOW + timedelta(minutes=2)
        )
        await manager.decide(denied.id, ApprovalDecision.DENIED, "reviewer", context)
        with pytest.raises(ApprovalError) as denied_error:
            await manager.consume(denied.id, context)
        assert denied_error.value.reason_code == "DENIED"

        for expires_at in (NOW - timedelta(seconds=1), NOW.replace(tzinfo=None)):
            with pytest.raises((ApprovalError, ValueError)):
                await manager.request(task_id, "DANGEROUS", context, expires_at)

        with pytest.raises(ApprovalError) as cancelled:
            await manager.request(
                task_id,
                "DANGEROUS",
                _context(task_state=TaskState.CANCELLED),
                NOW + timedelta(minutes=2),
            )
        assert cancelled.value.reason_code == "TASK_CANCELLED"
    finally:
        await database.close()


async def test_expiry_and_duplicate_target_are_stable_errors(tmp_path: Path) -> None:
    clock = _Clock()
    database, manager, task_id = await _manager(
        tmp_path / "expiry.sqlite3", clock=clock
    )
    context = _context()
    try:
        requested = await manager.request(
            task_id, "DANGEROUS", context, NOW + timedelta(seconds=1)
        )
        with pytest.raises(ApprovalError) as duplicate:
            await manager.request(
                task_id, "DANGEROUS", context, NOW + timedelta(seconds=2)
            )
        assert duplicate.value.reason_code == "DUPLICATE"

        clock.now = NOW + timedelta(seconds=2)
        with pytest.raises(ApprovalError) as expired:
            await manager.decide(
                requested.id, ApprovalDecision.APPROVED, "reviewer", context
            )
        assert expired.value.reason_code == "EXPIRED"
    finally:
        await database.close()


async def test_two_connections_have_exactly_one_consume_winner_without_sleep(
    tmp_path: Path,
) -> None:
    path = tmp_path / "race.sqlite3"
    first, manager, task_id = await _manager(path)
    context = _context()
    requested = await manager.request(
        task_id, "DANGEROUS", context, NOW + timedelta(minutes=1)
    )
    await manager.decide(requested.id, ApprovalDecision.APPROVED, "reviewer", context)
    second = await Database.open(path)
    try:
        results = await asyncio.gather(
            ApprovalManager(first, _Clock(), uuid4).consume(requested.id, context),
            ApprovalManager(second, _Clock(), uuid4).consume(requested.id, context),
            return_exceptions=True,
        )
        assert sum(isinstance(result, ApprovalRecord) for result in results) == 1
        errors = [result for result in results if isinstance(result, ApprovalError)]
        assert len(errors) == 1
        assert errors[0].reason_code == "REPLAYED"
        assert not any(isinstance(result, sqlite3.OperationalError) for result in results)
    finally:
        await first.close()
        await second.close()
