from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.models import Task
from coding_agent_harness.replay import branches as branch_module
from coding_agent_harness.replay.branches import CorrectionBranchService
from coding_agent_harness.storage.correction_branches import StoredCorrectionBranch


class _Worker:
    async def run(self, function, *args):
        return function(*args)


class _Branches:
    def __init__(self, branch: StoredCorrectionBranch) -> None:
        self.branch = branch
        self.calls: list[str] = []
        self.fail_ready = False

    async def reserve(self, branch_id, workspace_id, parent_task_id, source_event_sequence, base_commit, patch_sha256, patch_bytes, checkpoint_file_name, child_task_id):
        self.calls.append("reserve")
        from dataclasses import replace
        self.branch = replace(self.branch, child_task_id=child_task_id)
        return self.branch, True

    async def mark_ready(self, branch_id: UUID, child_task_id: UUID):
        self.calls.append("ready")
        from dataclasses import replace
        self.branch = replace(self.branch, child_task_id=child_task_id, status="READY")
        if self.fail_ready:
            raise RuntimeError("ready update failed")
        return self.branch

    async def mark_uncertain(self, branch_id: UUID):
        self.calls.append("uncertain")
        from dataclasses import replace
        self.branch = replace(self.branch, status="UNCERTAIN")
        return self.branch

    async def is_child_task(self, task_id: UUID) -> bool:
        return False


class _Tasks:
    def __init__(self, task: Task) -> None:
        self.task = task

    async def get(self, task_id: UUID):
        return self.task if task_id == self.task.id else None


class _Events:
    async def list_for_task(self, task_id: UUID):
        return [type("Event", (), {"sequence": 7, "event_type": "VERIFICATION_FAILED", "payload": {}})()]


class _Workspaces:
    def __init__(self, workspace: object) -> None:
        self.workspace = workspace

    async def get(self, workspace_id: UUID):
        return self.workspace


class _Providers:
    async def build_for_task(self, task: Task):
        return object()


class _Runner:
    def __init__(self, *, mark_ready_fails: bool = False) -> None:
        self.mark_ready_fails = mark_ready_fails
        self.created_id: UUID | None = None

    async def create(self, *args, **kwargs):
        self.created_id = args[1]
        raise RuntimeError("child creation failed")


@pytest.mark.asyncio
async def test_branch_failure_restores_parent_writer_after_reservation(monkeypatch, tmp_path: Path) -> None:
    parent_id, workspace_id, branch_id = uuid4(), uuid4(), uuid4()
    parent = Task(id=parent_id, workspace_id=workspace_id, requirement="fix", state=TaskState.WAITING_USER,
                  step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
    workspace = type("Workspace", (), {"id": workspace_id, "workspace": type("Profile", (), {"git_root": tmp_path})()})()
    stored = StoredCorrectionBranch(branch_id, workspace_id, parent_id, 7, None, "CREATING", "a" * 40,
                                    "b" * 64, 12, f"{branch_id}.patch", datetime.now(UTC))
    repository = _Branches(stored)
    calls: list[str] = []

    class _Manager:
        def __init__(self, *args):
            pass
        def freeze(self, task_id: UUID) -> None:
            calls.append("freeze")
        def restore_writer(self, task_id: UUID) -> None:
            calls.append("restore")

    monkeypatch.setattr(branch_module, "WorktreeManager", _Manager)
    monkeypatch.setattr(branch_module, "capture_patch", lambda *args: ("a" * 40, b"patch"))
    monkeypatch.setattr(branch_module, "write_checkpoint", lambda *args: calls.append("checkpoint"))
    service = CorrectionBranchService(branches=repository, tasks=_Tasks(parent), events=_Events(),
        workspaces=_Workspaces(workspace), runner=_Runner(), providers=_Providers(), state_root=tmp_path / "state", worker=_Worker())

    with pytest.raises(RuntimeError, match="child creation failed"):
        await service.create(parent_id, 7, "try another assertion")

    assert repository.calls == ["reserve", "uncertain"]
    assert calls == ["freeze", "checkpoint", "restore"]


@pytest.mark.asyncio
async def test_branch_keeps_reserved_child_id_when_ready_update_fails(monkeypatch, tmp_path: Path) -> None:
    parent_id, workspace_id, branch_id = uuid4(), uuid4(), uuid4()
    parent = Task(id=parent_id, workspace_id=workspace_id, requirement="fix", state=TaskState.WAITING_USER,
                  step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
    workspace = type("Workspace", (), {"id": workspace_id, "workspace": type("Profile", (), {"git_root": tmp_path})()})()
    stored = StoredCorrectionBranch(branch_id, workspace_id, parent_id, 7, None, "CREATING", "a" * 40,
                                    "b" * 64, 12, f"{branch_id}.patch", datetime.now(UTC))
    repository = _Branches(stored)
    runner = _SuccessRunner()
    repository.fail_ready = True
    monkeypatch.setattr(branch_module, "WorktreeManager", _NoopManager)
    monkeypatch.setattr(branch_module, "capture_patch", lambda *args: ("a" * 40, b"patch"))
    monkeypatch.setattr(branch_module, "write_checkpoint", lambda *args: None)
    service = CorrectionBranchService(branches=repository, tasks=_Tasks(parent), events=_Events(),
        workspaces=_Workspaces(workspace), runner=runner, providers=_Providers(), state_root=tmp_path / "state", worker=_Worker())

    with pytest.raises(RuntimeError, match="ready update failed"):
        await service.create(parent_id, 7, "try another assertion")

    assert repository.branch.status == "UNCERTAIN"
    assert repository.branch.child_task_id == runner.created_id


class _NoopManager:
    def __init__(self, *args): pass
    def freeze(self, task_id: UUID) -> None: pass
    def restore_writer(self, task_id: UUID) -> None: pass


class _SuccessRunner:
    def __init__(self) -> None:
        self.created_id: UUID | None = None

    async def create(self, *args, **kwargs):
        self.created_id = args[1]
        return Task(id=self.created_id, workspace_id=uuid4(), requirement="child", state=TaskState.CREATED,
            step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None)
