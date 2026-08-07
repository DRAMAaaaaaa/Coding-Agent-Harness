"""OS Keyring 持久化后端。"""

import keyring
from pydantic import SecretStr

from coding_agent_harness.providers.credentials import CredentialVaultError

_SERVICE_NAME = "coding-agent-harness"


class KeyringCredentialStore:
    """使用固定 service，所有后端错误均收敛为稳定原因码。"""

    def put(self, reference: str, secret: SecretStr) -> None:
        try:
            keyring.set_password(_SERVICE_NAME, reference, secret.get_secret_value())
        except Exception:
            raise CredentialVaultError("CREDENTIAL_STORE_UNAVAILABLE") from None

    def get(self, reference: str) -> SecretStr | None:
        try:
            value = keyring.get_password(_SERVICE_NAME, reference)
        except Exception:
            raise CredentialVaultError("CREDENTIAL_STORE_UNAVAILABLE") from None
        return SecretStr(value) if value is not None else None

    def delete(self, reference: str) -> None:
        if self.get(reference) is None:
            return
        try:
            keyring.delete_password(_SERVICE_NAME, reference)
        except Exception:
            raise CredentialVaultError("CREDENTIAL_STORE_UNAVAILABLE") from None
