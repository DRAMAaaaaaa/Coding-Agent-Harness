"""项目级、单条且经用户批准的经验卡持久化。"""
from datetime import datetime
from uuid import UUID

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from coding_agent_harness.learning.cards import ProjectLearningCard
from coding_agent_harness.storage.database import Database


class ProjectLearningRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, card: "ProjectLearningCard") -> "ProjectLearningCard":
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute(
                    "INSERT INTO project_learning_cards VALUES (?, ?, ?, ?, ?, ?)",
                    (str(card.id), str(card.workspace_id), card.text, str(card.source_task_id),
                     card.source_event_sequence, card.approved_at.isoformat()),
                )
                await self._database.connection.commit()
            except Exception:
                await self._database.connection.rollback()
                raise
        return card

    async def latest_for_workspace(self, workspace_id: UUID) -> "ProjectLearningCard | None":
        async with self._database.operation_lock:
            row = await (await self._database.connection.execute(
                "SELECT id, workspace_id, text, source_task_id, source_event_sequence, approved_at "
                "FROM project_learning_cards WHERE workspace_id=? "
                "ORDER BY approved_at DESC, id ASC LIMIT 1", (str(workspace_id),)
            )).fetchone()
        return _card(row) if row is not None else None


def _card(row: object) -> "ProjectLearningCard":
    from coding_agent_harness.learning.cards import ProjectLearningCard
    values = cast(tuple[object, ...], tuple(row))  # type: ignore[arg-type]
    return ProjectLearningCard(id=UUID(str(values[0])), workspace_id=UUID(str(values[1])),
        text=str(values[2]), source_task_id=UUID(str(values[3])), source_event_sequence=int(str(values[4])),
        approved_at=datetime.fromisoformat(str(values[5])))
