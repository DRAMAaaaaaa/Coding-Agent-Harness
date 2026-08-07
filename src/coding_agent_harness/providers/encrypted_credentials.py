"""Argon2id 与 AES-GCM 保护的本地凭据保险库。"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
from typing import Any

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

from coding_agent_harness.providers.credentials import CredentialVaultError

_AAD = b"coding-agent-harness:credentials:v1"
_PARAMETERS = {"time_cost": 3, "memory_cost": 65536, "parallelism": 1, "hash_len": 32}


class EncryptedCredentialStore:
    """主密码只保留在进程内；无密码时的容器后端保持锁定。"""

    def __init__(self, path: Path, master_password: SecretStr | None = None) -> None:
        self._path = path
        self._master_password = master_password

    @property
    def unlocked(self) -> bool:
        return self._master_password is not None

    def unlock(self, master_password: SecretStr) -> None:
        self._master_password = master_password

    def lock(self) -> None:
        self._master_password = None

    def put(self, reference: str, secret: SecretStr) -> None:
        values = self._read_values() if self._path.exists() else {}
        values[reference] = secret.get_secret_value()
        self._write_values(values)

    def get(self, reference: str) -> SecretStr | None:
        value = self._read_values().get(reference)
        return SecretStr(value) if value is not None else None

    def delete(self, reference: str) -> None:
        if not self._path.exists():
            return
        values = self._read_values()
        if reference in values:
            del values[reference]
            self._write_values(values)

    def _password(self) -> bytes:
        if self._master_password is None:
            raise CredentialVaultError("CREDENTIAL_VAULT_LOCKED")
        return self._master_password.get_secret_value().encode("utf-8")

    def _read_values(self) -> dict[str, str]:
        try:
            envelope = json.loads(self._path.read_text(encoding="utf-8"))
            salt, nonce, ciphertext = self._validate_envelope(envelope)
            key = self._derive_key(salt, envelope["kdf"])
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, _AAD)
            values = json.loads(plaintext.decode("utf-8"))
            if not isinstance(values, dict) or any(
                not isinstance(reference, str) or not isinstance(secret, str)
                for reference, secret in values.items()
            ):
                raise ValueError
            return values
        except CredentialVaultError:
            raise
        except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError, InvalidTag):
            raise CredentialVaultError("CREDENTIAL_VAULT_INVALID") from None

    def _write_values(self, values: dict[str, str]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            salt = secrets.token_bytes(16)
            nonce = secrets.token_bytes(12)
            key = self._derive_key(salt, _PARAMETERS)
            plaintext = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ciphertext = AESGCM(key).encrypt(nonce, plaintext, _AAD)
            envelope = {
                "version": 1,
                "kdf": _PARAMETERS,
                "salt": base64.b64encode(salt).decode("ascii"),
                "nonce": base64.b64encode(nonce).decode("ascii"),
                "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            }
            payload = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
            temporary = self._path.with_name(f".{self._path.name}.{secrets.token_hex(16)}.tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self._path)
            finally:
                if temporary.exists():
                    temporary.unlink()
        except CredentialVaultError:
            raise
        except (OSError, ValueError, TypeError):
            raise CredentialVaultError("CREDENTIAL_VAULT_WRITE_FAILED") from None

    def _derive_key(self, salt: bytes, parameters: dict[str, int]) -> bytes:
        return hash_secret_raw(self._password(), salt, type=Type.ID, **parameters)

    @staticmethod
    def _validate_envelope(envelope: Any) -> tuple[bytes, bytes, bytes]:
        if not isinstance(envelope, dict) or set(envelope) != {
            "version", "kdf", "salt", "nonce", "ciphertext"
        } or envelope["version"] != 1:
            raise ValueError
        parameters = envelope["kdf"]
        if not isinstance(parameters, dict) or set(parameters) != set(_PARAMETERS):
            raise ValueError
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0 or value > _PARAMETERS[name]
            for name, value in parameters.items()
        ):
            raise ValueError
        salt = base64.b64decode(envelope["salt"], validate=True)
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
        if len(salt) != 16 or len(nonce) != 12 or not ciphertext:
            raise ValueError
        return salt, nonce, ciphertext
