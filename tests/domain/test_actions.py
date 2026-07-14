from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from coding_agent_harness.domain.actions import CompleteAction, TaskState, ToolAction
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.domain.models import Task


def test_task_state_has_only_the_frozen_workflow_members() -> None:
    assert [(state.name, state.value) for state in TaskState] == [
        ("CREATED", "CREATED"),
        ("SCANNING", "SCANNING"),
        ("PLANNING", "PLANNING"),
        ("WAITING_PLAN_APPROVAL", "WAITING_PLAN_APPROVAL"),
        ("DECIDING", "DECIDING"),
        ("WAITING_ACTION_APPROVAL", "WAITING_ACTION_APPROVAL"),
        ("EXECUTING", "EXECUTING"),
        ("VERIFYING", "VERIFYING"),
        ("CORRECTING", "CORRECTING"),
        ("WAITING_FINAL_REVIEW", "WAITING_FINAL_REVIEW"),
        ("WAITING_USER", "WAITING_USER"),
        ("COMPLETED", "COMPLETED"),
        ("FAILED", "FAILED"),
        ("CANCELLED", "CANCELLED"),
    ]


def test_tool_action_requires_idempotency_key_and_json_arguments() -> None:
    with pytest.raises(ValidationError):
        ToolAction(tool="read_file", arguments={})

    with pytest.raises(ValidationError):
        ToolAction(
            tool="read_file",
            arguments={"not_json": object()},
            idempotency_key="read-1",
        )


def test_actions_are_frozen_and_reject_unknown_fields() -> None:
    action = CompleteAction(summary="完成")

    with pytest.raises(ValidationError):
        action.summary = "变更"

    with pytest.raises(ValidationError):
        CompleteAction(summary="完成", unexpected=True)


def test_task_is_a_strict_frozen_minimal_contract() -> None:
    now = datetime.now(UTC)
    task = Task(
        id=uuid4(),
        workspace_id=uuid4(),
        requirement="实现严格动作解析",
        state=TaskState.CREATED,
        step_budget=12,
        time_budget_seconds=300.0,
        created_at=now,
        deadline_at=None,
    )

    with pytest.raises(ValidationError):
        task.state = TaskState.PLANNING

    with pytest.raises(ValidationError):
        Task(
            id=task.id,
            workspace_id=task.workspace_id,
            requirement=task.requirement,
            state=task.state,
            step_budget=task.step_budget,
            time_budget_seconds=task.time_budget_seconds,
            created_at=task.created_at,
            deadline_at=None,
            unexpected=True,
        )


def test_task_event_rejects_negative_sequence_and_non_json_payload() -> None:
    common = {
        "task_id": uuid4(),
        "event_type": "task.created",
        "state_before": None,
        "state_after": TaskState.CREATED,
        "occurred_at": datetime.now(UTC),
    }

    with pytest.raises(ValidationError):
        TaskEvent(sequence=-1, payload={}, **common)

    with pytest.raises(ValidationError):
        TaskEvent(sequence=0, payload={"not_json": object()}, **common)
