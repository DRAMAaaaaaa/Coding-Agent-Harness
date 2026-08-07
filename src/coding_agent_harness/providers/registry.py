from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from uuid import UUID

import httpx
from pydantic import SecretStr

from coding_agent_harness.domain.models import Task
from coding_agent_harness.providers.base import LLMProvider, LLMRequest, LLMResponse
from coding_agent_harness.providers.credentials import CredentialBroker, CredentialVaultError
from coding_agent_harness.providers.models import ProviderKind, ProviderProfile
from coding_agent_harness.providers.openai_compatible import OpenAICompatibleProvider
from coding_agent_harness.storage.provider_profiles import ProviderProfileRepository


PROVIDER_ENDPOINTS: Mapping[ProviderKind, str] = MappingProxyType(
    {
        ProviderKind.DEEPSEEK: "https://api.deepseek.com/v1",
        ProviderKind.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }
)


def _default_client_factory() -> httpx.AsyncClient:
    return httpx.AsyncClient(trust_env=False, follow_redirects=False)


class ProviderConfigurationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ProviderRegistry:
    def __init__(
        self,
        profiles: ProviderProfileRepository,
        credentials: CredentialBroker,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._profiles = profiles
        self._credentials = credentials
        self._client_factory = client_factory or _default_client_factory

    async def build_for_task(self, task: Task) -> LLMProvider:
        if (
            task.provider_profile_id is None
            or task.provider_profile_version is None
            or task.llm_api_authorized_at is None
        ):
            raise ProviderConfigurationError("LLM_AUTHORIZATION_REQUIRED")
        profile = await self._profile(task.provider_profile_id)
        if profile.version != task.provider_profile_version:
            raise ProviderConfigurationError("PROVIDER_AUTHORIZATION_STALE")
        return await self._provider(profile)

    async def probe(self, profile_id: UUID) -> LLMResponse:
        profile = await self._profile(profile_id)
        provider = await self._provider(profile)
        return await provider.complete(LLMRequest(messages=[{"role": "user", "content": "只回复 OK"}]))

    async def _profile(self, profile_id: UUID) -> ProviderProfile:
        profile = await self._profiles.get(profile_id)
        if profile is None:
            raise ProviderConfigurationError("PROVIDER_PROFILE_NOT_FOUND")
        return profile

    async def _provider(self, profile: ProviderProfile) -> OpenAICompatibleProvider:
        secret = await self._credential(profile.id)
        return OpenAICompatibleProvider(
            self._client_factory(), PROVIDER_ENDPOINTS[profile.kind], profile.model, secret.get_secret_value()
        )

    async def _credential(self, profile_id: UUID) -> SecretStr:
        try:
            secret = await self._credentials.get(profile_id)
        except CredentialVaultError as error:
            code = str(error)
            if code == "CREDENTIAL_VAULT_LOCKED":
                raise ProviderConfigurationError(code) from None
            raise ProviderConfigurationError("CREDENTIAL_VAULT_UNAVAILABLE") from None
        if secret is None:
            raise ProviderConfigurationError("PROVIDER_CREDENTIAL_NOT_CONFIGURED")
        return secret
