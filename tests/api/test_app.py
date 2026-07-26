from __future__ import annotations

from pathlib import Path

import pytest

import coding_agent_harness.api.app as app_module
from coding_agent_harness.api.app import create_app
from coding_agent_harness.api.dependencies import (
    ApiDependencies,
    BlockingWorker,
    SafeBranchResolver,
    UnavailableTaskRunner,
)
from coding_agent_harness.config import HarnessSettings
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.storage.workspaces import WorkspaceRepository
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.git import SafeGit
from coding_agent_harness.workspace.scanner import WorkspaceScanner


@pytest.mark.parametrize(
    "constructor_name",
    ["WorkspaceRepository", "WorkspaceScanner", "SafeGit", "UnavailableTaskRunner"],
)
async def test_startup_failure_closes_owned_database_exactly_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    constructor_name: str,
) -> None:
    close_calls = 0
    original_close = Database.close

    async def tracking_close(database: Database) -> None:
        nonlocal close_calls
        close_calls += 1
        await original_close(database)

    class FailingConstructor:
        def __init__(self, *_: object, **__: object) -> None:
            raise RuntimeError("fault injection after database open")

    monkeypatch.setattr(Database, "close", tracking_close)
    monkeypatch.setattr(app_module, constructor_name, FailingConstructor)
    state_root = tmp_path / "state"
    app = create_app(
        settings=HarnessSettings(
            state_root=state_root,
            database_path=state_root / "harness.db",
            trusted_hosts=("testserver",),
            trusted_origins=("http://testserver",),
        )
    )

    with pytest.raises(RuntimeError, match="fault injection"):
        async with app.router.lifespan_context(app):
            pass

    assert close_calls == 1


async def test_injected_database_remains_caller_owned(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    settings = HarnessSettings(
        state_root=state_root,
        database_path=state_root / "harness.db",
        trusted_hosts=("testserver",),
        trusted_origins=("http://testserver",),
    )
    database = await Database.open(settings.resolved_database_path())
    try:
        tasks = TaskRepository(database)
        dependencies = ApiDependencies(
            workspaces=WorkspaceRepository(database),
            tasks=tasks,
            event_store=EventStore(database),
            detector=ProjectDetector(),
            scanner=WorkspaceScanner(state_root=state_root),
            state_root=state_root,
            private_roots=settings.private_state_roots(),
            orchestrator_factory=None,
            task_runner=UnavailableTaskRunner(),
            branch_resolver=SafeBranchResolver(SafeGit(state_root)),
            worker=BlockingWorker(),
        )
        app = create_app(settings=settings, dependencies=dependencies)

        async with app.router.lifespan_context(app):
            pass

        cursor = await database.connection.execute("SELECT 1")
        try:
            assert await cursor.fetchone() == (1,)
        finally:
            await cursor.close()
    finally:
        await database.close()
