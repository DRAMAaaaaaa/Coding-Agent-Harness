"""不继承仓库可执行配置的 Git 子进程边界。"""

from __future__ import annotations

from collections.abc import Sequence
import os
from pathlib import Path
import shutil
import tempfile

from coding_agent_harness.workspace.processes import (
    CommandResult,
    ProcessRequest,
    ProcessRunner,
    SubprocessGitRunner,
)


class GitSafetyError(ValueError):
    """无法建立确定性的 Git 安全边界。"""


class UnsupportedGitFilterError(GitSafetyError):
    """仓库提交或工作树启用了外部 checkout filter。"""


class SafeGit:
    """固定 Git 可执行文件、配置、属性与宿主环境。"""

    def __init__(
        self,
        state_root: str | Path,
        *,
        git_executable: str | Path | None = None,
        runner: ProcessRunner | None = None,
    ) -> None:
        executable = git_executable or shutil.which("git")
        if executable is None:
            raise GitSafetyError("Git 可执行文件无效")
        try:
            self._git_executable = Path(executable).resolve(strict=True)
        except (OSError, RuntimeError):
            raise GitSafetyError("Git 可执行文件无效") from None
        if not self._git_executable.is_file() or not self._git_executable.is_absolute():
            raise GitSafetyError("Git 可执行文件无效")
        try:
            self._state_root = Path(state_root).resolve(strict=False)
            self._state_root.mkdir(parents=True, exist_ok=True)
        except (OSError, RuntimeError):
            raise GitSafetyError("Git 安全状态目录无效") from None
        self._safety_root = self._state_root / "git-safety"
        self._hooks_dir = self._safety_root / "hooks"
        self._global_config = self._safety_root / "global.gitconfig"
        self._global_attributes = self._safety_root / "global.gitattributes"
        self._prepare_safety_assets()
        self._runner = runner or SubprocessGitRunner()

    def run(
        self,
        root: str | Path,
        args: Sequence[str],
        stdin: bytes = b"",
    ) -> CommandResult:
        return self._run(root, args, stdin=stdin)

    def assert_filter_free(
        self,
        root: str | Path,
        commit: str,
        tracked_paths: bytes,
    ) -> None:
        """只读提交属性；在任何 checkout 发生前拒绝活动 filter。"""
        if not commit or "\x00" in commit:
            raise GitSafetyError("Git filter 审计提交无效")
        self._validate_path_stream(tracked_paths)
        descriptor, raw_index = tempfile.mkstemp(
            prefix="filter-index-",
            dir=self._safety_root,
        )
        os.close(descriptor)
        index = Path(raw_index)
        try:
            index.unlink()
            read_tree = self._run(
                root,
                ["read-tree", "--reset", commit],
                index_file=index,
            )
            if read_tree.returncode != 0:
                raise GitSafetyError("无法建立 Git filter 审计索引")
            checked = self._run(
                root,
                ["check-attr", "--cached", "-z", "--stdin", "filter"],
                stdin=tracked_paths,
                index_file=index,
            )
            if checked.returncode != 0:
                raise GitSafetyError("无法审计 Git filter")
            self._assert_filter_output_free(checked.stdout)
        finally:
            try:
                index.unlink(missing_ok=True)
            except OSError:
                raise GitSafetyError("无法清理 Git filter 审计索引") from None

    def assert_current_filter_free(
        self,
        root: str | Path,
        tracked_paths: bytes,
    ) -> None:
        """同时审计当前 index 与工作树属性，供 release 前重审。"""
        self._validate_path_stream(tracked_paths)
        for cached in (True, False):
            args = ["check-attr"]
            if cached:
                args.append("--cached")
            args.extend(["-z", "--stdin", "filter"])
            checked = self._run(root, args, stdin=tracked_paths)
            if checked.returncode != 0:
                raise GitSafetyError("无法审计 Git filter")
            self._assert_filter_output_free(checked.stdout)

    def _run(
        self,
        root: str | Path,
        args: Sequence[str],
        *,
        stdin: bytes = b"",
        index_file: Path | None = None,
    ) -> CommandResult:
        try:
            repository = Path(root).resolve(strict=True)
        except (OSError, RuntimeError):
            raise GitSafetyError("Git 工作目录无效") from None
        config = (
            "core.fsmonitor=",
            f"core.hooksPath={self._hooks_dir}",
            f"core.attributesFile={self._global_attributes}",
            "gc.auto=0",
            "maintenance.auto=false",
        )
        config_args = tuple(item for value in config for item in ("-c", value))
        return self._runner.run(
            ProcessRequest(
                argv=(
                    str(self._git_executable),
                    *config_args,
                    "-C",
                    str(repository),
                    *args,
                ),
                cwd=repository,
                env=self._safe_environment(index_file=index_file),
                stdin=stdin,
            )
        )

    def _prepare_safety_assets(self) -> None:
        try:
            if self._safety_root.is_symlink() or self._hooks_dir.is_symlink():
                raise GitSafetyError("Git 安全状态目录无效")
            self._hooks_dir.mkdir(parents=True, exist_ok=True)
            if not self._hooks_dir.is_dir() or any(self._hooks_dir.iterdir()):
                raise GitSafetyError("Git hooks 安全目录必须为空")
            for path in (self._global_config, self._global_attributes):
                if path.is_symlink():
                    raise GitSafetyError("Git 安全配置文件无效")
                try:
                    path.open("xb").close()
                except FileExistsError:
                    pass
                if not path.is_file() or path.stat().st_size != 0:
                    raise GitSafetyError("Git 安全配置文件必须为空")
        except GitSafetyError:
            raise
        except OSError:
            raise GitSafetyError("Git 安全状态目录无效") from None

    def _safe_environment(self, *, index_file: Path | None = None) -> dict[str, str]:
        allowed_host_names = {
            "COMSPEC",
            "NUMBER_OF_PROCESSORS",
            "PATHEXT",
            "PROCESSOR_ARCHITECTURE",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "WINDIR",
        }
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in allowed_host_names
        }
        environment.update(
            {
                "GIT_CONFIG_GLOBAL": str(self._global_config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_ALLOW_PROTOCOL": ":",
                "GIT_PROTOCOL_FROM_USER": "0",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "LC_ALL": "C.UTF-8",
            }
        )
        if index_file is not None:
            environment["GIT_INDEX_FILE"] = str(index_file)
        return environment

    @staticmethod
    def _validate_path_stream(raw: bytes) -> None:
        if raw and (not raw.endswith(b"\0") or b"\0\0" in raw):
            raise GitSafetyError("Git 跟踪文件列表无效")

    @staticmethod
    def _assert_filter_output_free(raw: bytes) -> None:
        if not raw:
            return
        fields = raw.split(b"\0")
        if fields[-1] != b"":
            raise GitSafetyError("Git filter 审计输出无效")
        fields.pop()
        if len(fields) % 3:
            raise GitSafetyError("Git filter 审计输出无效")
        for index in range(0, len(fields), 3):
            path, attribute, value = fields[index : index + 3]
            if not path or attribute != b"filter" or not value:
                raise GitSafetyError("Git filter 审计输出无效")
            if value not in {b"unspecified", b"unset"}:
                raise UnsupportedGitFilterError("仓库启用了不支持的 Git filter")
