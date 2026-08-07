from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from coding_agent_harness.api.app import create_app
from coding_agent_harness.config import HarnessSettings
from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.models import Task
from coding_agent_harness.providers.registry import ProviderRegistry
from coding_agent_harness.providers.models import ProviderKind
from coding_agent_harness.providers.credentials import (
    CredentialBroker,
    CredentialPersistence,
    CredentialVaultError,
    SessionOnlyCredentialStore,
)
from coding_agent_harness.runtime import RuntimeOrchestratorRouter
from coding_agent_harness.tools.models import ToolResult
from tests.api.conftest import session_headers
from tests.api.test_projects import _git_repo


class _InlineRunner:
    async def run(self, function: object, *args: object) -> object:
        return function(*args)  # type: ignore[operator]


def test_session_only_store_refuses_persistence_and_delete_is_idempotent() -> None:
    store = SessionOnlyCredentialStore()

    with pytest.raises(CredentialVaultError, match="^PERSISTENT_CREDENTIALS_DISABLED$"):
        store.put("provider-profile:test", SecretStr("test-key"))
    store.delete("provider-profile:test")
    assert store.get("provider-profile:test") is None


@pytest.mark.asyncio
async def test_clear_session_removes_all_session_credentials() -> None:
    broker = CredentialBroker(SessionOnlyCredentialStore(), _InlineRunner())
    first, second = uuid4(), uuid4()
    await broker.put(first, SecretStr("first-test-key"), CredentialPersistence.SESSION)
    await broker.put(second, SecretStr("second-test-key"), CredentialPersistence.SESSION)

    broker.clear_session()

    assert await broker.get(first) is None
    assert await broker.get(second) is None


@pytest.mark.asyncio
async def test_runtime_router_replays_failed_feedback_through_stubbed_provider(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []
    responses = iter((
        "最小计划",
        '{"kind":"tool","tool":"run_verification","arguments":{"name":"unit"},"idempotency_key":"verify-1"}',
        '{"kind":"tool","tool":"delete_file","arguments":{"path":"x"},"idempotency_key":"blocked-1"}',
    ))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": next(responses)}}]})

    app = create_app(settings=HarnessSettings(
        state_root=tmp_path / "state", database_path=tmp_path / "state" / "harness.db",
        trusted_hosts=("testserver",), trusted_origins=("http://testserver",),
    ))
    async with app.router.lifespan_context(app):
        active = app.state.dependencies
        assert active.profiles is not None and active.credentials is not None
        active.provider_registry = ProviderRegistry(
            active.profiles, active.credentials,
            client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        profile = await active.profiles.create(ProviderKind.DEEPSEEK, "deepseek-chat")
        await active.credentials.put(profile.id, SecretStr("test-session-provider-key"), CredentialPersistence.SESSION)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            headers = await session_headers(client)
            project = await client.post("/api/projects", json={"path": str(_git_repo(tmp_path / "repo"))}, headers=headers)
            trusted = await client.post(f"/api/projects/{project.json()['id']}/trust", json={"fingerprint": project.json()["trust_fingerprint"]}, headers=headers)
        stored = await active.workspaces.get(UUID(trusted.json()["id"]))
        assert stored is not None
        task_id = uuid4()
        worktree = active.state_root / "worktrees" / str(stored.workspace.id) / str(task_id)
        worktree.parent.mkdir(parents=True)
        (worktree.parent / ".active").write_text(str(task_id), encoding="ascii")
        _git_repo(worktree)
        task = await active.tasks.create(Task(
            id=task_id, workspace_id=stored.workspace.id, requirement="验证真实运行时",
            state=TaskState.CREATED, step_budget=8, time_budget_seconds=300,
            created_at=datetime.now(UTC), deadline_at=None, provider_profile_id=profile.id,
            provider_profile_version=profile.version, llm_api_authorized_at=datetime.now(UTC),
        ))
        router = RuntimeOrchestratorRouter(active, tool_registry_factory=lambda _: _FailingVerificationTools())
        await router.propose_plan(task.id)
        await router.approve_plan(task.id)
        final = await router.run_until_wait(task.id)

    assert final.state is TaskState.WAITING_USER
    assert len(requests) == 2


class _FailingVerificationTools:
    async def execute(self, action: object) -> ToolResult:
        return ToolResult(ok=False, code="VERIFICATION_FAILED", output="1 failed")

    def normalized_governance_scope(self, action: object) -> None:
        return None
