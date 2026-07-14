from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class TaskState(StrEnum):
    CREATED = "CREATED"
    SCANNING = "SCANNING"
    PLANNING = "PLANNING"
    WAITING_PLAN_APPROVAL = "WAITING_PLAN_APPROVAL"
    DECIDING = "DECIDING"
    WAITING_ACTION_APPROVAL = "WAITING_ACTION_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    CORRECTING = "CORRECTING"
    WAITING_FINAL_REVIEW = "WAITING_FINAL_REVIEW"
    WAITING_USER = "WAITING_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["tool"] = "tool"
    tool: str
    arguments: dict[str, JsonValue]
    idempotency_key: str


class CompleteAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["complete"] = "complete"
    summary: str


AgentAction: TypeAlias = Annotated[
    ToolAction | CompleteAction,
    Field(discriminator="kind"),
]
