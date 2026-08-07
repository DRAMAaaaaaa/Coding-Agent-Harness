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
        assert await (await database.connection.execute("PRAGMA user_version")).fetchone() == (5,)
    finally:
        await database.close()
