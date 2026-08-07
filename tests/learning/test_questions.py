from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.domain.models import Task
from coding_agent_harness.learning.questions import QuestionService
from coding_agent_harness.providers.base import LLMRequest, LLMResponse


class StubProvider:
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []
        self.response = "Stub explanation"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content=self.response)


class Tasks:
    def __init__(self, task: Task) -> None:
        self.task = task

    async def get(self, task_id: object) -> Task | None:
        return self.task if task_id == self.task.id else None


class Events:
    def __init__(self, values: list[TaskEvent]) -> None:
        self.values = values

    async def list_for_task(self, task_id: object) -> list[TaskEvent]:
        return list(self.values)

    async def append(self, event: TaskEvent, expected_sequence: int) -> TaskEvent:
        assert expected_sequence == len(self.values)
        stored = event.model_copy(update={"sequence": expected_sequence + 1})
        self.values.append(stored)
        return stored


TASK_ID = uuid4()


def make_event(sequence: int, event_type: str, payload: dict[str, object]) -> TaskEvent:
    return TaskEvent(task_id=TASK_ID, sequence=sequence, event_type=event_type, payload=payload, state_before=TaskState.WAITING_USER, state_after=TaskState.WAITING_USER, occurred_at=datetime.now(UTC))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_question_is_zero_tool_and_state_preserving(tmp_path: Path) -> None:
    task = Task(id=TASK_ID, workspace_id=uuid4(), requirement="fix", state=TaskState.WAITING_USER, step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
    events = Events([make_event(1, "VERIFICATION_RECORDED", {"run": {"diagnostic": "failed"}}), make_event(2, "VERIFICATION_FAILED", {"reason_code": "TEST_FAILURE"})])
    provider = StubProvider()
    service = QuestionService(Tasks(task), events, provider_for_task=lambda _: provider)
    before = (task.state, tuple(events.values), tmp_path.read_bytes() if tmp_path.is_file() else None)

    answer = await service.ask(TASK_ID, f"{TASK_ID}:verification_failure:2", "为什么失败？")

    assert answer.content == "Stub explanation"
    assert task.state is TaskState.WAITING_USER
    assert provider.requests and provider.requests[0].model_dump().keys() == {"messages"}
    assert all(item.state_before is item.state_after is TaskState.WAITING_USER for item in events.values[-2:])
    assert before[2] is None


@pytest.mark.asyncio
async def test_question_rejects_non_failure_card_and_oversized_utf8_input() -> None:
    task = Task(id=TASK_ID, workspace_id=uuid4(), requirement="fix", state=TaskState.WAITING_USER, step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
    events = Events([make_event(1, "PLAN_PROPOSED", {"plan": "plan"})])
    service = QuestionService(Tasks(task), events, provider_for_task=lambda _: StubProvider())

    with pytest.raises(ValueError, match="FAILURE_CARD_REQUIRED"):
        await service.ask(TASK_ID, f"{TASK_ID}:plan:1", "why")
    with pytest.raises(ValueError, match="QUESTION_TOO_LARGE"):
        await service.ask(TASK_ID, "missing", "你" * 1400)


@pytest.mark.asyncio
async def test_question_keeps_maximum_multibyte_answer_and_complete_question_after_large_card() -> None:
    task = Task(id=TASK_ID, workspace_id=uuid4(), requirement="fix", state=TaskState.WAITING_USER, step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
    events = Events([make_event(1, "VERIFICATION_RECORDED", {"run": {"diagnostic": "卡" * 8_000}}), make_event(2, "VERIFICATION_FAILED", {"reason_code": "TEST_FAILURE"})])
    provider = StubProvider()
    provider.response = "答" * 6_000
    service = QuestionService(Tasks(task), events, provider_for_task=lambda _: provider)
    question = "问" * 1_358 + "唯一问题标记"

    answer = await service.ask(TASK_ID, f"{TASK_ID}:verification_failure:2", question)

    content = provider.requests[0].messages[0]["content"]
    assert isinstance(content, str) and question in content and "事件摘要:" in content
    assert len(answer.content.encode("utf-8")) <= 16 * 1024
    assert len(answer.content) < len(provider.response)
