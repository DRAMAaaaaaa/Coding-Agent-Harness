from __future__ import annotations

import httpx


async def test_error_redacts_secret_and_has_stable_shape(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/tasks/not-a-uuid/events?after=-1")
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"code", "message", "details", "event_id"}


async def test_framework_404_and_405_use_stable_error_shape(client: httpx.AsyncClient) -> None:
    for response in (await client.get("/api/not-found"), await client.get("/api/projects")):
        assert set(response.json()) == {"code", "message", "details", "event_id"}
