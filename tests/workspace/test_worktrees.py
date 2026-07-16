from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import os
import subprocess
from uuid import UUID, uuid4

import pytest

from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.models import Workspace
from coding_agent_harness.workspace.processes import (
    CommandResult,
    GitProcessNotStartedError,
    SubprocessGitRunner,
)
from coding_agent_harness.workspace.worktrees import (
    BaseCommitError,
    NotGitRepositoryError,
    WorkspaceBusyError,
    WorktreeConflictError,
    WorktreeCreationError,
    WorktreeManager,
    WorktreeReleaseError,
    WorktreeStateError,
    WorktreeUncertainError,
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


def create_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            pytest.skip("当前系统无法创建目录符号链接")
    created = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
    )
    if created.returncode != 0:
        pytest.skip("当前系统无法创建目录符号链接或 junction")


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


@pytest.mark.parametrize("relationship", ["exact", "ancestor"])
def test_rejects_state_root_equal_to_or_ancestor_of_git_root_without_writing(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    relationship: str,
) -> None:
    root = git_repository_factory("overlapping-state", {"README.md": "base\n"})
    state_root = root if relationship == "exact" else root.parent
    worktrees = state_root / "worktrees"

    with pytest.raises(
        WorktreeStateError,
        match="^Harness 状态目录必须位于项目外$",
    ):
        WorktreeManager(workspace_for(root), state_root)

    assert not worktrees.exists()


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
        self.sentinel: Path | None = None

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 3 and argv[3:5] == ["worktree", "add"]:
            root = argv[2]
            branch = argv[-3]
            base = argv[-1]
            created = self._delegate.run(
                ["git", "-C", root, "branch", branch, base]
            )
            assert created.returncode == 0
            target = Path(argv[-2])
            target.mkdir(parents=True)
            self.sentinel = target / "partial-sentinel.txt"
            self.sentinel.write_text("manual recovery\n", encoding="utf-8")
            return CommandResult(returncode=1, stdout=b"", stderr=b"simulated failure")
        return self._delegate.run(argv)


class RaisingAddRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()
        self.calls: list[list[str]] = []

    def run(self, argv: Sequence[str]) -> CommandResult:
        self.calls.append(list(argv))
        if len(argv) > 3 and argv[3:5] == ["worktree", "add"]:
            raise GitProcessNotStartedError("Git 进程未启动")
        return self._delegate.run(argv)


class SideEffectThenOSErrorRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()
        self.sentinel: Path | None = None

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 3 and argv[3:5] == ["worktree", "add"]:
            root = argv[2]
            branch = argv[-3]
            base = argv[-1]
            created = self._delegate.run(["git", "-C", root, "branch", branch, base])
            assert created.returncode == 0
            target = Path(argv[-2])
            target.mkdir(parents=True)
            self.sentinel = target / "ordinary-oserror-sentinel.txt"
            self.sentinel.write_text("preserve unknown side effect\n", encoding="utf-8")
            raise OSError("unknown failure after side effect")
        return self._delegate.run(argv)


class MissingRegistrationAfterAddRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()

    def run(self, argv: Sequence[str]) -> CommandResult:
        result = self._delegate.run(argv)
        if len(argv) > 5 and argv[3:6] == ["worktree", "list", "--porcelain"]:
            return CommandResult(returncode=0, stdout=b"", stderr=b"")
        return result


class FalseSuccessRemoveRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 4 and argv[3:5] == ["worktree", "remove"]:
            return CommandResult(returncode=0, stdout=b"", stderr=b"")
        return self._delegate.run(argv)


class StaleRegistrationAfterRemoveRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()
        self._stale_registration: bytes | None = None

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 4 and argv[3:5] == ["worktree", "remove"]:
            target = Path(argv[-1])
            branch = git(target, "branch", "--show-current").stdout.decode().strip()
            commit = head(target)
            result = self._delegate.run(argv)
            if result.returncode == 0:
                self._stale_registration = (
                    f"worktree {target}\nHEAD {commit}\nbranch refs/heads/{branch}\n\n"
                ).encode()
            return result
        result = self._delegate.run(argv)
        if (
            self._stale_registration is not None
            and len(argv) > 5
            and argv[3:6] == ["worktree", "list", "--porcelain"]
        ):
            return CommandResult(
                returncode=0,
                stdout=result.stdout + self._stale_registration,
                stderr=b"",
            )
        return result


class PreflightStatusErrorRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 3 and argv[3] == "status":
            raise OSError("status runner failed")
        return self._delegate.run(argv)


class PartialRemoveRunner:
    def __init__(self, outcome: str) -> None:
        self._delegate = SubprocessGitRunner()
        self._outcome = outcome

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 4 and argv[3:5] == ["worktree", "remove"]:
            removed = self._delegate.run(argv)
            assert removed.returncode == 0
            if self._outcome == "nonzero":
                return CommandResult(returncode=1, stdout=b"", stderr=b"remove failed")
            raise OSError("remove raised after side effect")
        return self._delegate.run(argv)


class RemoveNotStartedRunner:
    def __init__(self) -> None:
        self._delegate = SubprocessGitRunner()

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 4 and argv[3:5] == ["worktree", "remove"]:
            raise GitProcessNotStartedError("Git 进程未启动")
        return self._delegate.run(argv)


class SwappingFailingAddRunner:
    def __init__(self, state_root: Path, outside: Path) -> None:
        self._delegate = SubprocessGitRunner()
        self._state_root = state_root
        self._outside = outside
        self.sentinel = outside / "not-created"

    def run(self, argv: Sequence[str]) -> CommandResult:
        if len(argv) > 3 and argv[3:5] == ["worktree", "add"]:
            worktrees = self._state_root / "worktrees"
            worktrees.rename(self._state_root / "worktrees-safe")
            create_directory_link(worktrees, self._outside)
            target = Path(argv[-2])
            target.mkdir(parents=True)
            self.sentinel = target / "external-sentinel.txt"
            self.sentinel.write_text("must remain\n", encoding="utf-8")
            return CommandResult(returncode=1, stdout=b"", stderr=b"simulated failure")
        return self._delegate.run(argv)


