from datetime import UTC, datetime
from uuid import uuid4

import pytest

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.domain.models import Task
from coding_agent_harness.learning.cards import ProjectLearningService
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.project_learning import ProjectLearningRepository
from coding_agent_harness.storage.repositories import TaskRepository


async def _task(repo: TaskRepository, workspace_id, state=TaskState.COMPLETED):
    task = Task(id=uuid4(), workspace_id=workspace_id, requirement="fix", state=state,
                step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
    return await repo.create(task)


async def test_approves_only_completed_final_summary_and_returns_stable_latest(tmp_path) -> None:
    database = await Database.open(tmp_path / "state.db")
    try:
        tasks, events = TaskRepository(database), EventStore(database)
        workspace_id = uuid4()
        await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
        await database.connection.commit()
        first, second = await _task(tasks, workspace_id), await _task(tasks, workspace_id)
        for task in (first, second):
            await events.append(TaskEvent(task_id=task.id, sequence=0, event_type="FINAL_SUMMARY_PROPOSED", payload={"summary":"done"}, state_before=TaskState.WAITING_FINAL_REVIEW, state_after=TaskState.WAITING_FINAL_REVIEW, occurred_at=datetime.now(UTC)), 0)
        service = ProjectLearningService(ProjectLearningRepository(database), tasks, events)
        await service.approve(first.id, 1, "先运行聚焦测试再修改")
        two = await service.approve(second.id, 1, "保留工具和治理边界")
        assert (await service.latest_for_workspace(workspace_id)).id == two.id
        with pytest.raises(ValueError):
            await service.approve(first.id, 1, "重复来源任务")
    finally:
        await database.close()


@pytest.mark.parametrize("value", ["", "\x00", "token=secret", "界" * 1025])
async def test_rejects_invalid_or_sensitive_card_before_persistence(tmp_path, value: str) -> None:
    database = await Database.open(tmp_path / "state.db")
    try:
        tasks, events = TaskRepository(database), EventStore(database)
        workspace_id = uuid4()
        await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
        await database.connection.commit()
        task = await _task(tasks, workspace_id)
        await events.append(TaskEvent(task_id=task.id, sequence=0, event_type="FINAL_SUMMARY_PROPOSED", payload={}, state_before=None, state_after=None, occurred_at=datetime.now(UTC)), 0)
        service = ProjectLearningService(ProjectLearningRepository(database), tasks, events)
        with pytest.raises(ValueError):
            await service.approve(task.id, 1, value)
        assert await service.latest_for_workspace(workspace_id) is None
    finally:
        await database.close()
