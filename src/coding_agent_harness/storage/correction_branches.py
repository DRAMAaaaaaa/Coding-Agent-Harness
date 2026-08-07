"""单级纠正分支的幂等持久化边界。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from coding_agent_harness.storage.database import Database


BranchStatus = Literal["CREATING", "READY", "UNCERTAIN"]


@dataclass(frozen=True, slots=True)
class StoredCorrectionBranch:
    id: UUID
    workspace_id: UUID
    parent_task_id: UUID
    source_event_sequence: int
    child_task_id: UUID | None
    status: BranchStatus
    base_commit: str
    patch_sha256: str
    patch_bytes: int
    checkpoint_file_name: str
    created_at: datetime


class CorrectionBranchRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def reserve(
        self,
        branch_id: UUID,
        workspace_id: UUID,
        parent_task_id: UUID,
        source_event_sequence: int,
        base_commit: str,
        patch_sha256: str,
        patch_bytes: int,
        checkpoint_file_name: str,
    ) -> tuple[StoredCorrectionBranch, bool]:
        """原子预留唯一记录；返回值的 bool 指示是否拥有后续副作用。"""
        created_at = datetime.now(UTC)
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                cursor = await self._database.connection.execute(
                    """INSERT INTO correction_branches
                    (id, workspace_id, parent_task_id, source_event_sequence, child_task_id,
                     status, base_commit, patch_sha256, patch_bytes, checkpoint_file_name, created_at)
                    VALUES (?, ?, ?, ?, NULL, 'CREATING', ?, ?, ?, ?, ?)
                    ON CONFLICT(parent_task_id, source_event_sequence) DO NOTHING""",
                    (str(branch_id), str(workspace_id), str(parent_task_id), source_event_sequence,
                     base_commit, patch_sha256, patch_bytes, checkpoint_file_name, created_at.isoformat()),
                )
                owner = cursor.rowcount == 1
                row = await (await self._database.connection.execute(
                    """SELECT id, workspace_id, parent_task_id, source_event_sequence, child_task_id,
                    status, base_commit, patch_sha256, patch_bytes, checkpoint_file_name, created_at
                    FROM correction_branches WHERE parent_task_id = ? AND source_event_sequence = ?""",
                    (str(parent_task_id), source_event_sequence),
                )).fetchone()
                if row is None:
                    raise RuntimeError("纠正分支预留结果不确定")
                await self._database.connection.commit()
            except BaseException:
                await self._database.connection.rollback()
                raise
        return _from_row(row), owner

    async def get(self, branch_id: UUID) -> StoredCorrectionBranch | None:
        async with self._database.operation_lock:
            row = await (await self._database.connection.execute(
                """SELECT id, workspace_id, parent_task_id, source_event_sequence, child_task_id,
                status, base_commit, patch_sha256, patch_bytes, checkpoint_file_name, created_at
                FROM correction_branches WHERE id = ?""", (str(branch_id),)
            )).fetchone()
        return _from_row(row) if row is not None else None

    async def is_child_task(self, task_id: UUID) -> bool:
        async with self._database.operation_lock:
            row = await (await self._database.connection.execute(
                "SELECT 1 FROM correction_branches WHERE child_task_id = ?", (str(task_id),)
            )).fetchone()
        return row is not None

    async def mark_ready(self, branch_id: UUID, child_task_id: UUID) -> StoredCorrectionBranch:
        return await self._set_status(branch_id, "READY", child_task_id)

    async def mark_uncertain(self, branch_id: UUID) -> StoredCorrectionBranch:
        return await self._set_status(branch_id, "UNCERTAIN", None)

    async def _set_status(self, branch_id: UUID, status: BranchStatus, child_task_id: UUID | None) -> StoredCorrectionBranch:
        async with self._database.operation_lock:
            try:
                cursor = await self._database.connection.execute(
                    """UPDATE correction_branches SET status = ?, child_task_id = COALESCE(?, child_task_id)
                    WHERE id = ? RETURNING id, workspace_id, parent_task_id, source_event_sequence,
                    child_task_id, status, base_commit, patch_sha256, patch_bytes, checkpoint_file_name, created_at""",
                    (status, str(child_task_id) if child_task_id else None, str(branch_id)),
                )
                row = await cursor.fetchone()
                if row is None:
                    raise LookupError("纠正分支不存在")
                await self._database.connection.commit()
            except BaseException:
                await self._database.connection.rollback()
                raise
        return _from_row(row)


def _from_row(row: sqlite3.Row | tuple[object, ...]) -> StoredCorrectionBranch:
    status = str(row[5])
    if status not in {"CREATING", "READY", "UNCERTAIN"}:
        raise ValueError("纠正分支状态无效")
    return StoredCorrectionBranch(
        id=UUID(str(row[0])), workspace_id=UUID(str(row[1])), parent_task_id=UUID(str(row[2])),
        source_event_sequence=int(str(row[3])), child_task_id=UUID(str(row[4])) if row[4] is not None else None,
        status=cast(BranchStatus, status), base_commit=str(row[6]), patch_sha256=str(row[7]),
        patch_bytes=int(str(row[8])), checkpoint_file_name=str(row[9]),
        created_at=datetime.fromisoformat(str(row[10])),
    )
