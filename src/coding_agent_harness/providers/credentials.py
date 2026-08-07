"""凭据生命周期的确定性边界。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, SecretStr


class CredentialPersistence(StrEnum):
    SESSION = "session"
    PERSISTENT = "persistent"


class CredentialStatus(BaseModel):
    configured: bool
    persistence: CredentialPersistence | None
    unlocked: bool


class CredentialVaultError(RuntimeError):
    """只携带稳定原因码，避免泄露外部错误或秘密。"""


class SessionOnlyCredentialStore:
    """拒绝一切持久化写入的后端，实际凭据仅由 Broker 保存在内存中。"""

    def put(self, reference: str, secret: SecretStr) -> None:
        del reference, secret
        raise CredentialVaultError("PERSISTENT_CREDENTIALS_DISABLED")

    def get(self, reference: str) -> None:
        del reference
        return None

    def delete(self, reference: str) -> None:
        del reference


class PersistentCredentialStore(Protocol):
    def put(self, reference: str, secret: SecretStr) -> None: ...

    def get(self, reference: str) -> SecretStr | None: ...

    def delete(self, reference: str) -> None: ...


class UnlockableCredentialStore(PersistentCredentialStore, Protocol):
    @property
    def unlocked(self) -> bool: ...

    def unlock(self, master_password: SecretStr) -> None: ...

    def lock(self) -> None: ...


T = TypeVar("T")


class BlockingCallRunner(Protocol):
    def run(self, function: Callable[..., T], *args: object) -> Awaitable[T]: ...


class CredentialBroker:
    """以会话优先规则隔离同步凭据后端。"""

    def __init__(self, persistent_store: PersistentCredentialStore, runner: BlockingCallRunner) -> None:
        self._persistent_store = persistent_store
        self._runner = runner
        self._session: dict[str, SecretStr] = {}

    async def put(
        self, profile_id: UUID, secret: SecretStr, persistence: CredentialPersistence
    ) -> None:
        reference = self._reference(profile_id)
        if persistence is CredentialPersistence.SESSION:
            self._session[reference] = secret
            return
        await self._run(self._persistent_store.put, reference, secret)

    async def get(self, profile_id: UUID) -> SecretStr | None:
        reference = self._reference(profile_id)
        if reference in self._session:
            return self._session[reference]
        return await self._run(self._persistent_store.get, reference)

    async def delete(self, profile_id: UUID) -> None:
        reference = self._reference(profile_id)
        self._session.pop(reference, None)
        await self._run(self._persistent_store.delete, reference)

    async def status(self, profile_id: UUID) -> CredentialStatus:
        reference = self._reference(profile_id)
        if reference in self._session:
            return CredentialStatus(
                configured=True, persistence=CredentialPersistence.SESSION, unlocked=True
            )
        unlocked = getattr(self._persistent_store, "unlocked", True)
        if not unlocked:
            return CredentialStatus(configured=False, persistence=None, unlocked=False)
        secret = await self._run(self._persistent_store.get, reference)
        return CredentialStatus(
            configured=secret is not None,
            persistence=CredentialPersistence.PERSISTENT if secret is not None else None,
            unlocked=True,
        )

    async def unlock(self, master_password: SecretStr) -> None:
        store = self._unlockable_store()
        await self._run(store.unlock, master_password)

    async def lock(self) -> None:
        store = self._unlockable_store()
        await self._run(store.lock)
        self._session.clear()

    def clear_session(self) -> None:
        self._session.clear()

    @staticmethod
    def _reference(profile_id: UUID) -> str:
        return f"provider-profile:{profile_id}"

    def _unlockable_store(self) -> UnlockableCredentialStore:
        store = self._persistent_store
        if not all(hasattr(store, attribute) for attribute in ("unlocked", "unlock", "lock")):
            raise CredentialVaultError("CREDENTIAL_STORE_NOT_UNLOCKABLE")
        return store  # type: ignore[return-value]

    async def _run(self, function: Callable[..., T], *args: object) -> T:
        task = asyncio.ensure_future(self._runner.run(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # 取消不能丢失已开始的阻塞副作用或其异常结果。
            try:
                await asyncio.shield(task)
            except BaseException:
                pass
            raise
