from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from coding_agent_harness.domain.actions import TaskState


class TaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: UUID
    sequence: int = Field(ge=0)
    event_type: str
    payload: dict[str, JsonValue]
    state_before: TaskState | None
    state_after: TaskState | None
    occurred_at: datetime
