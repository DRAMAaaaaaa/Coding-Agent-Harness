from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.storage.event_store import EventStore


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
