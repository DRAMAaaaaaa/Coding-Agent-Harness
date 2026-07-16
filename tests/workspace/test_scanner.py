from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from io import BufferedReader, BytesIO
from pathlib import Path
import subprocess
from time import perf_counter

import pytest

import coding_agent_harness.workspace.scanner as scanner_module
from coding_agent_harness.workspace.scanner import (
    CommandResult,
    GitProcessNotStartedError,
    GitProcessUncertainError,
    RepositoryScanError,
    SubprocessGitRunner,
    WorkspaceLimitError,
    WorkspaceScanner,
)


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

    def run(self, argv: Sequence[str]) -> CommandResult:
        self.calls.append(list(argv))
        operation = argv[3]
        if operation == "ls-files":
            stdout = "\0".join(self.tracked_files)
            if self.tracked_files:
                stdout += "\0"
            return CommandResult(returncode=0, stdout=stdout.encode(), stderr=b"")
        if operation == "log":
            return CommandResult(returncode=0, stdout=b"", stderr=b"")
        if operation == "status":
            return CommandResult(returncode=0, stdout=self.status_output, stderr=b"")
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


def mark_git_root(root: Path) -> None:
    (root / ".git").write_text("gitdir: synthetic\n", encoding="utf-8")


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


def test_invokes_only_the_three_read_only_git_commands(tmp_path: Path) -> None:
    mark_git_root(tmp_path)
    runner = RecordingGitRunner([])

    WorkspaceScanner(runner).scan(tmp_path)

    root = str(tmp_path.resolve())
    assert runner.calls == [
        ["git", "-C", root, "ls-files", "-z"],
        ["git", "-C", root, "log", "-n", "20"],
        ["git", "-C", root, "status", "--porcelain=v1", "-z"],
    ]


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


def test_scans_10000_synthetic_files_in_under_five_seconds(tmp_path: Path) -> None:
    mark_git_root(tmp_path)
    runner = RecordingGitRunner([f"src/f{i}.py" for i in range(10_000)])

    started = perf_counter()
    repository_map = WorkspaceScanner(runner).scan(tmp_path)
    elapsed = perf_counter() - started

    assert len(repository_map.tracked_files) == 10_000
    assert elapsed < 5.0


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

    with pytest.raises(RepositoryScanError, match="^跟踪文件路径越界$"):
        WorkspaceScanner().scan(root)


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


def test_subprocess_runner_maps_popen_construction_failure_to_not_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_before_start(*args: object, **kwargs: object) -> None:
        raise OSError("process construction failed")

    monkeypatch.setattr(subprocess, "Popen", fail_before_start)

    with pytest.raises(GitProcessNotStartedError, match="^Git 进程未启动$"):
        SubprocessGitRunner().run(["git", "--version"])


def test_subprocess_runner_closes_first_temporary_file_when_second_cannot_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = BytesIO()
    calls = 0

    def open_temporary_file() -> BytesIO:
        nonlocal calls
        calls += 1
        if calls == 1:
            return first
        raise OSError("second temporary file failed")

    monkeypatch.setattr(scanner_module.tempfile, "TemporaryFile", open_temporary_file)

    with pytest.raises(GitProcessNotStartedError, match="^Git 进程未启动$"):
        SubprocessGitRunner().run(["git", "--version"])

    assert first.closed


def test_subprocess_runner_maps_communicate_failure_to_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StartedProcess:
        returncode: int | None = None
        killed = False
        waited = False

        def communicate(self, *, timeout: float | None = None) -> tuple[None, None]:
            raise OSError("communicate failed after start")

        def kill(self) -> None:
            self.killed = True

        def wait(self, *, timeout: float | None = None) -> int:
            self.waited = True
            return -9

    process = StartedProcess()
    streams: list[object] = []

    def start(*args: object, **kwargs: object) -> StartedProcess:
        streams.extend([kwargs["stdout"], kwargs["stderr"]])
        return process

    monkeypatch.setattr(subprocess, "Popen", start)

    with pytest.raises(GitProcessUncertainError, match="^Git 进程状态不确定$"):
        SubprocessGitRunner().run(["git", "--version"])

    assert process.killed
    assert process.waited
    assert all(getattr(stream, "closed", False) for stream in streams)


