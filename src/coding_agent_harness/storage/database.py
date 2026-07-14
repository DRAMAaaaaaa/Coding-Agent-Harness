import asyncio
from pathlib import Path
from types import TracebackType
from typing import Self

import aiosqlite


_MIGRATION_FILE = Path(__file__).with_name("migrations") / "001_initial.sql"
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
            migration = _MIGRATION_FILE.read_text(encoding="utf-8")
            await connection.executescript(migration)
            await connection.commit()
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
