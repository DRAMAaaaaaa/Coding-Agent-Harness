from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Callable
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

import coding_agent_harness.providers.registry as registry_module
from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.models import Task
from coding_agent_harness.providers.credentials import CredentialVaultError
from coding_agent_harness.providers.models import ProviderKind, ProviderProfile
from coding_agent_harness.providers.base import LLMRequest
from coding_agent_harness.providers.registry import (
    PROVIDER_ENDPOINTS,
    ProviderConfigurationError,
    ProviderRegistry,
)


PROFILE_ID = UUID("00000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 7, tzinfo=UTC)


class ProfileRepository:
    def __init__(self, profile: ProviderProfile | None) -> None:
        self.profile = profile

    async def get(self, profile_id: UUID) -> ProviderProfile | None:
        return self.profile if self.profile is not None and self.profile.id == profile_id else None


class Broker:
    def __init__(self, secret: SecretStr | None = SecretStr("test-api-key"), *, locked: bool = False) -> None:
        self.secret = secret
        self.locked = locked

    async def get(self, profile_id: UUID) -> SecretStr | None:
        if self.locked:
            raise CredentialVaultError("CREDENTIAL_VAULT_LOCKED")
        return self.secret


def profile(kind: ProviderKind = ProviderKind.DEEPSEEK, version: int = 1) -> ProviderProfile:
    return ProviderProfile(
        id=PROFILE_ID, kind=kind, model="tested-model", version=version, created_at=NOW, updated_at=NOW
    )


def task(*, profile_id: UUID | None = PROFILE_ID, version: int | None = 1) -> Task:
    authorized_at = NOW if profile_id is not None else None
    return Task(
        id=uuid4(), workspace_id=uuid4(), requirement="test", state=TaskState.CREATED,
        step_budget=1, time_budget_seconds=1.0, created_at=NOW, deadline_at=None,
        provider_profile_id=profile_id, provider_profile_version=version if profile_id else None,
        llm_api_authorized_at=authorized_at,
    )


def client_factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.AsyncClient]:
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


_DEFAULT = object()


def registry(
    stored_profile: ProviderProfile | None | object = _DEFAULT,
    broker: Broker | None = None,
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> ProviderRegistry:
    return ProviderRegistry(
        ProfileRepository(profile() if stored_profile is _DEFAULT else stored_profile),  # type: ignore[arg-type]
        broker or Broker(),
        client_factory=client_factory(handler or (lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]}))),
    )


def test_provider_endpoints_are_exact_and_immutable() -> None:
    assert dict(PROVIDER_ENDPOINTS) == {
        ProviderKind.DEEPSEEK: "https://api.deepseek.com/v1",
        ProviderKind.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }
    with pytest.raises(TypeError):
        PROVIDER_ENDPOINTS[ProviderKind.DEEPSEEK] = "https://attacker.invalid"  # type: ignore[index]


async def test_registry_rejects_task_without_exact_profile_authorization() -> None:
    with pytest.raises(ProviderConfigurationError, match="LLM_AUTHORIZATION_REQUIRED") as captured:
        await registry().build_for_task(task(profile_id=None, version=None))
    assert captured.value.code == "LLM_AUTHORIZATION_REQUIRED"


@pytest.mark.parametrize(
    ("stored_profile", "bound_task", "broker", "code"),
    [
        (None, task(), Broker(), "PROVIDER_PROFILE_NOT_FOUND"),
        (profile(version=2), task(version=1), Broker(), "PROVIDER_AUTHORIZATION_STALE"),
        (profile(), task(), Broker(secret=None), "PROVIDER_CREDENTIAL_NOT_CONFIGURED"),
        (profile(), task(), Broker(locked=True), "CREDENTIAL_VAULT_LOCKED"),
    ],
)
async def test_registry_fails_closed_for_invalid_provider_configuration(
    stored_profile: ProviderProfile | None, bound_task: Task, broker: Broker, code: str
) -> None:
    with pytest.raises(ProviderConfigurationError, match=f"^{code}$") as captured:
        await registry(stored_profile, broker).build_for_task(bound_task)
    assert captured.value.code == code


async def test_registry_builds_only_with_fixed_endpoint_and_profile_model() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}]})

    provider = await registry(profile(ProviderKind.QWEN), handler=handler).build_for_task(task())
    assert (await provider.complete(LLMRequest(messages=[]))).content == "done"
    assert str(requests[0].url) == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert b'"model":"tested-model"' in requests[0].content


async def test_registry_default_client_factory_disables_environment_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    original_async_client = httpx.AsyncClient

    def recording_async_client(**kwargs: object) -> httpx.AsyncClient:
        calls.append(kwargs)
        return original_async_client(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

    monkeypatch.setattr(registry_module.httpx, "AsyncClient", recording_async_client)

    await ProviderRegistry(ProfileRepository(profile()), Broker()).build_for_task(task())

    assert calls == [{"trust_env": False, "follow_redirects": False}]


async def test_probe_uses_a_fixed_minimal_message() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    response = await registry(handler=handler).probe(PROFILE_ID)
    assert response.content == "OK"
    assert len(requests) == 1
    assert json.loads(requests[0].content) == {
        "model": "tested-model",
        "messages": [{"role": "user", "content": "只回复 OK"}],
        "temperature": 0,
    }
