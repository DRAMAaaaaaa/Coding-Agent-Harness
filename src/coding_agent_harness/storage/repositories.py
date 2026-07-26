import sqlite3
from datetime import datetime
from uuid import UUID

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.models import Task
from coding_agent_harness.domain.limits import validate_requirement_size
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.storage.database import Database


_TASK_COLUMNS = """
    id, workspace_id, requirement, state, step_budget,
    time_budget_seconds, created_at, deadline_at
"""


class TaskNotFoundError(LookupError):
    """更新不存在的任务时抛出的稳定异常。"""


class TaskRepository:
    def __init__(self, database: Database, redactor: Redactor | None = None) -> None:
        self._database = database
        self._redactor = redactor or Redactor()

    async def create(self, task: Task) -> Task:
        validate_requirement_size(task.requirement)
        requirement = self._redactor.sanitize(task.requirement).value
        if not isinstance(requirement, str):
            raise TypeError("任务需求必须是字符串")
        validate_requirement_size(requirement)
        task = task.model_copy(update={"requirement": requirement})
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute(
                    f"""
                    INSERT INTO tasks ({_TASK_COLUMNS})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(task.id),
                        str(task.workspace_id),
                        task.requirement,
                        task.state.value,
                        task.step_budget,
                        task.time_budget_seconds,
                        task.created_at.isoformat(),
                        task.deadline_at.isoformat() if task.deadline_at else None,
                    ),
                )
                await self._database.connection.commit()
            except BaseException:
                await self._database.connection.rollback()
                raise
        return task

    async def get(self, task_id: UUID) -> Task | None:
        async with self._database.operation_lock:
            cursor = await self._database.connection.execute(
                f"SELECT {_TASK_COLUMNS} FROM tasks WHERE id = ?",
                (str(task_id),),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _task_from_row(row)

    async def update_state(self, task_id: UUID, state: TaskState) -> Task:
        async with self._database.operation_lock:
            try:
                cursor = await self._database.connection.execute(
                    f"""
                    UPDATE tasks SET state = ? WHERE id = ?
                    RETURNING {_TASK_COLUMNS}
                    """,
                    (state.value, str(task_id)),
                )
                row = await cursor.fetchone()
                if row is None:
                    await self._database.connection.rollback()
                    raise TaskNotFoundError(f"任务不存在：{task_id}")
                await self._database.connection.commit()
            except TaskNotFoundError:
                raise
            except BaseException:
                await self._database.connection.rollback()
                raise
        return _task_from_row(row)


def _task_from_row(row: sqlite3.Row) -> Task:
    deadline = row[7]
    return Task(
        id=UUID(str(row[0])),
        workspace_id=UUID(str(row[1])),
        requirement=str(row[2]),
        state=TaskState(str(row[3])),
        step_budget=int(str(row[4])),
        time_budget_seconds=float(str(row[5])),
        created_at=datetime.fromisoformat(str(row[6])),
        deadline_at=datetime.fromisoformat(str(deadline)) if deadline is not None else None,
    )
