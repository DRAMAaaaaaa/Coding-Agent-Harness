from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from conftest import session_headers


@pytest.mark.asyncio
async def test_session_credential_is_configured_without_returning_secret(
    client: httpx.AsyncClient,
) -> None:
    headers = await session_headers(client)

    created = await client.post(
        "/api/providers", json={"kind": "deepseek", "model": "deepseek-chat"}, headers=headers
    )
    profile_id = UUID(created.json()["id"])
    configured = await client.put(
        f"/api/providers/{profile_id}/session-credential",
        json={"api_key": "test-session-provider-key"},
        headers=headers,
    )
    listed = await client.get("/api/providers")

    assert created.status_code == 201
    assert created.json() == {
        "id": str(profile_id), "kind": "deepseek", "model": "deepseek-chat", "version": 1, "configured": False,
    }
    assert configured.status_code == 200
    assert configured.json()["configured"] is True
    assert "test-session-provider-key" not in str(configured.json())
    assert listed.json()[0]["configured"] is True


@pytest.mark.asyncio
async def test_session_credential_rejects_nul_and_oversized_key(client: httpx.AsyncClient) -> None:
    headers = await session_headers(client)
    created = await client.post(
        "/api/providers", json={"kind": "qwen", "model": "qwen-plus"}, headers=headers
    )

    response = await client.put(
        f"/api/providers/{created.json()['id']}/session-credential",
        json={"api_key": "x" * 193}, headers=headers,
    )

    assert response.status_code == 422
    assert "x" * 193 not in str(response.json())
