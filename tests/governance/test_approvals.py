import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import aiosqlite
from pydantic import ValidationError

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.governance import approvals as approvals_module
from coding_agent_harness.governance.approvals import (
    ApprovalContext,
    ApprovalDecision,
    ApprovalError,
    ApprovalManager,
    ApprovalRecord,
)
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage import database as database_module


NOW = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class _RecordingCursor:
    def __init__(self, row: tuple[int] | None = None) -> None:
        self._row = row

    async def fetchone(self) -> tuple[int] | None:
        return self._row


class _RecordingConnection:
    def __init__(self, user_version: int) -> None:
        self.user_version = user_version
        self.statements: list[str] = []

    async def execute(self, sql: str) -> _RecordingCursor:
        statement = " ".join(sql.split())
        self.statements.append(statement)
        if statement == "PRAGMA user_version":
            return _RecordingCursor((self.user_version,))
        if statement.startswith("PRAGMA user_version = "):
            self.user_version = int(statement.rsplit(" ", 1)[1])
        return _RecordingCursor()

    async def commit(self) -> None:
        self.statements.append("COMMIT")

    async def rollback(self) -> None:
        self.statements.append("ROLLBACK")

    async def executescript(self, sql: str) -> None:
        self.statements.append(f"SCRIPT:{sql.strip()}")


class _BusyRecordingConnection(_RecordingConnection):
    async def execute(self, sql: str) -> _RecordingCursor:
        if " ".join(sql.split()) == "BEGIN IMMEDIATE":
            raise sqlite3.OperationalError("database is locked")
        return await super().execute(sql)


