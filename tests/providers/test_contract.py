import inspect
import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from coding_agent_harness.providers.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
)
from coding_agent_harness.providers.mock import ScriptedMockProvider, ScriptExhaustedError
from coding_agent_harness.providers.openai_compatible import OpenAICompatibleProvider


def test_provider_contract_models_are_strict_and_frozen() -> None:
    request = LLMRequest(messages=[{"role": "user", "content": "你好"}])

    with pytest.raises(ValidationError):
        request.messages = []

    with pytest.raises(ValidationError):
        LLMResponse(content="完成", unexpected=True)

    with pytest.raises(ValidationError):
        LLMRequest(messages=[{"role": "user", "content": object()}])


def test_llm_provider_is_an_async_protocol() -> None:
    assert getattr(LLMProvider, "_is_protocol", False)
    assert inspect.iscoroutinefunction(ScriptedMockProvider.complete)


async def test_scripted_mock_is_deterministic_and_records_requests() -> None:
    provider = ScriptedMockProvider(
        ['{"kind":"complete","summary":"第一步"}', '{"kind":"complete","summary":"完成"}']
    )
    first_request = LLMRequest(messages=[])
    second_request = LLMRequest(messages=[{"role": "user", "content": "继续"}])

    assert (await provider.complete(first_request)).content.endswith('"第一步"}')
    assert (await provider.complete(second_request)).content.endswith('"完成"}')
    assert provider.requests == [first_request, second_request]


async def test_scripted_mock_fails_deterministically_when_exhausted() -> None:
    provider = ScriptedMockProvider([])

    with pytest.raises(ScriptExhaustedError) as captured:
        await provider.complete(LLMRequest(messages=[]))

    assert captured.value.kind == "script_exhausted"
    assert captured.value.retryable is False


@pytest.mark.parametrize(
    ("base_url", "model"),
    [
        ("https://api.deepseek.example/v1/", "deepseek-chat"),
        ("https://dashscope.example/compatible-mode/v1", "qwen-plus"),
    ],
)
async def test_openai_compatible_provider_uses_injected_configuration(
    base_url: str, model: str
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "完成"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(client, base_url, model, "placeholder-api-key")
        response = await provider.complete(
            LLMRequest(messages=[{"role": "user", "content": "执行"}])
        )

    assert response == LLMResponse(content="完成")
    assert len(requests) == 1
    assert str(requests[0].url) == f"{base_url.rstrip('/')}/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer placeholder-api-key"
    assert json.loads(requests[0].content) == {
        "model": model,
        "messages": [{"role": "user", "content": "执行"}],
        "temperature": 0,
    }


@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(400, False), (408, True), (429, True), (503, True)],
)
async def test_http_errors_are_safely_classified(status_code: int, retryable: bool) -> None:
    secret = "placeholder-secret-that-must-not-leak"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"message": f"Authorization: Bearer {secret}"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(client, "https://provider.example/v1", "model", secret)
        with pytest.raises(ProviderError) as captured:
            await provider.complete(LLMRequest(messages=[]))

    error = captured.value
    assert error.kind == "http_status"
    assert error.retryable is retryable
    assert secret not in str(error)
    assert secret not in repr(error)
    assert "Authorization" not in str(error)
    assert secret not in repr(vars(error))


@pytest.mark.parametrize("exception_type", [httpx.ConnectError, httpx.ConnectTimeout])
async def test_temporary_network_errors_are_retryable_and_sanitized(
    exception_type: type[httpx.RequestError],
) -> None:
    secret = "placeholder-network-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        raise exception_type(f"Authorization: Bearer {secret}", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(client, "https://provider.example/v1", "model", secret)
        with pytest.raises(ProviderError) as captured:
            await provider.complete(LLMRequest(messages=[]))

    assert captured.value.kind == "network"
    assert captured.value.retryable is True
    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)
    assert secret not in repr(vars(captured.value))


@pytest.mark.parametrize(
    "response_kwargs",
    [
        {"content": b"not-json", "headers": {"content-type": "application/json"}},
        {"json": {"choices": []}},
        {"json": {"choices": [{"message": {"content": 42}}]}},
    ],
)
async def test_response_schema_errors_are_non_retryable_and_sanitized(
    response_kwargs: dict[str, Any],
) -> None:
    secret = "placeholder-schema-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, **response_kwargs)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(client, "https://provider.example/v1", "model", secret)
        with pytest.raises(ProviderError) as captured:
            await provider.complete(LLMRequest(messages=[]))

    assert captured.value.kind == "response_schema"
    assert captured.value.retryable is False
    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)
    assert secret not in repr(vars(captured.value))
