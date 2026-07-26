import pytest

from coding_agent_harness.agent.state_machine import (
    LEGAL_TRANSITIONS,
    IllegalTransition,
    StateMachine,
)
from coding_agent_harness.domain.actions import TaskState


BASE_TRANSITIONS = {
    TaskState.CREATED: {TaskState.SCANNING, TaskState.CANCELLED},
    TaskState.SCANNING: {
        TaskState.PLANNING,
        TaskState.DECIDING,
        TaskState.WAITING_USER,
        TaskState.FAILED,
    },
    TaskState.PLANNING: {
        TaskState.WAITING_PLAN_APPROVAL,
        TaskState.WAITING_USER,
        TaskState.FAILED,
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
    },
    TaskState.VERIFYING: {
        TaskState.CORRECTING,
        TaskState.DECIDING,
        TaskState.WAITING_FINAL_REVIEW,
        TaskState.WAITING_USER,
        TaskState.FAILED,
    },
    TaskState.CORRECTING: {
        TaskState.DECIDING,
        TaskState.WAITING_USER,
        TaskState.FAILED,
    },
    TaskState.WAITING_FINAL_REVIEW: {TaskState.COMPLETED, TaskState.CANCELLED},
    TaskState.WAITING_USER: {
        TaskState.DECIDING,
        TaskState.CANCELLED,
        TaskState.FAILED,
    },
}
TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}


def test_legal_transitions_match_frozen_contract() -> None:
    expected = {
        state: targets | {TaskState.CANCELLED}
        for state, targets in BASE_TRANSITIONS.items()
    }
    expected.update({state: set() for state in TERMINAL_STATES})

    assert LEGAL_TRANSITIONS == expected


@pytest.mark.parametrize(
    ("current", "event_type", "expected"),
    [
        (TaskState.CREATED, "SCAN_STARTED", TaskState.SCANNING),
        (TaskState.SCANNING, "PLAN_STARTED", TaskState.PLANNING),
        (TaskState.PLANNING, "PLAN_PROPOSED", TaskState.WAITING_PLAN_APPROVAL),
        (TaskState.WAITING_PLAN_APPROVAL, "PLAN_APPROVED", TaskState.DECIDING),
        (TaskState.WAITING_PLAN_APPROVAL, "PLAN_REJECTED", TaskState.PLANNING),
        (TaskState.DECIDING, "ACTION_PROPOSED", TaskState.EXECUTING),
        (
            TaskState.DECIDING,
            "ACTION_APPROVAL_REQUIRED",
            TaskState.WAITING_ACTION_APPROVAL,
        ),
        (TaskState.WAITING_ACTION_APPROVAL, "ACTION_APPROVED", TaskState.EXECUTING),
        (TaskState.WAITING_ACTION_APPROVAL, "ACTION_REJECTED", TaskState.DECIDING),
        (TaskState.EXECUTING, "READ_TOOL_COMPLETED", TaskState.DECIDING),
        (TaskState.EXECUTING, "TOOL_COMPLETED", TaskState.VERIFYING),
        (TaskState.VERIFYING, "VERIFICATION_READY", TaskState.DECIDING),
        (TaskState.VERIFYING, "VERIFICATION_FAILED", TaskState.CORRECTING),
        (TaskState.DECIDING, "FINAL_SUMMARY_PROPOSED", TaskState.WAITING_FINAL_REVIEW),
        (TaskState.CORRECTING, "CORRECTION_READY", TaskState.DECIDING),
        (
            TaskState.VERIFYING,
            "VERIFICATION_PASSED",
            TaskState.WAITING_FINAL_REVIEW,
        ),
        (
            TaskState.WAITING_FINAL_REVIEW,
            "FINAL_REVIEW_APPROVED",
            TaskState.COMPLETED,
        ),
        (TaskState.SCANNING, "USER_INPUT_REQUIRED", TaskState.WAITING_USER),
        (TaskState.WAITING_USER, "USER_RESUMED", TaskState.DECIDING),
        (TaskState.SCANNING, "TASK_FAILED", TaskState.FAILED),
        (TaskState.CREATED, "TASK_CANCELLED", TaskState.CANCELLED),
    ],
)
def test_state_machine_supports_required_events(
    current: TaskState,
    event_type: str,
    expected: TaskState,
) -> None:
    assert StateMachine().transition(current, event_type) is expected


def test_state_machine_rejects_execution_before_plan_approval() -> None:
    with pytest.raises(IllegalTransition):
        StateMachine().transition(TaskState.PLANNING, "ACTION_PROPOSED")


def test_state_machine_rejects_unknown_event() -> None:
    with pytest.raises(IllegalTransition):
        StateMachine().transition(TaskState.CREATED, "UNKNOWN")


def test_state_machine_records_tool_start_without_advancing_side_effect_state() -> None:
    assert (
        StateMachine().transition(TaskState.EXECUTING, "TOOL_EXECUTION_STARTED")
        is TaskState.EXECUTING
    )


@pytest.mark.parametrize("current", sorted(TERMINAL_STATES, key=str))
def test_terminal_states_have_no_outgoing_transition(current: TaskState) -> None:
    with pytest.raises(IllegalTransition):
        StateMachine().transition(current, "TASK_CANCELLED")


@pytest.mark.parametrize("current", sorted(set(TaskState) - TERMINAL_STATES, key=str))
def test_every_non_terminal_state_can_be_cancelled(current: TaskState) -> None:
    assert StateMachine().transition(current, "TASK_CANCELLED") is TaskState.CANCELLED
