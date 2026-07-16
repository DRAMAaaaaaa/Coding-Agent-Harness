import asyncio
import os
import sqlite3
import threading
import time
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

import aiosqlite

from coding_agent_harness.governance.path_identity import (
    collapse_windows_extended_path,
    path_key,
)


_MIGRATION_DIRECTORY = Path(__file__).with_name("migrations")
_BUSY_TIMEOUT_MILLISECONDS = 5_000
_WAL_WAIT_TIMEOUT_SECONDS = 5.0
_WAL_OBSERVATION_INTERVAL_SECONDS = 0.01
_wal_clock: Callable[[], float] = time.monotonic
_wal_wait: Callable[[float], Awaitable[None]] = asyncio.sleep
_INITIALIZATION_GATES_LOCK = threading.Lock()
_INITIALIZATION_GATES: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    weakref.WeakValueDictionary[tuple[str, ...], asyncio.Lock],
] = weakref.WeakKeyDictionary()


class MigrationBusyError(RuntimeError):
    """另一个数据库连接正在执行迁移。"""


@dataclass(frozen=True)
class Migration:
    version: int
    sql: str


class Database:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
        self._write_lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def open(cls, path: str | Path) -> Self:
        raw_path = str(path)
        if os.name == "nt":
            raw_path = collapse_windows_extended_path(raw_path)
        database_path = Path(raw_path).resolve(strict=False)
        gate = _database_initialization_gate(
            database_path,
            asyncio.get_running_loop(),
        )
        async with gate:
            connection = await aiosqlite.connect(database_path)
            database = cls(connection)
            try:
                await connection.execute(
                    f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MILLISECONDS}"
                )
                await connection.execute("PRAGMA foreign_keys=ON")
                await _apply_migrations(connection)
                await _ensure_wal_mode(connection)
            except BaseException:
                await connection.close()
                raise
            return database

    @property
    def connection(self) -> aiosqlite.Connection:
        return self._connection

    @property
    def operation_lock(self) -> asyncio.Lock:
        return self._write_lock

    async def close(self) -> None:
        async with self.operation_lock:
            if self._closed:
                return
            self._closed = True
            await self._connection.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()


def _split_migration_statements(sql: str) -> tuple[str, ...]:
    statements: list[str] = []
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statement = pending.strip()
            if statement:
                statements.append(statement)
            pending = ""
    if pending.strip():
        raise RuntimeError("数据库迁移 SQL 不完整")
    return tuple(statements)


def _database_initialization_gate(
    path: str | Path,
    loop: asyncio.AbstractEventLoop,
) -> asyncio.Lock:
    path_key = _database_path_key(path)
    with _INITIALIZATION_GATES_LOCK:
        loop_gates = _INITIALIZATION_GATES.get(loop)
        if loop_gates is None:
            loop_gates = weakref.WeakValueDictionary()
            _INITIALIZATION_GATES[loop] = loop_gates
        gate = loop_gates.get(path_key)
        if gate is None:
            gate = asyncio.Lock()
            loop_gates[path_key] = gate
        return gate


def _database_path_key(path: str | Path) -> tuple[str, ...]:
    raw_path = str(path)
    if os.name == "nt":
        raw_path = collapse_windows_extended_path(raw_path)
    return path_key(Path(raw_path))


async def _ensure_wal_mode(connection: aiosqlite.Connection) -> None:
    try:
        row = await _fetchone_closed(connection, "PRAGMA journal_mode=WAL")
        if row is None or str(row[0]).casefold() != "wal":
            raise RuntimeError("数据库日志模式无效")
    except sqlite3.OperationalError as error:
        if not _is_lock_contention(error):
            raise
        deadline = _wal_clock() + _WAL_WAIT_TIMEOUT_SECONDS
        await _wait_for_wal_owner(connection, deadline, error)


async def _wait_for_wal_owner(
    connection: aiosqlite.Connection,
    deadline: float,
    contention_error: sqlite3.OperationalError,
) -> None:
    while True:
        remaining = deadline - _wal_clock()
        if remaining <= 0:
            _raise_migration_error(contention_error)
        await _wal_wait(min(_WAL_OBSERVATION_INTERVAL_SECONDS, remaining))
        try:
            row = await _fetchone_closed(connection, "PRAGMA journal_mode")
        except sqlite3.OperationalError as error:
            if not _is_lock_contention(error):
                raise
            continue
        if row is not None and str(row[0]).casefold() == "wal":
            return


async def _fetchone_closed(
    connection: aiosqlite.Connection,
    sql: str,
) -> sqlite3.Row | tuple[object, ...] | None:
    cursor = await connection.execute(sql)
    try:
        row = await cursor.fetchone()
    except BaseException:
        try:
            await cursor.close()
        except BaseException:
            pass
        raise
    else:
        await cursor.close()
        return row


async def _read_version_locked(connection: aiosqlite.Connection) -> int:
    try:
        await connection.execute("BEGIN IMMEDIATE")
        row = await (await connection.execute("PRAGMA user_version")).fetchone()
        version = int(row[0]) if row is not None else 0
        await connection.commit()
        return version
    except BaseException as error:
        await _rollback_quietly(connection)
        _raise_migration_error(error)
        raise AssertionError("unreachable")


async def _apply_one_migration_locked(
    connection: aiosqlite.Connection,
    migration: Migration,
) -> bool:
    try:
        await connection.execute("BEGIN IMMEDIATE")
        row = await (await connection.execute("PRAGMA user_version")).fetchone()
        current_version = int(row[0]) if row is not None else 0
        if current_version >= migration.version:
            await connection.commit()
            return False
        if current_version != migration.version - 1:
            raise RuntimeError("数据库迁移版本不连续")
        for statement in _split_migration_statements(migration.sql):
            await connection.execute(statement)
        await connection.execute(f"PRAGMA user_version = {migration.version}")
        await connection.commit()
        return True
    except BaseException as error:
        await _rollback_quietly(connection)
        _raise_migration_error(error)
        raise AssertionError("unreachable")


async def _apply_migrations(connection: aiosqlite.Connection) -> None:
    migrations = tuple(
        Migration(
            version=int(path.name[:3]),
            sql=path.read_text(encoding="utf-8"),
        )
        for path in sorted(_MIGRATION_DIRECTORY.glob("[0-9][0-9][0-9]_*.sql"))
    )
    if not migrations:
        raise RuntimeError("未找到数据库迁移")
    if tuple(migration.version for migration in migrations) != tuple(
        range(1, migrations[-1].version + 1)
    ):
        raise RuntimeError("数据库迁移版本不连续")

    current_version = await _read_version_locked(connection)
    if current_version > migrations[-1].version:
        raise RuntimeError("数据库版本高于代码支持版本")
    for migration in migrations:
        if migration.version > current_version:
            await _apply_one_migration_locked(connection, migration)


async def _rollback_quietly(connection: aiosqlite.Connection) -> None:
    try:
        await connection.rollback()
    except sqlite3.Error:
        pass


def _raise_migration_error(error: BaseException) -> None:
    if isinstance(error, sqlite3.OperationalError) and _is_lock_contention(error):
        raise MigrationBusyError("数据库迁移正忙") from None
    raise error


def _is_lock_contention(error: sqlite3.OperationalError) -> bool:
    error_code = getattr(error, "sqlite_errorcode", None)
    if isinstance(error_code, int):
        return error_code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
    return "locked" in str(error).casefold() or "busy" in str(error).casefold()
