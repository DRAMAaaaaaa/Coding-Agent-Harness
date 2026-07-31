"""确定性 TaskEvent 的一次性 SSE 编码。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol
from uuid import UUID

from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.storage.event_store import MAX_EVENT_BATCH_SIZE
from coding_agent_harness.governance.redaction import Redactor

_MAX_EVENT_BYTES = 32 * 1024
_PRIVATE_FIELDS = frozenset({"state_root", "database_path", "session", "x-harness-session"})


class EventBatchReader(Protocol):
    async def list_batch_for_task(
        self,
        task_id: UUID,
        after: int = 0,
        limit: int = MAX_EVENT_BATCH_SIZE,
    ) -> list[TaskEvent]: ...


async def task_events(
    store: EventBatchReader,
    task_id: UUID,
    after: int,
    redactor: Redactor | None = None,
    *,
    follow: bool = False,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    poll_interval: float = 1.0,
    heartbeat_interval: float = 15.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> AsyncIterator[bytes]:
    sanitizer = redactor or Redactor()
    cursor = after
    last_heartbeat = monotonic()
    while True:
        if follow and is_disconnected is not None and await is_disconnected():
            return
        batch = await store.list_batch_for_task(
            task_id,
            after=cursor,
            limit=MAX_EVENT_BATCH_SIZE,
        )
        if not batch:
            if not follow:
                return
            now = monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                yield b": keep-alive\n\n"
                last_heartbeat = now
            await sleep(poll_interval)
            continue
        for event in batch:
            payload = _encode_event(event, sanitizer)
            yield f"id: {event.sequence}\nevent: task-event\ndata: {payload}\n\n".encode(
                "utf-8"
            )
        cursor = batch[-1].sequence
        if follow and is_disconnected is not None and await is_disconnected():
            return
        if not follow and len(batch) < MAX_EVENT_BATCH_SIZE:
            return


def _encode_event(event: TaskEvent, sanitizer: Redactor) -> str:
    transport = _hide_private(
        sanitizer.sanitize(event.model_dump(mode="json")).value
    )
    if not isinstance(transport, dict):
        raise TypeError("事件传输信封无效")
    payload = json.dumps(
        transport,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(payload.encode("utf-8")) > _MAX_EVENT_BYTES:
        transport = {
            **transport,
            "payload": {
                "redacted": "[REDACTED: event exceeds safety limit]",
            },
        }
        payload = json.dumps(
            transport,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return payload


def _hide_private(value: object) -> object:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.casefold() in _PRIVATE_FIELDS else _hide_private(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_hide_private(item) for item in value]
    return value
