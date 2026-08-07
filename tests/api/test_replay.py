from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.models import Task
from coding_agent_harness.replay.branches import BranchComparison, CorrectionBranch
from tests.api.conftest import session_headers


class _Branches:
    async def create(self, task_id, source_event_sequence, correction):
        assert source_event_sequence == 7
        assert correction == "补充边界"
        return CorrectionBranch(id=uuid4(), workspace_id=uuid4(), parent_task_id=task_id,
            source_event_sequence=7, child_task_id=None, status="CREATING", created_at=datetime.now(UTC))

    async def compare(self, branch_id):
        return BranchComparison(branch_id, "WAITING_USER", "WAITING_FINAL_REVIEW", "parent failed", "child passed", "- old", "+ new")


@pytest.mark.asyncio
async def test_replay_routes_create_branch_and_return_comparison(client) -> None:
    active = client._transport.app.state.dependencies  # type: ignore[attr-defined]
    task_id = uuid4()
    active.tasks = type("Tasks", (), {"get": lambda _, value: _task(task_id) if value == task_id else _none()})()
    active.correction_branches = _Branches()
    response = await client.post(f"/api/tasks/{task_id}/correction-branches", headers=await session_headers(client),
        json={"source_event_sequence": 7, "correction": "补充边界"})
    assert response.status_code == 201
    comparison = await client.get(f"/api/correction-branches/{response.json()['id']}/comparison")
    assert comparison.status_code == 200
    assert comparison.json()["child_diff"] == "+ new"


async def _task(task_id):
    return Task(id=task_id, workspace_id=uuid4(), requirement="fix", state=TaskState.WAITING_USER,
        step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)


async def _none():
    return None
