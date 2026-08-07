from datetime import UTC, datetime
from uuid import uuid4

import pytest

from coding_agent_harness.learning.questions import ReadOnlyAnswer
from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.domain.models import Task
from tests.api.conftest import session_headers


class StubQuestions:
    async def ask(self, task_id: object, card_id: str, question: str) -> ReadOnlyAnswer:
        assert card_id == "failure-card"
        assert question == "为什么失败？"
        return ReadOnlyAnswer(content="Stub explanation")


class Tasks:
    def __init__(self, task: Task) -> None:
        self.task = task

    async def get(self, task_id: object) -> Task | None:
        return self.task if task_id == self.task.id else None


class Events:
    def __init__(self, event: TaskEvent) -> None:
        self.event = event

    async def list_for_task(self, task_id: object) -> list[TaskEvent]:
        return [self.event] if task_id == self.event.task_id else []


class Workspaces:
    async def get(self, workspace_id: object) -> object:
        return object()


@pytest.mark.asyncio
async def test_learning_routes_return_cards_and_failure_answer(client) -> None:
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    active.workspaces = Workspaces()
    active.question_service = StubQuestions()
    task_id = uuid4()
    task = Task(id=task_id, workspace_id=uuid4(), requirement="fix", state=TaskState.WAITING_USER, step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
    active.tasks = Tasks(task)
    active.event_store = Events(TaskEvent(task_id=task_id, sequence=1, event_type="VERIFICATION_FAILED", payload={"reason_code": "TEST_FAILURE"}, state_before=TaskState.WAITING_USER, state_after=TaskState.WAITING_USER, occurred_at=datetime.now(UTC)))
    cards = await client.get(f"/api/tasks/{task_id}/intent-cards")
    assert cards.status_code == 200
    assert cards.json()[0]["kind"] == "verification_failure"
    response = await client.post(f"/api/tasks/{task_id}/questions", headers=await session_headers(client), json={"card_id": "failure-card", "question": "为什么失败？"})
    assert response.status_code == 200
    assert response.json() == {"content": "Stub explanation"}


@pytest.mark.asyncio
async def test_project_learning_requires_final_completed_source_and_is_queryable(client) -> None:
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    active.workspaces = Workspaces()
    workspace_id, task_id = uuid4(), uuid4()
    await active.event_store._database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))  # type: ignore[attr-defined]
    await active.event_store._database.connection.commit()  # type: ignore[attr-defined]
    task = Task(id=task_id, workspace_id=workspace_id, requirement="fix", state=TaskState.COMPLETED, step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
    await active.tasks.create(task)
    await active.event_store.append(TaskEvent(task_id=task_id, sequence=0, event_type="FINAL_SUMMARY_PROPOSED", payload={"summary":"done"}, state_before=None, state_after=None, occurred_at=datetime.now(UTC)), 0)
    headers = await session_headers(client)
    saved = await client.post(f"/api/tasks/{task_id}/project-learning", headers=headers, json={"source_event_sequence": 1, "text": "先运行聚焦测试"})
    assert saved.status_code == 200
    latest = await client.get(f"/api/projects/{workspace_id}/project-learning/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == saved.json()["id"]
