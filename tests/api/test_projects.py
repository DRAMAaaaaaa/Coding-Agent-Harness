from __future__ import annotations

import subprocess
from pathlib import Path

import httpx
import pytest

from coding_agent_harness.api.app import create_app
from coding_agent_harness.api.dependencies import DefaultBranchError
from coding_agent_harness.config import HarnessSettings
from coding_agent_harness.workspace.detector import ProjectDetectionError
from coding_agent_harness.workspace.scanner import RepositoryScanError
from tests.api.conftest import session_headers


def _git_repo(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "pyproject.toml").write_text("[build-system]\nrequires=[]\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


async def test_project_requires_git_and_hides_host_paths(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    non_git = tmp_path / "not-git"
    non_git.mkdir()
    headers = await session_headers(client)
    rejected = await client.post("/api/projects", json={"path": str(non_git)}, headers=headers)
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "INVALID_PROJECT"

    project = _git_repo(tmp_path / "project")
    response = await client.post("/api/projects", json={"path": str(project)}, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["trust_fingerprint"]
    assert str(project) not in response.text
    assert "state_root" not in body


async def test_project_rejects_sensitive_detected_profile_without_persisting_canary(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    project = _git_repo(tmp_path / "sensitive-profile")
    canary = "profile-" + project.name
    (project / ".harness.yml").write_text(
        f"test: [python, -m, pytest, token={canary}]\n",
        encoding="utf-8",
    )
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]

    response = await client.post(
        "/api/projects",
        json={"path": str(project)},
        headers=await session_headers(client),
    )

    row = await (
        await active.workspaces._database.connection.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*), COALESCE(group_concat(profile_json), '') FROM workspaces"
        )
    ).fetchone()
    assert response.status_code == 409
    assert response.json()["code"] == "WORKSPACE_CONFLICT"
    assert canary not in response.text
    assert row == (0, "")


async def test_trust_requires_current_exact_fingerprint(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    project = _git_repo(tmp_path / "project")
    headers = await session_headers(client)
    created = await client.post("/api/projects", json={"path": str(project)}, headers=headers)
    stale = await client.post(
        f"/api/projects/{created.json()['id']}/trust",
        json={"fingerprint": "0" * 64},
        headers=headers,
    )
    assert stale.status_code == 409
    trusted = await client.post(
        f"/api/projects/{created.json()['id']}/trust",
        json={"fingerprint": created.json()["trust_fingerprint"]},
        headers=headers,
    )
    assert trusted.status_code == 200
    assert trusted.json()["trusted"] is True
    repeated = await client.post(
        f"/api/projects/{created.json()['id']}/trust",
        json={"fingerprint": created.json()["trust_fingerprint"]}, headers=headers,
    )
    assert repeated.status_code == 409


async def test_project_response_has_bounded_repository_summary(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    project = _git_repo(tmp_path / "summary")
    (project / "tests").mkdir()
    (project / "tests" / "test_a.py").write_text("pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=project, check=True)
    subprocess.run(["git", "commit", "-m", "Bearer commit-canary"], cwd=project, check=True, capture_output=True)
    response = await client.post("/api/projects", json={"path": str(project)}, headers=await session_headers(client))
    summary = response.json()["repository"]
    assert summary["tracked_count"] >= 2
    assert "tests/test_a.py" in summary["test_paths"]
    assert "pass" not in response.text
    assert "commit-canary" not in response.text
    assert "[REDACTED]" in response.text


async def test_mutations_require_same_origin_and_session(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/projects", json={"path": "x"})
    assert response.status_code == 403
    assert response.json() == {
        "code": "SESSION_REQUIRED",
        "message": "请求会话无效",
        "details": {},
        "event_id": None,
    }


async def test_schema_rejects_host_configuration_fields(client: httpx.AsyncClient) -> None:
    headers = await session_headers(client)
    response = await client.post(
        "/api/projects",
        json={"path": "x", "state_root": "C:/private", "api_key": "secret"},
        headers=headers,
    )
    assert response.status_code == 422
    assert "secret" not in response.text


async def test_project_rejects_private_database_parent_overlap(tmp_path: Path) -> None:
    project = _git_repo(tmp_path / "project-with-private-state")
    state_root = project / "private-state"
    app = create_app(
        settings=HarnessSettings(
            state_root=state_root,
            database_path=state_root / "database" / "harness.db",
            trusted_hosts=("testserver",),
            trusted_origins=("http://testserver",),
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as value:
            response = await value.post(
                "/api/projects",
                json={"path": str(project)},
                headers=await session_headers(value),
            )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PROJECT"


@pytest.mark.parametrize(
    ("port_name", "method_name", "error"),
    [
        ("detector", "detect", RuntimeError("detector internal token=hidden")),
        ("detector", "detect", ValueError("detector value token=hidden")),
        ("scanner", "scan", RuntimeError("scanner internal token=hidden")),
        ("scanner", "scan", ValueError("scanner value token=hidden")),
        (
            "branch_resolver",
            "default_branch",
            RuntimeError("branch internal token=hidden"),
        ),
        (
            "branch_resolver",
            "default_branch",
            ValueError("branch value token=hidden"),
        ),
    ],
)
async def test_project_unknown_port_errors_remain_internal(
    client: httpx.AsyncClient,
    tmp_path: Path,
    port_name: str,
    method_name: str,
    error: Exception,
) -> None:
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    setattr(active, port_name, _FailingProjectPort(method_name, error))

    response = await _post_without_app_exception(
        client,
        "/api/projects",
        json={"path": str(_git_repo(tmp_path / f"unknown-{port_name}-{type(error).__name__}"))},
        headers=await session_headers(client),
    )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.json()["details"] == {}
    assert "hidden" not in response.text


@pytest.mark.parametrize(
    ("port_name", "method_name", "error"),
    [
        ("detector", "detect", ProjectDetectionError("unsupported")),
        ("scanner", "scan", RepositoryScanError("unreadable")),
        (
            "branch_resolver",
            "default_branch",
            DefaultBranchError("unavailable"),
        ),
    ],
)
async def test_project_specific_domain_errors_remain_invalid_project(
    client: httpx.AsyncClient,
    tmp_path: Path,
    port_name: str,
    method_name: str,
    error: Exception,
) -> None:
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    setattr(active, port_name, _FailingProjectPort(method_name, error))

    response = await client.post(
        "/api/projects",
        json={"path": str(_git_repo(tmp_path / f"known-{port_name}"))},
        headers=await session_headers(client),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PROJECT"


class _FailingProjectPort:
    def __init__(self, method_name: str, error: Exception) -> None:
        self._method_name = method_name
        self._error = error

    def __getattr__(self, name: str) -> object:
        if name != self._method_name:
            raise AttributeError(name)

        def fail(*_: object) -> object:
            raise self._error

        return fail


async def _post_without_app_exception(
    client: httpx.AsyncClient,
    path: str,
    *,
    json: dict[str, object],
    headers: dict[str, str],
) -> httpx.Response:
    app = client._transport.app  # type: ignore[attr-defined]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as safe_client:
        return await safe_client.post(path, json=json, headers=headers)
