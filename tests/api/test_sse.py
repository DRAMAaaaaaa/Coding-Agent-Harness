from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.api.sse import task_events


async def test_sse_streams_only_events_after_sequence(client: httpx.AsyncClient) -> None:
    from tests.api.conftest import session_headers
    from tests.api.test_projects import _git_repo

    headers = await session_headers(client)
    root = _git_repo(client._transport.app.state.dependencies.state_root.parent / "repo")  # type: ignore[attr-defined]
    project = await client.post("/api/projects", json={"path": str(root)}, headers=headers)
    trusted = await client.post(
        f"/api/projects/{project.json()['id']}/trust",
        json={"fingerprint": project.json()["trust_fingerprint"]}, headers=headers,
    )
    task = await client.post("/api/tasks", json={"workspace_id": trusted.json()["id"], "requirement": "测试"}, headers=headers)
    store: EventStore = client._transport.app.state.event_store  # type: ignore[attr-defined]
    task_id = UUID(task.json()["id"])
    existing = await store.list_for_task(task_id)
    event = await store.append(
        TaskEvent(
            task_id=task_id,
            sequence=0,
            event_type="USER_INPUT_REQUIRED",
                payload={"reason_code": "TEST", "token": "test-only-canary"},
            state_before=TaskState.WAITING_PLAN_APPROVAL,
            state_after=TaskState.WAITING_USER,
            occurred_at=datetime.now(UTC),
        ),
        expected_sequence=len(existing),
    )
    response = await client.get(f"/api/tasks/{task_id}/events?after={len(existing)}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert f"id: {event.sequence}" in response.text
    assert "event: task-event" in response.text
    assert "test-only-canary" not in response.text
    assert "[REDACTED]" in response.text
    resumed = await client.get(f"/api/tasks/{task_id}/events?after={event.sequence}")
    assert resumed.status_code == 200
    assert resumed.text == ""


async def test_sse_consumes_event_history_in_multiple_bounded_batches() -> None:
    task_id = UUID("00000000-0000-0000-0000-000000000007")
    events = tuple(
        TaskEvent(
            task_id=task_id,
            sequence=sequence,
            event_type="BATCH_TEST",
            payload={"index": sequence},
            state_before=TaskState.CREATED,
            state_after=TaskState.SCANNING,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        for sequence in range(1, 206)
    )
    reader = _BatchOnlyEventReader(events)

    chunks = [chunk async for chunk in task_events(reader, task_id, after=0)]  # type: ignore[arg-type]

    sequences = [
        int(chunk.split(b"\n", 1)[0].removeprefix(b"id: "))
        for chunk in chunks
    ]
    assert len(sequences) == 205
    assert sequences[0] == 1
    assert sequences[-1] == 205


async def test_sse_oversize_event_preserves_complete_envelope() -> None:
    import json

    task_id = UUID("00000000-0000-0000-0000-000000000008")
    event = TaskEvent(
        task_id=task_id,
        sequence=9,
        event_type="OVERSIZE_TEST",
        payload={"content": "大" * 20_000},
        state_before=TaskState.EXECUTING,
        state_after=TaskState.WAITING_USER,
        occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    reader = _StaticEventReader((event,))

    [chunk] = [chunk async for chunk in task_events(reader, task_id, after=0)]  # type: ignore[arg-type]
    data = json.loads(chunk.decode("utf-8").split("data: ", 1)[1])

    assert data == {
        "event_type": "OVERSIZE_TEST",
        "occurred_at": "2026-01-02T03:04:05Z",
        "payload": {"redacted": "[REDACTED: event exceeds safety limit]"},
        "sequence": 9,
        "state_after": "WAITING_USER",
        "state_before": "EXECUTING",
        "task_id": str(task_id),
    }


async def test_following_sse_keeps_connection_open_until_client_disconnects() -> None:
    task_id = UUID("00000000-0000-0000-0000-000000000009")
    reader = _StaticEventReader(())
    checks = 0

    async def disconnected() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    chunks = [
        chunk
        async for chunk in task_events(
            reader,
            task_id,
            after=0,
            follow=True,
            is_disconnected=disconnected,
            poll_interval=0,
        )
    ]

    assert chunks == [b": keep-alive\n\n"]


class _StaticEventReader:
    def __init__(self, events: tuple[TaskEvent, ...]) -> None:
        self._events = events

    async def list_for_task(self, task_id: UUID, after: int = 0) -> list[TaskEvent]:
        return [
            event
            for event in self._events
            if event.task_id == task_id and event.sequence > after
        ]

    async def list_batch_for_task(
        self,
        task_id: UUID,
        after: int = 0,
        limit: int = 100,
    ) -> list[TaskEvent]:
        return (await self.list_for_task(task_id, after=after))[:limit]


class _BatchOnlyEventReader(_StaticEventReader):
    async def list_for_task(self, task_id: UUID, after: int = 0) -> list[TaskEvent]:
        raise AssertionError("SSE 不得无界读取事件历史")

    async def list_batch_for_task(
        self,
        task_id: UUID,
        after: int = 0,
        limit: int = 100,
    ) -> list[TaskEvent]:
        matches = [
            event
            for event in self._events
            if event.task_id == task_id and event.sequence > after
        ]
        return matches[:limit]