def test_nonzero_git_add_preserves_partial_state_for_manual_recovery(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("failure", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    target = state_root / "worktrees" / str(workspace.id) / str(task_id)

    runner = FailingAddRunner()
    manager = WorktreeManager(workspace, state_root, runner=runner)
    with pytest.raises(
        WorktreeUncertainError,
        match="^创建任务工作树结果不确定，需人工处理$",
    ):
        manager.create(
            task_id,
            head(root),
        )

    assert runner.sentinel is not None
    assert runner.sentinel.read_text(encoding="utf-8") == "manual recovery\n"
    branch = f"harness/task-{task_id.hex[:8]}"
    assert git(root, "show-ref", "--verify", f"refs/heads/{branch}").returncode == 0
    assert (target.parent / ".active").read_text(encoding="ascii") == str(task_id)
    with pytest.raises(WorkspaceBusyError, match="^Workspace 已有写任务$"):
        WorktreeManager(workspace, state_root).create(uuid4(), head(root))


def test_cleans_active_marker_when_git_add_cannot_start(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("start-failure", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    target = state_root / "worktrees" / str(workspace.id) / str(task_id)

    runner = RaisingAddRunner()
    with pytest.raises(WorktreeCreationError, match="^创建任务工作树失败$"):
        WorktreeManager(workspace, state_root, runner=runner).create(
            task_id,
            head(root),
        )

    assert not target.exists()
    assert not (target.parent / ".active").exists()
    assert not any(call[3:5] == ["branch", "-d"] for call in runner.calls)

    next_task = uuid4()
    manager = WorktreeManager(workspace, state_root)
    manager.create(next_task, head(root))
    manager.release(next_task)


def test_ordinary_oserror_after_side_effect_preserves_marker_and_blocks_writer(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("ordinary-oserror", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    runner = SideEffectThenOSErrorRunner()

    with pytest.raises(
        WorktreeUncertainError,
        match="^创建任务工作树结果不确定，需人工处理$",
    ):
        WorktreeManager(workspace, state_root, runner=runner).create(task_id, head(root))

    assert runner.sentinel is not None
    assert runner.sentinel.read_text(encoding="utf-8") == "preserve unknown side effect\n"
    marker = state_root / "worktrees" / str(workspace.id) / ".active"
    assert marker.read_text(encoding="ascii") == str(task_id)
    branch = f"harness/task-{task_id.hex[:8]}"
    assert git(root, "show-ref", "--verify", f"refs/heads/{branch}").returncode == 0
    with pytest.raises(WorkspaceBusyError, match="^Workspace 已有写任务$"):
        WorktreeManager(workspace, state_root).create(uuid4(), head(root))


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


def test_release_maps_preflight_runner_error_and_preserves_marker(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("release-preflight", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    manager = WorktreeManager(
        workspace,
        state_root,
        runner=PreflightStatusErrorRunner(),
    )
    manager.create(task_id, head(root))

    with pytest.raises(
        WorktreeReleaseError,
        match="^无法检查任务工作树状态$",
    ):
        manager.release(task_id)

    marker = state_root / "worktrees" / str(workspace.id) / ".active"
    assert marker.read_text(encoding="ascii") == str(task_id)
    with pytest.raises(WorkspaceBusyError, match="^Workspace 已有写任务$"):
        WorktreeManager(workspace, state_root).create(uuid4(), head(root))
    WorktreeManager(workspace, state_root).release(task_id)


@pytest.mark.parametrize("outcome", ["nonzero", "exception"])
def test_release_partial_remove_is_uncertain_and_blocks_next_writer(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
    outcome: str,
) -> None:
    root = git_repository_factory(f"partial-remove-{outcome}", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    manager = WorktreeManager(
        workspace,
        state_root,
        runner=PartialRemoveRunner(outcome),
    )
    info = manager.create(task_id, head(root))

    with pytest.raises(
        WorktreeUncertainError,
        match="^释放任务工作树结果不确定，需人工处理$",
    ):
        manager.release(task_id)

    assert not info.path.exists()
    marker = state_root / "worktrees" / str(workspace.id) / ".active"
    assert marker.read_text(encoding="ascii") == str(task_id)
    with pytest.raises(WorkspaceBusyError, match="^Workspace 已有写任务$"):
        WorktreeManager(workspace, state_root).create(uuid4(), head(root))


def test_release_remove_not_started_is_ordinary_failure_and_preserves_worktree(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("remove-not-started", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    manager = WorktreeManager(
        workspace,
        state_root,
        runner=RemoveNotStartedRunner(),
    )
    info = manager.create(task_id, head(root))

    with pytest.raises(WorktreeReleaseError, match="^释放任务工作树失败$"):
        manager.release(task_id)

    assert info.path.is_dir()
    marker = state_root / "worktrees" / str(workspace.id) / ".active"
    assert marker.read_text(encoding="ascii") == str(task_id)
    WorktreeManager(workspace, state_root).release(task_id)


def test_rejects_state_worktrees_symlink_before_external_write(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("state-symlink", {"README.md": "base\n"})
    state_root = tmp_path / "state"
    outside = tmp_path / "outside"
    state_root.mkdir()
    outside.mkdir()
    try:
        (state_root / "worktrees").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"当前系统无法创建目录符号链接：{type(error).__name__}")

    with pytest.raises(WorktreeStateError, match="^Harness 状态子路径越界$"):
        WorktreeManager(workspace_for(root), state_root)

    assert list(outside.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows junction 语义")
def test_rejects_state_worktrees_junction_before_external_write(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("state-junction", {"README.md": "base\n"})
    state_root = tmp_path / "state"
    outside = tmp_path / "outside"
    state_root.mkdir()
    outside.mkdir()
    junction = state_root / "worktrees"
    created = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
        check=False,
        capture_output=True,
    )
    if created.returncode != 0:
        pytest.skip("当前系统无法创建 junction")

    with pytest.raises(WorktreeStateError, match="^Harness 状态子路径越界$"):
        WorktreeManager(workspace_for(root), state_root)

    assert list(outside.iterdir()) == []


def test_failed_create_never_removes_external_target_after_path_swap(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("cleanup-escape", {"README.md": "base\n"})
    state_root = tmp_path / "state"
    outside = tmp_path / "outside"
    outside.mkdir()
    runner = SwappingFailingAddRunner(state_root, outside)
    manager = WorktreeManager(workspace_for(root), state_root, runner=runner)

    with pytest.raises(WorktreeUncertainError):
        manager.create(uuid4(), head(root))

    assert runner.sentinel.read_text(encoding="utf-8") == "must remain\n"


def test_successful_add_with_missing_registration_is_uncertain_and_blocks_next_writer(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("missing-registration", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    manager = WorktreeManager(
        workspace,
        state_root,
        runner=MissingRegistrationAfterAddRunner(),
    )

    with pytest.raises(
        WorktreeUncertainError,
        match="^创建任务工作树后验验证失败，需人工处理$",
    ):
        manager.create(task_id, head(root))

    target = state_root / "worktrees" / str(workspace.id) / str(task_id)
    assert target.is_dir()
    assert (target.parent / ".active").read_text(encoding="ascii") == str(task_id)
    with pytest.raises(WorkspaceBusyError, match="^Workspace 已有写任务$"):
        WorktreeManager(workspace, state_root).create(uuid4(), head(root))


def test_release_false_success_preserves_marker_for_manual_recovery(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("remove-false-success", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    manager = WorktreeManager(workspace, state_root, runner=FalseSuccessRemoveRunner())
    info = manager.create(task_id, head(root))

    with pytest.raises(
        WorktreeUncertainError,
        match="^释放任务工作树后验验证失败，需人工处理$",
    ):
        manager.release(task_id)

    assert info.path.is_dir()
    assert (info.path.parent / ".active").read_text(encoding="ascii") == str(task_id)


def test_release_stale_registration_preserves_marker_after_target_disappears(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("remove-stale-registration", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    task_id = uuid4()
    manager = WorktreeManager(
        workspace,
        state_root,
        runner=StaleRegistrationAfterRemoveRunner(),
    )
    info = manager.create(task_id, head(root))

    with pytest.raises(
        WorktreeUncertainError,
        match="^释放任务工作树后验验证失败，需人工处理$",
    ):
        manager.release(task_id)

    assert not info.path.exists()
    assert (info.path.parent / ".active").read_text(encoding="ascii") == str(task_id)


def test_release_path_identity_change_is_uncertain_and_preserves_original_marker(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("release-path-swap", {"README.md": "base\n"})
    workspace = workspace_for(root)
    state_root = tmp_path / "state"
    outside = tmp_path / "outside"
    outside.mkdir()
    task_id = uuid4()
    manager = WorktreeManager(workspace, state_root)
    manager.create(task_id, head(root))
    worktrees = state_root / "worktrees"
    backup = state_root / "worktrees-safe"
    worktrees.rename(backup)
    create_directory_link(worktrees, outside)

    with pytest.raises(
        WorktreeUncertainError,
        match="^任务工作树路径身份变化，需人工处理$",
    ):
        manager.release(task_id)

    original_marker = backup / str(workspace.id) / ".active"
    assert original_marker.read_text(encoding="ascii") == str(task_id)
