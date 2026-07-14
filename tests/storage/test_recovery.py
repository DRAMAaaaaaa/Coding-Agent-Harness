from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from coding_agent_harness.agent.state_machine import RecoveryError, recover_task
from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent


def _event(
    task_id: UUID,
    sequence: int,
    event_type: str,
    state_before: TaskState,
    state_after: TaskState,
    payload: dict[str, object] | None = None,
) -> TaskEvent:
    return TaskEvent(
        task_id=task_id,
        sequence=sequence,
        event_type=event_type,
        payload=payload or {},
        state_before=state_before,
        state_after=state_after,
        occurred_at=datetime.now(UTC),
    )


def _events_to_executing(task_id: UUID) -> list[TaskEvent]:
    return [
        _event(task_id, 1, "SCAN_STARTED", TaskState.CREATED, TaskState.SCANNING),
        _event(task_id, 2, "PLAN_STARTED", TaskState.SCANNING, TaskState.PLANNING),
        _event(
            task_id,
            3,
            "PLAN_PROPOSED",
            TaskState.PLANNING,
            TaskState.WAITING_PLAN_APPROVAL,
        ),
        _event(
            task_id,
            4,
            "PLAN_APPROVED",
            TaskState.WAITING_PLAN_APPROVAL,
            TaskState.DECIDING,
        ),
        _event(
            task_id,
            5,
            "ACTION_PROPOSED",
            TaskState.DECIDING,
            TaskState.EXECUTING,
        ),
    ]


def test_recover_empty_task_to_created() -> None:
    result = recover_task([])

    assert result.state is TaskState.CREATED
    assert result.reason_code is None
    assert result.last_sequence == 0


def test_recover_replays_persisted_state_chain() -> None:
    result = recover_task(_events_to_executing(uuid4()))

    assert result.state is TaskState.EXECUTING
    assert result.reason_code is None
    assert result.last_sequence == 5


def test_recover_allows_state_preserving_events() -> None:
    task_id = uuid4()
    events = _events_to_executing(task_id)
    events.append(
        _event(
            task_id,
            6,
            "OBSERVATION_RECORDED",
            TaskState.EXECUTING,
            TaskState.EXECUTING,
        )
    )

    assert recover_task(events).state is TaskState.EXECUTING


@pytest.mark.parametrize("corruption", ["mixed", "duplicate", "gap", "reverse", "chain"])
def test_recover_rejects_corrupted_event_stream(corruption: str) -> None:
    task_id = uuid4()
    events = _events_to_executing(task_id)[:2]
    if corruption == "mixed":
        events[1] = events[1].model_copy(update={"task_id": uuid4()})
    elif corruption == "duplicate":
        events[1] = events[1].model_copy(update={"sequence": 1})
    elif corruption == "gap":
        events[1] = events[1].model_copy(update={"sequence": 3})
    elif corruption == "reverse":
        events = list(reversed(events))
    else:
        events[1] = events[1].model_copy(update={"state_before": TaskState.CREATED})

    with pytest.raises(RecoveryError):
        recover_task(events)


def test_recover_rejects_illegal_persisted_state_change() -> None:
    task_id = uuid4()
    event = _event(
        task_id,
        1,
        "CORRUPT",
        TaskState.CREATED,
        TaskState.EXECUTING,
    )

    with pytest.raises(RecoveryError):
        recover_task([event])


def test_recover_does_not_replay_uncertain_tool_side_effect() -> None:
    task_id = uuid4()
    events = _events_to_executing(task_id)
    events.append(
        _event(
            task_id,
            6,
            "TOOL_EXECUTION_STARTED",
            TaskState.EXECUTING,
            TaskState.EXECUTING,
            {"execution_id": "exec-1"},
        )
    )

    result = recover_task(events)

    assert result.state is TaskState.WAITING_USER
    assert result.reason_code == "UNCERTAIN_SIDE_EFFECT"
    assert result.last_sequence == 6
    assert not hasattr(result, "actions")


@pytest.mark.parametrize(
    "terminal_event_type",
    ["TOOL_EXECUTION_COMPLETED", "TOOL_EXECUTION_FAILED"],
)
def test_recover_matches_finished_tool_execution(terminal_event_type: str) -> None:
    task_id = uuid4()
    events = _events_to_executing(task_id)
    events.extend(
        [
            _event(
                task_id,
                6,
                "TOOL_EXECUTION_STARTED",
                TaskState.EXECUTING,
                TaskState.EXECUTING,
                {"execution_id": "exec-1"},
            ),
            _event(
                task_id,
                7,
                terminal_event_type,
                TaskState.EXECUTING,
                TaskState.EXECUTING,
                {"execution_id": "exec-1"},
            ),
        ]
    )

    result = recover_task(events)

    assert result.state is TaskState.EXECUTING
    assert result.reason_code is None
    assert result.last_sequence == 7


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("TOOL_EXECUTION_STARTED", {}),
        ("TOOL_EXECUTION_STARTED", {"execution_id": 7}),
        ("TOOL_EXECUTION_COMPLETED", {"execution_id": "unknown"}),
    ],
)
def test_recover_rejects_invalid_tool_execution_pairing(
    event_type: str,
    payload: dict[str, object],
) -> None:
    task_id = uuid4()
    events = _events_to_executing(task_id)
    events.append(
        _event(
            task_id,
            6,
            event_type,
            TaskState.EXECUTING,
            TaskState.EXECUTING,
            payload,
        )
    )

    with pytest.raises(RecoveryError):
        recover_task(events)
