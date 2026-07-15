import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field

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
    "INVALID_CONTEXT": "审批上下文无效",
    "INVALID_DECISION": "审批决定无效",
    "INVALID_TIME": "审批时间无效",
    "INVALID_MUTATION": "审批数据库变更无效",
    "STORAGE_ERROR": "审批存储失败",
}
_MAX_ACTION_ID_LENGTH = 256
_MAX_SCOPE_LENGTH = 8_192
_MAX_CONFIG_VERSION_LENGTH = 128
_MAX_REASON_CODE_LENGTH = 128
_MAX_ACTOR_LENGTH = 256
_MAX_EVENT_SEQUENCE = 2**63 - 1
_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROTECTED_MUTATION_TABLES = frozenset({"approvals", "tasks", "task_events"})


class ApprovalDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class ApprovalMutationOperation(StrEnum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"


class ApprovalMutationBinding(StrEnum):
    APPROVAL_ID = "APPROVAL_ID"
    TASK_ID = "TASK_ID"
    CREATED_AT = "CREATED_AT"
    CONSUMED_AT = "CONSUMED_AT"


@dataclass(frozen=True)
class ApprovalDatabaseMutation:
    operation: ApprovalMutationOperation
    table: str
    values: tuple[tuple[str, object], ...]
    where: tuple[tuple[str, object], ...] = ()

    async def __call__(
        self,
        connection: aiosqlite.Connection,
        context: object,
    ) -> None:
        del connection, context
        raise ApprovalError("INVALID_MUTATION")


class ApprovalContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_id: str = Field(min_length=1, max_length=_MAX_ACTION_ID_LENGTH)
    event_sequence: int = Field(ge=0, le=_MAX_EVENT_SEQUENCE)
    normalized_scope: str = Field(min_length=1, max_length=_MAX_SCOPE_LENGTH)
    task_state: TaskState
    config_version: str = Field(min_length=1, max_length=_MAX_CONFIG_VERSION_LENGTH)


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


@dataclass(frozen=True)
class _TaskAuthority:
    state: TaskState
    config_version: str
    event_sequence: int


@dataclass(frozen=True)
class _MutationContext:
    approval_id: UUID
    task_id: UUID
    created_at: datetime
    consumed_at: datetime | None


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
        return await self._request_with_mutation(
            task_id, reason_code, context, expires_at, None
        )

    async def request_and_apply(
        self,
        task_id: UUID,
        reason_code: str,
        context: ApprovalContext,
        expires_at: datetime,
        apply: Callable[
            [aiosqlite.Connection, ApprovalRecord], Awaitable[None]
        ],
    ) -> ApprovalRecord:
        mutation = _require_mutation(apply, ApprovalMutationOperation.INSERT)
        return await self._request_with_mutation(
            task_id, reason_code, context, expires_at, mutation
        )

    async def _request_with_mutation(
        self,
        task_id: UUID,
        reason_code: str,
        context: ApprovalContext,
        expires_at: datetime,
        mutation: ApprovalDatabaseMutation | None,
    ) -> ApprovalRecord:
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                self._validate_request(reason_code, context)
                now = self._utc_now()
                expiration = _require_aware(expires_at)
                if expiration <= now:
                    raise ApprovalError("EXPIRED")
                authority = await self._load_task_authority(task_id)
                self._validate_authority(context, authority)
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
                if mutation is not None:
                    await _execute_mutation(
                        self._database.connection,
                        mutation,
                        _MutationContext(
                            approval_id=record.id,
                            task_id=record.task_id,
                            created_at=record.created_at,
                            consumed_at=None,
                        ),
                    )
                await self._database.connection.commit()
            except Exception as error:
                await self._database.connection.rollback()
                self._raise_stable_write_error(error)
            except BaseException:
                await self._database.connection.rollback()
                raise
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
                self._validate_context(context)
                if (
                    not isinstance(decision, ApprovalDecision)
                    or decision not in {ApprovalDecision.APPROVED, ApprovalDecision.DENIED}
                    or not actor
                    or len(actor) > _MAX_ACTOR_LENGTH
                ):
                    raise ApprovalError("INVALID_DECISION")
                now = self._utc_now()
                record = await self._load(approval_id)
                authority = await self._load_task_authority(record.task_id)
                self._validate_authority(record, authority)
                self._validate_live(record, context, now)
                if record.decision is ApprovalDecision.DENIED:
                    raise ApprovalError("DENIED")
                if record.decision is not ApprovalDecision.PENDING:
                    raise ApprovalError("NOT_APPROVED")
                cursor = await self._database.connection.execute(
                    """
                    UPDATE approvals
                    SET decision = ?, decided_by = ?, decided_at = ?
                    WHERE id = ? AND decision = 'PENDING'
                    """,
                    (decision.value, actor, now.isoformat(), str(approval_id)),
                )
                if cursor.rowcount != 1:
                    current = await self._load(approval_id)
                    if current.decision is ApprovalDecision.DENIED:
                        raise ApprovalError("DENIED")
                    raise ApprovalError("NOT_APPROVED")
                await self._database.connection.commit()
            except Exception as error:
                await self._database.connection.rollback()
                self._raise_stable_write_error(error)
            except BaseException:
                await self._database.connection.rollback()
                raise
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
        return await self._consume_with_mutation(approval_id, context, None)

    async def consume_and_apply(
        self,
        approval_id: UUID,
        context: ApprovalContext,
        apply: Callable[[aiosqlite.Connection, datetime], Awaitable[None]],
    ) -> ApprovalRecord:
        mutation = _require_mutation(apply, ApprovalMutationOperation.UPDATE)
        return await self._consume_with_mutation(approval_id, context, mutation)

    async def _consume_with_mutation(
        self,
        approval_id: UUID,
        context: ApprovalContext,
        mutation: ApprovalDatabaseMutation | None,
    ) -> ApprovalRecord:
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                self._validate_context(context)
                now = self._utc_now()
                record = await self._load(approval_id)
                authority = await self._load_task_authority(record.task_id)
                self._validate_authority(record, authority)
                self._validate_live(record, context, now)
                if record.decision is ApprovalDecision.DENIED:
                    raise ApprovalError("DENIED")
                if record.decision is not ApprovalDecision.APPROVED:
                    raise ApprovalError("NOT_APPROVED")
                cursor = await self._database.connection.execute(
                    """
                    UPDATE approvals
                    SET consumed_at = ?
                    WHERE id = ?
                      AND decision = 'APPROVED'
                      AND consumed_at IS NULL
                      AND expires_at > ?
                      AND action_id = ?
                      AND event_sequence = ?
                      AND normalized_scope = ?
                      AND task_state = ?
                      AND config_version = ?
                    """,
                    (
                        now.isoformat(),
                        str(approval_id),
                        now.isoformat(),
                        context.action_id,
                        context.event_sequence,
                        context.normalized_scope,
                        context.task_state.value,
                        context.config_version,
                    ),
                )
                if cursor.rowcount != 1:
                    current = await self._load(approval_id)
                    self._validate_live(current, context, now)
                    if current.decision is ApprovalDecision.DENIED:
                        raise ApprovalError("DENIED")
                    if current.decision is not ApprovalDecision.APPROVED:
                        raise ApprovalError("NOT_APPROVED")
                    raise ApprovalError("REPLAYED")
                if mutation is not None:
                    await _execute_mutation(
                        self._database.connection,
                        mutation,
                        _MutationContext(
                            approval_id=record.id,
                            task_id=record.task_id,
                            created_at=record.created_at,
                            consumed_at=now,
                        ),
                    )
                await self._database.connection.commit()
            except Exception as error:
                await self._database.connection.rollback()
                self._raise_stable_write_error(error)
            except BaseException:
                await self._database.connection.rollback()
                raise
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

    async def _load_task_authority(self, task_id: UUID) -> _TaskAuthority:
        cursor = await self._database.connection.execute(
            """
            SELECT tasks.state, tasks.config_version,
                   COALESCE(MAX(task_events.sequence), 0)
            FROM tasks
            LEFT JOIN task_events ON task_events.task_id = tasks.id
            WHERE tasks.id = ?
            GROUP BY tasks.id, tasks.state, tasks.config_version
            """,
            (str(task_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ApprovalError("NOT_FOUND")
        if str(row[0]) == TaskState.CANCELLED.value:
            raise ApprovalError("TASK_CANCELLED")
        return _TaskAuthority(
            state=TaskState(str(row[0])),
            config_version=str(row[1]),
            event_sequence=int(str(row[2])),
        )

    @staticmethod
    def _validate_authority(
        context: ApprovalContext | ApprovalRecord,
        authority: _TaskAuthority,
    ) -> None:
        mismatches = (
            (context.event_sequence != authority.event_sequence, "STALE_EVENT"),
            (context.task_state is not authority.state, "STALE_STATE"),
            (context.config_version != authority.config_version, "STALE_CONFIG"),
        )
        for mismatched, reason_code in mismatches:
            if mismatched:
                raise ApprovalError(reason_code)

    @staticmethod
    def _validate_request(reason_code: str, context: ApprovalContext) -> None:
        ApprovalManager._validate_context(context)
        if not reason_code or len(reason_code) > _MAX_REASON_CODE_LENGTH:
            raise ApprovalError("INVALID_CONTEXT")

    @staticmethod
    def _validate_context(context: ApprovalContext) -> None:
        valid = (
            0 < len(context.action_id) <= _MAX_ACTION_ID_LENGTH
            and 0 <= context.event_sequence <= _MAX_EVENT_SEQUENCE
            and 0 < len(context.normalized_scope) <= _MAX_SCOPE_LENGTH
            and 0 < len(context.config_version) <= _MAX_CONFIG_VERSION_LENGTH
            and isinstance(context.task_state, TaskState)
        )
        if not valid:
            raise ApprovalError("INVALID_CONTEXT")

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
    def _raise_stable_write_error(error: Exception) -> None:
        if isinstance(error, ApprovalError):
            raise error from None
        if isinstance(error, sqlite3.OperationalError) and _is_lock_contention(error):
            raise ApprovalError("BUSY") from None
        if isinstance(error, sqlite3.IntegrityError) and _is_unique_violation(error):
            raise ApprovalError("DUPLICATE") from None
        if isinstance(error, (sqlite3.Error, ValueError, TypeError)):
            raise ApprovalError("STORAGE_ERROR") from None
        raise error


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApprovalError("INVALID_TIME")
    return value.astimezone(UTC)


def _require_mutation(
    candidate: object,
    expected_operation: ApprovalMutationOperation,
) -> ApprovalDatabaseMutation:
    if type(candidate) is not ApprovalDatabaseMutation:
        raise ApprovalError("INVALID_MUTATION")
    mutation = candidate
    if mutation.operation is not expected_operation:
        raise ApprovalError("INVALID_MUTATION")
    if (
        type(mutation.table) is not str
        or _SQL_IDENTIFIER.fullmatch(mutation.table) is None
        or mutation.table.casefold() in _PROTECTED_MUTATION_TABLES
    ):
        raise ApprovalError("INVALID_MUTATION")
    values = _validate_mutation_pairs(mutation.values, require_values=True)
    where = _validate_mutation_pairs(mutation.where, require_values=False)
    required_bindings = {
        ApprovalMutationBinding.APPROVAL_ID,
        ApprovalMutationBinding.TASK_ID,
    }
    if mutation.operation is ApprovalMutationOperation.INSERT:
        value_bindings = {
            value for _, value in values if type(value) is ApprovalMutationBinding
        }
        if where or not required_bindings.issubset(value_bindings):
            raise ApprovalError("INVALID_MUTATION")
    else:
        where_bindings = {
            value for _, value in where if type(value) is ApprovalMutationBinding
        }
        if not where or not required_bindings.issubset(where_bindings):
            raise ApprovalError("INVALID_MUTATION")
    return mutation


def _validate_mutation_pairs(
    pairs: object,
    *,
    require_values: bool,
) -> tuple[tuple[str, object], ...]:
    if type(pairs) is not tuple or (require_values and not pairs):
        raise ApprovalError("INVALID_MUTATION")
    validated = cast(tuple[object, ...], pairs)
    columns: set[str] = set()
    for pair in validated:
        if type(pair) is not tuple or len(pair) != 2:
            raise ApprovalError("INVALID_MUTATION")
        column, value = cast(tuple[object, object], pair)
        if (
            type(column) is not str
            or _SQL_IDENTIFIER.fullmatch(column) is None
            or column.casefold() in columns
            or not _valid_mutation_value(value)
        ):
            raise ApprovalError("INVALID_MUTATION")
        columns.add(column.casefold())
    return cast(tuple[tuple[str, object], ...], validated)


def _valid_mutation_value(value: object) -> bool:
    return type(value) in {str, int, float, bytes, type(None)} or type(
        value
    ) is ApprovalMutationBinding


async def _execute_mutation(
    connection: aiosqlite.Connection,
    mutation: ApprovalDatabaseMutation,
    context: _MutationContext,
) -> None:
    columns = ", ".join(_quote_identifier(column) for column, _ in mutation.values)
    values = tuple(_resolve_mutation_value(value, context) for _, value in mutation.values)
    if mutation.operation is ApprovalMutationOperation.INSERT:
        placeholders = ", ".join("?" for _ in values)
        statement = (
            f"INSERT INTO {_quote_identifier(mutation.table)} "
            f"({columns}) VALUES ({placeholders})"
        )
        await connection.execute(statement, values)
        return
    assignments = ", ".join(
        f"{_quote_identifier(column)} = ?" for column, _ in mutation.values
    )
    predicates = " AND ".join(
        f"{_quote_identifier(column)} = ?" for column, _ in mutation.where
    )
    where_values = tuple(
        _resolve_mutation_value(value, context) for _, value in mutation.where
    )
    cursor = await connection.execute(
        f"UPDATE {_quote_identifier(mutation.table)} SET {assignments} WHERE {predicates}",
        values + where_values,
    )
    if cursor.rowcount != 1:
        raise ApprovalError("INVALID_MUTATION")


def _resolve_mutation_value(value: object, context: _MutationContext) -> object:
    if type(value) is not ApprovalMutationBinding:
        return value
    bindings: dict[ApprovalMutationBinding, object] = {
        ApprovalMutationBinding.APPROVAL_ID: str(context.approval_id),
        ApprovalMutationBinding.TASK_ID: str(context.task_id),
        ApprovalMutationBinding.CREATED_AT: context.created_at.isoformat(),
    }
    if context.consumed_at is not None:
        bindings[ApprovalMutationBinding.CONSUMED_AT] = context.consumed_at.isoformat()
    try:
        return bindings[value]
    except KeyError:
        raise ApprovalError("INVALID_MUTATION") from None


def _quote_identifier(value: str) -> str:
    return f'"{value}"'


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
