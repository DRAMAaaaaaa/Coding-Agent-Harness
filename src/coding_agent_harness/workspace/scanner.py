"""通过只读 Git argv 命令生成有界仓库地图。"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import tempfile

from coding_agent_harness.governance.path_identity import (
    UnsafePathNamespaceError,
    same_path,
)

from coding_agent_harness.workspace.models import RepositoryDocument, RepositoryMap
from coding_agent_harness.workspace.files import (
    BinaryFileOpener,
    BoundedFileReadError,
    BoundedFileReader,
    BoundedFileTooLargeError,
    UnsafeBoundedFileError,
    is_symlink_or_reparse,
)
from coding_agent_harness.workspace.git import SafeGit
from coding_agent_harness.workspace.processes import CommandResult, ProcessRunner

_MAX_TRACKED_FILES = 10_000
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


class WorkspaceScanner:
    """从跟踪文件和只读 Git 元数据构建 RepositoryMap。"""

    def __init__(
        self,
        runner: ProcessRunner | None = None,
        *,
        safe_git: SafeGit | None = None,
        state_root: str | Path | None = None,
        max_document_bytes: int = 128 * 1024,
        file_opener: BinaryFileOpener | None = None,
    ) -> None:
        if max_document_bytes < 1:
            raise ValueError("文档大小上限必须为正数")
        self._temporary_state: tempfile.TemporaryDirectory[str] | None = None
        if safe_git is None:
            if state_root is None:
                self._temporary_state = tempfile.TemporaryDirectory(
                    prefix="coding-agent-harness-"
                )
                state_root = self._temporary_state.name
            safe_git = SafeGit(state_root, runner=runner)
        self._git = safe_git
        self._max_document_bytes = max_document_bytes
        self._file_reader = BoundedFileReader(file_opener)

    def scan(self, root: str | Path) -> RepositoryMap:
        project_root = self._resolve_root(root)
        self._validate_git_root_marker(project_root)
        top_level = self._run_git(project_root, ["rev-parse", "--show-toplevel"])
        try:
            reported_root = Path(self._decode(top_level.stdout).strip())
            if not reported_root.is_absolute() or not same_path(
                reported_root,
                project_root,
            ):
                raise RepositoryScanError("所选目录不是 Git 根目录")
        except UnsafePathNamespaceError:
            raise RepositoryScanError("所选目录不是 Git 根目录") from None
        tracked_result = self._run_git(project_root, ["ls-files", "-z"])
        tracked_files = self._parse_tracked_files(tracked_result.stdout)
        if len(tracked_files) > _MAX_TRACKED_FILES:
            raise WorkspaceLimitError("仓库跟踪文件超过 10000 个")

        filtered_files = [
            path for path in tracked_files if not self._is_ignored(path)
        ]
        for relative_path in filtered_files:
            self._validate_tracked_path(project_root, relative_path)

        self._git.assert_current_filter_free(project_root, tracked_result.stdout)

        log_result = self._run_git(
            project_root,
            ["log", "--no-show-signature", "-n", "20"],
        )
        status_result = self._run_git(
            project_root,
            ["status", "--porcelain=v1", "-z"],
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
        try:
            marker_stat = marker.lstat()
        except OSError:
            raise RepositoryScanError("所选目录不是 Git 根目录") from None
        if is_symlink_or_reparse(marker_stat) or not stat.S_ISDIR(marker_stat.st_mode):
            raise RepositoryScanError("所选目录不是 Git 根目录")

    def _run_git(self, root: Path, args: list[str]) -> CommandResult:
        try:
            result = self._git.run(root, args)
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
    def _validate_tracked_path(
        root: Path,
        relative_path: str,
    ) -> None:
        portable_path = PurePosixPath(relative_path)
        if portable_path.is_absolute() or ".." in portable_path.parts:
            raise RepositoryScanError("跟踪文件路径越界")
        if os.name == "nt":
            windows_path = PureWindowsPath(relative_path)
            if (
                windows_path.drive
                or windows_path.root
                or ".." in windows_path.parts
            ):
                raise RepositoryScanError("跟踪文件路径越界")
        parent = root
        for part in portable_path.parts[:-1]:
            parent = parent / part
            try:
                parent_stat = parent.lstat()
            except FileNotFoundError:
                return
            except OSError:
                raise RepositoryScanError("跟踪文件不可读取") from None
            if (
                is_symlink_or_reparse(parent_stat)
                or not stat.S_ISDIR(parent_stat.st_mode)
            ):
                raise RepositoryScanError("跟踪文件不可读取")

        candidate = parent / portable_path.name
        try:
            candidate_stat = candidate.lstat()
        except FileNotFoundError:
            return
        except OSError:
            raise RepositoryScanError("跟踪文件不可读取") from None
        if is_symlink_or_reparse(candidate_stat):
            raise RepositoryScanError("跟踪文件不可读取")

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
