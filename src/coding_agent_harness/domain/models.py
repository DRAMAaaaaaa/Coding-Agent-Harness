from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from coding_agent_harness.domain.actions import TaskState


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    workspace_id: UUID
    requirement: str
    state: TaskState
    step_budget: int = Field(ge=0)
    time_budget_seconds: float = Field(gt=0)
    created_at: datetime
    deadline_at: datetime | None
    provider_profile_id: UUID | None = None
    provider_profile_version: int | None = None
    llm_api_authorized_at: datetime | None = None

    @field_validator("llm_api_authorized_at")
    @classmethod
    def authorization_is_utc_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("llm authorization timestamp must be UTC-aware")
        return value

    @model_validator(mode="after")
    def provider_binding_is_complete(self) -> "Task":
        values = (self.provider_profile_id, self.provider_profile_version, self.llm_api_authorized_at)
        if any(value is None for value in values) and any(value is not None for value in values):
            raise ValueError("provider binding fields must be all null or all set")
        return self
