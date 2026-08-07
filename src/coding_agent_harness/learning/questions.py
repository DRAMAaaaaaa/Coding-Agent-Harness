"""失败卡片的只读提问服务。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from inspect import isawaitable
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.domain.models import Task
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.learning.intent import IntentKind, IntentProjector, _clip
from coding_agent_harness.providers.base import LLMProvider, LLMRequest, ProviderError


MAX_QUESTION_BYTES = 4096


class ReadOnlyAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    content: str


ProviderForTask = Callable[[Task], Awaitable[LLMProvider] | LLMProvider]


class TaskReader(Protocol):
    async def get(self, task_id: UUID) -> Task | None: ...


class LearningEventStore(Protocol):
    async def list_for_task(self, task_id: UUID) -> list[TaskEvent]: ...
    async def append(self, event: TaskEvent, expected_sequence: int) -> TaskEvent: ...


class QuestionService:
    def __init__(self, tasks: TaskReader, events: LearningEventStore, *, provider_for_task: ProviderForTask, projector: IntentProjector | None = None, redactor: Redactor | None = None) -> None:
        self._tasks, self._events, self._provider_for_task = tasks, events, provider_for_task
        self._projector, self._redactor = projector or IntentProjector(), redactor or Redactor()

    async def ask(self, task_id: UUID, card_id: str, question: str) -> ReadOnlyAnswer:
        if not 1 <= len(question.encode("utf-8")) <= MAX_QUESTION_BYTES:
            raise ValueError("QUESTION_TOO_LARGE")
        task = await self._tasks.get(task_id)
        if task is None:
            raise KeyError("TASK_NOT_FOUND")
        events = await self._events.list_for_task(task_id)
        card = next((item for item in self._projector.project(task_id, events) if item.id == card_id), None)
        if card is None or card.kind is not IntentKind.VERIFICATION_FAILURE:
            raise ValueError("FAILURE_CARD_REQUIRED")
        safe_question = _clip_text(self._redactor, question)
        await self._append(task_id, task.state, events, "LEARNING_QUESTION_ASKED", {"card_id": card.id, "question": safe_question})
        try:
            provider = self._provider_for_task(task)
            if isawaitable(provider):
                provider = await provider
            request = LLMRequest(messages=[{"role": "user", "content": _clip(f"卡片: {card.actual_result}\n问题: {safe_question}")}])
            response = await provider.complete(request)
        except ProviderError as error:
            await self._append(task_id, task.state, await self._events.list_for_task(task_id), "LEARNING_QUESTION_FAILED", {"provider_kind": error.kind})
            raise
        answer = _clip_text(self._redactor, response.content)
        await self._append(task_id, task.state, await self._events.list_for_task(task_id), "LEARNING_QUESTION_ANSWERED", {"card_id": card.id, "answer": answer})
        return ReadOnlyAnswer(content=answer)

    async def _append(self, task_id: UUID, state: TaskState, events: list[TaskEvent], event_type: str, payload: dict[str, JsonValue]) -> None:
        await self._events.append(TaskEvent(task_id=task_id, sequence=0, event_type=event_type, payload=payload, state_before=state, state_after=state, occurred_at=datetime.now(UTC)), expected_sequence=len(events))


def _clip_text(redactor: Redactor, value: str) -> str:
    sanitized = redactor.sanitize(value).value
    return _clip(sanitized if isinstance(sanitized, str) else "")
