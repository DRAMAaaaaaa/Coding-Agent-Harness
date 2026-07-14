import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

import pytest

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.domain.models import Task
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import ConcurrencyError, EventStore
from coding_agent_harness.storage.repositories import TaskNotFoundError, TaskRepository


BUSINESS_TABLES = {
    "workspaces",
    "tasks",
    "task_events",
    "plans",
    "actions",
    "approvals",
    "tool_executions",
    "verification_runs",
    "artifacts",
    "memory_records",
    "credential_references",
}


class _ObservableLock:
    """让测试能用事件判断连接级锁是否发生竞争。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.contended = asyncio.Event()

    async def acquire(self) -> None:
        if self._lock.locked():
            self.contended.set()
        await self._lock.acquire()

    def release(self) -> None:
        self._lock.release()

    def locked(self) -> bool:
        return self._lock.locked()

    async def __aenter__(self) -> Self:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


async def _open_database(path: Path) -> Database:
    return await Database.open(path)


async def _insert_workspace(database: Database, workspace_id: UUID) -> None:
    await database.connection.execute(
        "INSERT INTO workspaces (id) VALUES (?)",
        (str(workspace_id),),
    )
    await database.connection.commit()


def _task(workspace_id: UUID, *, requirement: str = "实现状态存储") -> Task:
    now = datetime.now(UTC)
    return Task(
        id=uuid4(),
        workspace_id=workspace_id,
        requirement=requirement,
        state=TaskState.CREATED,
        step_budget=12,
        time_budget_seconds=1800.5,
        created_at=now,
        deadline_at=now + timedelta(minutes=30),
    )


def _event(task_id: UUID, *, payload: dict[str, object] | None = None) -> TaskEvent:
    return TaskEvent(
        task_id=task_id,
        sequence=0,
        event_type="SCAN_STARTED",
        payload=payload or {"说明": {"阶段": "扫描", "标签": ["甲", "乙"]}},
        state_before=TaskState.CREATED,
        state_after=TaskState.SCANNING,
        occurred_at=datetime.now(UTC),
    )


@pytest.fixture
async def database(tmp_path: Path):
    opened = await _open_database(tmp_path / "event-store.sqlite3")
    try:
        yield opened
    finally:
        await opened.close()


@pytest.fixture
async def persisted_task(database: Database) -> Task:
    workspace_id = uuid4()
    await _insert_workspace(database, workspace_id)
    return await TaskRepository(database).create(_task(workspace_id))


async def test_open_enables_pragmas_and_creates_all_tables(
    database: Database,
) -> None:
    foreign_keys = await (await database.connection.execute("PRAGMA foreign_keys")).fetchone()
    journal_mode = await (await database.connection.execute("PRAGMA journal_mode")).fetchone()
    busy_timeout = await (await database.connection.execute("PRAGMA busy_timeout")).fetchone()
    rows = await (
        await database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ?",
            ("table",),
        )
    ).fetchall()

    assert foreign_keys == (1,)
    assert journal_mode is not None and journal_mode[0].lower() == "wal"
    assert busy_timeout is not None and busy_timeout[0] > 0
    user_tables = {row[0] for row in rows if not row[0].startswith("sqlite_")}
    assert user_tables == BUSINESS_TABLES


async def test_reopening_database_runs_migrations_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "idempotent.sqlite3"
    workspace_id = uuid4()
    first = await _open_database(path)
    await _insert_workspace(first, workspace_id)
    await first.close()

    second = await _open_database(path)
    try:
        row = await (
            await second.connection.execute(
                "SELECT id FROM workspaces WHERE id = ?",
                (str(workspace_id),),
            )
        ).fetchone()
        assert row == (str(workspace_id),)
    finally:
        await second.close()


async def test_database_close_is_idempotent_and_context_managed(tmp_path: Path) -> None:
    database = await _open_database(tmp_path / "close.sqlite3")

    async with database as entered:
        assert entered is database

    await database.close()
    with pytest.raises(ValueError, match="active connection"):
        await database.connection.execute("SELECT 1")


async def test_task_repository_round_trips_strict_values(database: Database) -> None:
    workspace_id = uuid4()
    await _insert_workspace(database, workspace_id)
    original = _task(workspace_id, requirement="处理 O'Reilly；DROP TABLE tasks; --")
    repository = TaskRepository(database)

    created = await repository.create(original)
    loaded = await repository.get(original.id)
    updated = await repository.update_state(original.id, TaskState.SCANNING)

    assert created == original
    assert loaded == original
    assert updated == original.model_copy(update={"state": TaskState.SCANNING})
    assert await repository.get(uuid4()) is None


async def test_task_repository_round_trips_null_deadline(database: Database) -> None:
    workspace_id = uuid4()
    await _insert_workspace(database, workspace_id)
    original = _task(workspace_id).model_copy(
        update={"id": uuid4(), "deadline_at": None}
    )
    repository = TaskRepository(database)

    assert await repository.create(original) == original
    assert await repository.get(original.id) == original
    assert await repository.update_state(original.id, TaskState.SCANNING) == (
        original.model_copy(update={"state": TaskState.SCANNING})
    )


async def test_task_repository_requires_existing_workspace(database: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        await TaskRepository(database).create(_task(uuid4()))


async def test_task_repository_rejects_missing_task_update(database: Database) -> None:
    with pytest.raises(TaskNotFoundError):
        await TaskRepository(database).update_state(uuid4(), TaskState.FAILED)


async def test_append_assigns_ordered_sequences_and_lists_after(
    database: Database,
    persisted_task: Task,
) -> None:
    store = EventStore(database)
    first = await store.append(_event(persisted_task.id), expected_sequence=0)
    second_source = _event(persisted_task.id, payload={"quote": "x' OR 1=1 --"})
    second = await store.append(second_source, expected_sequence=1)

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.payload == {"quote": "x' OR 1=1 --"}
    assert await store.list_for_task(persisted_task.id) == [first, second]
    assert await store.list_for_task(persisted_task.id, after=1) == [second]
    assert await store.list_for_task(uuid4()) == []


async def test_append_rejects_stale_sequence_without_partial_write(
    database: Database,
    persisted_task: Task,
) -> None:
    store = EventStore(database)
    first = await store.append(_event(persisted_task.id), expected_sequence=0)

    with pytest.raises(ConcurrencyError):
        await store.append(_event(persisted_task.id), expected_sequence=0)

    assert await store.list_for_task(persisted_task.id) == [first]


async def test_append_rolls_back_constraint_failure(
    database: Database,
    persisted_task: Task,
) -> None:
    store = EventStore(database)

    with pytest.raises(sqlite3.IntegrityError):
        await store.append(_event(uuid4()), expected_sequence=0)

    valid = await store.append(_event(persisted_task.id), expected_sequence=0)
    assert valid.sequence == 1


async def test_same_connection_concurrency_has_one_winner(
    database: Database,
    persisted_task: Task,
) -> None:
    store = EventStore(database)
    results = await asyncio.gather(
        store.append(_event(persisted_task.id), expected_sequence=0),
        store.append(_event(persisted_task.id), expected_sequence=0),
        return_exceptions=True,
    )

    assert sum(isinstance(result, TaskEvent) for result in results) == 1
    assert sum(isinstance(result, ConcurrencyError) for result in results) == 1


async def test_two_connections_concurrency_has_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "competition.sqlite3"
    first_database = await _open_database(path)
    workspace_id = uuid4()
    await _insert_workspace(first_database, workspace_id)
    task = await TaskRepository(first_database).create(_task(workspace_id))
    second_database = await _open_database(path)
    try:
        results = await asyncio.gather(
            EventStore(first_database).append(_event(task.id), expected_sequence=0),
            EventStore(second_database).append(_event(task.id), expected_sequence=0),
            return_exceptions=True,
        )

        assert sum(isinstance(result, TaskEvent) for result in results) == 1
        assert sum(isinstance(result, ConcurrencyError) for result in results) == 1
        assert not any(isinstance(result, sqlite3.OperationalError) for result in results)
    finally:
        await first_database.close()
        await second_database.close()


async def test_busy_write_lock_becomes_stable_concurrency_error(tmp_path: Path) -> None:
    path = tmp_path / "busy.sqlite3"
    first_database = await _open_database(path)
    workspace_id = uuid4()
    await _insert_workspace(first_database, workspace_id)
    task = await TaskRepository(first_database).create(_task(workspace_id))
    second_database = await _open_database(path)
    await second_database.connection.execute("PRAGMA busy_timeout=0")
    try:
        await first_database.connection.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(ConcurrencyError) as captured:
                await EventStore(second_database).append(
                    _event(task.id),
                    expected_sequence=0,
                )
            assert str(captured.value) == "SQLite 写入竞争"
        finally:
            await first_database.connection.rollback()

        appended = await EventStore(second_database).append(
            _event(task.id),
            expected_sequence=0,
        )
        assert appended.sequence == 1
    finally:
        await first_database.close()
        await second_database.close()


async def test_non_busy_operational_error_is_not_misclassified(
    database: Database,
    persisted_task: Task,
) -> None:
    await database.connection.execute("DROP TABLE task_events")
    await database.connection.commit()

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        await EventStore(database).append(_event(persisted_task.id), expected_sequence=0)


async def test_task_read_waits_for_rollback_and_does_not_see_uncommitted_data(
    database: Database,
) -> None:
    workspace_id = uuid4()
    await _insert_workspace(database, workspace_id)
    task = _task(workspace_id)
    operation_lock = _ObservableLock()
    database._write_lock = operation_lock
    await operation_lock.acquire()
    await database.connection.execute("BEGIN IMMEDIATE")
    await database.connection.execute(
        """
        INSERT INTO tasks (
            id, workspace_id, requirement, state, step_budget,
            time_budget_seconds, created_at, deadline_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(task.id),
            str(task.workspace_id),
            task.requirement,
            task.state.value,
            task.step_budget,
            task.time_budget_seconds,
            task.created_at.isoformat(),
            task.deadline_at.isoformat() if task.deadline_at else None,
        ),
    )
    read_task = asyncio.create_task(TaskRepository(database).get(task.id))
    contention_task = asyncio.create_task(operation_lock.contended.wait())
    try:
        done, _ = await asyncio.wait(
            {read_task, contention_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        assert contention_task in done
        assert read_task not in done
        await database.connection.rollback()
        operation_lock.release()
        assert await read_task is None
    finally:
        if operation_lock.locked():
            await database.connection.rollback()
            operation_lock.release()
        if not contention_task.done():
            contention_task.cancel()
        await asyncio.gather(read_task, contention_task, return_exceptions=True)


async def test_event_read_waits_for_rollback_and_does_not_see_uncommitted_data(
    database: Database,
    persisted_task: Task,
) -> None:
    event = _event(persisted_task.id)
    operation_lock = _ObservableLock()
    database._write_lock = operation_lock
    await operation_lock.acquire()
    await database.connection.execute("BEGIN IMMEDIATE")
    await database.connection.execute(
        """
        INSERT INTO task_events (
            task_id, sequence, event_type, payload,
            state_before, state_after, occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(event.task_id),
            1,
            event.event_type,
            "{}",
            event.state_before.value if event.state_before else None,
            event.state_after.value if event.state_after else None,
            event.occurred_at.isoformat(),
        ),
    )
    read_task = asyncio.create_task(EventStore(database).list_for_task(persisted_task.id))
    contention_task = asyncio.create_task(operation_lock.contended.wait())
    try:
        done, _ = await asyncio.wait(
            {read_task, contention_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        assert contention_task in done
        assert read_task not in done
        await database.connection.rollback()
        operation_lock.release()
        assert await read_task == []
    finally:
        if operation_lock.locked():
            await database.connection.rollback()
            operation_lock.release()
        if not contention_task.done():
            contention_task.cancel()
        await asyncio.gather(read_task, contention_task, return_exceptions=True)


async def test_close_waits_for_active_connection_operation(tmp_path: Path) -> None:
    database = await _open_database(tmp_path / "close-lock.sqlite3")
    operation_lock = _ObservableLock()
    database._write_lock = operation_lock
    await operation_lock.acquire()
    close_task = asyncio.create_task(database.close())
    contention_task = asyncio.create_task(operation_lock.contended.wait())
    try:
        done, _ = await asyncio.wait(
            {close_task, contention_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        assert contention_task in done
        assert close_task not in done
        operation_lock.release()
        await close_task
    finally:
        if operation_lock.locked():
            operation_lock.release()
        if not contention_task.done():
            contention_task.cancel()
        await asyncio.gather(close_task, contention_task, return_exceptions=True)
        await database.close()
