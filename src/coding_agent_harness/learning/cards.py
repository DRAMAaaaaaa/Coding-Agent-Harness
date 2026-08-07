"""把完成任务的最终交付转成可审计的项目经验。"""
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.project_learning import ProjectLearningRepository
from coding_agent_harness.storage.repositories import TaskRepository

MAX_PROJECT_LEARNING_BYTES = 2048


class ProjectLearningCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: UUID
    workspace_id: UUID
    text: str
    source_task_id: UUID
    source_event_sequence: int
    approved_at: datetime


class ProjectLearningService:
    def __init__(self, cards: ProjectLearningRepository, tasks: TaskRepository, events: EventStore,
                 redactor: Redactor | None = None) -> None:
        self._cards, self._tasks, self._events, self._redactor = cards, tasks, events, redactor or Redactor()

    async def approve(self, task_id: UUID, source_event_sequence: int, text: str) -> ProjectLearningCard:
        self._validate_text(text)
        task = await self._tasks.get(task_id)
        if task is None or task.state is not TaskState.COMPLETED:
            raise ValueError("PROJECT_LEARNING_SOURCE_NOT_COMPLETED")
        events = await self._events.list_for_task(task_id)
        if not any(event.sequence == source_event_sequence and event.event_type == "FINAL_SUMMARY_PROPOSED" for event in events):
            raise ValueError("PROJECT_LEARNING_SOURCE_NOT_FINAL")
        card = ProjectLearningCard(id=uuid4(), workspace_id=task.workspace_id, text=text,
            source_task_id=task_id, source_event_sequence=source_event_sequence, approved_at=datetime.now(UTC))
        try:
            return await self._cards.create(card)
        except Exception as error:
            if "UNIQUE constraint failed" in str(error):
                raise ValueError("PROJECT_LEARNING_SOURCE_ALREADY_APPROVED") from None
            raise

    async def latest_for_workspace(self, workspace_id: UUID) -> ProjectLearningCard | None:
        return await self._cards.latest_for_workspace(workspace_id)

    def _validate_text(self, text: str) -> None:
        if not isinstance(text, str) or not text or "\x00" in text or len(text.encode("utf-8")) > MAX_PROJECT_LEARNING_BYTES:
            raise ValueError("PROJECT_LEARNING_INVALID_TEXT")
        if self._redactor.sanitize(text).rule_names:
            raise ValueError("PROJECT_LEARNING_SENSITIVE_TEXT")
