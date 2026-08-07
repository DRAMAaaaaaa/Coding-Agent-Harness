"""单进程 Provider 绑定协调；多进程部署不在首版支持范围内。"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from uuid import UUID

class ProviderBindingCoordinator:
    def __init__(self) -> None:
        self._locks: dict[UUID, asyncio.Lock] = {}

    @asynccontextmanager
    async def hold(self, profile_id: UUID) -> AsyncIterator[None]:
        lock = self._locks.setdefault(profile_id, asyncio.Lock())
        async with lock:
            yield
