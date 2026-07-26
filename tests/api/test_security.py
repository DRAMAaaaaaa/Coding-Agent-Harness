from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tests.api.test_projects import _git_repo


async def test_error_redacts_secret_and_has_stable_shape(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/tasks/not-a-uuid/events?after=-1")
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"code", "message", "details", "event_id"}


async def test_framework_404_and_405_use_stable_error_shape(client: httpx.AsyncClient) -> None:
    for response in (await client.get("/api/not-found"), await client.get("/api/projects")):
        assert set(response.json()) == {"code", "message", "details", "event_id"}


async def test_unknown_host_cannot_bootstrap_or_mutate(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe_bootstrap = await client.get("/")
    token = safe_bootstrap.headers["x-harness-session"]
    calls = 0

    def record_business_call(_: Path) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("未知 Host 不得调用业务依赖")

    dependencies = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    monkeypatch.setattr(dependencies.detector, "detect", record_business_call)
    project = _git_repo(tmp_path / "evil-host-project")

    bootstrap = await client.get("/", headers={"Host": "evil.example"})
    mutation = await client.post(
        "/api/projects",
        json={"path": str(project)},
        headers={
            "Host": "evil.example",
            "Origin": "http://evil.example",
            "X-Harness-Session": token,
        },
    )

    assert bootstrap.status_code == 403
    assert "x-harness-session" not in bootstrap.headers
    assert mutation.status_code == 403
    assert calls == 0


async def test_bootstrap_is_not_cacheable(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("origin", "token"),
    [
        ("http://evil.example", None),
        ("http://testserver", "wrong-session-token"),
    ],
)
async def test_mutation_requires_configured_origin_and_exact_session(
    client: httpx.AsyncClient,
    origin: str,
    token: str | None,
) -> None:
    bootstrap = await client.get("/")
    headers = {
        "Origin": origin,
        "X-Harness-Session": token or bootstrap.headers["x-harness-session"],
    }

    response = await client.post("/api/projects", json={"path": "x"}, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "SESSION_REQUIRED"
