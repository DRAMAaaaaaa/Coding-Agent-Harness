from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProviderKind(StrEnum):
    DEEPSEEK = "deepseek"
    QWEN = "qwen"


def normalize_model(model: str) -> str:
    normalized = model.strip()
    if not normalized or len(normalized.encode("utf-8")) > 128:
        raise ValueError("provider model must contain 1-128 UTF-8 bytes")
    if any(unicodedata.category(char).startswith("C") for char in normalized):
        raise ValueError("provider model must not contain control characters")
    return normalized


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    kind: ProviderKind
    model: str
    version: int = Field(gt=0)
    created_at: datetime
    updated_at: datetime

    @field_validator("model")
    @classmethod
    def model_is_normalized(cls, value: str) -> str:
        return normalize_model(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_utc_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("provider profile timestamp must be UTC-aware")
        return value.astimezone(UTC)
