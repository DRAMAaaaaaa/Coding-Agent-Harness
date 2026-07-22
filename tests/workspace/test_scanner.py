from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from io import BufferedReader
from pathlib import Path
import os
import stat
import subprocess
from time import perf_counter
from types import SimpleNamespace

import pytest

from coding_agent_harness.workspace.scanner import (
    RepositoryScanError,
    WorkspaceLimitError,
    WorkspaceScanner,
)
from coding_agent_harness.workspace.processes import CommandResult, ProcessRequest


class RecordingGitRunner:
    def __init__(
        self,
        tracked_files: Sequence[str],
        *,
        status_output: bytes = b"",
    ) -> None:
        self.tracked_files = tracked_files
        self.status_output = status_output
        self.calls: list[list[str]] = []
        self.requests: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.requests.append(request)
        argv = list(request.argv)
        if "-C" in argv:
            command = argv[argv.index("-C") + 2 :]
        else:
            command = argv[1:]
        operation = command[0]
        if operation == "config":
            return CommandResult(returncode=0, stdout=b"", stderr=b"")
        self.calls.append(command)
        if operation == "rev-parse":
            assert request.cwd is not None
            return CommandResult(
                returncode=0,
                stdout=str(request.cwd).encode("utf-8") + b"\n",
                stderr=b"",
            )
        if operation == "ls-files":
            stdout = "\0".join(self.tracked_files)
            if self.tracked_files:
                stdout += "\0"
            return CommandResult(returncode=0, stdout=stdout.encode(), stderr=b"")
        if operation == "log":
            return CommandResult(returncode=0, stdout=b"", stderr=b"")
        if operation == "status":
            return CommandResult(returncode=0, stdout=self.status_output, stderr=b"")
        if operation == "check-attr":
            paths = request.stdin.split(b"\0")
            if paths and paths[-1] == b"":
                paths.pop()
            stdout = b"".join(
                path + b"\0filter\0unspecified\0" for path in paths
            )
            return CommandResult(returncode=0, stdout=stdout, stderr=b"")
        raise AssertionError(f"unexpected git operation: {operation}")


class RecordingBinaryFile:
    def __init__(self, raw: BufferedReader, read_sizes: list[int]) -> None:
        self._raw = raw
        self._read_sizes = read_sizes

    def fileno(self) -> int:
        return self._raw.fileno()

    def read(self, size: int = -1) -> bytes:
        self._read_sizes.append(size)
        return self._raw.read(size)


class ControlledFileOpener:
    def __init__(
        self,
        *,
        after_open: Callable[[Path], None] | None = None,
        redirect_to: Path | None = None,
    ) -> None:
        self._after_open = after_open
        self._redirect_to = redirect_to
        self.read_sizes: list[int] = []

    @contextmanager
    def __call__(self, path: Path) -> Iterator[RecordingBinaryFile]:
        opened_path = self._redirect_to or path
        with opened_path.open("rb") as raw:
            if self._after_open is not None:
                self._after_open(path)
            yield RecordingBinaryFile(raw, self.read_sizes)


class RedirectedTopLevelGit:
    def __init__(self, reported_root: Path) -> None:
        self.reported_root = reported_root
        self.calls: list[list[str]] = []

    def run(
        self,
        root: str | Path,
        args: Sequence[str],
        stdin: bytes = b"",
    ) -> CommandResult:
        del root, stdin
        command = list(args)
        self.calls.append(command)
        if command == ["rev-parse", "--show-toplevel"]:
            return CommandResult(0, str(self.reported_root).encode("utf-8") + b"\n", b"")
        raise AssertionError(f"unexpected command after toplevel check: {command}")

    def assert_current_filter_free(self, root: Path, tracked: bytes) -> None:
        del root, tracked
        raise AssertionError("toplevel 不匹配时不得审计 filter")


def mark_git_root(root: Path) -> None:
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_bytes(b"")


