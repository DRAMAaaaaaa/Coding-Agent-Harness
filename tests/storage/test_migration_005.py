from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from coding_agent_harness.storage.database import Database


_MIGRATIONS = Path(__file__).parents[2] / "src" / "coding_agent_harness" / "storage" / "migrations"


async def test_v4_applies_005_with_single_branch_per_failure(tmp_path: Path) -> None:
    path = tmp_path / "v4.db"
    connection = sqlite3.connect(path)
    for name in (
        "001_initial.sql",
        "002_governance_approvals.sql",
        "003_mvp_workspaces.sql",
        "004_provider_profiles.sql",
    ):
        connection.executescript((_MIGRATIONS / name).read_text(encoding="utf-8"))
    workspace_id, parent_task_id = uuid4(), uuid4()
    connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    connection.execute(
        "INSERT INTO tasks (id, workspace_id, requirement, state, step_budget, time_budget_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(parent_task_id), str(workspace_id), "existing", "WAITING_USER", 1, 1.0, "2026-01-01T00:00:00+00:00"),
    )
    connection.execute("PRAGMA user_version=4")
    connection.commit()
    connection.close()

    database = await Database.open(path)
    try:
        branch_id = uuid4()
        await database.connection.execute(
            """INSERT INTO correction_branches
            (id, workspace_id, parent_task_id, source_event_sequence, child_task_id, status,
             base_commit, patch_sha256, patch_bytes, checkpoint_file_name, created_at)
            VALUES (?, ?, ?, ?, NULL, 'CREATING', ?, ?, ?, ?, ?)""",
            (str(branch_id), str(workspace_id), str(parent_task_id), 7, "a" * 40, "b" * 64, 1, f"{branch_id}.patch", "2026-01-01T00:00:00+00:00"),
        )
        try:
            await database.connection.execute(
                """INSERT INTO correction_branches
                (id, workspace_id, parent_task_id, source_event_sequence, child_task_id, status,
                 base_commit, patch_sha256, patch_bytes, checkpoint_file_name, created_at)
                VALUES (?, ?, ?, ?, NULL, 'CREATING', ?, ?, ?, ?, ?)""",
                (str(uuid4()), str(workspace_id), str(parent_task_id), 7, "a" * 40, "c" * 64, 1, "other.patch", "2026-01-01T00:00:00+00:00"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("同一失败节点不得预留第二条纠正分支")
        await database.connection.execute(
            "UPDATE correction_branches SET child_task_id = ? WHERE id = ?",
            (str(uuid4()), str(branch_id)),
        )
        assert await (await database.connection.execute("PRAGMA user_version")).fetchone() == (7,)
    finally:
        await database.close()


async def test_v5_correction_branch_schema_upgrades_without_losing_rows(tmp_path: Path) -> None:
    path = tmp_path / "v5.db"
    connection = sqlite3.connect(path)
    for name in ("001_initial.sql", "002_governance_approvals.sql", "003_mvp_workspaces.sql", "004_provider_profiles.sql"):
        connection.executescript((_MIGRATIONS / name).read_text(encoding="utf-8"))
    workspace_id, parent_task_id, branch_id, child_id = uuid4(), uuid4(), uuid4(), uuid4()
    connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    connection.execute("INSERT INTO tasks (id, workspace_id, requirement, state, step_budget, time_budget_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(parent_task_id), str(workspace_id), "parent", "WAITING_USER", 1, 1.0, "2026-01-01T00:00:00+00:00"))
    connection.executescript("""
        CREATE TABLE correction_branches (
            id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
            parent_task_id TEXT NOT NULL REFERENCES tasks(id), source_event_sequence INTEGER NOT NULL CHECK (source_event_sequence > 0),
            child_task_id TEXT REFERENCES tasks(id), status TEXT NOT NULL CHECK (status IN ('CREATING','READY','UNCERTAIN')),
            base_commit TEXT NOT NULL, patch_sha256 TEXT NOT NULL, patch_bytes INTEGER NOT NULL CHECK (patch_bytes BETWEEN 1 AND 1048576),
            checkpoint_file_name TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(parent_task_id, source_event_sequence)
        );
    """)
    connection.execute("INSERT INTO correction_branches VALUES (?, ?, ?, ?, NULL, 'CREATING', ?, ?, ?, ?, ?)",
        (str(branch_id), str(workspace_id), str(parent_task_id), 7, "a" * 40, "b" * 64, 1, "old.patch", "2026-01-01T00:00:00+00:00"))
    connection.execute("PRAGMA user_version=5")
    connection.commit()
    connection.close()

    database = await Database.open(path)
    try:
        assert await (await database.connection.execute("PRAGMA user_version")).fetchone() == (7,)
        assert await (await database.connection.execute("SELECT id FROM correction_branches")).fetchone() == (str(branch_id),)
        await database.connection.execute("UPDATE correction_branches SET child_task_id = ? WHERE id = ?", (str(child_id), str(branch_id)))
        await database.connection.commit()
    finally:
        await database.close()