async def _seed_task(database: Database, task_id: UUID) -> None:
    workspace_id = uuid4()
    await database.connection.execute(
        "INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),)
    )
    await database.connection.execute(
        """
        INSERT INTO tasks (
            id, workspace_id, requirement, state, step_budget,
            time_budget_seconds, created_at, deadline_at, config_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "cfg-4",
        ),
    )
    await database.connection.execute(
        """
        INSERT INTO task_events (
            task_id, sequence, event_type, payload,
            state_before, state_after, occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(task_id),
            8,
            "APPROVAL_REQUESTED",
            "{}",
            TaskState.DECIDING.value,
            TaskState.WAITING_ACTION_APPROVAL.value,
            NOW.isoformat(),
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


async def test_migration_acquires_write_lock_before_reading_version(
) -> None:
    connection = _RecordingConnection(user_version=1)

    applied = await database_module._apply_one_migration_locked(
        connection,  # type: ignore[arg-type]
        database_module.Migration(
            version=2,
            sql="CREATE TABLE marker (id INTEGER);",
        ),
    )

    assert applied is True
    assert connection.statements[:2] == ["BEGIN IMMEDIATE", "PRAGMA user_version"]
    assert connection.statements[-2:] == ["PRAGMA user_version = 2", "COMMIT"]


def test_migration_files_do_not_manage_transactions_or_user_version() -> None:
    migration_directory = (
        Path(__file__).parents[2]
        / "src"
        / "coding_agent_harness"
        / "storage"
        / "migrations"
    )

    for migration in migration_directory.glob("[0-9][0-9][0-9]_*.sql"):
        sql = migration.read_text(encoding="utf-8").upper()
        assert "BEGIN" not in sql
        assert "COMMIT" not in sql
        assert "PRAGMA USER_VERSION" not in sql


async def test_migration_lock_timeout_has_one_fixed_error() -> None:
    connection = _BusyRecordingConnection(user_version=1)

    with pytest.raises(database_module.MigrationBusyError) as captured:
        await database_module._apply_one_migration_locked(
            connection,  # type: ignore[arg-type]
            database_module.Migration(
                version=2,
                sql="CREATE TABLE marker (id INTEGER);",
            ),
        )

    assert str(captured.value) == "数据库迁移正忙"
    assert "CREATE TABLE" not in str(captured.value)


async def test_fresh_database_runs_all_migrations_and_adds_task_config_version(
    tmp_path: Path,
) -> None:
    database = await Database.open(tmp_path / "fresh.sqlite3")
    try:
        version = await (
            await database.connection.execute("PRAGMA user_version")
        ).fetchone()
        columns = await (
            await database.connection.execute("PRAGMA table_info(tasks)")
        ).fetchall()

        assert version == (2,)
        config_column = next(row for row in columns if row[1] == "config_version")
        assert config_column[2:5] == ("TEXT", 1, "'v1'")
    finally:
        await database.close()


async def test_database_migrates_v1_legacy_approval_and_reopen_is_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.sqlite3"
    workspace_id = uuid4()
    task_id = uuid4()
    approval_id = uuid4()
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
    connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    connection.execute(
        """
        INSERT INTO tasks (
            id, workspace_id, requirement, state, step_budget,
            time_budget_seconds, created_at, deadline_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(task_id),
            str(workspace_id),
            "legacy",
            TaskState.WAITING_ACTION_APPROVAL.value,
            1,
            1.0,
            NOW.isoformat(),
            None,
        ),
    )
    connection.execute(
        "INSERT INTO approvals (id, task_id, decision, created_at) VALUES (?, ?, ?, ?)",
        (str(approval_id), str(task_id), "APPROVED", NOW.isoformat()),
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
            (str(approval_id),),
        )
    ).fetchone()
    await first.close()

    second = await Database.open(path)
    try:
        count = await (
            await second.connection.execute(
                "SELECT COUNT(*) FROM approvals WHERE id = ?", (str(approval_id),)
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
        legacy_context = ApprovalContext(
            action_id=f"legacy:{approval_id}",
            event_sequence=0,
            normalized_scope="legacy",
            task_state=TaskState.CANCELLED,
            config_version="legacy-v1",
        )
        with pytest.raises(ApprovalError) as rejected:
            await ApprovalManager(second, _Clock(), uuid4).consume(
                approval_id,
                legacy_context,
            )
        assert rejected.value.reason_code in {
            "REPLAYED",
            "DENIED",
            "EXPIRED",
            "STALE_STATE",
        }
    finally:
        await second.close()


async def test_two_database_instances_migrate_legacy_v1_once_without_sleep(
    tmp_path: Path,
) -> None:
    path = tmp_path / "concurrent-legacy.sqlite3"
    workspace_id = uuid4()
    task_id = uuid4()
    approval_id = uuid4()
    connection = sqlite3.connect(path)
    initial_sql = (
        Path(__file__).parents[2]
        / "src"
        / "coding_agent_harness"
        / "storage"
        / "migrations"
        / "001_initial.sql"
    ).read_text(encoding="utf-8")
    connection.executescript(initial_sql)
    connection.execute("PRAGMA user_version=1")
    connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    connection.execute(
        """
        INSERT INTO tasks (
            id, workspace_id, requirement, state, step_budget,
            time_budget_seconds, created_at, deadline_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(task_id),
            str(workspace_id),
            "legacy-race",
            TaskState.WAITING_ACTION_APPROVAL.value,
            1,
            1.0,
            NOW.isoformat(),
            None,
        ),
    )
    connection.execute(
        "INSERT INTO approvals (id, task_id, decision, created_at) VALUES (?, ?, ?, ?)",
        (str(approval_id), str(task_id), "APPROVED", NOW.isoformat()),
    )
    business_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    connection.commit()
    connection.close()

    first, second = await asyncio.gather(Database.open(path), Database.open(path))
    try:
        for database in (first, second):
            version = await (
                await database.connection.execute("PRAGMA user_version")
            ).fetchone()
            journal_mode = await (
                await database.connection.execute("PRAGMA journal_mode")
            ).fetchone()
            assert version == (2,)
            assert journal_mode is not None and journal_mode[0].casefold() == "wal"
        migrated = await (
            await first.connection.execute(
                """
                SELECT action_id, reason_code, event_sequence, task_state,
                       config_version, decision, decided_by, expires_at,
                       consumed_at
                FROM approvals WHERE id = ?
                """,
                (str(approval_id),),
            )
        ).fetchall()
        current_tables = {
            row[0]
            for row in await (
                await first.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            ).fetchall()
        }

        assert migrated == [
            (
                f"legacy:{approval_id}",
                "LEGACY_APPROVAL",
                0,
                TaskState.CANCELLED.value,
                "legacy-v1",
                ApprovalDecision.DENIED.value,
                "migration",
                "1970-01-01T00:00:00+00:00",
                NOW.isoformat(),
            )
        ]
        assert current_tables == business_tables
    finally:
        await first.close()
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
        assert cancelled.value.reason_code == "STALE_STATE"
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


async def test_two_connections_have_exactly_one_decision_winner_without_sleep(
    tmp_path: Path,
) -> None:
    path = tmp_path / "decision-race.sqlite3"
    first, manager, task_id = await _manager(path)
    context = _context()
    requested = await manager.request(
        task_id, "DANGEROUS", context, NOW + timedelta(minutes=1)
    )
    second = await Database.open(path)
    try:
        results = await asyncio.gather(
            ApprovalManager(first, _Clock(), uuid4).decide(
                requested.id,
                ApprovalDecision.APPROVED,
                "reviewer-one",
                context,
            ),
            ApprovalManager(second, _Clock(), uuid4).decide(
                requested.id,
                ApprovalDecision.DENIED,
                "reviewer-two",
                context,
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, ApprovalRecord) for result in results) == 1
        errors = [result for result in results if isinstance(result, ApprovalError)]
        assert len(errors) == 1
        assert errors[0].reason_code in {"DENIED", "NOT_APPROVED"}
    finally:
        await first.close()
        await second.close()


async def test_persisted_task_cancellation_invalidates_approved_record(
    tmp_path: Path,
) -> None:
    database, manager, task_id = await _manager(tmp_path / "cancelled.sqlite3")
    context = _context()
    try:
        requested = await manager.request(
            task_id, "DANGEROUS", context, NOW + timedelta(minutes=1)
        )
        await manager.decide(requested.id, ApprovalDecision.APPROVED, "reviewer", context)
        await database.connection.execute(
            "UPDATE tasks SET state = ? WHERE id = ?",
            (TaskState.CANCELLED.value, str(task_id)),
        )
        await database.connection.commit()

        with pytest.raises(ApprovalError) as captured:
            await manager.consume(requested.id, context)
        assert captured.value.reason_code == "TASK_CANCELLED"
    finally:
        await database.close()


async def test_busy_lock_is_a_stable_approval_error(tmp_path: Path) -> None:
    path = tmp_path / "busy.sqlite3"
    first, manager, task_id = await _manager(path)
    context = _context()
    requested = await manager.request(
        task_id, "DANGEROUS", context, NOW + timedelta(minutes=1)
    )
    await manager.decide(requested.id, ApprovalDecision.APPROVED, "reviewer", context)
    second = await Database.open(path)
    await second.connection.execute("PRAGMA busy_timeout=0")
    try:
        await first.connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(ApprovalError) as captured:
            await ApprovalManager(second, _Clock(), uuid4).consume(requested.id, context)
        assert captured.value.reason_code == "BUSY"
        assert "locked" not in str(captured.value).casefold()
    finally:
        await first.connection.rollback()
        await first.close()
        await second.close()


async def test_pending_and_missing_records_have_distinct_stable_errors(tmp_path: Path) -> None:
    database, manager, task_id = await _manager(tmp_path / "states.sqlite3")
    context = _context()
    try:
        requested = await manager.request(
            task_id, "DANGEROUS", context, NOW + timedelta(minutes=1)
        )
        with pytest.raises(ApprovalError) as pending:
            await manager.consume(requested.id, context)
        with pytest.raises(ApprovalError) as missing:
            await manager.consume(uuid4(), context)
        assert pending.value.reason_code == "NOT_APPROVED"
        assert missing.value.reason_code == "NOT_FOUND"
    finally:
        await database.close()


async def test_request_for_missing_task_is_a_stable_not_found_error(tmp_path: Path) -> None:
    database = await Database.open(tmp_path / "missing-task.sqlite3")
    try:
        with pytest.raises(ApprovalError) as captured:
            await ApprovalManager(database, _Clock(), uuid4).request(
                uuid4(),
                "DANGEROUS",
                _context(),
                NOW + timedelta(minutes=1),
            )
        assert captured.value.reason_code == "NOT_FOUND"
        assert "FOREIGN KEY" not in str(captured.value)
        assert "INSERT" not in str(captured.value)
    finally:
        await database.close()


@pytest.mark.parametrize(
    "updates",
    [
        {"action_id": ""},
        {"action_id": "a" * 257},
        {"event_sequence": -1},
        {"event_sequence": 2**63},
        {"normalized_scope": ""},
        {"config_version": ""},
    ],
)
def test_approval_context_rejects_empty_negative_or_unbounded_values(
    updates: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "action_id": "action-1",
        "event_sequence": 8,
        "normalized_scope": "scope",
        "task_state": TaskState.WAITING_ACTION_APPROVAL,
        "config_version": "cfg-4",
    }
    values.update(updates)

    with pytest.raises(ValidationError):
        ApprovalContext.model_validate(values, strict=True)


async def test_manager_rejects_constructed_invalid_context_with_fixed_code(
    tmp_path: Path,
) -> None:
    database, manager, task_id = await _manager(tmp_path / "invalid-context.sqlite3")
    invalid = ApprovalContext.model_construct(
        action_id="",
        event_sequence=-1,
        normalized_scope="",
        task_state=TaskState.WAITING_ACTION_APPROVAL,
        config_version="",
    )
    try:
        with pytest.raises(ApprovalError) as captured:
            await manager.request(
                task_id,
                "",
                invalid,
                NOW + timedelta(minutes=1),
            )
        assert captured.value.reason_code == "INVALID_CONTEXT"
    finally:
        await database.close()


async def test_invalid_decision_actor_and_time_have_fixed_codes(tmp_path: Path) -> None:
    database, manager, task_id = await _manager(tmp_path / "invalid-inputs.sqlite3")
    context = _context()
    try:
        with pytest.raises(ApprovalError) as invalid_time:
            await manager.request(
                task_id,
                "DANGEROUS",
                context,
                NOW.replace(tzinfo=None),
            )
        assert invalid_time.value.reason_code == "INVALID_TIME"

        requested = await manager.request(
            task_id,
            "DANGEROUS",
            context,
            NOW + timedelta(minutes=1),
        )
        with pytest.raises(ApprovalError) as invalid_decision:
            await manager.decide(
                requested.id,
                ApprovalDecision.PENDING,
                "reviewer",
                context,
            )
        assert invalid_decision.value.reason_code == "INVALID_DECISION"

        with pytest.raises(ApprovalError) as invalid_actor:
            await manager.decide(
                requested.id,
                ApprovalDecision.APPROVED,
                "",
                context,
            )
        assert invalid_actor.value.reason_code == "INVALID_DECISION"
    finally:
        await database.close()


async def test_non_lock_sqlite_error_is_sanitized_as_storage_error(tmp_path: Path) -> None:
    database, manager, task_id = await _manager(tmp_path / "storage-error.sqlite3")
    await database.connection.execute("DROP TABLE approvals")
    await database.connection.commit()
    try:
        with pytest.raises(ApprovalError) as captured:
            await manager.request(
                task_id,
                "DANGEROUS",
                _context(),
                NOW + timedelta(minutes=1),
            )
        error = captured.value
        assert error.reason_code == "STORAGE_ERROR"
        assert error.__cause__ is None
        assert error.__suppress_context__
        rendered = f"{error!s} {error!r}".casefold()
        assert "sqlite" not in rendered
        assert "approvals" not in rendered
        assert "insert" not in rendered
    finally:
        await database.close()


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"event_sequence": 7}, "STALE_EVENT"),
        ({"task_state": TaskState.EXECUTING}, "STALE_STATE"),
        ({"config_version": "caller-override"}, "STALE_CONFIG"),
    ],
)
async def test_request_uses_database_task_context_as_authority(
    tmp_path: Path,
    updates: dict[str, object],
    reason_code: str,
) -> None:
    database, manager, task_id = await _manager(tmp_path / f"authority-{reason_code}.sqlite3")
    try:
        with pytest.raises(ApprovalError) as captured:
            await manager.request(
                task_id,
                "DANGEROUS",
                _context(**updates),
                NOW + timedelta(minutes=1),
            )
        assert captured.value.reason_code == reason_code
    finally:
        await database.close()


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("UPDATE tasks SET state = 'EXECUTING' WHERE id = ?", "STALE_STATE"),
        ("UPDATE tasks SET config_version = 'cfg-5' WHERE id = ?", "STALE_CONFIG"),
    ],
)
async def test_decide_rechecks_authoritative_task_state_and_config(
    tmp_path: Path,
    mutation: str,
    reason_code: str,
) -> None:
    database, manager, task_id = await _manager(tmp_path / f"decide-{reason_code}.sqlite3")
    context = _context()
    try:
        requested = await manager.request(
            task_id, "DANGEROUS", context, NOW + timedelta(minutes=1)
        )
        await database.connection.execute(mutation, (str(task_id),))
        await database.connection.commit()

        with pytest.raises(ApprovalError) as captured:
            await manager.decide(
                requested.id,
                ApprovalDecision.APPROVED,
                "reviewer",
                context,
            )
        assert captured.value.reason_code == reason_code
    finally:
        await database.close()


