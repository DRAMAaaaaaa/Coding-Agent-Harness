"""为每个写任务创建位于 Harness 状态目录的独立 Git worktree。"""

from __future__ import annotations

import os
from pathlib import Path
import stat
from threading import RLock
from collections.abc import Callable
from typing import ParamSpec, TypeVar, cast
from uuid import UUID

from coding_agent_harness.governance.path_identity import (
    UnsafePathNamespaceError,
    collapse_windows_extended_path,
    same_path,
    trusted_paths_overlap,
)
from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.workspace.models import Workspace, WorktreeInfo
from coding_agent_harness.workspace.git import GitSafetyError, SafeGit
from coding_agent_harness.workspace.files import is_symlink_or_reparse
from coding_agent_harness.workspace.processes import (
    GitProcessNotStartedError,
    ProcessRunner,
)


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

    def __init__(self, message: str, *, active_task_id: UUID | None = None) -> None:
        super().__init__(message)
        self.active_task_id = active_task_id


class WorktreeConflictError(WorktreeError):
    """任务分支或目标目录已经存在。"""


class WorktreeCreationError(WorktreeError):
    """Git 无法创建隔离工作树。"""


class WorktreeReleaseError(WorktreeError):
    """工作树无法安全释放。"""


class WorktreeUncertainError(WorktreeError):
    """Git 副作用结果无法安全确认，需要人工接管。"""


# 单进程 MVP：跨实例共享锁仅保护本进程内的 marker 生命周期，不提供跨进程互斥。
_MARKER_LIFECYCLE_LOCK = RLock()
_Params = ParamSpec("_Params")
_Result = TypeVar("_Result")


def _marker_lifecycle_locked(function: Callable[_Params, _Result]) -> Callable[_Params, _Result]:
    def guarded(*args: _Params.args, **kwargs: _Params.kwargs) -> _Result:
        with _MARKER_LIFECYCLE_LOCK:
            return function(*args, **kwargs)
    return cast(Callable[_Params, _Result], guarded)


