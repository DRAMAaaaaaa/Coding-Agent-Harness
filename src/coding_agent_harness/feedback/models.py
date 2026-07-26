from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from coding_agent_harness.domain.actions import TaskState


class FailureCategory(StrEnum):
    TEST = "TEST"
    LINT = "LINT"
    TYPECHECK = "TYPECHECK"
    BUILD = "BUILD"
    TIMEOUT = "TIMEOUT"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    POLICY = "POLICY"
    TOOL = "TOOL"
    UNKNOWN = "UNKNOWN"


class VerificationRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(min_length=1)
    ok: bool
    output: str = ""
    failure_count: int | None = Field(default=None, ge=0)


class FeedbackObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    category: FailureCategory
    fingerprint: str = Field(min_length=1)
    failure_count: int | None = Field(ge=0)


class FeedbackDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    observation: FeedbackObservation
    next_state: TaskState
    reason_code: str
