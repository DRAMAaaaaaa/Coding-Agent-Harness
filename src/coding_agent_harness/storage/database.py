import asyncio
from pathlib import Path
from types import TracebackType
from typing import Self

import aiosqlite


_MIGRATION_DIRECTORY = Path(__file__).with_name("migrations")
_BUSY_TIMEOUT_MILLISECONDS = 5_000


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
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.execute(
                f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MILLISECONDS}"
            )
            await _apply_migrations(connection)
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


async def _apply_migrations(connection: aiosqlite.Connection) -> None:
    migrations = sorted(
        (
            (int(path.name[:3]), path)
            for path in _MIGRATION_DIRECTORY.glob("[0-9][0-9][0-9]_*.sql")
        ),
        key=lambda item: item[0],
    )
    if not migrations:
        raise RuntimeError("未找到数据库迁移")

    row = await (await connection.execute("PRAGMA user_version")).fetchone()
    current_version = int(row[0]) if row is not None else 0
    supported_version = migrations[-1][0]
    if current_version > supported_version:
        raise RuntimeError("数据库版本高于代码支持版本")

    for version, path in migrations:
        if version <= current_version:
            continue
        await connection.executescript(path.read_text(encoding="utf-8"))
        row = await (await connection.execute("PRAGMA user_version")).fetchone()
        applied_version = int(row[0]) if row is not None else 0
        if applied_version != version:
            raise RuntimeError("数据库迁移版本无效")
        current_version = applied_version
