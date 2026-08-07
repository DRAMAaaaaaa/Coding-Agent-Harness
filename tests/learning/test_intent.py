from datetime import UTC, datetime
from uuid import uuid4

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.learning.intent import IntentKind, IntentProjector


def event(sequence: int, event_type: str, payload: dict[str, object]) -> TaskEvent:
    return TaskEvent(
        task_id=TASK_ID,
        sequence=sequence,
        event_type=event_type,
        payload=payload,  # type: ignore[arg-type]
        state_before=TaskState.DECIDING,
        state_after=TaskState.DECIDING,
        occurred_at=datetime.now(UTC),
    )


TASK_ID = uuid4()


def test_projects_four_stable_cards_from_unsorted_duplicate_events() -> None:
    cards = IntentProjector().project(
        TASK_ID,
        [
            event(8, "FINAL_SUMMARY_PROPOSED", {"summary": "delivered"}),
            event(5, "VERIFICATION_FAILED", {"reason_code": "TEST_FAILURE"}),
            event(4, "FEEDBACK_RECORDED", {"output": "assertion failed"}),
            event(2, "PLAN_PROPOSED", {"plan": "change one file"}),
            event(3, "TOOL_EXECUTION_COMPLETED", {"result": {"changed_paths": ["src/a.py"]}}),
            event(3, "TOOL_EXECUTION_COMPLETED", {"result": {"changed_paths": ["src/a.py"]}}),
            event(1, "SCAN_STARTED", {}),
        ],
    )

    assert [card.kind for card in cards] == [
        IntentKind.PLAN,
        IntentKind.FIRST_EDIT,
        IntentKind.VERIFICATION_FAILURE,
        IntentKind.FINAL_DELIVERY,
    ]
    assert [card.id for card in cards] == [
        f"{TASK_ID}:plan:2",
        f"{TASK_ID}:first_edit:3",
        f"{TASK_ID}:verification_failure:5",
        f"{TASK_ID}:final_delivery:8",
    ]
    assert cards[2].evidence_sequences == (4, 5)
