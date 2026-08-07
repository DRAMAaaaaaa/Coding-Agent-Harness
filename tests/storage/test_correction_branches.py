from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from coding_agent_harness.storage.correction_branches import CorrectionBranchRepository
from coding_agent_harness.storage.database import Database


async def test_reserve_is_idempotent_and_only_first_caller_is_owner(tmp_path) -> None:
    database = await Database.open(tmp_path / "branches.db")
    try:
        workspace_id, task_id = uuid4(), uuid4()
        await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
        await database.connection.execute(
            "INSERT INTO tasks (id, workspace_id, requirement, state, step_budget, time_budget_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(task_id), str(workspace_id), "existing", "WAITING_USER", 1, 1.0, datetime.now(UTC).isoformat()),
        )
        await database.connection.commit()
        repository = CorrectionBranchRepository(database)
        branch_id = uuid4()
        first, first_owner = await repository.reserve(
            branch_id, workspace_id, task_id, 7, "a" * 40, "b" * 64, 12, f"{branch_id}.patch"
        )
        second, second_owner = await repository.reserve(
            uuid4(), workspace_id, task_id, 7, "a" * 40, "b" * 64, 12, f"{branch_id}.patch"
        )
        assert first.id == second.id
        assert (first_owner, second_owner) == (True, False)
    finally:
        await database.close()
