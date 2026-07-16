"""为每个写任务创建位于 Harness 状态目录的独立 Git worktree。"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.workspace.models import Workspace, WorktreeInfo
from coding_agent_harness.workspace.processes import (
    GitProcessNotStartedError,
    GitRunner,
    SubprocessGitRunner,
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


class WorktreeConflictError(WorktreeError):
    """任务分支或目标目录已经存在。"""


class WorktreeCreationError(WorktreeError):
    """Git 无法创建隔离工作树。"""


class WorktreeReleaseError(WorktreeError):
    """工作树无法安全释放。"""


class WorktreeUncertainError(WorktreeError):
    """Git 副作用结果无法安全确认，需要人工接管。"""


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
        if (
            self._state_root == self._git_root
            or self._state_root.is_relative_to(self._git_root)
            or self._git_root.is_relative_to(self._state_root)
        ):
            raise WorktreeStateError("Harness 状态目录必须位于项目外")
        try:
            self._state_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise WorktreeStateError("Harness 状态目录无效") from None
        self._state_guard = PathGuard(self._state_root)
        self._workspace_state = self._resolve_state_path(
            self._state_root / "worktrees" / str(workspace.id)
        )
        self._active_marker = self._workspace_state / ".active"

    def create(self, task_id: UUID, base_commit: str) -> WorktreeInfo:
        self._validate_git_root()
        resolved_base = self._resolve_base_commit(base_commit)
        branch = f"harness/task-{task_id.hex[:8]}"
        workspace_state = self._resolve_state_path(self._workspace_state)
        target = self._resolve_state_path(workspace_state / str(task_id))
        if self._branch_exists(branch) or target.exists() or target.is_symlink():
            raise WorktreeConflictError("任务分支或工作树已存在")

        workspace_state.mkdir(parents=True, exist_ok=True)
        workspace_state = self._resolve_state_path(workspace_state)
        target = self._resolve_state_path(workspace_state / str(task_id))
        self._acquire_active_marker(task_id)
        target = self._resolve_state_path(target)
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
        self._validate_created_worktree(target, branch, resolved_base)
        return WorktreeInfo(
            workspace_id=self._workspace.id,
            task_id=task_id,
            path=target,
            branch=branch,
            base_commit=resolved_base,
        )

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
            status = self._runner.run(
                ["git", "-C", str(target), "status", "--porcelain=v1"]
            )
        except Exception:
            raise WorktreeReleaseError("无法检查任务工作树状态") from None
        if status.returncode != 0:
            raise WorktreeReleaseError("任务工作树不存在")
        if status.stdout:
            raise WorktreeReleaseError("任务工作树包含未提交改动")
        try:
            removed = self._runner.run(
                ["git", "-C", str(self._git_root), "worktree", "remove", str(target)]
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
        marker = self._resolve_state_path(self._active_marker)
        try:
            descriptor = os.open(
                marker,
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

    def _validate_created_worktree(
        self,
        target: Path,
        branch: str,
        base_commit: str,
    ) -> None:
        try:
            safe_target = self._resolve_state_path(target)
            if safe_target != target or not safe_target.is_dir():
                raise WorktreeUncertainError(
                    "创建任务工作树后验验证失败，需人工处理"
                )
            root_result = self._runner.run(
                ["git", "-C", str(safe_target), "rev-parse", "--show-toplevel"]
            )
            if root_result.returncode != 0:
                raise WorktreeUncertainError(
                    "创建任务工作树后验验证失败，需人工处理"
                )
            reported_root = Path(root_result.stdout.decode("utf-8").strip()).resolve(
                strict=True
            )
            registration = self._registration_for(safe_target)
        except (OSError, RuntimeError, UnicodeDecodeError, WorktreeStateError):
            raise WorktreeUncertainError(
                "创建任务工作树后验验证失败，需人工处理"
            ) from None
        if (
            reported_root != safe_target
            or registration is None
            or registration[0] != base_commit
            or registration[1] != f"refs/heads/{branch}"
        ):
            raise WorktreeUncertainError(
                "创建任务工作树后验验证失败，需人工处理"
            )

    def _validate_released_worktree(self, target: Path) -> None:
        try:
            safe_target = self._resolve_state_path(target)
            if safe_target != target or safe_target.exists():
                raise WorktreeUncertainError(
                    "释放任务工作树后验验证失败，需人工处理"
                )
            registration = self._registration_for(target)
        except (OSError, RuntimeError, UnicodeDecodeError, WorktreeStateError):
            raise WorktreeUncertainError(
                "释放任务工作树后验验证失败，需人工处理"
            ) from None
        if registration is not None:
            raise WorktreeUncertainError(
                "释放任务工作树后验验证失败，需人工处理"
            )

    def _registration_for(self, target: Path) -> tuple[str, str] | None:
        result = self._runner.run(
            [
                "git",
                "-C",
                str(self._git_root),
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
                resolved_path = Path(registered_path).resolve(strict=False)
            except (OSError, RuntimeError):
                raise WorktreeUncertainError("Git worktree 注册表无效") from None
            if resolved_path == target:
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
        if resolved == self._git_root or resolved.is_relative_to(self._git_root):
            raise WorktreeStateError("Harness 状态子路径与项目重叠")
        return resolved
