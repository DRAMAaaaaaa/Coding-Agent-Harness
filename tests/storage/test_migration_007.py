import sqlite3
from pathlib import Path
from uuid import uuid4

from coding_agent_harness.storage.database import Database


async def test_migration_007_creates_project_learning_cards(tmp_path: Path) -> None:
    path = tmp_path / "v6.db"
    connection = sqlite3.connect(path)
    migrations = Path(__file__).parents[2] / "src" / "coding_agent_harness" / "storage" / "migrations"
    for migration in sorted(migrations.glob("00[1-6]_*.sql")):
        connection.executescript(migration.read_text(encoding="utf-8"))
    workspace_id, task_id = uuid4(), uuid4()
    connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
    connection.execute("INSERT INTO tasks (id, workspace_id, requirement, state, step_budget, time_budget_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (str(task_id), str(workspace_id), "x", "COMPLETED", 1, 1, "2026-01-01T00:00:00+00:00"))
    connection.execute("PRAGMA user_version=6")
    connection.commit()
    connection.close()
    database = await Database.open(path)
    try:
        await database.connection.execute("INSERT INTO project_learning_cards VALUES (?, ?, ?, ?, ?, ?)", (str(uuid4()), str(workspace_id), "经验", str(task_id), 1, "2026-01-01T00:00:00+00:00"))
        await database.connection.commit()
        assert await (await database.connection.execute("PRAGMA user_version")).fetchone() == (7,)
    finally:
        await database.close()
