from io import BytesIO
import subprocess
import sys
import threading
from time import perf_counter

import pytest

import coding_agent_harness.workspace.processes as processes_module
from coding_agent_harness.workspace.processes import (
    CappedOutputReader,
    CommandResult,
    GitProcessNotStartedError,
    GitProcessUncertainError,
    SubprocessGitRunner,
)


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_runner_rejects_non_finite_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="^Git 超时必须为有限正数$"):
        SubprocessGitRunner(timeout_seconds=timeout)


def test_capped_reader_retains_only_limit_plus_one_and_drains_to_eof() -> None:
    source = BytesIO(b"x" * 100_000)
    failures = 0

    def record_failure() -> None:
        nonlocal failures
        failures += 1

    reader = CappedOutputReader(source, limit=7, on_failure=record_failure)

    reader.read_to_eof()

    assert reader.exceeded
    assert reader.error is None
    assert reader.output == b"x" * 8
    assert source.tell() == 100_000
    assert failures == 1


def test_runner_caps_and_reaps_real_process_writing_both_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_popen = subprocess.Popen
    started: list[subprocess.Popen[bytes]] = []

    def start(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = original_popen(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(processes_module.subprocess, "Popen", start)
    script = (
        "import os\n"
        "chunk = b'x' * 65536\n"
        "for _ in range(1024):\n"
        "    os.write(1, chunk)\n"
        "    os.write(2, chunk)\n"
    )
    started_at = perf_counter()

    with pytest.raises(
        GitProcessUncertainError,
        match="^Git 进程状态不确定$",
    ) as error:
        SubprocessGitRunner(
            timeout_seconds=5,
            max_stdout_bytes=4096,
            max_stderr_bytes=4096,
        ).run([sys.executable, "-c", script])

    assert perf_counter() - started_at < 5
    assert "x" not in str(error.value)
    assert len(started) == 1
    assert started[0].poll() is not None
    assert started[0].stdout is not None and started[0].stdout.closed
    assert started[0].stderr is not None and started[0].stderr.closed


def test_runner_timeout_kills_only_after_real_wait_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimedOutProcess:
        args = ["git", "status"]
        returncode: int | None = None
        stdout = BytesIO()
        stderr = BytesIO()
        timed_out = False
        killed = False
        waited = False

        def wait(self, *, timeout: float | None = None) -> int:
            self.waited = True
            if self.killed:
                self.returncode = -9
                return -9
            self.timed_out = True
            raise subprocess.TimeoutExpired(self.args, timeout)

        def kill(self) -> None:
            assert self.timed_out
            self.killed = True

    process = TimedOutProcess()
    monkeypatch.setattr(processes_module.subprocess, "Popen", lambda *a, **k: process)

    with pytest.raises(GitProcessUncertainError, match="^Git 进程状态不确定$"):
        SubprocessGitRunner(timeout_seconds=0.001).run(process.args)

    assert process.waited
    assert process.timed_out
    assert process.killed
    assert process.returncode == -9
    assert process.stdout.closed
    assert process.stderr.closed


def test_runner_cleanup_exceptions_remain_uncertain_and_close_pipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExplodingPipe(BytesIO):
        def read(self, size: int = -1) -> bytes:
            raise OSError("drain failed")

    class CleanupFailingProcess:
        args = ["git", "status"]
        returncode: int | None = None
        stdout = ExplodingPipe()
        stderr = ExplodingPipe()
        kill_calls = 0
        wait_calls = 0

        def kill(self) -> None:
            self.kill_calls += 1
            raise OSError("kill failed")

        def wait(self, *, timeout: float | None = None) -> int:
            self.wait_calls += 1
            raise OSError("wait failed")

    process = CleanupFailingProcess()
    join_calls = 0

    def fail_join(thread: object, timeout: float | None = None) -> None:
        nonlocal join_calls
        join_calls += 1
        raise OSError("join failed")

    monkeypatch.setattr(processes_module.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(processes_module.threading.Thread, "join", fail_join)

    with pytest.raises(GitProcessUncertainError, match="^Git 进程状态不确定$"):
        SubprocessGitRunner(timeout_seconds=0.01).run(process.args)

    assert process.kill_calls >= 1
    assert process.wait_calls >= 1
    assert join_calls >= 1
    assert process.stdout.closed
    assert process.stderr.closed


@pytest.mark.parametrize(
    "interruption",
    [KeyboardInterrupt("host interrupt"), SystemExit(23)],
    ids=["keyboard-interrupt", "system-exit"],
)
def test_runner_cleans_process_before_propagating_host_interruption(
    monkeypatch: pytest.MonkeyPatch,
    interruption: BaseException,
) -> None:
    class CleanupInterruptingPipe(BytesIO):
        def close(self) -> None:
            super().close()
            raise SystemExit("cleanup interruption")

    class InterruptedProcess:
        args = ["git", "status"]
        returncode: int | None = None
        stdout = CleanupInterruptingPipe(b"stdout")
        stderr = BytesIO(b"stderr")
        killed = False
        wait_calls = 0

        def wait(self, *, timeout: float | None = None) -> int:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise interruption
            assert self.killed
            self.returncode = -9
            return -9

        def kill(self) -> None:
            self.killed = True

    process = InterruptedProcess()
    original_thread = threading.Thread
    reader_threads: list[threading.Thread] = []

    def record_thread(*args: object, **kwargs: object) -> threading.Thread:
        thread = original_thread(*args, **kwargs)
        reader_threads.append(thread)
        return thread

    monkeypatch.setattr(processes_module.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(processes_module.threading, "Thread", record_thread)

    with pytest.raises(type(interruption)) as raised:
        SubprocessGitRunner().run(process.args)

    assert raised.value is interruption
    assert process.killed
    assert process.wait_calls >= 2
    assert process.stdout.closed
    assert process.stderr.closed
    assert len(reader_threads) == 2
    assert all(not thread.is_alive() for thread in reader_threads)


def test_runner_closes_partial_pipe_state_after_process_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PartialPipeProcess:
        args = ["git", "status"]
        returncode: int | None = None
        stdout = BytesIO()
        stderr = None
        killed = False
        waited = False

        def kill(self) -> None:
            self.killed = True

        def wait(self, *, timeout: float | None = None) -> int:
            self.waited = True
            self.returncode = -9
            return -9

    process = PartialPipeProcess()
    monkeypatch.setattr(processes_module.subprocess, "Popen", lambda *a, **k: process)

    with pytest.raises(GitProcessUncertainError, match="^Git 进程状态不确定$"):
        SubprocessGitRunner().run(process.args)

    assert process.killed
    assert process.waited
    assert process.stdout.closed


def test_runner_maps_normal_path_pipe_close_failure_to_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CloseFailingPipe(BytesIO):
        def close(self) -> None:
            super().close()
            raise OSError("close failed")

    class CloseFailingProcess:
        args = ["git", "status"]
        returncode: int | None = None
        stdout = CloseFailingPipe(b"normal stdout")
        stderr = BytesIO(b"normal stderr")

        def wait(self, *, timeout: float | None = None) -> int:
            self.returncode = 0
            return 0

        def kill(self) -> None:
            return None

    process = CloseFailingProcess()
    monkeypatch.setattr(processes_module.subprocess, "Popen", lambda *a, **k: process)

    with pytest.raises(GitProcessUncertainError, match="^Git 进程状态不确定$"):
        SubprocessGitRunner().run(process.args)

    assert process.stdout.closed
    assert process.stderr.closed


def test_runner_maps_popen_failure_and_preserves_normal_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_before_start(*args: object, **kwargs: object) -> None:
        raise OSError("process construction failed")

    monkeypatch.setattr(processes_module.subprocess, "Popen", fail_before_start)
    with pytest.raises(GitProcessNotStartedError, match="^Git 进程未启动$"):
        SubprocessGitRunner().run(["git", "--version"])

    class CompletedProcess:
        args = ["git", "status"]
        returncode: int | None = None
        stdout = BytesIO(b"normal stdout")
        stderr = BytesIO(b"normal stderr")

        def wait(self, *, timeout: float | None = None) -> int:
            self.returncode = 7
            return 7

        def kill(self) -> None:
            raise AssertionError("normal process must not be killed")

    monkeypatch.setattr(
        processes_module.subprocess,
        "Popen",
        lambda *a, **k: CompletedProcess(),
    )
    assert SubprocessGitRunner().run(["git", "status"]) == CommandResult(
        returncode=7,
        stdout=b"normal stdout",
        stderr=b"normal stderr",
    )
