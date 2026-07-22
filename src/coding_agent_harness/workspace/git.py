"""不继承仓库可执行配置的 Git 子进程边界。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import tempfile

from coding_agent_harness.governance.path_identity import (
    UnsafePathNamespaceError,
    is_within,
    same_path,
    windows_anchors_differ,
)
from coding_agent_harness.workspace.files import (
    BoundedFileError,
    BoundedFileReader,
    is_symlink_or_reparse,
)
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


@dataclass(frozen=True)
class _TrustedLinkedWorktree:
    git_dir: Path
    common_git_dir: Path
    marker_identity: os.stat_result
    git_dir_identity: os.stat_result
    common_git_dir_identity: os.stat_result
    commondir_identity: os.stat_result


@dataclass(frozen=True)
class _RepositoryConfigIdentity:
    path: Path
    identity: os.stat_result
    forbidden_worktree_config: Path


_UNSAFE_LOCAL_CONFIG_KEYS = frozenset(
    {
        "core.alternaterefscommand",
        "core.askpass",
        "core.editor",
        "core.excludesfile",
        "core.sshcommand",
        "core.worktree",
        "credential.helper",
        "diff.external",
        "extensions.worktreeconfig",
        "gpg.program",
        "sequence.editor",
    }
)


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
        self._trusted_linked_worktrees: dict[tuple[str, ...], _TrustedLinkedWorktree] = {}
        self._file_reader = BoundedFileReader()
        self._prepare_safety_assets()
        self._runner = runner or SubprocessGitRunner()

    def run(
        self,
        root: str | Path,
        args: Sequence[str],
        stdin: bytes = b"",
    ) -> CommandResult:
        return self._run(root, args, stdin=stdin)

    def trust_linked_worktree(
        self,
        root: str | Path,
        repository_root: str | Path,
    ) -> None:
        """显式验证 Harness 刚创建的 linked-worktree gitfile。"""

        try:
            worktree = Path(root).resolve(strict=True)
            repository = Path(repository_root).resolve(strict=True)
            marker = worktree / ".git"
            marker_stat = marker.lstat()
            if is_symlink_or_reparse(marker_stat) or not stat.S_ISREG(marker_stat.st_mode):
                raise GitSafetyError("Git 工作目录无效")
            main_git_dir = repository / ".git"
            main_git_stat = main_git_dir.lstat()
            if is_symlink_or_reparse(main_git_stat) or not stat.S_ISDIR(
                main_git_stat.st_mode
            ):
                raise GitSafetyError("Git 工作目录无效")
            approved_container = main_git_dir / "worktrees"
            container_stat = approved_container.lstat()
            if is_symlink_or_reparse(container_stat) or not stat.S_ISDIR(
                container_stat.st_mode
            ):
                raise GitSafetyError("Git 工作目录无效")
            git_dir = self._parse_gitfile(marker)
            if windows_anchors_differ(git_dir, approved_container):
                raise GitSafetyError("Git 工作目录无效")
            resolved_git_dir = git_dir.resolve(strict=True)
            if not is_within(resolved_git_dir, approved_container):
                raise GitSafetyError("Git 工作目录无效")
            if not same_path(resolved_git_dir.parent, approved_container):
                raise GitSafetyError("Git 工作目录无效")
            git_dir_stat = resolved_git_dir.lstat()
            if is_symlink_or_reparse(git_dir_stat) or not stat.S_ISDIR(
                git_dir_stat.st_mode
            ):
                raise GitSafetyError("Git 工作目录无效")
            commondir_path = resolved_git_dir / "commondir"
            commondir_identity = commondir_path.lstat()
            if is_symlink_or_reparse(commondir_identity) or not stat.S_ISREG(
                commondir_identity.st_mode
            ):
                raise GitSafetyError("Git 工作目录无效")
            commondir = self._file_reader.read(commondir_path, 64)
            if commondir.strip() not in {b"../..", b"..\\.."}:
                raise GitSafetyError("Git 工作目录无效")
            self._trusted_linked_worktrees[self._repository_key(worktree)] = (
                _TrustedLinkedWorktree(
                    git_dir=resolved_git_dir,
                    common_git_dir=main_git_dir,
                    marker_identity=marker_stat,
                    git_dir_identity=git_dir_stat,
                    common_git_dir_identity=main_git_stat,
                    commondir_identity=commondir_identity,
                )
            )
        except GitSafetyError:
            raise
        except (
            BoundedFileError,
            FileNotFoundError,
            OSError,
            RuntimeError,
            UnsafePathNamespaceError,
        ):
            raise GitSafetyError("Git 工作目录无效") from None

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
        config_identity = self._validate_repository_context(repository)
        audit = self._run_config_audit(config_identity.path)
        if audit.returncode != 0:
            raise GitSafetyError("无法审计 Git 仓库本地配置")
        self._verify_repository_config(config_identity)
        self._validate_local_config(audit.stdout)
        return self._run_unchecked(
            repository,
            args,
            stdin=stdin,
            index_file=index_file,
        )

    def _run_config_audit(self, config: Path) -> CommandResult:
        """只审计已验证的精确文件，不触发 Git repository discovery。"""
        return self._runner.run(
            ProcessRequest(
                argv=(
                    str(self._git_executable),
                    "config",
                    "--file",
                    str(config),
                    "--no-includes",
                    "-z",
                    "--list",
                ),
                cwd=self._safety_root,
                env=self._safe_environment(),
                stdin=b"",
            )
        )

    def _run_unchecked(
        self,
        repository: Path,
        args: Sequence[str],
        *,
        stdin: bytes = b"",
        index_file: Path | None = None,
    ) -> CommandResult:
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
            state_identity = self._verified_directory(self._state_root)
            safety_identity = self._ensure_verified_directory(self._safety_root)
            hooks_identity = self._ensure_verified_directory(self._hooks_dir)
            if not same_path(self._safety_root.parent, self._state_root):
                raise GitSafetyError("Git 安全状态目录无效")
            if not same_path(self._hooks_dir.parent, self._safety_root):
                raise GitSafetyError("Git 安全状态目录无效")
            if any(self._hooks_dir.iterdir()):
                raise GitSafetyError("Git hooks 安全目录必须为空")
            file_identities: dict[Path, os.stat_result] = {}
            for path in (self._global_config, self._global_attributes):
                file_identities[path] = self._ensure_empty_regular_file(path)
            if not os.path.samestat(state_identity, self._state_root.lstat()):
                raise GitSafetyError("Git 安全状态目录无效")
            if not os.path.samestat(safety_identity, self._safety_root.lstat()):
                raise GitSafetyError("Git 安全状态目录无效")
            if not os.path.samestat(hooks_identity, self._hooks_dir.lstat()):
                raise GitSafetyError("Git 安全状态目录无效")
            for path, identity in file_identities.items():
                if not os.path.samestat(identity, path.lstat()):
                    raise GitSafetyError("Git 安全配置文件无效")
        except GitSafetyError:
            raise
        except (OSError, UnsafePathNamespaceError):
            raise GitSafetyError("Git 安全状态目录无效") from None

    @staticmethod
    def _verified_directory(path: Path) -> os.stat_result:
        identity = path.lstat()
        if is_symlink_or_reparse(identity) or not stat.S_ISDIR(identity.st_mode):
            raise GitSafetyError("Git 安全状态目录无效")
        return identity

    def _ensure_verified_directory(self, path: Path) -> os.stat_result:
        try:
            identity = path.lstat()
        except FileNotFoundError:
            path.mkdir()
            identity = path.lstat()
        if is_symlink_or_reparse(identity) or not stat.S_ISDIR(identity.st_mode):
            raise GitSafetyError("Git 安全状态目录无效")
        return identity

    def _ensure_empty_regular_file(self, path: Path) -> os.stat_result:
        try:
            identity = path.lstat()
        except FileNotFoundError:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags, 0o600)
            os.close(descriptor)
            identity = path.lstat()
        if is_symlink_or_reparse(identity) or not stat.S_ISREG(identity.st_mode):
            raise GitSafetyError("Git 安全配置文件无效")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened_identity = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        current_identity = path.stat(follow_symlinks=False)
        if (
            identity.st_size != 0
            or not os.path.samestat(identity, opened_identity)
            or not os.path.samestat(identity, current_identity)
            or not same_path(path.parent, self._safety_root)
        ):
            raise GitSafetyError("Git 安全配置文件必须为空")
        return identity

    def _validate_repository_context(
        self,
        repository: Path,
    ) -> _RepositoryConfigIdentity:
        marker = repository / ".git"
        try:
            marker_stat = marker.lstat()
        except OSError:
            raise GitSafetyError("Git 工作目录无效") from None
        if is_symlink_or_reparse(marker_stat):
            raise GitSafetyError("Git 工作目录无效")
        if stat.S_ISDIR(marker_stat.st_mode):
            self._reject_primary_commondir(marker)
            return self._repository_config_identity(marker, marker)
        if not stat.S_ISREG(marker_stat.st_mode):
            raise GitSafetyError("Git 工作目录无效")
        trusted = self._trusted_linked_worktrees.get(self._repository_key(repository))
        if trusted is None:
            raise GitSafetyError("Git 工作目录无效")
        try:
            if not os.path.samestat(marker_stat, trusted.marker_identity):
                raise GitSafetyError("Git 工作目录无效")
            current_git_dir = self._parse_gitfile(marker)
            if windows_anchors_differ(current_git_dir, trusted.git_dir):
                raise GitSafetyError("Git 工作目录无效")
            resolved_git_dir = current_git_dir.resolve(strict=True)
            if not same_path(resolved_git_dir, trusted.git_dir):
                raise GitSafetyError("Git 工作目录无效")
            if not os.path.samestat(resolved_git_dir.lstat(), trusted.git_dir_identity):
                raise GitSafetyError("Git 工作目录无效")
            if not os.path.samestat(
                trusted.common_git_dir.lstat(),
                trusted.common_git_dir_identity,
            ):
                raise GitSafetyError("Git 工作目录无效")
            commondir_path = trusted.git_dir / "commondir"
            commondir_identity = commondir_path.lstat()
            if (
                is_symlink_or_reparse(commondir_identity)
                or not stat.S_ISREG(commondir_identity.st_mode)
                or not os.path.samestat(
                    commondir_identity,
                    trusted.commondir_identity,
                )
                or self._file_reader.read(commondir_path, 64).strip()
                not in {b"../..", b"..\\.."}
            ):
                raise GitSafetyError("Git 工作目录无效")
            return self._repository_config_identity(
                trusted.common_git_dir,
                trusted.git_dir,
            )
        except GitSafetyError:
            raise
        except (BoundedFileError, OSError, RuntimeError, UnsafePathNamespaceError):
            raise GitSafetyError("Git 工作目录无效") from None

    @staticmethod
    def _reject_primary_commondir(git_dir: Path) -> None:
        try:
            (git_dir / "commondir").lstat()
        except FileNotFoundError:
            return
        except OSError:
            raise GitSafetyError("Git 工作目录无效") from None
        raise GitSafetyError("Git 工作目录无效")

    @staticmethod
    def _repository_config_identity(
        common_git_dir: Path,
        worktree_git_dir: Path,
    ) -> _RepositoryConfigIdentity:
        config = common_git_dir / "config"
        try:
            identity = config.lstat()
        except OSError:
            raise GitSafetyError("Git 仓库本地配置不安全") from None
        if (
            is_symlink_or_reparse(identity)
            or not stat.S_ISREG(identity.st_mode)
            or identity.st_size > 1024 * 1024
        ):
            raise GitSafetyError("Git 仓库本地配置不安全")
        forbidden_worktree_config = worktree_git_dir / "config.worktree"
        try:
            forbidden_worktree_config.lstat()
        except FileNotFoundError:
            pass
        except OSError:
            raise GitSafetyError("Git 仓库本地配置不安全") from None
        else:
            raise GitSafetyError("Git 仓库本地配置不安全")
        return _RepositoryConfigIdentity(
            path=config,
            identity=identity,
            forbidden_worktree_config=forbidden_worktree_config,
        )

    @staticmethod
    def _verify_repository_config(config: _RepositoryConfigIdentity) -> None:
        try:
            current = config.path.lstat()
        except OSError:
            raise GitSafetyError("Git 仓库本地配置不安全") from None
        if (
            is_symlink_or_reparse(current)
            or not stat.S_ISREG(current.st_mode)
            or not os.path.samestat(config.identity, current)
            or current.st_size != config.identity.st_size
            or current.st_mtime_ns != config.identity.st_mtime_ns
        ):
            raise GitSafetyError("Git 仓库本地配置不安全")
        try:
            config.forbidden_worktree_config.lstat()
        except FileNotFoundError:
            return
        except OSError:
            raise GitSafetyError("Git 仓库本地配置不安全") from None
        raise GitSafetyError("Git 仓库本地配置不安全")

    def _parse_gitfile(self, marker: Path) -> Path:
        raw = self._file_reader.read(marker, 4096)
        try:
            line = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise GitSafetyError("Git 工作目录无效") from None
        prefix = "gitdir: "
        if not line.startswith(prefix) or "\n" in line or "\r" in line:
            raise GitSafetyError("Git 工作目录无效")
        candidate = Path(line[len(prefix) :])
        if not candidate.is_absolute():
            candidate = marker.parent / candidate
        return candidate

    @staticmethod
    def _repository_key(repository: Path) -> tuple[str, ...]:
        from coding_agent_harness.governance.path_identity import path_key

        return path_key(repository)

    @staticmethod
    def _validate_local_config(raw: bytes) -> None:
        if raw and not raw.endswith(b"\0"):
            raise GitSafetyError("Git 仓库本地配置输出无效")
        for record in raw.split(b"\0")[:-1]:
            key_raw, separator, _value = record.partition(b"\n")
            if not separator or not key_raw:
                raise GitSafetyError("Git 仓库本地配置输出无效")
            try:
                key = key_raw.decode("ascii").casefold()
            except UnicodeDecodeError:
                raise GitSafetyError("Git 仓库本地配置输出无效") from None
            include_key = key == "include.path" or (
                key.startswith("includeif.") and key.endswith(".path")
            )
            unsafe_driver = (
                (key.startswith("diff.") and key.endswith((".command", ".textconv")))
                or (key.startswith("merge.") and key.endswith(".driver"))
                or (key.startswith("gpg.") and key.endswith(".program"))
            )
            if include_key or unsafe_driver or key in _UNSAFE_LOCAL_CONFIG_KEYS:
                raise GitSafetyError("Git 仓库本地配置不安全")

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