async def test_consume_rechecks_authoritative_event_sequence(tmp_path: Path) -> None:
    database, manager, task_id = await _manager(tmp_path / "consume-stale-event.sqlite3")
    context = _context()
    try:
        requested = await manager.request(
            task_id, "DANGEROUS", context, NOW + timedelta(minutes=1)
        )
        await manager.decide(
            requested.id, ApprovalDecision.APPROVED, "reviewer", context
        )
        await database.connection.execute(
            """
            INSERT INTO task_events (
                task_id, sequence, event_type, payload,
                state_before, state_after, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(task_id),
                9,
                "STATE_CHANGED",
                "{}",
                TaskState.WAITING_ACTION_APPROVAL.value,
                TaskState.WAITING_ACTION_APPROVAL.value,
                NOW.isoformat(),
            ),
        )
        await database.connection.commit()

        with pytest.raises(ApprovalError) as captured:
            await manager.consume(requested.id, context)
        assert captured.value.reason_code == "STALE_EVENT"
    finally:
        await database.close()


async def test_request_and_apply_never_invokes_arbitrary_callable(
    tmp_path: Path,
) -> None:
    database, manager, task_id = await _manager(tmp_path / "request-apply.sqlite3")
    called = False

    async def write_file_side_effect(
        connection: aiosqlite.Connection,
        record: ApprovalRecord,
    ) -> None:
        del connection, record
        nonlocal called
        called = True
        raise RuntimeError("secret callback failure")

    try:
        with pytest.raises(ApprovalError) as captured:
            await manager.request_and_apply(
                task_id,
                "EXTERNAL_TRANSFER",
                _context(),
                NOW + timedelta(minutes=1),
                write_file_side_effect,
            )
        assert captured.value.reason_code == "INVALID_MUTATION"
        assert "secret callback failure" not in str(captured.value)
        assert called is False
        approvals = await (
            await database.connection.execute("SELECT COUNT(*) FROM approvals")
        ).fetchone()
        assert approvals == (0,)
    finally:
        await database.close()


def _mutation_contract() -> tuple[type[object], type[object], type[object]]:
    mutation_type = getattr(approvals_module, "ApprovalDatabaseMutation", None)
    binding_type = getattr(approvals_module, "ApprovalMutationBinding", None)
    operation_type = getattr(approvals_module, "ApprovalMutationOperation", None)
    assert mutation_type is not None
    assert binding_type is not None
    assert operation_type is not None
    return mutation_type, binding_type, operation_type


async def test_declarative_request_mutation_commits_with_approval(
    tmp_path: Path,
) -> None:
    mutation_type, binding_type, operation_type = _mutation_contract()
    database, manager, task_id = await _manager(tmp_path / "request-declaration.sqlite3")
    await database.connection.execute(
        "CREATE TABLE approval_bindings (approval_id TEXT PRIMARY KEY, task_id TEXT NOT NULL)"
    )
    await database.connection.commit()
    mutation = mutation_type(
        operation=operation_type.INSERT,  # type: ignore[attr-defined]
        table="approval_bindings",
        values=(
            ("approval_id", binding_type.APPROVAL_ID),  # type: ignore[attr-defined]
            ("task_id", binding_type.TASK_ID),  # type: ignore[attr-defined]
        ),
    )
    try:
        requested = await manager.request_and_apply(
            task_id,
            "EXTERNAL_TRANSFER",
            _context(),
            NOW + timedelta(minutes=1),
            mutation,  # type: ignore[arg-type]
        )
        binding = await (
            await database.connection.execute(
                "SELECT approval_id, task_id FROM approval_bindings"
            )
        ).fetchone()
        assert binding == (str(requested.id), str(task_id))
    finally:
        await database.close()


async def test_declarative_request_mutation_failure_rolls_back_approval(
    tmp_path: Path,
) -> None:
    mutation_type, binding_type, operation_type = _mutation_contract()
    database, manager, task_id = await _manager(tmp_path / "request-rollback.sqlite3")
    mutation = mutation_type(
        operation=operation_type.INSERT,  # type: ignore[attr-defined]
        table="missing_bindings",
        values=(("approval_id", binding_type.APPROVAL_ID),),  # type: ignore[attr-defined]
    )
    try:
        with pytest.raises(ApprovalError) as captured:
            await manager.request_and_apply(
                task_id,
                "EXTERNAL_TRANSFER",
                _context(),
                NOW + timedelta(minutes=1),
                mutation,  # type: ignore[arg-type]
            )
        assert captured.value.reason_code == "STORAGE_ERROR"
        approvals = await (
            await database.connection.execute("SELECT COUNT(*) FROM approvals")
        ).fetchone()
        assert approvals == (0,)
    finally:
        await database.close()


async def test_consume_and_apply_never_invokes_arbitrary_callable(
    tmp_path: Path,
) -> None:
    database, manager, task_id = await _manager(tmp_path / "consume-apply.sqlite3")
    context = _context()
    requested = await manager.request(
        task_id, "EXTERNAL_TRANSFER", context, NOW + timedelta(minutes=1)
    )
    await manager.decide(
        requested.id, ApprovalDecision.APPROVED, "reviewer", context
    )
    called = False

    async def process_side_effect(
        connection: aiosqlite.Connection,
        consumed_at: datetime,
    ) -> None:
        del connection, consumed_at
        nonlocal called
        called = True
        raise RuntimeError("secret callback failure")

    try:
        with pytest.raises(ApprovalError) as captured:
            await manager.consume_and_apply(
                requested.id,
                context,
                process_side_effect,
            )
        assert captured.value.reason_code == "INVALID_MUTATION"
        assert "secret callback failure" not in str(captured.value)
        assert called is False
        approval = await (
            await database.connection.execute(
                "SELECT consumed_at FROM approvals WHERE id = ?",
                (str(requested.id),),
            )
        ).fetchone()
        assert approval == (None,)
    finally:
        await database.close()


async def test_declarative_consume_mutation_commits_with_consumption(
    tmp_path: Path,
) -> None:
    mutation_type, binding_type, operation_type = _mutation_contract()
    database, manager, task_id = await _manager(tmp_path / "consume-declaration.sqlite3")
    context = _context()
    requested = await manager.request(
        task_id, "EXTERNAL_TRANSFER", context, NOW + timedelta(minutes=1)
    )
    await manager.decide(
        requested.id, ApprovalDecision.APPROVED, "reviewer", context
    )
    await database.connection.execute(
        "CREATE TABLE transfer_state (approval_id TEXT PRIMARY KEY, state TEXT NOT NULL, consumed_at TEXT)"
    )
    await database.connection.execute(
        "INSERT INTO transfer_state (approval_id, state) VALUES (?, 'READY')",
        (str(requested.id),),
    )
    await database.connection.commit()
    mutation = mutation_type(
        operation=operation_type.UPDATE,  # type: ignore[attr-defined]
        table="transfer_state",
        values=(
            ("state", "EXECUTING"),
            ("consumed_at", binding_type.CONSUMED_AT),  # type: ignore[attr-defined]
        ),
        where=(("approval_id", binding_type.APPROVAL_ID),),  # type: ignore[attr-defined]
    )
    try:
        consumed = await manager.consume_and_apply(
            requested.id, context, mutation  # type: ignore[arg-type]
        )
        transfer = await (
            await database.connection.execute(
                "SELECT state, consumed_at FROM transfer_state WHERE approval_id = ?",
                (str(requested.id),),
            )
        ).fetchone()
        assert consumed.consumed_at == NOW
        assert transfer == ("EXECUTING", NOW.isoformat())
    finally:
        await database.close()
