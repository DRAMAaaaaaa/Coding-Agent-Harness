from dataclasses import dataclass
from typing import Final, Sequence

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent


_TERMINAL_STATES: Final = {
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.CANCELLED,
}

LEGAL_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.SCANNING, TaskState.CANCELLED},
    TaskState.SCANNING: {
        TaskState.PLANNING,
        TaskState.DECIDING,
        TaskState.WAITING_USER,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.PLANNING: {
        TaskState.WAITING_PLAN_APPROVAL,
        TaskState.WAITING_USER,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAITING_PLAN_APPROVAL: {
        TaskState.PLANNING,
        TaskState.DECIDING,
        TaskState.WAITING_USER,
        TaskState.CANCELLED,
    },
    TaskState.DECIDING: {
        TaskState.EXECUTING,
        TaskState.WAITING_ACTION_APPROVAL,
        TaskState.VERIFYING,
        TaskState.WAITING_FINAL_REVIEW,
        TaskState.WAITING_USER,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAITING_ACTION_APPROVAL: {
        TaskState.EXECUTING,
        TaskState.DECIDING,
        TaskState.WAITING_USER,
        TaskState.CANCELLED,
    },
    TaskState.EXECUTING: {
        TaskState.VERIFYING,
        TaskState.DECIDING,
        TaskState.WAITING_USER,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.VERIFYING: {
        TaskState.CORRECTING,
        TaskState.DECIDING,
        TaskState.WAITING_FINAL_REVIEW,
        TaskState.WAITING_USER,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.CORRECTING: {
        TaskState.DECIDING,
        TaskState.WAITING_USER,
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
    TaskState.WAITING_FINAL_REVIEW: {
        TaskState.COMPLETED,
        TaskState.CANCELLED,
    },
    TaskState.WAITING_USER: {
        TaskState.DECIDING,
        TaskState.CANCELLED,
        TaskState.FAILED,
    },
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
}

_EVENT_TARGETS: Final[dict[str, TaskState]] = {
    "SCAN_STARTED": TaskState.SCANNING,
    "PLAN_STARTED": TaskState.PLANNING,
    "PLAN_PROPOSED": TaskState.WAITING_PLAN_APPROVAL,
    "PLAN_APPROVED": TaskState.DECIDING,
    "PLAN_REJECTED": TaskState.PLANNING,
    "ACTION_PROPOSED": TaskState.EXECUTING,
    "ACTION_APPROVAL_REQUIRED": TaskState.WAITING_ACTION_APPROVAL,
    "ACTION_APPROVED": TaskState.EXECUTING,
    "ACTION_REJECTED": TaskState.DECIDING,
    "READ_TOOL_COMPLETED": TaskState.DECIDING,
    "TOOL_COMPLETED": TaskState.VERIFYING,
    "VERIFICATION_READY": TaskState.DECIDING,
    "VERIFICATION_FAILED": TaskState.CORRECTING,
    "CORRECTION_READY": TaskState.DECIDING,
    "VERIFICATION_PASSED": TaskState.WAITING_FINAL_REVIEW,
    "FINAL_SUMMARY_PROPOSED": TaskState.WAITING_FINAL_REVIEW,
    "FINAL_REVIEW_APPROVED": TaskState.COMPLETED,
    "USER_INPUT_REQUIRED": TaskState.WAITING_USER,
    "USER_RESUMED": TaskState.DECIDING,
    "TASK_FAILED": TaskState.FAILED,
    "TASK_CANCELLED": TaskState.CANCELLED,
}

_TOOL_STARTED: Final = "TOOL_EXECUTION_STARTED"
_TOOL_FINISHED: Final = {"TOOL_EXECUTION_COMPLETED", "TOOL_EXECUTION_FAILED"}
_STATE_PRESERVING_EVENTS: Final = {
    "LLM_REQUESTED",
    "LLM_RESPONSE_RECEIVED",
    "ACTION_PARSED",
    "ACTION_PARSE_FAILED",
    "GOVERNANCE_ALLOWED",
    "GOVERNANCE_BLOCKED",
    "TOOL_EXECUTION_STARTED",
    "TOOL_EXECUTION_COMPLETED",
    "TOOL_EXECUTION_FAILED",
    "VERIFICATION_RECORDED",
    "VERIFICATION_SUCCEEDED",
    "FEEDBACK_RECORDED",
    "FINAL_SUMMARY_RECORDED",
    "OBSERVATION_RECORDED",
}


class IllegalTransition(RuntimeError):
    """未知事件或不合法状态路径。"""


class RecoveryError(RuntimeError):
    """已落盘事件流不满足确定性重放约束。"""


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    state: TaskState
    reason_code: str | None
    last_sequence: int


class StateMachine:
    def transition(self, current: TaskState, event_type: str) -> TaskState:
        if event_type in _STATE_PRESERVING_EVENTS:
            if event_type in {_TOOL_STARTED, *_TOOL_FINISHED} and current is not TaskState.EXECUTING:
                raise IllegalTransition(f"工具执行事件只能发生在 EXECUTING：{event_type}")
            return current
        target = _EVENT_TARGETS.get(event_type)
        if target is None:
            raise IllegalTransition(f"未知事件类型：{event_type}")
        allowed = LEGAL_TRANSITIONS.get(current)
        if allowed is None or target not in allowed:
            raise IllegalTransition(f"不合法状态迁移：{current} --{event_type}--> {target}")
        return target


def recover_task(events: Sequence[TaskEvent]) -> RecoveryResult:
    if not events:
        return RecoveryResult(TaskState.CREATED, None, 0)

    task_id = events[0].task_id
    state = TaskState.CREATED
    pending_executions: set[str] = set()

    for expected_sequence, event in enumerate(events, start=1):
        if event.task_id != task_id:
            raise RecoveryError("事件流包含多个任务")
        if event.sequence != expected_sequence:
            raise RecoveryError("事件序号必须从 1 开始严格连续递增")
        if event.state_before is not state or event.state_after is None:
            raise RecoveryError("事件状态链断裂")
        if event.state_after is not state and event.state_after not in LEGAL_TRANSITIONS[state]:
            raise RecoveryError("事件包含不合法状态迁移")

        if event.event_type == _TOOL_STARTED:
            execution_id = _execution_id(event)
            if execution_id in pending_executions:
                raise RecoveryError("工具执行开始事件重复")
            pending_executions.add(execution_id)
        elif event.event_type in _TOOL_FINISHED:
            execution_id = _execution_id(event)
            if execution_id not in pending_executions:
                raise RecoveryError("工具执行结束事件没有对应开始事件")
            pending_executions.remove(execution_id)

        state = event.state_after

    if pending_executions:
        return RecoveryResult(
            TaskState.WAITING_USER,
            "UNCERTAIN_SIDE_EFFECT",
            events[-1].sequence,
        )
    return RecoveryResult(state, None, events[-1].sequence)


def _execution_id(event: TaskEvent) -> str:
    execution_id = event.payload.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id:
        raise RecoveryError("工具执行事件缺少有效 execution_id")
    return execution_id
