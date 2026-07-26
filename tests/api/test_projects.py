from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

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
