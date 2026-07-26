"""确定性 TaskEvent 的一次性 SSE 编码。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.governance.redaction import Redactor

_MAX_EVENT_BYTES = 32 * 1024
_PRIVATE_FIELDS = frozenset({"state_root", "database_path", "session", "x-harness-session"})


async def task_events(store: EventStore, task_id: UUID, after: int, redactor: Redactor | None = None) -> AsyncIterator[bytes]:
    sanitizer = redactor or Redactor()
    for event in await store.list_for_task(task_id, after=after):
        transport = _hide_private(sanitizer.sanitize(event.model_dump(mode="json")).value)
        payload = json.dumps(
            transport, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if len(payload.encode("utf-8")) > _MAX_EVENT_BYTES:
            payload = json.dumps({"sequence": event.sequence, "payload": "[REDACTED: event exceeds safety limit]"}, separators=(",", ":"))
        yield f"id: {event.sequence}\nevent: task-event\ndata: {payload}\n\n".encode("utf-8")


def _hide_private(value: object) -> object:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.casefold() in _PRIVATE_FIELDS else _hide_private(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_hide_private(item) for item in value]
    return value
