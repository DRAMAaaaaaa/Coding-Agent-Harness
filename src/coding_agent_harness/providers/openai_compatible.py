import json
from typing import Any

import httpx

from coding_agent_harness.providers.base import LLMRequest, LLMResponse, ProviderError


_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429})


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_HTTP_STATUSES or 500 <= status_code < 600


_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _extract_content(payload_bytes: bytes) -> str | None:
    try:
        payload: Any = json.loads(payload_bytes)
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return content if isinstance(content, str) else None


class OpenAICompatibleProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        model: str,
        api_key: str,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "messages": request.messages, "temperature": 0},
                follow_redirects=False,
            ) as response:
                if not response.is_success:
                    raise ProviderError(
                        f"Provider returned HTTP status {response.status_code}.",
                        kind="http_status",
                        retryable=_is_retryable_http_status(response.status_code),
                    )
                chunks: list[bytes] = []
                received = 0
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > _MAX_RESPONSE_BYTES:
                        raise ProviderError(
                            "Provider response exceeded the 2 MiB limit.",
                            kind="response_too_large",
                            retryable=False,
                        )
                    chunks.append(chunk)
        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderError(
                "Provider request timed out.",
                kind="timeout",
                retryable=True,
            ) from None
        except httpx.RequestError:
            raise ProviderError(
                "Provider request failed due to a temporary network error.", kind="network", retryable=True
            ) from None

        content = _extract_content(b"".join(chunks))
        if content is None:
            raise ProviderError(
                "Provider response did not match the expected schema.",
                kind="response_schema",
                retryable=False,
            )
        return LLMResponse(content=content)