def test_subprocess_runner_times_out_and_cleans_started_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimedOutProcess:
        returncode: int | None = None
        killed = False
        waited = False

        def communicate(self, *, timeout: float | None = None) -> tuple[None, None]:
            if self.killed:
                return None, None
            raise subprocess.TimeoutExpired(["git", "status"], timeout)

        def kill(self) -> None:
            self.killed = True

        def wait(self, *, timeout: float | None = None) -> int:
            self.waited = True
            self.returncode = -9
            return -9

    process = TimedOutProcess()
    streams: list[object] = []

    def start(*args: object, **kwargs: object) -> TimedOutProcess:
        streams.extend([kwargs["stdout"], kwargs["stderr"]])
        return process

    monkeypatch.setattr(subprocess, "Popen", start)

    with pytest.raises(GitProcessUncertainError, match="^Git 进程状态不确定$"):
        SubprocessGitRunner(timeout_seconds=0.001).run(["git", "status"])

    assert process.killed
    assert process.waited
    assert all(getattr(stream, "closed", False) for stream in streams)


@pytest.mark.parametrize(
    ("stream_name", "limit_name"),
    [("stdout", "max_stdout_bytes"), ("stderr", "max_stderr_bytes")],
)
def test_subprocess_runner_rejects_output_over_limit_and_cleans_process(
    monkeypatch: pytest.MonkeyPatch,
    stream_name: str,
    limit_name: str,
) -> None:
    class CompletedProcess:
        returncode: int | None = 0
        killed = False
        waited = False

        def communicate(self, *, timeout: float | None = None) -> tuple[None, None]:
            return None, None

        def kill(self) -> None:
            self.killed = True

        def wait(self, *, timeout: float | None = None) -> int:
            self.waited = True
            return 0

    process = CompletedProcess()
    streams: list[object] = []

    def start(*args: object, **kwargs: object) -> CompletedProcess:
        stream = kwargs[stream_name]
        stream.write(b"12345")
        stream.flush()
        streams.extend([kwargs["stdout"], kwargs["stderr"]])
        return process

    monkeypatch.setattr(subprocess, "Popen", start)

    with pytest.raises(GitProcessUncertainError, match="^Git 进程状态不确定$"):
        SubprocessGitRunner(**{limit_name: 4}).run(["git", "status"])

    assert process.killed
    assert process.waited
    assert all(getattr(stream, "closed", False) for stream in streams)


def test_subprocess_runner_cleanup_failure_remains_uncertain_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CleanupFailingProcess:
        returncode: int | None = None

        def communicate(self, *, timeout: float | None = None) -> tuple[None, None]:
            raise OSError("drain failed")

        def kill(self) -> None:
            raise OSError("kill failed")

        def wait(self, *, timeout: float | None = None) -> int:
            raise OSError("wait failed")

    streams: list[object] = []

    def start(*args: object, **kwargs: object) -> CleanupFailingProcess:
        streams.extend([kwargs["stdout"], kwargs["stderr"]])
        return CleanupFailingProcess()

    monkeypatch.setattr(subprocess, "Popen", start)

    with pytest.raises(GitProcessUncertainError, match="^Git 进程状态不确定$"):
        SubprocessGitRunner().run(["git", "status"])

    assert all(getattr(stream, "closed", False) for stream in streams)


def test_subprocess_runner_preserves_normal_bytes_and_returncode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CompletedProcess:
        returncode: int | None = 7

        def communicate(self, *, timeout: float | None = None) -> tuple[None, None]:
            return None, None

    def start(*args: object, **kwargs: object) -> CompletedProcess:
        kwargs["stdout"].write(b"normal stdout")
        kwargs["stderr"].write(b"normal stderr")
        return CompletedProcess()

    monkeypatch.setattr(subprocess, "Popen", start)

    assert SubprocessGitRunner().run(["git", "status"]) == CommandResult(
        returncode=7,
        stdout=b"normal stdout",
        stderr=b"normal stderr",
    )