def test_scanner_rejects_untrusted_gitfile_before_git_command(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text(
        "gitdir: \\\\untrusted.invalid\\share\\repository\n",
        encoding="utf-8",
    )
    runner = RecordingGitRunner([])

    with pytest.raises(RepositoryScanError, match="^所选目录不是 Git 根目录$"):
        WorkspaceScanner(runner).scan(tmp_path)

    assert runner.calls == []


def test_scanner_validates_effective_toplevel_before_repository_commands(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git").mkdir()
    outside = tmp_path.parent / "outside-worktree"
    outside.mkdir(exist_ok=True)
    safe_git = RedirectedTopLevelGit(outside)

    with pytest.raises(RepositoryScanError, match="^所选目录不是 Git 根目录$"):
        WorkspaceScanner(safe_git=safe_git).scan(tmp_path)

    assert safe_git.calls == [["rev-parse", "--show-toplevel"]]


def test_scans_real_git_repository_and_preserves_dirty_main_workspace(
    git_repository_factory: Callable[[str, dict[str, str]], Path],
) -> None:
    root = git_repository_factory(
        "repository with spaces",
        {
            "README.md": "# Example\n",
            "AGENTS.md": "Only deterministic changes.\n",
            "pyproject.toml": "[tool.pytest.ini_options]\n",
            "src/sample.py": "value = 1\n",
            "tests/test_sample.py": "def test_sample():\n    assert True\n",
            "node_modules/tracked.js": "ignored\n",
            "dist/output.js": "ignored\n",
        },
    )
    dirty_file = root / "src" / "sample.py"
    dirty_file.write_text("value = 2\n", encoding="utf-8")

    repository_map = WorkspaceScanner().scan(root)

    assert repository_map.root == root.resolve()
    assert "src/sample.py" in repository_map.tracked_files
    assert "node_modules/tracked.js" not in repository_map.tracked_files
    assert "dist/output.js" not in repository_map.tracked_files
    assert repository_map.test_paths == ("tests/test_sample.py",)
    assert {document.path for document in repository_map.documents} == {
        "AGENTS.md",
        "README.md",
        "pyproject.toml",
    }
    assert any("initial commit" in entry for entry in repository_map.recent_commits)
    assert repository_map.dirty_paths == ("src/sample.py",)
    assert dirty_file.read_text(encoding="utf-8") == "value = 2\n"


def test_status_paths_preserve_unicode_spaces_quotes_arrows_and_rename_destination(
    git_repository_factory: Callable[[str, dict[str, str]], Path],
) -> None:
    rename_source = "rename source 中文.txt"
    rename_target = "renamed 中文 final.txt"
    modified_paths = {
        "普通 中文.txt",
        "space name.txt",
        "single'quote.txt",
    }
    root = git_repository_factory(
        "porcelain-z",
        {path: "base\n" for path in (*modified_paths, rename_source)},
    )
    for path in modified_paths:
        (root / path).write_text("changed\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(root), "mv", rename_source, rename_target],
        check=True,
        capture_output=True,
    )

    dirty_paths = WorkspaceScanner().scan(root).dirty_paths

    assert set(dirty_paths) == {*modified_paths, rename_target}
    assert rename_source not in dirty_paths


def test_status_z_parser_treats_arrows_and_double_quotes_as_literal_path_bytes(
    tmp_path: Path,
) -> None:
    mark_git_root(tmp_path)
    runner = RecordingGitRunner(
        [],
        status_output=(
            b'M  literal -> arrow.txt\0'
            b'R  renamed "quote".txt\0source -> old.txt\0'
            b'C  copy -> target.txt\0copy "source".txt\0'
        ),
    )

    repository_map = WorkspaceScanner(runner).scan(tmp_path)

    assert repository_map.dirty_paths == (
        "literal -> arrow.txt",
        'renamed "quote".txt',
        "copy -> target.txt",
    )


def test_invokes_only_safe_read_only_git_commands(tmp_path: Path) -> None:
    mark_git_root(tmp_path)
    runner = RecordingGitRunner([])

    WorkspaceScanner(runner).scan(tmp_path)

    assert runner.calls == [
        ["rev-parse", "--show-toplevel"],
        ["ls-files", "-z"],
        ["check-attr", "--cached", "-z", "--stdin", "filter"],
        ["check-attr", "-z", "--stdin", "filter"],
        ["log", "--no-show-signature", "-n", "20"],
        ["status", "--porcelain=v1", "-z"],
    ]
    assert all(Path(request.argv[0]).is_absolute() for request in runner.requests)
    audit_requests = [request for request in runner.requests if "-C" not in request.argv]
    protected_requests = [request for request in runner.requests if "-C" in request.argv]
    assert len(audit_requests) == len(protected_requests) == len(runner.calls)
    assert all(
        list(request.argv[1:])
        == [
            "config",
            "--file",
            str(tmp_path / ".git" / "config"),
            "--no-includes",
            "-z",
            "--list",
        ]
        for request in audit_requests
    )
    assert all(request.cwd != tmp_path for request in audit_requests)
    assert all("core.fsmonitor=" in request.argv for request in protected_requests)
    assert all(
        "-C" not in runner.requests[index].argv
        and "-C" in runner.requests[index + 1].argv
        for index in range(0, len(runner.requests), 2)
    )


def test_repository_map_sequences_are_deeply_immutable_and_json_stays_arrays(
    tmp_path: Path,
) -> None:
    mark_git_root(tmp_path)
    repository_map = WorkspaceScanner(
        RecordingGitRunner(
            ["src/app.py"],
            status_output=b"M  src/app.py\0",
        )
    ).scan(tmp_path)

    for sequence in (
        repository_map.tracked_files,
        repository_map.documents,
        repository_map.test_paths,
        repository_map.recent_commits,
        repository_map.dirty_paths,
    ):
        assert not hasattr(sequence, "append")
    with pytest.raises(TypeError):
        repository_map.dirty_paths[0] = "changed.py"  # type: ignore[index]
    dumped = repository_map.model_dump(mode="json")
    assert dumped["tracked_files"] == ["src/app.py"]
    assert dumped["dirty_paths"] == ["src/app.py"]


def test_rejects_more_than_10000_tracked_files(tmp_path: Path) -> None:
    mark_git_root(tmp_path)
    runner = RecordingGitRunner([f"f{i}" for i in range(10_001)])

    with pytest.raises(WorkspaceLimitError, match="^仓库跟踪文件超过 10000 个$"):
        WorkspaceScanner(runner).scan(tmp_path)


def test_scans_10000_synthetic_files(
    tmp_path: Path,
    record_property: Callable[[str, float], None],
) -> None:
    mark_git_root(tmp_path)
    runner = RecordingGitRunner([f"src/f{i}.py" for i in range(10_000)])

    started = perf_counter()
    repository_map = WorkspaceScanner(runner).scan(tmp_path)
    elapsed = perf_counter() - started

    assert len(repository_map.tracked_files) == 10_000
    record_property("elapsed_seconds", elapsed)


def test_rejects_oversized_repository_document(
    git_repository_factory: Callable[[str, dict[str, str]], Path],
) -> None:
    root = git_repository_factory("oversized", {"README.md": "x" * 257})

    with pytest.raises(RepositoryScanError, match="^仓库文档超过大小限制$"):
        WorkspaceScanner(max_document_bytes=256).scan(root)


def test_rejects_non_git_directory_with_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(RepositoryScanError, match="^所选目录不是 Git 根目录$"):
        WorkspaceScanner().scan(tmp_path)


def test_rejects_repository_subdirectory_instead_of_mixing_path_bases(
    git_repository_factory: Callable[[str, dict[str, str]], Path],
) -> None:
    root = git_repository_factory("root-only", {"src/app.py": "value = 1\n"})

    with pytest.raises(RepositoryScanError, match="^所选目录不是 Git 根目录$"):
        WorkspaceScanner().scan(root / "src")


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 路径语义")
@pytest.mark.parametrize(
    "tracked",
    [
        r"..\outside.py",
        r"safe\..\..\outside.py",
        r"C:outside.py",
        r"C:\outside.py",
        r"\\server\share\outside.py",
    ],
)
def test_rejects_windows_escape_before_metadata_probe(
    tmp_path: Path,
    tracked: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_git_root(tmp_path)
    probes: list[tuple[str, Path]] = []
    original_exists = Path.exists
    original_stat = Path.stat

    def fail_probe(self: Path) -> bool:
        if self.name.casefold() == "outside.py":
            probes.append(("exists", self))
            raise AssertionError("越界路径不得被探测")
        return original_exists(self)

    def fail_stat(
        self: Path,
        *,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        if self.name.casefold() == "outside.py":
            probes.append(("stat", self))
            raise AssertionError("越界路径不得被探测")
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "exists", fail_probe)
    monkeypatch.setattr(Path, "stat", fail_stat)

    with pytest.raises(RepositoryScanError, match="^跟踪文件路径越界$"):
        WorkspaceScanner(RecordingGitRunner([tracked])).scan(tmp_path)

    assert probes == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX 文件名允许反斜杠")
def test_posix_backslash_filename_is_not_treated_as_windows_traversal(
    tmp_path: Path,
) -> None:
    mark_git_root(tmp_path)
    tracked = r"literal\..\name.py"

    repository_map = WorkspaceScanner(RecordingGitRunner([tracked])).scan(tmp_path)

    assert repository_map.tracked_files == (tracked,)


def test_rejects_tracked_symlink_escape(
    git_repository_factory: Callable[[str, dict[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("symlink", {"README.md": "safe\n"})
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = root / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"当前系统无法创建符号链接：{type(error).__name__}")
    subprocess.run(
        ["git", "-C", str(root), "add", "linked.txt"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "add symlink"],
        check=True,
        capture_output=True,
    )

    with pytest.raises(RepositoryScanError, match="^跟踪文件不可读取$"):
        WorkspaceScanner().scan(root)


def test_rejects_tracked_symlink_before_follow_target_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    mark_git_root(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    candidate = root / "linked-to-outside.txt"
    try:
        candidate.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"当前系统无法创建符号链接：{type(error).__name__}")

    probes: list[tuple[str, Path]] = []
    original_exists = Path.exists
    original_stat = Path.stat
    original_resolve = Path.resolve

    def fail_exists(self: Path) -> bool:
        if self == candidate:
            probes.append(("exists", self))
            raise AssertionError("follow-target exists reached")
        return original_exists(self)

    def fail_stat(
        self: Path,
        *,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        if self == candidate and follow_symlinks:
            probes.append(("stat", self))
            raise AssertionError("follow-target stat reached")
        return original_stat(self, follow_symlinks=follow_symlinks)

    def fail_resolve(self: Path, strict: bool = False) -> Path:
        if self == candidate:
            probes.append(("resolve", self))
            raise AssertionError("follow-target resolve reached")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "exists", fail_exists)
    monkeypatch.setattr(Path, "stat", fail_stat)
    monkeypatch.setattr(Path, "resolve", fail_resolve)

    with pytest.raises(RepositoryScanError, match="^跟踪文件不可读取$"):
        WorkspaceScanner(RecordingGitRunner([candidate.name])).scan(root)

    assert probes == []


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows reparse 契约")
def test_rejects_tracked_reparse_before_follow_target_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark_git_root(tmp_path)
    candidate = tmp_path / "linked-to-unc.txt"
    probes: list[tuple[str, Path]] = []
    original_exists = Path.exists
    original_stat = Path.stat
    original_resolve = Path.resolve

    def reparse_lstat(self: Path) -> os.stat_result | SimpleNamespace:
        if self == candidate:
            return SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return original_stat(self, follow_symlinks=False)

    def fail_exists(self: Path) -> bool:
        if self == candidate:
            probes.append(("exists", self))
            raise AssertionError("follow-target exists reached")
        return original_exists(self)

    def fail_stat(
        self: Path,
        *,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        if self == candidate and follow_symlinks:
            probes.append(("stat", self))
            raise AssertionError("follow-target stat reached")
        return original_stat(self, follow_symlinks=follow_symlinks)

    def fail_resolve(self: Path, strict: bool = False) -> Path:
        if self == candidate:
            probes.append(("resolve", self))
            raise AssertionError("follow-target resolve reached")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "lstat", reparse_lstat)
    monkeypatch.setattr(Path, "exists", fail_exists)
    monkeypatch.setattr(Path, "stat", fail_stat)
    monkeypatch.setattr(Path, "resolve", fail_resolve)

    with pytest.raises(RepositoryScanError, match="^跟踪文件不可读取$"):
        WorkspaceScanner(RecordingGitRunner([candidate.name])).scan(tmp_path)

    assert probes == []


def test_document_growth_after_open_reads_only_limit_plus_one(
    git_repository_factory: Callable[[str, dict[str, str]], Path],
) -> None:
    root = git_repository_factory("growing-document", {"README.md": "safe\n"})

    def grow(path: Path) -> None:
        with path.open("ab") as stream:
            stream.write(b"x" * 100)

    opener = ControlledFileOpener(after_open=grow)
    with pytest.raises(RepositoryScanError, match="^仓库文档超过大小限制$"):
        WorkspaceScanner(max_document_bytes=8, file_opener=opener).scan(root)

    assert opener.read_sizes == [9]


def test_document_opener_cannot_redirect_to_replaced_file(
    git_repository_factory: Callable[[str, dict[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory("replaced-document", {"README.md": "safe\n"})
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    opener = ControlledFileOpener(redirect_to=outside)

    with pytest.raises(
        RepositoryScanError,
        match="^仓库文档路径已替换或不安全$",
    ):
        WorkspaceScanner(file_opener=opener).scan(root)

    assert opener.read_sizes == []
