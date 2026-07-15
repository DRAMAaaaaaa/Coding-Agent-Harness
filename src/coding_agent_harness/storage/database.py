import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

import aiosqlite


_MIGRATION_DIRECTORY = Path(__file__).with_name("migrations")
_BUSY_TIMEOUT_MILLISECONDS = 5_000


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
        connection = await aiosqlite.connect(Path(path))
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


async def _ensure_wal_mode(connection: aiosqlite.Connection) -> None:
    try:
        row = await (await connection.execute("PRAGMA journal_mode=WAL")).fetchone()
        if row is None or str(row[0]).casefold() != "wal":
            raise RuntimeError("数据库日志模式无效")
    except sqlite3.OperationalError as error:
        if not _is_lock_contention(error):
            raise
        row = await (await connection.execute("PRAGMA journal_mode")).fetchone()
        if row is None or str(row[0]).casefold() != "wal":
            _raise_migration_error(error)


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
