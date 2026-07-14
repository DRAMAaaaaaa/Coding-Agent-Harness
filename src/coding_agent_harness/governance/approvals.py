import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.storage.database import Database


_APPROVAL_COLUMNS = """
    id, task_id, action_id, reason_code, event_sequence,
    normalized_scope, task_state, config_version, decision,
    decided_by, expires_at, created_at, decided_at, consumed_at
"""
_ERROR_MESSAGES = {
    "NOT_FOUND": "审批不存在",
    "EXPIRED": "审批已过期",
    "REPLAYED": "审批已被消费",
    "NOT_APPROVED": "审批尚未批准",
    "DENIED": "审批已被拒绝",
    "STALE_ACTION": "审批动作已变化",
    "STALE_EVENT": "审批事件序号已变化",
    "STALE_SCOPE": "审批范围已变化",
    "STALE_STATE": "审批任务状态已变化",
    "STALE_CONFIG": "审批配置版本已变化",
    "TASK_CANCELLED": "任务已取消",
    "DUPLICATE": "审批目标已存在",
    "BUSY": "审批存储正忙",
}


class ApprovalDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class ApprovalContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_id: str
    event_sequence: int
    normalized_scope: str
    task_state: TaskState
    config_version: str


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    task_id: UUID
    action_id: str
    reason_code: str
    event_sequence: int
    normalized_scope: str
    task_state: TaskState
    config_version: str
    decision: ApprovalDecision
    decided_by: str | None
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None
    consumed_at: datetime | None


class ApprovalError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(_ERROR_MESSAGES[reason_code])


