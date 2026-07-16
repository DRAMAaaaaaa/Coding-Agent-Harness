"""通过只读 Git argv 命令生成有界仓库地图。"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import time
from typing import BinaryIO, Protocol, cast

from coding_agent_harness.workspace.models import RepositoryDocument, RepositoryMap
from coding_agent_harness.workspace.files import (
    BinaryFileOpener,
    BoundedFileReadError,
    BoundedFileReader,
    BoundedFileTooLargeError,
    UnsafeBoundedFileError,
)

_MAX_TRACKED_FILES = 10_000
# 64 MiB 可容纳 10,000 条平均约 6.7 KiB 的 Git 路径，同时给错误输出留出同等上限。
DEFAULT_GIT_TIMEOUT_SECONDS = 300.0
DEFAULT_GIT_STDOUT_LIMIT_BYTES = 64 * 1024 * 1024
DEFAULT_GIT_STDERR_LIMIT_BYTES = 64 * 1024 * 1024
_OUTPUT_POLL_SECONDS = 0.05
_CLEANUP_TIMEOUT_SECONDS = 1.0
_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)
_DOCUMENT_NAMES = frozenset(
    {
        ".harness.yml",
        "agents.md",
        "package.json",
        "pyproject.toml",
        "readme",
        "readme.md",
        "readme.rst",
        "readme.txt",
    }
)


class RepositoryScanError(ValueError):
    """Git 仓库无法在安全边界内生成地图。"""


class WorkspaceLimitError(RepositoryScanError):
    """仓库超过正式支持的跟踪文件数量。"""


class GitProcessNotStartedError(OSError):
    """Git 子进程构造失败，能够确认从未启动。"""


class GitProcessUncertainError(OSError):
    """Git 子进程已启动或启动状态无法安全确认。"""


@dataclass(frozen=True)
class CommandResult:
    """子进程边界返回的最小结果。"""

    returncode: int
    stdout: bytes
    stderr: bytes


class GitRunner(Protocol):
    """唯一可注入的 Git 子进程边界。"""

    def run(self, argv: Sequence[str]) -> CommandResult: ...


class SubprocessGitRunner:
    """以 300 秒和每流 64 MiB 默认上限执行 Git argv。"""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_GIT_TIMEOUT_SECONDS,
        max_stdout_bytes: int = DEFAULT_GIT_STDOUT_LIMIT_BYTES,
        max_stderr_bytes: int = DEFAULT_GIT_STDERR_LIMIT_BYTES,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise ValueError("Git 超时必须为正数")
        if (
            isinstance(max_stdout_bytes, bool)
            or not isinstance(max_stdout_bytes, int)
            or max_stdout_bytes < 1
            or isinstance(max_stderr_bytes, bool)
            or not isinstance(max_stderr_bytes, int)
            or max_stderr_bytes < 1
        ):
            raise ValueError("Git 输出上限必须为正整数")
        self._timeout_seconds = float(timeout_seconds)
        self._max_stdout_bytes = max_stdout_bytes
        self._max_stderr_bytes = max_stderr_bytes

    def run(self, argv: Sequence[str]) -> CommandResult:
        with ExitStack() as resources:
            try:
                stdout_buffer = cast(
                    BinaryIO,
                    resources.enter_context(tempfile.TemporaryFile()),
                )
                stderr_buffer = cast(
                    BinaryIO,
                    resources.enter_context(tempfile.TemporaryFile()),
                )
            except OSError:
                raise GitProcessNotStartedError("Git 进程未启动") from None
            try:
                process = subprocess.Popen(
                    list(argv),
                    stdout=stdout_buffer,
                    stderr=stderr_buffer,
                )
            except OSError:
                raise GitProcessNotStartedError("Git 进程未启动") from None
            try:
                self._communicate_bounded(process, stdout_buffer, stderr_buffer)
                if process.returncode is None:
                    raise RuntimeError("Git 进程缺少退出状态")
                stdout = self._read_bounded(
                    stdout_buffer, self._max_stdout_bytes
                )
                stderr = self._read_bounded(
                    stderr_buffer, self._max_stderr_bytes
                )
            except Exception:
                self._cleanup_started_process(process)
                raise GitProcessUncertainError("Git 进程状态不确定") from None
            return CommandResult(
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
            )

    def _communicate_bounded(
        self,
        process: subprocess.Popen[bytes],
        stdout_buffer: BinaryIO,
        stderr_buffer: BinaryIO,
    ) -> None:
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            self._check_output_limits(stdout_buffer, stderr_buffer)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, self._timeout_seconds)
            try:
                process.communicate(timeout=min(_OUTPUT_POLL_SECONDS, remaining))
            except subprocess.TimeoutExpired:
                self._check_output_limits(stdout_buffer, stderr_buffer)
                continue
            self._check_output_limits(stdout_buffer, stderr_buffer)
            return

    def _check_output_limits(
        self,
        stdout_buffer: BinaryIO,
        stderr_buffer: BinaryIO,
    ) -> None:
        stdout_buffer.flush()
        stderr_buffer.flush()
        if (
            os.fstat(stdout_buffer.fileno()).st_size > self._max_stdout_bytes
            or os.fstat(stderr_buffer.fileno()).st_size > self._max_stderr_bytes
        ):
            raise RuntimeError("Git 输出超过上限")

    @staticmethod
    def _read_bounded(buffer: BinaryIO, limit: int) -> bytes:
        buffer.flush()
        buffer.seek(0)
        output = buffer.read(limit + 1)
        if len(output) > limit:
            raise RuntimeError("Git 输出超过上限")
        return output

    @staticmethod
    def _cleanup_started_process(process: subprocess.Popen[bytes]) -> None:
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.communicate(timeout=_CLEANUP_TIMEOUT_SECONDS)
        except Exception:
            pass
        try:
            process.wait(timeout=_CLEANUP_TIMEOUT_SECONDS)
        except Exception:
            pass


class WorkspaceScanner:
    """从跟踪文件和只读 Git 元数据构建 RepositoryMap。"""

    def __init__(
        self,
        runner: GitRunner | None = None,
        *,
        max_document_bytes: int = 128 * 1024,
        file_opener: BinaryFileOpener | None = None,
    ) -> None:
        if max_document_bytes < 1:
            raise ValueError("文档大小上限必须为正数")
        self._runner = runner or SubprocessGitRunner()
        self._max_document_bytes = max_document_bytes
        self._file_reader = BoundedFileReader(file_opener)

    def scan(self, root: str | Path) -> RepositoryMap:
        project_root = self._resolve_root(root)
        self._validate_git_root_marker(project_root)
        root_argument = str(project_root)
        tracked_result = self._run_git(
            ["git", "-C", root_argument, "ls-files", "-z"]
        )
        tracked_files = self._parse_tracked_files(tracked_result.stdout)
        if len(tracked_files) > _MAX_TRACKED_FILES:
            raise WorkspaceLimitError("仓库跟踪文件超过 10000 个")

        filtered_files = [
            path for path in tracked_files if not self._is_ignored(path)
        ]
        for relative_path in filtered_files:
            self._validate_tracked_path(project_root, relative_path)

        log_result = self._run_git(
            ["git", "-C", root_argument, "log", "-n", "20"]
        )
        status_result = self._run_git(
            ["git", "-C", root_argument, "status", "--porcelain=v1", "-z"]
        )
        documents = self._read_documents(project_root, filtered_files)
        test_paths = [path for path in filtered_files if self._is_test_path(path)]
        return RepositoryMap(
            root=project_root,
            tracked_files=tuple(filtered_files),
            documents=tuple(documents),
            test_paths=tuple(test_paths),
            recent_commits=tuple(self._parse_log(log_result.stdout)),
            dirty_paths=tuple(self._parse_status(status_result.stdout)),
        )

    @staticmethod
    def _resolve_root(root: str | Path) -> Path:
        try:
            resolved = Path(root).resolve(strict=True)
        except (OSError, RuntimeError):
            raise RepositoryScanError("仓库目录无效") from None
        if not resolved.is_dir():
            raise RepositoryScanError("仓库目录无效")
        return resolved

    @staticmethod
    def _validate_git_root_marker(root: Path) -> None:
        marker = root / ".git"
        if marker.is_symlink() or not (marker.is_file() or marker.is_dir()):
            raise RepositoryScanError("所选目录不是 Git 根目录")

    def _run_git(self, argv: list[str]) -> CommandResult:
        try:
            result = self._runner.run(argv)
        except OSError:
            raise RepositoryScanError("无法读取 Git 仓库") from None
        if result.returncode != 0:
            raise RepositoryScanError("无法读取 Git 仓库")
        return result

    @staticmethod
    def _decode(raw: bytes) -> str:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            raise RepositoryScanError("Git 输出不是 UTF-8") from None

    @classmethod
    def _parse_tracked_files(cls, raw: bytes) -> list[str]:
        decoded = cls._decode(raw)
        paths = decoded.split("\0")
        if paths and paths[-1] == "":
            paths.pop()
        if any(not path or "\x00" in path for path in paths):
            raise RepositoryScanError("Git 跟踪文件列表无效")
        return paths

    @staticmethod
    def _is_ignored(relative_path: str) -> bool:
        return bool(set(PurePosixPath(relative_path).parts) & _IGNORED_DIRECTORIES)

    @staticmethod
    def _validate_tracked_path(root: Path, relative_path: str) -> None:
        portable_path = PurePosixPath(relative_path)
        if portable_path.is_absolute() or ".." in portable_path.parts:
            raise RepositoryScanError("跟踪文件路径越界")
        candidate = root.joinpath(*portable_path.parts)
        if not candidate.exists() and not candidate.is_symlink():
            return
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            raise RepositoryScanError("跟踪文件不可读取") from None
        if not resolved.is_relative_to(root):
            raise RepositoryScanError("跟踪文件路径越界")

    def _read_documents(
        self,
        root: Path,
        tracked_files: list[str],
    ) -> list[RepositoryDocument]:
        documents: list[RepositoryDocument] = []
        for relative_path in tracked_files:
            portable_path = PurePosixPath(relative_path)
            if len(portable_path.parts) != 1:
                continue
            if portable_path.name.lower() not in _DOCUMENT_NAMES:
                continue
            path = root / portable_path.name
            try:
                raw_content = self._file_reader.read(path, self._max_document_bytes)
                content = raw_content.decode("utf-8")
            except BoundedFileTooLargeError:
                raise RepositoryScanError("仓库文档超过大小限制") from None
            except UnsafeBoundedFileError:
                raise RepositoryScanError("仓库文档路径已替换或不安全") from None
            except BoundedFileReadError:
                raise RepositoryScanError("仓库文档不可读取") from None
            except UnicodeDecodeError:
                raise RepositoryScanError("仓库文档不是 UTF-8") from None
            documents.append(RepositoryDocument(path=relative_path, content=content))
        return documents

    @classmethod
    def _parse_log(cls, raw: bytes) -> list[str]:
        return [line.strip() for line in cls._decode(raw).splitlines() if line.strip()]

    @staticmethod
    def _parse_status(raw: bytes) -> list[str]:
        if not raw:
            return []
        records = raw.split(b"\0")
        if records[-1] != b"":
            raise RepositoryScanError("Git 状态输出无效")
        records.pop()
        paths: list[str] = []
        index = 0
        while index < len(records):
            record = records[index]
            if len(record) < 4 or record[2:3] != b" " or not record[3:]:
                raise RepositoryScanError("Git 状态输出无效")
            status = record[:2]
            paths.append(os.fsdecode(record[3:]))
            if b"R" in status or b"C" in status:
                index += 1
                if index >= len(records) or not records[index]:
                    raise RepositoryScanError("Git 状态输出无效")
                os.fsdecode(records[index])
            index += 1
        return paths

    @staticmethod
    def _is_test_path(relative_path: str) -> bool:
        path = PurePosixPath(relative_path)
        lowered_parts = tuple(part.lower() for part in path.parts)
        return (
            "tests" in lowered_parts
            or "test" in lowered_parts
            or path.name.startswith("test_")
            or ".test." in path.name
            or ".spec." in path.name
        )
