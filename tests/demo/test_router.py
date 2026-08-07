from datetime import UTC, datetime
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from coding_agent_harness.demo import DemoOrchestratorRouter
from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.domain.models import Task
from coding_agent_harness.providers.mock import ScriptedMockProvider
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.storage.workspaces import WorkspaceRepository
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.models import Workspace
from coding_agent_harness.workspace.worktrees import WorktreeManager


@pytest.mark.asyncio
async def test_final_approval_freezes_child_writer_and_allows_next_task(
    tmp_path: Path,
) -> None:
    """终审释放写租约，但保留子分支与其可比较现场。"""
    root = tmp_path / "final-approval"
    root.mkdir()
    for arguments in (
        ("init", "-b", "main"),
        ("config", "user.name", "Harness Tests"),
        ("config", "user.email", "harness@example.invalid"),
        ("config", "core.autocrlf", "false"),
    ):
        subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)
    (root / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'final-approval'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "initial"], check=True, capture_output=True)
    state_root = tmp_path / "state"
    database = await Database.open(state_root / "harness.sqlite3")
    try:
        workspace = Workspace(
            id=uuid4(), root=root, git_root=root, default_branch="main",
            profile=ProjectDetector().detect(root),
        )
        workspaces = WorkspaceRepository(database)
        await workspaces.create(workspace)
        tasks = TaskRepository(database)
        child_id = uuid4()
        child = await tasks.create(Task(
            id=child_id, workspace_id=workspace.id, requirement="已完成纠正",
            state=TaskState.CREATED, step_budget=8,
            time_budget_seconds=60, created_at=datetime.now(UTC), deadline_at=None,
        ))
        events = EventStore(database)
        state = TaskState.CREATED
        for event_type, next_state in (
            ("SCAN_STARTED", TaskState.SCANNING),
            ("PLAN_STARTED", TaskState.PLANNING),
            ("PLAN_PROPOSED", TaskState.WAITING_PLAN_APPROVAL),
            ("PLAN_APPROVED", TaskState.DECIDING),
            ("FINAL_SUMMARY_PROPOSED", TaskState.WAITING_FINAL_REVIEW),
        ):
            await events.append(TaskEvent(
                task_id=child.id, sequence=0, event_type=event_type, payload={},
                state_before=state, state_after=next_state, occurred_at=datetime.now(UTC),
            ), expected_sequence=len(await events.list_for_task(child.id)))
            state = next_state
        manager = WorktreeManager(workspace, state_root)
        info = manager.create(child.id, "HEAD")
        (info.path / "demo.py").write_text("VALUE = 2\n", encoding="utf-8")
        router = DemoOrchestratorRouter(
            provider=ScriptedMockProvider([]), tasks=tasks, workspaces=workspaces,
            event_store=events, state_root=state_root,
        )

        completed = await router.approve_final(child.id)

        assert completed.state is TaskState.COMPLETED
        assert info.path.is_dir()
        assert (state_root / "worktrees" / str(workspace.id) / f".frozen-{child.id}").is_file()
        assert manager._registration_for(info.path) is not None
        next_info = WorktreeManager(workspace, state_root).create(uuid4(), "HEAD")
        assert next_info.path.is_dir()
        router.cleanup()
        assert child.id not in router._workspaces_by_task
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_final_approval_does_not_persist_completed_when_freezing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "freeze-failure"
    root.mkdir()
    for arguments in (("init", "-b", "main"), ("config", "user.name", "Harness Tests"), ("config", "user.email", "harness@example.invalid")):
        subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)
    (root / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'freeze-failure'\nversion = '0.1.0'\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "initial"], check=True, capture_output=True)
    state_root = tmp_path / "state"
    database = await Database.open(state_root / "harness.sqlite3")
    try:
        workspace = Workspace(id=uuid4(), root=root, git_root=root, default_branch="main", profile=ProjectDetector().detect(root))
        await WorkspaceRepository(database).create(workspace)
        tasks = TaskRepository(database)
        task = await tasks.create(Task(id=uuid4(), workspace_id=workspace.id, requirement="final", state=TaskState.CREATED, step_budget=1, time_budget_seconds=1, created_at=datetime.now(UTC), deadline_at=None))
        events = EventStore(database)
        state = TaskState.CREATED
        for event_type, next_state in (("SCAN_STARTED", TaskState.SCANNING), ("PLAN_STARTED", TaskState.PLANNING), ("PLAN_PROPOSED", TaskState.WAITING_PLAN_APPROVAL), ("PLAN_APPROVED", TaskState.DECIDING), ("FINAL_SUMMARY_PROPOSED", TaskState.WAITING_FINAL_REVIEW)):
            await events.append(TaskEvent(task_id=task.id, sequence=0, event_type=event_type, payload={}, state_before=state, state_after=next_state, occurred_at=datetime.now(UTC)), expected_sequence=len(await events.list_for_task(task.id)))
            state = next_state
        manager = WorktreeManager(workspace, state_root)
        manager.create(task.id, "HEAD")
        router = DemoOrchestratorRouter(provider=ScriptedMockProvider([]), tasks=tasks, workspaces=WorkspaceRepository(database), event_store=events, state_root=state_root)
        original_freeze = WorktreeManager.freeze
        monkeypatch.setattr(WorktreeManager, "freeze", lambda _self, _task_id: (_ for _ in ()).throw(RuntimeError("freeze failed")))

        with pytest.raises(RuntimeError, match="freeze failed"):
            await router.approve_final(task.id)

        assert (await (await router._for(task.id)).task(task.id)).state is TaskState.WAITING_FINAL_REVIEW
        manager.assert_writable(task.id)
        monkeypatch.setattr(WorktreeManager, "freeze", original_freeze)
        assert (await router.approve_final(task.id)).state is TaskState.COMPLETED
    finally:
        await database.close()
