from typing import Protocol

from pydantic import BaseModel, ConfigDict, JsonValue


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    messages: list[dict[str, JsonValue]]


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    content: str


class ProviderError(RuntimeError):
    """仅公开稳定诊断，调用方不得附加或保留外部请求/响应对象。"""

    def __init__(self, message: str, *, kind: str, retryable: bool) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class LLMProvider(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
