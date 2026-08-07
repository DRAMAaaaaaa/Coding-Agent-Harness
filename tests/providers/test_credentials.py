"""凭据保险库的安全契约。"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from coding_agent_harness.providers.credentials import (
    CredentialBroker,
    CredentialPersistence,
    CredentialVaultError,
)
from coding_agent_harness.providers.encrypted_credentials import EncryptedCredentialStore
from coding_agent_harness.providers.keyring_credentials import KeyringCredentialStore


class InlineRunner:
    async def run(self, function: object, *args: object) -> object:
        return function(*args)  # type: ignore[operator]


class RecordingStore:
    def __init__(self) -> None:
        self.values: dict[str, SecretStr] = {}
        self.calls: list[str] = []

    def put(self, reference: str, secret: SecretStr) -> None:
        self.calls.append("put")
        self.values[reference] = secret

    def get(self, reference: str) -> SecretStr | None:
        self.calls.append("get")
        return self.values.get(reference)

    def delete(self, reference: str) -> None:
        self.calls.append("delete")
        self.values.pop(reference, None)


def test_secret_repr_does_not_leak_value() -> None:
    secret = SecretStr("fake-provider-secret")
    assert "fake-provider-secret" not in repr(secret)


@pytest.mark.asyncio
async def test_session_secret_never_calls_persistent_store() -> None:
    persistent = RecordingStore()
    broker = CredentialBroker(persistent, InlineRunner())
    profile_id = uuid4()

    await broker.put(profile_id, SecretStr("fake-session-secret"), CredentialPersistence.SESSION)

    assert persistent.calls == []
    assert (await broker.get(profile_id)).get_secret_value() == "fake-session-secret"  # type: ignore[union-attr]


def test_keyring_uses_fixed_service_and_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[tuple[str, str, str]] = []
    store = KeyringCredentialStore()
    monkeypatch.setattr(
        "coding_agent_harness.providers.keyring_credentials.keyring.set_password",
        lambda service, name, value: recorded.append((service, name, value)),
    )

    store.put("provider-profile:1", SecretStr("fake-keyring-secret"))

    assert recorded == [("coding-agent-harness", "provider-profile:1", "fake-keyring-secret")]


def test_keyring_failure_is_stable_and_does_not_leak_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    store = KeyringCredentialStore()
    monkeypatch.setattr(
        "coding_agent_harness.providers.keyring_credentials.keyring.get_password",
        lambda *_: (_ for _ in ()).throw(RuntimeError("fake-keyring-secret")),
    )

    with pytest.raises(CredentialVaultError, match="^CREDENTIAL_STORE_UNAVAILABLE$") as captured:
        store.get("provider-profile:1")

    assert "fake-keyring-secret" not in repr(captured.value)


def test_encrypted_store_writes_no_plaintext(tmp_path: Path) -> None:
    vault_path = tmp_path / "credentials.v1"
    store = EncryptedCredentialStore(vault_path, SecretStr("master-pass"))
    store.put("provider-profile:1", SecretStr("fake-provider-secret"))

    assert "fake-provider-secret" not in vault_path.read_text(encoding="utf-8")


def test_encrypted_store_preserves_an_empty_secret_as_a_secret(tmp_path: Path) -> None:
    store = EncryptedCredentialStore(tmp_path / "credentials.v1", SecretStr("master-pass"))
    store.put("provider-profile:1", SecretStr(""))

    result = store.get("provider-profile:1")

    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == ""  # type: ignore[union-attr]


@pytest.mark.parametrize("damage", ["password", "ciphertext"])
def test_encrypted_store_rejects_invalid_data_without_secret_leak(tmp_path: Path, damage: str) -> None:
    vault_path = tmp_path / "credentials.v1"
    store = EncryptedCredentialStore(vault_path, SecretStr("master-pass"))
    store.put("provider-profile:1", SecretStr("fake-provider-secret"))
    if damage == "password":
        store = EncryptedCredentialStore(vault_path, SecretStr("wrong-master-pass"))
    else:
        envelope = json.loads(vault_path.read_text(encoding="utf-8"))
        ciphertext = base64.b64decode(envelope["ciphertext"])
        envelope["ciphertext"] = base64.b64encode(ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])).decode()
        vault_path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(CredentialVaultError, match="^CREDENTIAL_VAULT_INVALID$") as captured:
        store.get("provider-profile:1")

    assert "fake-provider-secret" not in repr(captured.value)


def test_failed_atomic_replace_preserves_existing_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_path = tmp_path / "credentials.v1"
    store = EncryptedCredentialStore(vault_path, SecretStr("master-pass"))
    store.put("provider-profile:1", SecretStr("old-fake-secret"))
    old_contents = vault_path.read_bytes()
    monkeypatch.setattr(
        "coding_agent_harness.providers.encrypted_credentials.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(CredentialVaultError, match="^CREDENTIAL_VAULT_WRITE_FAILED$"):
        store.put("provider-profile:2", SecretStr("new-fake-secret"))

    assert vault_path.read_bytes() == old_contents


@pytest.mark.asyncio
async def test_broker_delete_clears_session_and_persistent_locations() -> None:
    persistent = RecordingStore()
    broker = CredentialBroker(persistent, InlineRunner())
    profile_id = uuid4()
    await broker.put(profile_id, SecretStr("fake-persistent-secret"), CredentialPersistence.PERSISTENT)
    await broker.put(profile_id, SecretStr("fake-session-secret"), CredentialPersistence.SESSION)

    await broker.delete(profile_id)

    assert persistent.values == {}
    assert persistent.calls[-1] == "delete"
    assert await broker.get(profile_id) is None


@pytest.mark.asyncio
async def test_broker_cancellation_waits_for_blocking_result() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingRunner:
        async def run(self, function: object, *args: object) -> object:
            started.set()
            await release.wait()
            return function(*args)  # type: ignore[operator]

    broker = CredentialBroker(RecordingStore(), BlockingRunner())
    task = asyncio.create_task(broker.put(uuid4(), SecretStr("fake-secret"), CredentialPersistence.PERSISTENT))
    await started.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
