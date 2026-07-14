from typing import Any

import httpx

from coding_agent_harness.providers.base import LLMRequest, LLMResponse, ProviderError


_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429})


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_HTTP_STATUSES or 500 <= status_code < 600


def _extract_content(response: httpx.Response) -> str | None:
    try:
        payload: Any = response.json()
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
        response: httpx.Response | None
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "messages": request.messages, "temperature": 0},
                follow_redirects=False,
            )
        except (httpx.NetworkError, httpx.TimeoutException):
            response = None

        if response is None:
            raise ProviderError(
                "Provider request failed due to a temporary network error.",
                kind="network",
                retryable=True,
            )

        if not response.is_success:
            raise ProviderError(
                f"Provider returned HTTP status {response.status_code}.",
                kind="http_status",
                retryable=_is_retryable_http_status(response.status_code),
            )

        content = _extract_content(response)
        if content is None:
            raise ProviderError(
                "Provider response did not match the expected schema.",
                kind="response_schema",
                retryable=False,
            )
        return LLMResponse(content=content)