class ApprovalManager:
    def __init__(
        self,
        database: Database,
        clock: Callable[[], datetime],
        uuid_factory: Callable[[], UUID],
    ) -> None:
        self._database = database
        self._clock = clock
        self._uuid_factory = uuid_factory

    async def request(
        self,
        task_id: UUID,
        reason_code: str,
        context: ApprovalContext,
        expires_at: datetime,
    ) -> ApprovalRecord:
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                now = self._utc_now()
                expiration = _require_aware(expires_at)
                if expiration <= now:
                    raise ApprovalError("EXPIRED")
                if context.task_state is TaskState.CANCELLED:
                    raise ApprovalError("TASK_CANCELLED")
                await self._ensure_task_active(task_id)
                record = ApprovalRecord(
                    id=self._uuid_factory(),
                    task_id=task_id,
                    action_id=context.action_id,
                    reason_code=reason_code,
                    event_sequence=context.event_sequence,
                    normalized_scope=context.normalized_scope,
                    task_state=context.task_state,
                    config_version=context.config_version,
                    decision=ApprovalDecision.PENDING,
                    decided_by=None,
                    expires_at=expiration,
                    created_at=now,
                    decided_at=None,
                    consumed_at=None,
                )
                await self._database.connection.execute(
                    """
                    INSERT INTO approvals (
                        id, task_id, action_id, reason_code, event_sequence,
                        normalized_scope, task_state, config_version, decision,
                        decided_by, expires_at, created_at, decided_at, consumed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _record_parameters(record),
                )
                await self._database.connection.commit()
            except BaseException as error:
                await self._database.connection.rollback()
                self._raise_stable_write_error(error)
        return record

    async def decide(
        self,
        approval_id: UUID,
        decision: ApprovalDecision,
        actor: str,
        context: ApprovalContext,
    ) -> ApprovalRecord:
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                if decision not in {ApprovalDecision.APPROVED, ApprovalDecision.DENIED}:
                    raise ValueError("审批决定必须是 APPROVED 或 DENIED")
                now = self._utc_now()
                record = await self._load(approval_id)
                await self._ensure_task_active(record.task_id)
                self._validate_live(record, context, now)
                if record.decision is ApprovalDecision.DENIED:
                    raise ApprovalError("DENIED")
                if record.decision is not ApprovalDecision.PENDING:
                    raise ApprovalError("NOT_APPROVED")
                await self._database.connection.execute(
                    """
                    UPDATE approvals
                    SET decision = ?, decided_by = ?, decided_at = ?
                    WHERE id = ?
                    """,
                    (decision.value, actor, now.isoformat(), str(approval_id)),
                )
                await self._database.connection.commit()
            except BaseException as error:
                await self._database.connection.rollback()
                self._raise_stable_write_error(error)
        return record.model_copy(
            update={
                "decision": decision,
                "decided_by": actor,
                "decided_at": now,
            }
        )

    async def consume(
        self,
        approval_id: UUID,
        context: ApprovalContext,
    ) -> ApprovalRecord:
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                now = self._utc_now()
                record = await self._load(approval_id)
                await self._ensure_task_active(record.task_id)
                self._validate_live(record, context, now)
                if record.decision is ApprovalDecision.DENIED:
                    raise ApprovalError("DENIED")
                if record.decision is not ApprovalDecision.APPROVED:
                    raise ApprovalError("NOT_APPROVED")
                await self._database.connection.execute(
                    "UPDATE approvals SET consumed_at = ? WHERE id = ?",
                    (now.isoformat(), str(approval_id)),
                )
                await self._database.connection.commit()
            except BaseException as error:
                await self._database.connection.rollback()
                self._raise_stable_write_error(error)
        return record.model_copy(update={"consumed_at": now})

    async def _load(self, approval_id: UUID) -> ApprovalRecord:
        cursor = await self._database.connection.execute(
            f"SELECT {_APPROVAL_COLUMNS} FROM approvals WHERE id = ?",
            (str(approval_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ApprovalError("NOT_FOUND")
        return _record_from_row(row)

    async def _ensure_task_active(self, task_id: UUID) -> None:
        cursor = await self._database.connection.execute(
            "SELECT state FROM tasks WHERE id = ?",
            (str(task_id),),
        )
        row = await cursor.fetchone()
        if row is not None and str(row[0]) == TaskState.CANCELLED.value:
            raise ApprovalError("TASK_CANCELLED")

    @staticmethod
    def _validate_live(
        record: ApprovalRecord,
        context: ApprovalContext,
        now: datetime,
    ) -> None:
        if record.consumed_at is not None:
            raise ApprovalError("REPLAYED")
        if record.expires_at <= now:
            raise ApprovalError("EXPIRED")
        mismatches = (
            (record.action_id != context.action_id, "STALE_ACTION"),
            (record.event_sequence != context.event_sequence, "STALE_EVENT"),
            (record.normalized_scope != context.normalized_scope, "STALE_SCOPE"),
            (record.task_state is not context.task_state, "STALE_STATE"),
            (record.config_version != context.config_version, "STALE_CONFIG"),
        )
        for mismatched, reason_code in mismatches:
            if mismatched:
                raise ApprovalError(reason_code)
        if context.task_state is TaskState.CANCELLED:
            raise ApprovalError("TASK_CANCELLED")

    def _utc_now(self) -> datetime:
        return _require_aware(self._clock())

    @staticmethod
    def _raise_stable_write_error(error: BaseException) -> None:
        if isinstance(error, ApprovalError):
            raise error
        if isinstance(error, sqlite3.OperationalError) and _is_lock_contention(error):
            raise ApprovalError("BUSY") from None
        if isinstance(error, sqlite3.IntegrityError) and _is_unique_violation(error):
            raise ApprovalError("DUPLICATE") from None
        raise error


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return value.astimezone(UTC)


def _record_parameters(record: ApprovalRecord) -> tuple[object, ...]:
    return (
        str(record.id),
        str(record.task_id),
        record.action_id,
        record.reason_code,
        record.event_sequence,
        record.normalized_scope,
        record.task_state.value,
        record.config_version,
        record.decision.value,
        record.decided_by,
        record.expires_at.isoformat(),
        record.created_at.isoformat(),
        record.decided_at.isoformat() if record.decided_at else None,
        record.consumed_at.isoformat() if record.consumed_at else None,
    )


def _record_from_row(row: sqlite3.Row) -> ApprovalRecord:
    return ApprovalRecord(
        id=UUID(str(row[0])),
        task_id=UUID(str(row[1])),
        action_id=str(row[2]),
        reason_code=str(row[3]),
        event_sequence=int(str(row[4])),
        normalized_scope=str(row[5]),
        task_state=TaskState(str(row[6])),
        config_version=str(row[7]),
        decision=ApprovalDecision(str(row[8])),
        decided_by=str(row[9]) if row[9] is not None else None,
        expires_at=datetime.fromisoformat(str(row[10])),
        created_at=datetime.fromisoformat(str(row[11])),
        decided_at=datetime.fromisoformat(str(row[12])) if row[12] is not None else None,
        consumed_at=(
            datetime.fromisoformat(str(row[13])) if row[13] is not None else None
        ),
    )


def _is_lock_contention(error: sqlite3.OperationalError) -> bool:
    error_code = getattr(error, "sqlite_errorcode", None)
    if not isinstance(error_code, int):
        return False
    return error_code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}


def _is_unique_violation(error: sqlite3.IntegrityError) -> bool:
    error_code = getattr(error, "sqlite_errorcode", None)
    return error_code in {
        sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY,
        sqlite3.SQLITE_CONSTRAINT_UNIQUE,
    }
