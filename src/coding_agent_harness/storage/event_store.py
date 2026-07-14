import json
import sqlite3
from datetime import datetime
from uuid import UUID

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.storage.database import Database


class ConcurrencyError(RuntimeError):
    """乐观序号与已落盘事件流不一致。"""


class EventStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def append(self, event: TaskEvent, expected_sequence: int) -> TaskEvent:
        if expected_sequence < 0:
            raise ValueError("expected_sequence 不能为负数")

        async with self._database.write_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                cursor = await self._database.connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0)
                    FROM task_events
                    WHERE task_id = ?
                    """,
                    (str(event.task_id),),
                )
                row = await cursor.fetchone()
                current_sequence = int(row[0]) if row is not None else 0
                if current_sequence != expected_sequence:
                    raise ConcurrencyError(
                        f"事件序号冲突：预期 {expected_sequence}，实际 {current_sequence}"
                    )

                next_sequence = current_sequence + 1
                await self._database.connection.execute(
                    """
                    INSERT INTO task_events (
                        task_id, sequence, event_type, payload,
                        state_before, state_after, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(event.task_id),
                        next_sequence,
                        event.event_type,
                        json.dumps(
                            event.payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        event.state_before.value if event.state_before else None,
                        event.state_after.value if event.state_after else None,
                        event.occurred_at.isoformat(),
                    ),
                )
                await self._database.connection.commit()
            except BaseException:
                await self._database.connection.rollback()
                raise

        return event.model_copy(update={"sequence": next_sequence})

    async def list_for_task(self, task_id: UUID, after: int = 0) -> list[TaskEvent]:
        cursor = await self._database.connection.execute(
            """
            SELECT task_id, sequence, event_type, payload,
                   state_before, state_after, occurred_at
            FROM task_events
            WHERE task_id = ? AND sequence > ?
            ORDER BY sequence ASC
            """,
            (str(task_id), after),
        )
        rows = await cursor.fetchall()
        return [_event_from_row(row) for row in rows]


def _event_from_row(row: sqlite3.Row) -> TaskEvent:
    state_before = row[4]
    state_after = row[5]
    payload = json.loads(str(row[3]))
    if not isinstance(payload, dict):
        raise ValueError("事件载荷必须是 JSON 对象")
    return TaskEvent(
        task_id=UUID(str(row[0])),
        sequence=int(str(row[1])),
        event_type=str(row[2]),
        payload=payload,
        state_before=TaskState(str(state_before)) if state_before is not None else None,
        state_after=TaskState(str(state_after)) if state_after is not None else None,
        occurred_at=datetime.fromisoformat(str(row[6])),
    )
