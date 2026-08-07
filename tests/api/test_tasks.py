from __future__ import annotations

import asyncio
from pathlib import Path
import threading
from uuid import UUID

import httpx
import pytest
from anyio import CapacityLimiter

from coding_agent_harness.api.app import create_app
from coding_agent_harness.api.dependencies import (
    BlockingWorker,
    LocalTaskRunner,
    RuntimeUnavailableError,
)
from coding_agent_harness.agent.orchestrator import AgentOrchestrator, TaskStateError
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.config import HarnessSettings
from coding_agent_harness.providers.base import ProviderError
from coding_agent_harness.providers.mock import ScriptedMockProvider
from coding_agent_harness.workspace.worktrees import (
    WorkspaceBusyError,
    WorktreeConflictError,
    WorktreeUncertainError,
)
from tests.api.conftest import session_headers
from tests.api.test_projects import _git_repo


async def test_task_api_runs_to_plan_gate(client: httpx.AsyncClient, tmp_path: Path) -> None:
    headers = await session_headers(client)
    project = await client.post("/api/projects", json={"path": str(_git_repo(tmp_path / "repo"))}, headers=headers)
    trusted = await client.post(
        f"/api/projects/{project.json()['id']}/trust",
        json={"fingerprint": project.json()["trust_fingerprint"]},
        headers=headers,
    )
    task = await client.post(
        "/api/tasks",
        json={"workspace_id": trusted.json()["id"], "requirement": "修复 add"},
        headers=headers,
    )
    assert task.status_code == 201
    assert task.json()["state"] == "WAITING_PLAN_APPROVAL"
    events = await client._transport.app.state.event_store.list_for_task(UUID(task.json()["id"]))  # type: ignore[attr-defined]
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
    assert [event.event_type for event in events] == ["SCAN_STARTED", "PLAN_STARTED", "LLM_REQUESTED", "LLM_RESPONSE_RECEIVED", "PLAN_PROPOSED"]
    assert events[-1].payload["content_bytes"] > 0
    assert "content_sha256" in events[-1].payload
    persisted = await client.get(f"/api/tasks/{task.json()['id']}")
    assert persisted.json() == task.json()
    rejected_final = await client.post(
        f"/api/tasks/{task.json()['id']}/final/approve", headers=headers,
    )
    assert rejected_final.status_code == 409


async def test_task_rejects_untrusted_and_host_controls(client: httpx.AsyncClient, tmp_path: Path) -> None:
    headers = await session_headers(client)
    project = await client.post("/api/projects", json={"path": str(_git_repo(tmp_path / "repo"))}, headers=headers)
    untrusted = await client.post(
        "/api/tasks",
        json={"workspace_id": project.json()["id"], "requirement": "修复 add"},
        headers=headers,
    )
    assert untrusted.status_code == 409
    rejected = await client.post(
        "/api/tasks",
        json={"workspace_id": project.json()["id"], "requirement": "", "branch": "main"},
        headers=headers,
    )
    assert rejected.status_code == 422


async def test_task_rejects_utf8_requirement_over_limit_without_side_effects(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    headers, workspace_id = await _trusted_workspace(client, tmp_path / "large-requirement")
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    before_tasks = await (
        await active.tasks._database.connection.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*) FROM tasks"
        )
    ).fetchone()
    before_state = _relative_state_entries(active.state_root)

    response = await client.post(
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": "汉" * 30_000},
        headers=headers,
    )

    assert response.status_code == 422
    after_tasks = await (
        await active.tasks._database.connection.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*) FROM tasks"
        )
    ).fetchone()
    assert before_tasks == after_tasks == (0,)
    assert _relative_state_entries(active.state_root) == before_state


async def test_task_rejects_redaction_expansion_before_worktree_side_effects(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    headers, workspace_id = await _trusted_workspace(
        client,
        tmp_path / "redaction-expansion",
    )
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    requirement = "token=x " * 8_192
    assert len(requirement.encode("utf-8")) == 65_536
    before_state = _relative_state_entries(active.state_root)

    response = await _post(
        client,
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": requirement},
        headers=headers,
        suppress_app_exception=True,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    task_count = await (
        await active.tasks._database.connection.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*) FROM tasks"
        )
    ).fetchone()
    workspace_state = active.state_root / "worktrees" / workspace_id
    assert task_count == (0,)
    assert not workspace_state.exists()
    assert not (workspace_state / ".active").exists()
    assert _relative_state_entries(active.state_root) == before_state


