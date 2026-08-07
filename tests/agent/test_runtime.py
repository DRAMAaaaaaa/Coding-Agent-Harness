from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import SecretStr

from coding_agent_harness.providers.credentials import (
    CredentialBroker,
    CredentialPersistence,
    CredentialVaultError,
    SessionOnlyCredentialStore,
)


class _InlineRunner:
    async def run(self, function: object, *args: object) -> object:
        return function(*args)  # type: ignore[operator]


def test_session_only_store_refuses_persistence_and_delete_is_idempotent() -> None:
    store = SessionOnlyCredentialStore()

    with pytest.raises(CredentialVaultError, match="^PERSISTENT_CREDENTIALS_DISABLED$"):
        store.put("provider-profile:test", SecretStr("test-key"))
    store.delete("provider-profile:test")
    assert store.get("provider-profile:test") is None


@pytest.mark.asyncio
async def test_clear_session_removes_all_session_credentials() -> None:
    broker = CredentialBroker(SessionOnlyCredentialStore(), _InlineRunner())
    first, second = uuid4(), uuid4()
    await broker.put(first, SecretStr("first-test-key"), CredentialPersistence.SESSION)
    await broker.put(second, SecretStr("second-test-key"), CredentialPersistence.SESSION)

    broker.clear_session()

    assert await broker.get(first) is None
    assert await broker.get(second) is None
