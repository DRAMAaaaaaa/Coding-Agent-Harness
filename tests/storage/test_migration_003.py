from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from coding_agent_harness.storage import database as database_module
from coding_agent_harness.storage.database import Database


_MIGRATIONS = Path(__file__).parents[2] / "src" / "coding_agent_harness" / "storage" / "migrations"


async def test_fresh_v0_applies_exactly_001_002_003(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    original = database_module._apply_one_migration_locked

    async def recorded(connection: object, migration: database_module.Migration) -> bool:
        seen.append(migration.version)
        return await original(connection, migration)  # type: ignore[arg-type]

    monkeypatch.setattr(database_module, "_apply_one_migration_locked", recorded)
    database = await Database.open(tmp_path / "fresh.db")
    try:
        assert seen == [1, 2, 3]
        assert await (await database.connection.execute("PRAGMA user_version")).fetchone() == (3,)
    finally:
        await database.close()


async def test_v2_only_runs_003_and_keeps_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "v2.db"
    connection = sqlite3.connect(path)
    connection.executescript((_MIGRATIONS / "001_initial.sql").read_text(encoding="utf-8"))
    workspace_id, task_id, approval_id = uuid4(), uuid4(), uuid4()
    connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    connection.execute("INSERT INTO tasks (id,workspace_id,requirement,state,step_budget,time_budget_seconds,created_at,deadline_at) VALUES (?,?,?,?,?,?,?,?)", (str(task_id), str(workspace_id), "x", "CREATED", 1, 1.0, "2026-01-01T00:00:00+00:00", None))
    connection.execute("INSERT INTO approvals (id,task_id,decision,created_at) VALUES (?,?,?,?)", (str(approval_id), str(task_id), "APPROVED", "2026-01-01T00:00:00+00:00"))
    connection.executescript((_MIGRATIONS / "002_governance_approvals.sql").read_text(encoding="utf-8"))
    columns = (
        "id,task_id,action_id,reason_code,event_sequence,normalized_scope,task_state,"
        "config_version,decision,decided_by,expires_at,created_at,decided_at,consumed_at"
    )
    before = connection.execute(f"SELECT {columns} FROM approvals WHERE id=?", (str(approval_id),)).fetchone()
    connection.execute("PRAGMA user_version=2")
    connection.commit()
    connection.close()
    seen: list[int] = []
    original = database_module._apply_one_migration_locked
    async def recorded(connection: object, migration: database_module.Migration) -> bool:
        seen.append(migration.version)
        return await original(connection, migration)  # type: ignore[arg-type]
    monkeypatch.setattr(database_module, "_apply_one_migration_locked", recorded)
    database = await Database.open(path)
    try:
        assert seen == [3]
        after = await (await database.connection.execute(f"SELECT {columns} FROM approvals WHERE id=?", (str(approval_id),))).fetchone()
        assert after == before
        assert await (await database.connection.execute("SELECT trust_state, trusted_at FROM workspaces WHERE id=?", (str(workspace_id),))).fetchone() == ("UNTRUSTED", None)
    finally:
        await database.close()


async def test_v3_reopen_performs_no_ddl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "v3.db"
    first = await Database.open(path)
    await first.close()
    async def forbidden(*_: object) -> bool:
        raise AssertionError("v3 reopen must not run DDL")
    monkeypatch.setattr(database_module, "_apply_one_migration_locked", forbidden)
    second = await Database.open(path)
    await second.close()


async def test_future_database_is_rejected_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version=4")
    connection.commit()
    connection.close()
    with pytest.raises(RuntimeError, match="高于代码支持"):
        await Database.open(path)
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone() == (4,)
