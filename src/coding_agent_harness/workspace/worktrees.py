"""为每个写任务创建位于 Harness 状态目录的独立 Git worktree。"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from uuid import UUID

from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.workspace.models import Workspace, WorktreeInfo
from coding_agent_harness.workspace.scanner import GitRunner, SubprocessGitRunner


class WorktreeError(ValueError):
    """工作树生命周期操作失败。"""


class WorktreeStateError(WorktreeError):
    """Harness 状态目录不满足隔离要求。"""


class NotGitRepositoryError(WorktreeError):
    """Workspace 没有指向 Git 根目录。"""


class BaseCommitError(WorktreeError):
    """基准提交不存在。"""


class WorkspaceBusyError(WorktreeError):
    """同一 Workspace 已经有写任务。"""


class WorktreeConflictError(WorktreeError):
    """任务分支或目标目录已经存在。"""


class WorktreeCreationError(WorktreeError):
    """Git 无法创建隔离工作树。"""


class WorktreeReleaseError(WorktreeError):
    """工作树无法安全释放。"""


class WorktreeManager:
    """使用原子活动标记维持每 Workspace 单写任务约束。"""

    def __init__(
        self,
        workspace: Workspace,
        state_root: str | Path,
        *,
        runner: GitRunner | None = None,
    ) -> None:
        self._workspace = workspace
        self._runner = runner or SubprocessGitRunner()
        try:
            self._git_root = workspace.git_root.resolve(strict=True)
            self._state_root = Path(state_root).resolve(strict=False)
        except (OSError, RuntimeError):
            raise WorktreeStateError("Harness 状态目录无效") from None
        guard = PathGuard(self._git_root)
        try:
            guard.resolve(self._state_root)
        except PathEscapeError:
            pass
        else:
            raise WorktreeStateError("Harness 状态目录必须位于项目外")
        self._workspace_state = self._state_root / "worktrees" / str(workspace.id)
        self._active_marker = self._workspace_state / ".active"

    def create(self, task_id: UUID, base_commit: str) -> WorktreeInfo:
        self._validate_git_root()
        resolved_base = self._resolve_base_commit(base_commit)
        branch = f"harness/task-{task_id.hex[:8]}"
        target = self._workspace_state / str(task_id)
        if self._branch_exists(branch) or target.exists() or target.is_symlink():
            raise WorktreeConflictError("任务分支或工作树已存在")

        self._workspace_state.mkdir(parents=True, exist_ok=True)
        self._acquire_active_marker(task_id)
        try:
            result = self._runner.run(
                [
                    "git",
                    "-C",
                    str(self._git_root),
                    "worktree",
                    "add",
                    "-b",
                    branch,
                    str(target),
                    resolved_base,
                ]
            )
        except OSError:
            self._cleanup_failed_create(target, branch)
            raise WorktreeCreationError("创建任务工作树失败") from None
        if result.returncode != 0:
            self._cleanup_failed_create(target, branch)
            raise WorktreeCreationError("创建任务工作树失败")
        return WorktreeInfo(
            workspace_id=self._workspace.id,
            task_id=task_id,
            path=target,
            branch=branch,
            base_commit=resolved_base,
        )

    def release(self, task_id: UUID) -> None:
        marker_task = self._read_active_marker()
        if marker_task != str(task_id):
            raise WorktreeReleaseError("任务工作树不存在")
        target = self._workspace_state / str(task_id)
        status = self._runner.run(
            ["git", "-C", str(target), "status", "--porcelain=v1"]
        )
        if status.returncode != 0:
            raise WorktreeReleaseError("任务工作树不存在")
        if status.stdout:
            raise WorktreeReleaseError("任务工作树包含未提交改动")
        removed = self._runner.run(
            ["git", "-C", str(self._git_root), "worktree", "remove", str(target)]
        )
        if removed.returncode != 0:
            raise WorktreeReleaseError("释放任务工作树失败")
        self._remove_active_marker()

    def _validate_git_root(self) -> None:
        result = self._runner.run(
            ["git", "-C", str(self._git_root), "rev-parse", "--show-toplevel"]
        )
        if result.returncode != 0:
            raise NotGitRepositoryError("Workspace 不是 Git 根目录")
        try:
            reported_root = Path(result.stdout.decode("utf-8").strip()).resolve(strict=True)
        except (UnicodeDecodeError, OSError, RuntimeError):
            raise NotGitRepositoryError("Workspace 不是 Git 根目录") from None
        if reported_root != self._git_root:
            raise NotGitRepositoryError("Workspace 不是 Git 根目录")

    def _resolve_base_commit(self, base_commit: str) -> str:
        if not base_commit or "\x00" in base_commit:
            raise BaseCommitError("基准提交不存在")
        result = self._runner.run(
            [
                "git",
                "-C",
                str(self._git_root),
                "rev-parse",
                "--verify",
                f"{base_commit}^{{commit}}",
            ]
        )
        if result.returncode != 0:
            raise BaseCommitError("基准提交不存在")
        try:
            resolved = result.stdout.decode("ascii").strip()
        except UnicodeDecodeError:
            raise BaseCommitError("基准提交不存在") from None
        if not resolved:
            raise BaseCommitError("基准提交不存在")
        return resolved

    def _branch_exists(self, branch: str) -> bool:
        result = self._runner.run(
            [
                "git",
                "-C",
                str(self._git_root),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch}",
            ]
        )
        if result.returncode not in (0, 1):
            raise WorktreeCreationError("无法检查任务分支")
        return result.returncode == 0

    def _acquire_active_marker(self, task_id: UUID) -> None:
        try:
            descriptor = os.open(
                self._active_marker,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            raise WorkspaceBusyError("Workspace 已有写任务") from None
        except OSError:
            raise WorktreeCreationError("无法记录 Workspace 写任务") from None
        try:
            os.write(descriptor, str(task_id).encode("ascii"))
        finally:
            os.close(descriptor)

    def _cleanup_failed_create(self, target: Path, branch: str) -> None:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        self._runner.run(
            ["git", "-C", str(self._git_root), "branch", "-d", branch]
        )
        self._remove_active_marker()

    def _read_active_marker(self) -> str | None:
        try:
            return self._active_marker.read_text(encoding="ascii")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError):
            raise WorktreeReleaseError("Workspace 活动标记无效") from None

    def _remove_active_marker(self) -> None:
        try:
            self._active_marker.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            raise WorktreeStateError("无法清理 Workspace 活动标记") from None