async def test_task_accepts_normal_requirement_at_utf8_byte_limit(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    headers, workspace_id = await _trusted_workspace(
        client,
        tmp_path / "normal-boundary",
    )
    requirement = "a" * 65_536

    response = await client.post(
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": requirement},
        headers=headers,
    )

    assert response.status_code == 201
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    stored = await active.tasks.get(UUID(response.json()["id"]))
    assert stored is not None
    assert stored.requirement == requirement


async def test_sqlite_task_insert_failure_removes_worktree_and_allows_retry(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    headers, workspace_id = await _trusted_workspace(
        client,
        tmp_path / "task-storage-retry",
    )
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    connection = active.tasks._database.connection  # type: ignore[attr-defined]
    await connection.execute(
        """
        CREATE TRIGGER fail_task_insert
        BEFORE INSERT ON tasks
        BEGIN
            SELECT RAISE(FAIL, 'injected task storage failure');
        END
        """
    )
    await connection.commit()

    failed = await _post(
        client,
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": "验证任务落盘补偿"},
        headers=headers,
        suppress_app_exception=True,
    )

    workspace_state = active.state_root / "worktrees" / workspace_id
    assert failed.status_code == 503
    assert failed.json()["code"] == "TASK_STORAGE_UNAVAILABLE"
    assert failed.json()["details"] == {"retryable": True}
    assert await _task_count(active) == 0
    assert not (workspace_state / ".active").exists()
    assert _task_worktree_directories(workspace_state) == ()

    await connection.execute("DROP TRIGGER fail_task_insert")
    await connection.commit()
    retried = await client.post(
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": "验证任务落盘补偿"},
        headers=headers,
    )

    assert retried.status_code == 201
    assert await _task_count(active) == 1
    assert (workspace_state / ".active").read_text(encoding="ascii") == retried.json()["id"]


async def test_task_storage_compensation_owner_change_is_uncertain_and_preserves_other_task(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, workspace_id = await _trusted_workspace(
        client,
        tmp_path / "task-storage-uncertain",
    )
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    stored = await active.workspaces.get(UUID(workspace_id))
    assert stored is not None
    connection = active.tasks._database.connection  # type: ignore[attr-defined]
    await connection.execute(
        """
        CREATE TRIGGER fail_task_insert
        BEFORE INSERT ON tasks
        BEGIN
            SELECT RAISE(FAIL, 'injected task storage failure');
        END
        """
    )
    await connection.commit()
    from coding_agent_harness.api import dependencies as dependency_module

    real_manager = dependency_module.WorktreeManager
    other_task_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    created_task_ids: list[UUID] = []

    class OwnershipChangingManager:
        def __init__(self, workspace: object, state_root: object) -> None:
            self._delegate = real_manager(workspace, state_root)  # type: ignore[arg-type]
            self._state_root = Path(state_root)  # type: ignore[arg-type]

        def create(self, task_id: UUID, base_commit: str) -> None:
            self._delegate.create(task_id, base_commit)
            created_task_ids.append(task_id)
            workspace_state = self._state_root / "worktrees" / workspace_id
            (workspace_state / ".active").write_text(str(other_task_id), encoding="ascii")
            other_target = workspace_state / str(other_task_id)
            other_target.mkdir()
            (other_target / "owner.txt").write_text("other", encoding="utf-8")

        def release(self, task_id: UUID) -> None:
            self._delegate.release(task_id)

    monkeypatch.setattr(dependency_module, "WorktreeManager", OwnershipChangingManager)
    active.task_runner = LocalTaskRunner(
        active.tasks,
        active.state_root,
        step_budget=8,
        time_budget_seconds=300,
        worker=active.worker,
    )
    workspace_state = active.state_root / "worktrees" / workspace_id
    try:
        failed = await _post(
            client,
            "/api/tasks",
            json={"workspace_id": workspace_id, "requirement": "验证补偿所有权"},
            headers=headers,
            suppress_app_exception=True,
        )

        assert failed.status_code == 503
        assert failed.json()["code"] == "WORKTREE_UNCERTAIN"
        assert await _task_count(active) == 0
        assert created_task_ids
        assert (workspace_state / str(created_task_ids[0])).is_dir()
        assert (workspace_state / ".active").read_text(encoding="ascii") == str(other_task_id)
        assert (workspace_state / str(other_task_id) / "owner.txt").read_text(
            encoding="utf-8"
        ) == "other"
    finally:
        await connection.execute("DROP TRIGGER fail_task_insert")
        await connection.commit()
        if created_task_ids:
            (workspace_state / str(other_task_id) / "owner.txt").unlink(missing_ok=True)
            (workspace_state / str(other_task_id)).rmdir()
            (workspace_state / ".active").write_text(
                str(created_task_ids[0]),
                encoding="ascii",
            )
            real_manager(stored.workspace, active.state_root).release(created_task_ids[0])


async def test_config_change_invalidates_trust_before_creating_task(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    root = _git_repo(tmp_path / "changed")
    headers = await session_headers(client)
    project = await client.post("/api/projects", json={"path": str(root)}, headers=headers)
    trusted = await client.post(
        f"/api/projects/{project.json()['id']}/trust",
        json={"fingerprint": project.json()["trust_fingerprint"]}, headers=headers,
    )
    dependencies = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    recording = _RecordingTaskRunner(dependencies.task_runner)
    dependencies.task_runner = recording
    assert dependencies.orchestrator_factory is not None
    recording_factory = _RecordingOrchestratorFactory(dependencies.orchestrator_factory)
    dependencies.orchestrator_factory = recording_factory
    before_tasks = await (
        await dependencies.tasks._database.connection.execute("SELECT COUNT(*) FROM tasks")  # type: ignore[attr-defined]
    ).fetchone()
    before_state = _relative_state_entries(dependencies.state_root)
    (root / "pyproject.toml").write_text("[build-system]\nrequires=['changed']\n", encoding="utf-8")
    response = await client.post(
        "/api/tasks", json={"workspace_id": trusted.json()["id"], "requirement": "修复"}, headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_PROJECT_TRUST"
    after_tasks = await (
        await dependencies.tasks._database.connection.execute("SELECT COUNT(*) FROM tasks")  # type: ignore[attr-defined]
    ).fetchone()
    assert before_tasks == after_tasks == (0,)
    assert recording.calls == 0
    assert recording_factory.calls == 0
    assert _relative_state_entries(dependencies.state_root) == before_state


async def test_default_app_requires_session_provider_before_creating_task_or_worktree(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    app = create_app(
        settings=HarnessSettings(
            state_root=state_root,
            database_path=state_root / "harness.db",
            trusted_hosts=("testserver",),
            trusted_origins=("http://testserver",),
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as value:
            headers = await session_headers(value)
            project = await value.post("/api/projects", json={"path": str(_git_repo(tmp_path / "repo"))}, headers=headers)
            trusted = await value.post(f"/api/projects/{project.json()['id']}/trust", json={"fingerprint": project.json()["trust_fingerprint"]}, headers=headers)
            response = await value.post("/api/tasks", json={"workspace_id": trusted.json()["id"], "requirement": "x"}, headers=headers)
        assert response.status_code == 409
        assert response.json()["code"] == "PROVIDER_CREDENTIAL_REQUIRED"
        count = await (await app.state.tasks._database.connection.execute("SELECT COUNT(*) FROM tasks")).fetchone()  # type: ignore[attr-defined]
        assert count == (0,)
        assert not (state_root / "worktrees").exists()


async def test_project_blocking_ports_run_off_event_loop_and_health_responds(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    loop = asyncio.get_running_loop()
    main_thread = threading.get_ident()
    detector = _ThreadProbe(active.detector, "detect", loop, client)
    scanner = _ThreadProbe(active.scanner, "scan", loop, client)
    branch = _ThreadProbe(active.branch_resolver, "default_branch", loop, client)
    active.detector = detector
    active.scanner = scanner
    active.branch_resolver = branch

    response = await client.post(
        "/api/projects",
        json={"path": str(_git_repo(tmp_path / "responsive"))},
        headers=await session_headers(client),
    )

    assert response.status_code == 201
    assert detector.thread_id != main_thread
    assert scanner.thread_id != main_thread
    assert branch.thread_id != main_thread
    assert detector.concurrent_status == 200
    assert scanner.concurrent_status == 200
    assert branch.concurrent_status == 200


async def test_cancelled_worktree_creation_settles_and_persists_owner(
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace_id = await _trusted_workspace(client, tmp_path / "cancelled-create")
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    stored = await active.workspaces.get(UUID(workspace_id))
    assert stored is not None
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    observed_release: list[bool] = []

    class BlockingWorktreeManager:
        def __init__(self, workspace: object, state_root: object) -> None:
            pass

        def create(self, task_id: UUID, base_commit: str) -> None:
            started.set()
            observed_release.append(release.wait(timeout=1))
            completed.set()

    monkeypatch.setattr(
        "coding_agent_harness.api.dependencies.WorktreeManager",
        BlockingWorktreeManager,
    )
    task_id = UUID("12345678-1234-5678-1234-567812345678")
    runner = LocalTaskRunner(
        active.tasks,
        active.state_root,
        step_budget=8,
        time_budget_seconds=300,
        worker=active.worker,
    )
    creation = asyncio.create_task(
        runner.create(stored.workspace, task_id, "取消期间仍应收敛")
    )
    assert await asyncio.to_thread(started.wait, 2)
    creation.cancel()
    assert not creation.done()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await creation
    assert completed.is_set()
    assert observed_release == [True]
    assert (await active.tasks.get(task_id)) is not None


async def test_cancelled_plan_request_recovers_same_task_after_restart(
    tmp_path: Path,
) -> None:
    settings = HarnessSettings(
        state_root=tmp_path / "state",
        database_path=tmp_path / "state" / "harness.db",
        trusted_hosts=("testserver",),
        trusted_origins=("http://testserver",),
    )
    provider = _CancellationBarrierProvider()
    first_app = create_app(settings=settings)
    async with first_app.router.lifespan_context(first_app):
        active = first_app.state.dependencies
        orchestrator = AgentOrchestrator(
            provider=provider,
            parser=ActionParser(()),
            tools=_UnusedTools(),
            event_store=active.event_store,
            tasks=active.tasks,
        )
        recovery = _CancellationRecoveryBarrier(orchestrator)
        active.orchestrator_factory = lambda: recovery
        active.require_provider_profile = False
        active.task_runner = LocalTaskRunner(
            active.tasks,
            active.state_root,
            step_budget=8,
            time_budget_seconds=300,
            worker=active.worker,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=first_app),
            base_url="http://testserver",
        ) as first_client:
            headers, workspace_id = await _trusted_workspace(
                first_client,
                tmp_path / "cancelled-plan",
            )
            request = asyncio.create_task(
                first_client.post(
                    "/api/tasks",
                    json={"workspace_id": workspace_id, "requirement": "取消计划请求"},
                    headers=headers,
                )
            )
            await provider.started.wait()
            request.cancel()
            await recovery.started.wait()
            request.cancel()
            assert not request.done()
            recovery.release.set()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert provider.cancelled.is_set()
            assert provider.settled.is_set()
            rows = await (
                await active.tasks._database.connection.execute(  # type: ignore[attr-defined]
                    "SELECT id, state FROM tasks"
                )
            ).fetchall()
            assert len(rows) == 1
            task_id = str(rows[0][0])
            assert str(rows[0][1]) == "WAITING_USER"

    second_app = create_app(settings=settings)
    async with second_app.router.lifespan_context(second_app):
        active = second_app.state.dependencies
        orchestrator = AgentOrchestrator(
            provider=ScriptedMockProvider([]),
            parser=ActionParser(()),
            tools=_UnusedTools(),
            event_store=active.event_store,
            tasks=active.tasks,
        )
        active.orchestrator_factory = lambda: orchestrator
        active.require_provider_profile = False
        active.task_runner = LocalTaskRunner(
            active.tasks,
            active.state_root,
            step_budget=8,
            time_budget_seconds=300,
            worker=active.worker,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=second_app),
            base_url="http://testserver",
        ) as second_client:
            persisted = await second_client.get(f"/api/tasks/{task_id}")
            headers = await session_headers(second_client)
            resumed = await second_client.post(
                f"/api/tasks/{task_id}/run",
                headers=headers,
            )
            repeated = await second_client.post(
                "/api/tasks",
                json={"workspace_id": workspace_id, "requirement": "取消计划请求"},
                headers=headers,
            )

            assert persisted.status_code == resumed.status_code == 200
            assert persisted.json()["state"] == resumed.json()["state"] == "WAITING_USER"
            assert repeated.status_code == 409
            assert repeated.json()["details"]["task_id"] == task_id
            workspace_state = active.state_root / "worktrees" / workspace_id
            assert _task_worktree_directories(workspace_state) == (
                workspace_state / task_id,
            )
            assert (workspace_state / ".active").read_text(encoding="ascii") == task_id


async def test_blocking_worker_capacity_is_shared_and_bounded() -> None:
    worker = BlockingWorker(CapacityLimiter(1))
    first_started = threading.Event()
    second_started = threading.Event()
    release_first = threading.Event()
    second_submitted = asyncio.Event()

    def first() -> str:
        first_started.set()
        release_first.wait()
        return "first"

    def second() -> str:
        second_started.set()
        return "second"

    async def submit_second() -> str:
        second_submitted.set()
        return await worker.run(second)

    first_task = asyncio.create_task(worker.run(first))
    second_task = asyncio.create_task(submit_second())
    assert await asyncio.to_thread(first_started.wait, 2)
    await second_submitted.wait()
    assert not second_started.is_set()
    release_first.set()

    assert await asyncio.gather(first_task, second_task) == ["first", "second"]
    assert second_started.is_set()


async def test_provider_failure_returns_recoverable_task_and_retry_keeps_owner(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    headers = await session_headers(client)
    project = await client.post(
        "/api/projects",
        json={"path": str(_git_repo(tmp_path / "provider-failure"))},
        headers=headers,
    )
    trusted = await client.post(
        f"/api/projects/{project.json()['id']}/trust",
        json={"fingerprint": project.json()["trust_fingerprint"]},
        headers=headers,
    )
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    orchestrator = AgentOrchestrator(
        provider=ScriptedMockProvider([]),
        parser=ActionParser(()),
        tools=_UnusedTools(),
        event_store=active.event_store,
        tasks=active.tasks,
    )
    active.orchestrator_factory = lambda: orchestrator

    failed = await client.post(
        "/api/tasks",
        json={"workspace_id": trusted.json()["id"], "requirement": "修复失败"},
        headers=headers,
    )
    task_id = failed.json()["details"]["task_id"]
    persisted = await client.get(f"/api/tasks/{task_id}")
    events = await active.event_store.list_for_task(UUID(task_id))
    retry = await client.post(
        "/api/tasks",
        json={"workspace_id": trusted.json()["id"], "requirement": "修复失败"},
        headers=headers,
    )

    assert failed.status_code == 503
    assert failed.json()["code"] == "PROVIDER_UNAVAILABLE"
    assert persisted.json()["state"] == "WAITING_USER"
    assert events[-1].event_type == "USER_INPUT_REQUIRED"
    assert events[-1].payload["reason_code"] == "PROVIDER_UNAVAILABLE"
    assert retry.status_code == 409
    assert retry.json()["code"] == "WORKSPACE_BUSY"
    assert retry.json()["details"]["task_id"] == task_id
    marker = active.state_root / "worktrees" / trusted.json()["id"] / ".active"
    assert marker.read_text(encoding="ascii") == task_id


async def test_unknown_propose_failure_keeps_persisted_task_identity(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    headers, workspace_id = await _trusted_workspace(client, tmp_path / "unknown-propose")
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    orchestrator = AgentOrchestrator(
        provider=_FailingProvider(ValueError("programmer bug token=hidden")),
        parser=ActionParser(()),
        tools=_UnusedTools(),
        event_store=active.event_store,
        tasks=active.tasks,
    )
    active.orchestrator_factory = lambda: orchestrator

    response = await _post(
        client,
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": "修复未知故障"},
        headers=headers,
        suppress_app_exception=True,
    )
    task_id = response.json()["details"]["task_id"]
    persisted = await client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert persisted.status_code == 200
    assert persisted.json()["state"] == "WAITING_USER"
    assert "hidden" not in str(response.json())


async def test_record_runtime_failure_error_does_not_hide_provider_task_identity(
    client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    headers, workspace_id = await _trusted_workspace(client, tmp_path / "record-failure")
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    delegate = AgentOrchestrator(
        provider=ScriptedMockProvider([]),
        parser=ActionParser(()),
        tools=_UnusedTools(),
        event_store=active.event_store,
        tasks=active.tasks,
    )
    active.orchestrator_factory = lambda: _FailingFailureRecorder(delegate)

    response = await client.post(
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": "保留故障任务"},
        headers=headers,
    )
    task_id = response.json()["details"]["task_id"]
    persisted = await client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 503
    assert response.json()["code"] == "PROVIDER_UNAVAILABLE"
    assert persisted.status_code == 200
    assert persisted.json()["id"] == task_id
    assert "secondary-hidden" not in str(response.json())


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (WorkspaceBusyError("busy"), 409, "WORKSPACE_BUSY"),
        (WorktreeConflictError("conflict"), 409, "WORKSPACE_BUSY"),
        (WorktreeUncertainError("uncertain"), 503, "WORKTREE_UNCERTAIN"),
        (RuntimeUnavailableError("runtime"), 503, "RUNTIME_UNAVAILABLE"),
        (ValueError("programmer bug token=hidden"), 500, "INTERNAL_ERROR"),
    ],
)
async def test_task_creation_maps_only_specific_domain_errors(
    client: httpx.AsyncClient,
    tmp_path: Path,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    headers, workspace_id = await _trusted_workspace(client, tmp_path / code)
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    active.task_runner = _FailingTaskRunner(error)
    response = await _post(
        client,
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": "修复"},
        headers=headers,
        suppress_app_exception=status_code == 500,
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code
    assert "hidden" not in str(response.json())


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (TaskStateError("state"), 409, "INVALID_TASK_STATE"),
        (
            ProviderError("provider token=hidden", kind="transport", retryable=True),
            503,
            "PROVIDER_UNAVAILABLE",
        ),
        (RuntimeUnavailableError("runtime"), 503, "RUNTIME_UNAVAILABLE"),
        (ValueError("programmer bug token=hidden"), 500, "INTERNAL_ERROR"),
        (KeyError("unrelated missing key token=hidden"), 500, "INTERNAL_ERROR"),
    ],
)
async def test_orchestrator_maps_only_specific_domain_errors(
    client: httpx.AsyncClient,
    tmp_path: Path,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    headers, workspace_id = await _trusted_workspace(client, tmp_path / f"orchestrator-{code}")
    task = await client.post(
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": "修复"},
        headers=headers,
    )
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    active.orchestrator_factory = lambda: _FailingOrchestrator(error)
    response = await _post(
        client,
        f"/api/tasks/{task.json()['id']}/plan/approve",
        headers=headers,
        suppress_app_exception=status_code == 500,
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code
    if status_code != 500:
        assert response.json()["details"]["task_id"] == task.json()["id"]
    else:
        assert response.json()["details"] == {}
    assert "hidden" not in str(response.json())


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            ProviderError("provider token=hidden", kind="transport", retryable=True),
            503,
            "PROVIDER_UNAVAILABLE",
        ),
        (RuntimeUnavailableError("runtime"), 503, "RUNTIME_UNAVAILABLE"),
        (ValueError("factory bug token=hidden"), 500, "INTERNAL_ERROR"),
    ],
)
async def test_orchestrator_factory_has_the_same_typed_error_boundary(
    client: httpx.AsyncClient,
    tmp_path: Path,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    headers, workspace_id = await _trusted_workspace(client, tmp_path / f"factory-{code}")
    task = await client.post(
        "/api/tasks",
        json={"workspace_id": workspace_id, "requirement": "修复"},
        headers=headers,
    )
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]

    def failing_factory() -> object:
        raise error

    active.orchestrator_factory = failing_factory
    response = await _post(
        client,
        f"/api/tasks/{task.json()['id']}/plan/approve",
        headers=headers,
        suppress_app_exception=status_code == 500,
    )

    assert response.status_code == status_code
    assert response.json()["code"] == code
    if status_code != 500:
        assert response.json()["details"]["task_id"] == task.json()["id"]
    else:
        assert response.json()["details"] == {}
    assert "hidden" not in str(response.json())


class _RecordingTaskRunner:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self.calls = 0

    async def create(self, workspace: object, task_id: object, requirement: str) -> object:
        self.calls += 1
        return await self._delegate.create(workspace, task_id, requirement)  # type: ignore[union-attr]


class _RecordingOrchestratorFactory:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        return self._delegate()  # type: ignore[operator]


class _ThreadProbe:
    def __init__(self, delegate: object, method: str, loop: asyncio.AbstractEventLoop, client: httpx.AsyncClient) -> None:
        self._delegate = delegate
        self._method = method
        self._loop = loop
        self._client = client
        self.thread_id: int | None = None
        self.concurrent_status: int | None = None

    def __getattr__(self, name: str) -> object:
        if name != self._method:
            return getattr(self._delegate, name)

        def call(*args: object) -> object:
            self.thread_id = threading.get_ident()
            future = asyncio.run_coroutine_threadsafe(self._client.get("/"), self._loop)
            try:
                self.concurrent_status = future.result(timeout=1).status_code
            except TimeoutError:
                self.concurrent_status = None
            return getattr(self._delegate, self._method)(*args)

        return call


class _FailingTaskRunner:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def create(self, workspace: object, task_id: object, requirement: str, **_: object) -> object:
        raise self._error


class _FailingOrchestrator:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def approve_plan(self, task_id: UUID) -> object:
        raise self._error


class _FailingProvider:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def complete(self, request: object) -> object:
        raise self._error


class _CancellationBarrierProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.settled = asyncio.Event()
        self._release = asyncio.Event()

    async def complete(self, request: object) -> object:
        self.started.set()
        try:
            await self._release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.settled.set()
        raise AssertionError("计划 Provider 不应在取消测试中正常返回")


class _CancellationRecoveryBarrier:
    def __init__(self, delegate: AgentOrchestrator) -> None:
        self._delegate = delegate
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def propose_plan(self, task_id: UUID) -> object:
        return await self._delegate.propose_plan(task_id)

    async def record_runtime_failure(self, task_id: UUID, reason_code: str) -> object:
        self.started.set()
        await self.release.wait()
        return await self._delegate.record_runtime_failure(task_id, reason_code)


class _FailingFailureRecorder:
    def __init__(self, delegate: AgentOrchestrator) -> None:
        self._delegate = delegate

    async def propose_plan(self, task_id: UUID) -> object:
        return await self._delegate.propose_plan(task_id)

    async def record_runtime_failure(self, task_id: UUID, reason_code: str) -> object:
        raise ValueError("record failure token=secondary-hidden")


class _UnusedTools:
    async def execute(self, action: object) -> object:
        raise AssertionError("计划失败测试不应执行工具")


async def _trusted_workspace(client: httpx.AsyncClient, root: Path) -> tuple[dict[str, str], str]:
    headers = await session_headers(client)
    project = await client.post(
        "/api/projects", json={"path": str(_git_repo(root))}, headers=headers,
    )
    trusted = await client.post(
        f"/api/projects/{project.json()['id']}/trust",
        json={"fingerprint": project.json()["trust_fingerprint"]},
        headers=headers,
    )
    return headers, trusted.json()["id"]


async def _post(
    client: httpx.AsyncClient,
    path: str,
    *,
    headers: dict[str, str],
    json: dict[str, object] | None = None,
    suppress_app_exception: bool = False,
) -> httpx.Response:
    if not suppress_app_exception:
        return await client.post(path, headers=headers, json=json)
    app = client._transport.app  # type: ignore[attr-defined]
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as safe_client:
        return await safe_client.post(path, headers=headers, json=json)


def _relative_state_entries(root: Path) -> tuple[str, ...]:
    if not root.exists():
        return ()
    return tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*")))


async def _task_count(active: object) -> int:
    row = await (
        await active.tasks._database.connection.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*) FROM tasks"
        )
    ).fetchone()
    assert row is not None
    return int(row[0])


def _task_worktree_directories(workspace_state: Path) -> tuple[Path, ...]:
    if not workspace_state.exists():
        return ()
    return tuple(path for path in workspace_state.iterdir() if path.is_dir())
