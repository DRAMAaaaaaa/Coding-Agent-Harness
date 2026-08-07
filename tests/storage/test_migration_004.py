from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

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
        assert await (await database.connection.execute("PRAGMA user_version")).fetchone() == (4,)
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
