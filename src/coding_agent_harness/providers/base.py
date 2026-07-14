from typing import Protocol

from pydantic import BaseModel, ConfigDict, JsonValue


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    messages: list[dict[str, JsonValue]]


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    content: str


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, kind: str, retryable: bool) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class LLMProvider(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
