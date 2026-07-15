from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import subprocess
from uuid import UUID, uuid4

import pytest

from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.models import Workspace
from coding_agent_harness.workspace.scanner import CommandResult, SubprocessGitRunner
from coding_agent_harness.workspace.worktrees import (
    BaseCommitError,
    NotGitRepositoryError,
    WorkspaceBusyError,
    WorktreeConflictError,
    WorktreeCreationError,
    WorktreeManager,
    WorktreeReleaseError,
    WorktreeStateError,
)


def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=check,
        capture_output=True,
    )


def workspace_for(root: Path, *, workspace_id: UUID | None = None) -> Workspace:
    return Workspace(
        id=workspace_id or uuid4(),
        root=root.resolve(),
        git_root=root.resolve(),
        default_branch="main",
        profile=ProjectDetector().detect(root),
    )


def head(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").stdout.decode().strip()


def test_creates_and_releases_worktree_without_touching_dirty_main_workspace(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory(
        "main repository with spaces",
        {"README.md": "clean\n", "src/app.py": "value = 1\n"},
    )
    readme = root / "README.md"
    readme.write_text("dirty main\n", encoding="utf-8")
    state_root = tmp_path / "harness state with spaces"
    task_id = uuid4()
    manager = WorktreeManager(workspace_for(root), state_root)

    info = manager.create(task_id, head(root))

    assert info.path.is_dir()
    assert info.path.is_relative_to(state_root.resolve())
    assert not info.path.is_relative_to(root.resolve())
    assert info.branch == f"harness/task-{task_id.hex[:8]}"
    assert git(info.path, "branch", "--show-current").stdout.decode().strip() == info.branch
    assert readme.read_text(encoding="utf-8") == "dirty main\n"
    assert b"README.md" in git(root, "status", "--porcelain=v1").stdout

    manager.release(task_id)

    assert not info.path.exists()
    assert (
        git(root, "show-ref", "--verify", f"refs/heads/{info.branch}", check=False).returncode
        == 0
    )
    assert readme.read_text(encoding="utf-8") == "dirty main\n"


def test_rejects_non_git_workspace(tmp_path: Path) -> None:
    root = tmp_path / "not git"
    root.mkdir()
    manager = WorktreeManager(workspace_for(root), tmp_path / "state")

    with pytest.raises(NotGitRepositoryError, match="^Workspace 不是 Git 根目录$"):
        manager.create(uuid4(), "HEAD")


def test_rejects_missing_base_commit_and_cleans_active_marker(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("base", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    manager = WorktreeManager(workspace, state_root)

    with pytest.raises(BaseCommitError, match="^基准提交不存在$"):
        manager.create(uuid4(), "deadbeef")

    active_marker = state_root / "worktrees" / str(workspace.id) / ".active"
    assert not active_marker.exists()


def test_rejects_second_writer_across_manager_instances(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("busy", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    first_task = uuid4()
    first = WorktreeManager(workspace, state_root)
    first.create(first_task, head(root))
    try:
        with pytest.raises(WorkspaceBusyError, match="^Workspace 已有写任务$"):
            WorktreeManager(workspace, state_root).create(uuid4(), head(root))
    finally:
        first.release(first_task)


def test_rejects_state_directory_inside_project(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
) -> None:
    root = git_repository_factory("inside", {"README.md": "base\n"})

    with pytest.raises(WorktreeStateError, match="^Harness 状态目录必须位于项目外$"):
        WorktreeManager(workspace_for(root), root / ".harness-state")


def test_rejects_existing_branch_or_target_without_overwriting(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("conflict", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    branch = f"harness/task-{task_id.hex[:8]}"
    git(root, "branch", branch)

    with pytest.raises(WorktreeConflictError, match="^任务分支或工作树已存在$"):
        WorktreeManager(workspace, state_root).create(task_id, head(root))

    target_task = uuid4()
    target = state_root / "worktrees" / str(workspace.id) / str(target_task)
    target.mkdir(parents=True)
    sentinel = target / "sentinel.txt"
    sentinel.write_text("keep\n", encoding="utf-8")
    with pytest.raises(WorktreeConflictError, match="^任务分支或工作树已存在$"):
        WorktreeManager(workspace, state_root).create(target_task, head(root))
    assert sentinel.read_text(encoding="utf-8") == "keep\n"


class FailingAddRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 3 and argv[3:5] == ["worktree", "add"]:
            Path(argv[-2]).mkdir(parents=True)
            return CommandResult(returncode=1, stdout=b"", stderr=b"simulated failure")
        return self._delegate.run(argv)


class RaisingAddRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 3 and argv[3:5] == ["worktree", "add"]:
            Path(argv[-2]).mkdir(parents=True)
            raise OSError("simulated process start failure")
        return self._delegate.run(argv)


def test_cleans_only_new_target_after_git_add_failure(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("failure", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    target = state_root / "worktrees" / str(workspace.id) / str(task_id)

    with pytest.raises(WorktreeCreationError, match="^创建任务工作树失败$"):
        WorktreeManager(workspace, state_root, runner=FailingAddRunner()).create(
            task_id,
            head(root),
        )

    assert not target.exists()
    assert not (target.parent / ".active").exists()


def test_cleans_active_marker_when_git_add_cannot_start(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("start-failure", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    target = state_root / "worktrees" / str(workspace.id) / str(task_id)

    with pytest.raises(WorktreeCreationError, match="^创建任务工作树失败$"):
        WorktreeManager(workspace, state_root, runner=RaisingAddRunner()).create(
            task_id,
            head(root),
        )

    assert not target.exists()
    assert not (target.parent / ".active").exists()


def test_release_refuses_dirty_task_worktree(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("dirty-task", {"README.md": "base\n"})
    task_id = uuid4()
    manager = WorktreeManager(workspace_for(root), tmp_path / "state")
    info = manager.create(task_id, head(root))
    readme = info.path / "README.md"
    readme.write_text("task change\n", encoding="utf-8")

    with pytest.raises(WorktreeReleaseError, match="^任务工作树包含未提交改动$"):
        manager.release(task_id)
    assert info.path.exists()

    readme.write_text("base\n", encoding="utf-8")
    manager.release(task_id)
    assert not info.path.exists()