class WorktreeManager:
    """使用原子活动标记维持每 Workspace 单写任务约束。"""

    def __init__(
        self,
        workspace: Workspace,
        state_root: str | Path,
        *,
        runner: ProcessRunner | None = None,
        safe_git: SafeGit | None = None,
    ) -> None:
        self._workspace = workspace
        try:
            self._git_root = workspace.git_root.resolve(strict=True)
            state_root_text = str(state_root)
            if os.name == "nt":
                state_root_text = collapse_windows_extended_path(state_root_text)
            raw_state_root = Path(state_root_text)
            if trusted_paths_overlap(raw_state_root, self._git_root):
                raise WorktreeStateError("Harness 状态目录必须位于项目外")
            self._state_root = raw_state_root.resolve(strict=False)
        except WorktreeStateError:
            raise
        except (OSError, RuntimeError, UnsafePathNamespaceError):
            raise WorktreeStateError("Harness 状态目录无效") from None
        try:
            self._state_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise WorktreeStateError("Harness 状态目录无效") from None
        self._git = safe_git or SafeGit(self._state_root, runner=runner)
        self._state_guard = PathGuard(self._state_root)
        self._workspace_state = self._resolve_state_path(
            self._state_root / "worktrees" / str(workspace.id)
        )
        self._active_marker = self._workspace_state / ".active"

    @_marker_lifecycle_locked
    def freeze(self, task_id: UUID) -> None:
        """冻结已验证的父 worktree，保留现场并释放唯一写租约。"""
        try:
            target = self._resolve_state_path(self._workspace_state / str(task_id))
            frozen = self._resolve_state_path(self._workspace_state / f".frozen-{task_id}")
            already_frozen = frozen.exists()
            if already_frozen:
                if not frozen.is_file() or frozen.read_text(encoding="ascii") != str(task_id):
                    raise WorktreeUncertainError("父任务冻结状态不确定，需要人工处理")
            elif self._read_active_marker() != str(task_id):
                raise WorktreeUncertainError("父任务写租约归属不确定，需要人工处理")
            self._git.trust_linked_worktree(target, self._git_root)
            root = self._git.run(target, ["rev-parse", "--show-toplevel"])
            registration = self._registration_for(target)
            if root.returncode != 0 or registration is None:
                raise WorktreeUncertainError("父任务 worktree 身份不确定，需要人工处理")
            reported = Path(root.stdout.decode("utf-8").strip()).resolve(strict=True)
            if not same_path(reported, target):
                raise WorktreeUncertainError("父任务 worktree 身份不确定，需要人工处理")
            if already_frozen:
                if self._read_active_marker() == str(task_id):
                    self._remove_active_marker()
                return
            descriptor = os.open(frozen, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, str(task_id).encode("ascii"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._remove_active_marker()
        except WorktreeUncertainError:
            raise
        except (OSError, UnicodeDecodeError, WorktreeError, GitSafetyError):
            raise WorktreeUncertainError("父任务冻结结果不确定，需要人工处理") from None

    def assert_writable(self, task_id: UUID) -> None:
        """仅接受当前精确 owner，且拒绝所有已冻结任务。"""
        try:
            frozen = self._resolve_state_path(self._workspace_state / f".frozen-{task_id}")
            if frozen.exists() or self._read_active_marker() != str(task_id):
                raise WorkspaceBusyError("任务没有当前写租约")
        except WorkspaceBusyError:
            raise
        except WorktreeError:
            raise WorktreeUncertainError("任务写租约状态不确定，需要人工处理") from None

    def is_frozen(self, task_id: UUID) -> bool:
        """仅确认私有 frozen marker 的精确 owner，供 cleanup 跳过冻结现场。"""
        try:
            frozen = self._resolve_state_path(self._workspace_state / f".frozen-{task_id}")
            return frozen.is_file() and frozen.read_text(encoding="ascii") == str(task_id)
        except (OSError, UnicodeDecodeError, WorktreeError):
            return False

    @_marker_lifecycle_locked
    def restore_writer(self, task_id: UUID) -> None:
        """只在创建子任务前的确定失败路径恢复父任务写租约。"""
        try:
            frozen = self._resolve_state_path(self._workspace_state / f".frozen-{task_id}")
            if not frozen.is_file() or frozen.read_text(encoding="ascii") != str(task_id):
                raise WorktreeUncertainError("父任务冻结状态不确定，需要人工处理")
            if self._active_marker.exists():
                raise WorkspaceBusyError("Workspace 已有写任务")
            self._acquire_active_marker(task_id)
            frozen.unlink()
        except (WorktreeUncertainError, WorkspaceBusyError):
            raise
        except (OSError, UnicodeDecodeError, WorktreeError):
            raise WorktreeUncertainError("父任务写租约恢复结果不确定，需要人工处理") from None

    @_marker_lifecycle_locked
    def create(self, task_id: UUID, base_commit: str) -> WorktreeInfo:
        self._validate_git_root()
        resolved_base = self._resolve_base_commit(base_commit)
        branch = f"harness/task-{task_id.hex[:8]}"
        workspace_state = self._resolve_state_path(self._workspace_state)
        target = self._resolve_state_path(workspace_state / str(task_id))
        if self._branch_exists(branch) or target.exists() or target.is_symlink():
            raise WorktreeConflictError("任务分支或工作树已存在")

        tracked = self._git.run(
            self._git_root,
            ["ls-tree", "-r", "--name-only", "-z", resolved_base],
        )
        if tracked.returncode != 0:
            raise WorktreeCreationError("无法审计任务工作树")
        self._git.assert_filter_free(self._git_root, resolved_base, tracked.stdout)

        workspace_state.mkdir(parents=True, exist_ok=True)
        workspace_state = self._resolve_state_path(workspace_state)
        target = self._resolve_state_path(workspace_state / str(task_id))
        self._acquire_active_marker(task_id)
        target = self._resolve_state_path(target)
        try:
            result = self._git.run(
                self._git_root,
                [
                    "worktree",
                    "add",
                    "--no-checkout",
                    "-b",
                    branch,
                    str(target),
                    resolved_base,
                ]
            )
        except GitProcessNotStartedError:
            try:
                self._remove_active_marker()
            except WorktreeStateError:
                raise WorktreeUncertainError(
                    "创建任务工作树结果不确定，需人工处理"
                ) from None
            raise WorktreeCreationError("创建任务工作树失败") from None
        except Exception:
            raise WorktreeUncertainError("创建任务工作树结果不确定，需人工处理") from None
        if result.returncode != 0:
            raise WorktreeUncertainError("创建任务工作树结果不确定，需人工处理")
        try:
            self._git.trust_linked_worktree(target, self._git_root)
            read_tree = self._git.run(
                target,
                ["read-tree", "--reset", resolved_base],
            )
            if read_tree.returncode != 0:
                raise WorktreeUncertainError(
                    "创建任务工作树结果不确定，需人工处理"
                )
            self._git.assert_current_filter_free(target, tracked.stdout)
            materialized = self._git.run(target, ["checkout-index", "--all"])
            if materialized.returncode != 0:
                raise WorktreeUncertainError(
                    "创建任务工作树结果不确定，需人工处理"
                )
        except GitProcessNotStartedError:
            raise WorktreeUncertainError(
                "创建任务工作树结果不确定，需人工处理"
            ) from None
        except WorktreeUncertainError:
            raise
        except Exception:
            raise WorktreeUncertainError(
                "创建任务工作树结果不确定，需人工处理"
            ) from None
        self._validate_created_worktree(target, branch, resolved_base)
        return WorktreeInfo(
            workspace_id=self._workspace.id,
            task_id=task_id,
            path=target,
            branch=branch,
            base_commit=resolved_base,
        )

    @_marker_lifecycle_locked
    def release(self, task_id: UUID) -> None:
        try:
            marker_task = self._read_active_marker()
        except WorktreeStateError:
            raise WorktreeUncertainError("任务工作树路径身份变化，需人工处理") from None
        if marker_task != str(task_id):
            raise WorktreeReleaseError("任务工作树不存在")
        try:
            target = self._resolve_state_path(self._workspace_state / str(task_id))
        except WorktreeStateError:
            raise WorktreeUncertainError("任务工作树路径身份变化，需人工处理") from None
        try:
            self._git.trust_linked_worktree(target, self._git_root)
            tracked = self._git.run(target, ["ls-files", "-z"])
            if tracked.returncode != 0:
                raise WorktreeReleaseError("无法检查任务工作树状态")
            self._git.assert_current_filter_free(target, tracked.stdout)
            status = self._git.run(target, ["status", "--porcelain=v1"])
        except GitSafetyError:
            raise
        except Exception:
            raise WorktreeReleaseError("无法检查任务工作树状态") from None
        if status.returncode != 0:
            raise WorktreeReleaseError("任务工作树不存在")
        if status.stdout:
            raise WorktreeReleaseError("任务工作树包含未提交改动")
        try:
            removed = self._git.run(
                self._git_root,
                ["worktree", "remove", str(target)],
            )
        except GitProcessNotStartedError:
            raise WorktreeReleaseError("释放任务工作树失败") from None
        except Exception:
            raise WorktreeUncertainError(
                "释放任务工作树结果不确定，需人工处理"
            ) from None
        if removed.returncode != 0:
            raise WorktreeUncertainError("释放任务工作树结果不确定，需人工处理")
        self._validate_released_worktree(target)
        try:
            self._remove_active_marker()
        except WorktreeStateError:
            raise WorktreeUncertainError(
                "释放任务工作树后验验证失败，需人工处理"
            ) from None

    def _validate_git_root(self) -> None:
        try:
            marker_stat = (self._git_root / ".git").lstat()
        except OSError:
            raise NotGitRepositoryError("Workspace 不是 Git 根目录") from None
        if is_symlink_or_reparse(marker_stat) or not stat.S_ISDIR(marker_stat.st_mode):
            raise NotGitRepositoryError("Workspace 不是 Git 根目录")
        result = self._git.run(self._git_root, ["rev-parse", "--show-toplevel"])
        if result.returncode != 0:
            raise NotGitRepositoryError("Workspace 不是 Git 根目录")
        try:
            reported_root = Path(result.stdout.decode("utf-8").strip()).resolve(strict=True)
        except (UnicodeDecodeError, OSError, RuntimeError):
            raise NotGitRepositoryError("Workspace 不是 Git 根目录") from None
        try:
            matches_git_root = same_path(reported_root, self._git_root)
        except UnsafePathNamespaceError:
            matches_git_root = False
        if not matches_git_root:
            raise NotGitRepositoryError("Workspace 不是 Git 根目录")

    def _resolve_base_commit(self, base_commit: str) -> str:
        if not base_commit or "\x00" in base_commit:
            raise BaseCommitError("基准提交不存在")
        result = self._git.run(
            self._git_root,
            [
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
        result = self._git.run(
            self._git_root,
            [
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
        marker = self._resolve_state_path(self._active_marker)
        try:
            descriptor = os.open(
                marker,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            try:
                active_task = self._read_active_marker()
                active_task_id = UUID(active_task) if active_task is not None else None
            except (ValueError, WorktreeError):
                raise WorktreeUncertainError(
                    "Workspace 活动任务归属不确定，需人工处理"
                ) from None
            if active_task_id is None:
                raise WorktreeUncertainError(
                    "Workspace 活动任务归属不确定，需人工处理"
                )
            raise WorkspaceBusyError(
                "Workspace 已有写任务",
                active_task_id=active_task_id,
            ) from None
        except OSError:
            raise WorktreeCreationError("无法记录 Workspace 写任务") from None
        try:
            os.write(descriptor, str(task_id).encode("ascii"))
        finally:
            os.close(descriptor)

    def _validate_created_worktree(
        self,
        target: Path,
        branch: str,
        base_commit: str,
    ) -> None:
        try:
            safe_target = self._resolve_state_path(target)
            if not same_path(safe_target, target) or not safe_target.is_dir():
                raise WorktreeUncertainError(
                    "创建任务工作树后验验证失败，需人工处理"
                )
            root_result = self._git.run(
                safe_target,
                ["rev-parse", "--show-toplevel"],
            )
            if root_result.returncode != 0:
                raise WorktreeUncertainError(
                    "创建任务工作树后验验证失败，需人工处理"
                )
            reported_root = Path(root_result.stdout.decode("utf-8").strip()).resolve(
                strict=True
            )
            registration = self._registration_for(safe_target)
            if (
                not same_path(reported_root, safe_target)
                or registration is None
                or registration[0] != base_commit
                or registration[1] != f"refs/heads/{branch}"
            ):
                raise WorktreeUncertainError(
                    "创建任务工作树后验验证失败，需人工处理"
                )
        except WorktreeUncertainError:
            raise
        except (
            OSError,
            RuntimeError,
            UnicodeDecodeError,
            UnsafePathNamespaceError,
            WorktreeStateError,
        ):
            raise WorktreeUncertainError(
                "创建任务工作树后验验证失败，需人工处理"
            ) from None

    def _validate_released_worktree(self, target: Path) -> None:
        try:
            safe_target = self._resolve_state_path(target)
            if not same_path(safe_target, target) or safe_target.exists():
                raise WorktreeUncertainError(
                    "释放任务工作树后验验证失败，需人工处理"
                )
            registration = self._registration_for(target)
        except (
            OSError,
            RuntimeError,
            UnicodeDecodeError,
            UnsafePathNamespaceError,
            WorktreeStateError,
        ):
            raise WorktreeUncertainError(
                "释放任务工作树后验验证失败，需人工处理"
            ) from None
        if registration is not None:
            raise WorktreeUncertainError(
                "释放任务工作树后验验证失败，需人工处理"
            )

    def _registration_for(self, target: Path) -> tuple[str, str] | None:
        result = self._git.run(
            self._git_root,
            [
                "worktree",
                "list",
                "--porcelain",
            ]
        )
        if result.returncode != 0:
            raise WorktreeUncertainError("Git worktree 注册表不可读取")
        output = result.stdout.decode("utf-8")
        for block in output.split("\n\n"):
            fields: dict[str, str] = {}
            for line in block.splitlines():
                key, separator, value = line.partition(" ")
                if separator:
                    fields[key] = value
            registered_path = fields.get("worktree")
            if registered_path is None:
                continue
            try:
                matches_target = same_path(Path(registered_path), target)
            except UnsafePathNamespaceError:
                raise WorktreeUncertainError("Git worktree 注册表无效") from None
            if matches_target:
                return fields.get("HEAD", ""), fields.get("branch", "")
        return None

    def _read_active_marker(self) -> str | None:
        marker = self._resolve_state_path(self._active_marker)
        try:
            return marker.read_text(encoding="ascii")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError):
            raise WorktreeReleaseError("Workspace 活动标记无效") from None

    def _remove_active_marker(self) -> None:
        marker = self._resolve_state_path(self._active_marker)
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            raise WorktreeStateError("无法清理 Workspace 活动标记") from None

    def _resolve_state_path(self, candidate: Path) -> Path:
        try:
            resolved = self._state_guard.resolve(candidate)
        except PathEscapeError:
            raise WorktreeStateError("Harness 状态子路径越界") from None
        try:
            overlaps_git_root = trusted_paths_overlap(resolved, self._git_root)
        except UnsafePathNamespaceError:
            raise WorktreeStateError("Harness 状态子路径越界") from None
        if overlaps_git_root:
            raise WorktreeStateError("Harness 状态子路径与项目重叠")
        return resolved
