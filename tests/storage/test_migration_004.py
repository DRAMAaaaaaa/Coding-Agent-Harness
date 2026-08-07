from __future__ import annotations

import asyncio
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from coding_agent_harness.storage import database as database_module
from coding_agent_harness.storage.database import Database


_MIGRATIONS = Path(__file__).parents[2] / "src" / "coding_agent_harness" / "storage" / "migrations"


async def _open_v3_fixture(path: Path) -> Database:
    connection = sqlite3.connect(path)
    for name in ("001_initial.sql", "002_governance_approvals.sql", "003_mvp_workspaces.sql"):
        connection.executescript((_MIGRATIONS / name).read_text(encoding="utf-8"))
    workspace_id, task_id = uuid4(), uuid4()
    connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    connection.execute(
        "INSERT INTO tasks (id, workspace_id, requirement, state, step_budget, time_budget_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(task_id), str(workspace_id), "existing", "CREATED", 1, 1.0, "2026-01-01T00:00:00+00:00"),
    )
    connection.execute("PRAGMA user_version=3")
    connection.commit()
    connection.close()
    return await Database.open(path)


async def test_v3_only_applies_004_and_preserves_existing_task(tmp_path: Path) -> None:
    database = await _open_v3_fixture(tmp_path / "v3.db")
    try:
        row = await (await database.connection.execute(
            "SELECT provider_profile_id, provider_profile_version, llm_api_authorized_at FROM tasks"
        )).fetchone()
        assert row == (None, None, None)
        assert await (await database.connection.execute("PRAGMA user_version")).fetchone() == (6,)
    finally:
        await database.close()


async def test_binding_trigger_rejects_partial_provider_binding(tmp_path: Path) -> None:
    database = await Database.open(tmp_path / "binding.db")
    try:
        workspace_id = uuid4()
        await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
        with pytest.raises(sqlite3.IntegrityError, match="invalid provider binding"):
            await database.connection.execute(
                "INSERT INTO tasks (id, workspace_id, requirement, state, step_budget, time_budget_seconds, created_at, provider_profile_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid4()), str(workspace_id), "x", "CREATED", 1, 1.0, "2026-01-01T00:00:00+00:00", str(uuid4())),
            )
    finally:
        await database.close()


async def test_two_connections_apply_004_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "concurrent.db"
    connection = sqlite3.connect(path)
    for name in ("001_initial.sql", "002_governance_approvals.sql", "003_mvp_workspaces.sql"):
        connection.executescript((_MIGRATIONS / name).read_text(encoding="utf-8"))
    connection.execute("PRAGMA user_version=3")
    connection.commit()
    connection.close()
    seen: list[int] = []
    original = database_module._apply_one_migration_locked

    async def recorded(connection: object, migration: database_module.Migration) -> bool:
        if migration.version == 4:
            seen.append(migration.version)
        return await original(connection, migration)  # type: ignore[arg-type]

    monkeypatch.setattr(database_module, "_apply_one_migration_locked", recorded)
    first, second = await asyncio.gather(Database.open(path), Database.open(path))
    try:
        assert seen == [4]
    finally:
        await first.close()
        await second.close()


async def test_failed_004_rolls_back_and_can_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "failed.db"
    connection = sqlite3.connect(path)
    for name in ("001_initial.sql", "002_governance_approvals.sql", "003_mvp_workspaces.sql"):
        connection.executescript((_MIGRATIONS / name).read_text(encoding="utf-8"))
    connection.execute("PRAGMA user_version=3")
    connection.commit()
    connection.close()
    migration_directory = tmp_path / "migrations"
    shutil.copytree(_MIGRATIONS, migration_directory)
    (migration_directory / "004_provider_profiles.sql").write_text("CREATE TABLE broken (", encoding="utf-8")
    monkeypatch.setattr(database_module, "_MIGRATION_DIRECTORY", migration_directory)
    with pytest.raises(RuntimeError, match="不完整"):
        await Database.open(path)
    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA user_version").fetchone() == (3,)
        assert check.execute("SELECT name FROM sqlite_master WHERE name='provider_profiles'").fetchone() is None
    finally:
        check.close()
    shutil.copy2(_MIGRATIONS / "004_provider_profiles.sql", migration_directory / "004_provider_profiles.sql")
    database = await Database.open(path)
    try:
        assert await (await database.connection.execute("PRAGMA user_version")).fetchone() == (6,)
    finally:
        await database.close()
