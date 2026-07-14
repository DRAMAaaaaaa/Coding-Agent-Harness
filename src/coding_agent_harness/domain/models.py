from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
