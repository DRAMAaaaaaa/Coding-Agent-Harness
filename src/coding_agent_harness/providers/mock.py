from collections import deque
from collections.abc import Iterable

from coding_agent_harness.providers.base import LLMRequest, LLMResponse, ProviderError


class ScriptExhaustedError(ProviderError):
    def __init__(self) -> None:
        super().__init__(
            "Scripted mock response sequence is exhausted.",
            kind="script_exhausted",
            retryable=False,
        )


class ScriptedMockProvider:
    def __init__(self, script: Iterable[str]) -> None:
        self._script = deque(script)
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._script:
            raise ScriptExhaustedError
        return LLMResponse(content=self._script.popleft())
