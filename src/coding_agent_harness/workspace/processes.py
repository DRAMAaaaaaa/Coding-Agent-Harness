"""跨平台、有界地执行并回收 Git 子进程。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
import subprocess
import threading
import time
from typing import BinaryIO, Protocol, cast

DEFAULT_GIT_TIMEOUT_SECONDS = 300.0
DEFAULT_GIT_STDOUT_LIMIT_BYTES = 64 * 1024 * 1024
DEFAULT_GIT_STDERR_LIMIT_BYTES = 64 * 1024 * 1024
OUTPUT_READ_CHUNK_BYTES = 64 * 1024
_WAIT_POLL_SECONDS = 0.05
_CLEANUP_TIMEOUT_SECONDS = 1.0


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


class CappedOutputReader:
    """固定块读取一个 pipe，仅保留 limit+1 bytes 并始终 drain 到 EOF。"""

    def __init__(
        self,
        stream: BinaryIO,
        *,
        limit: int,
        on_failure: Callable[[], None],
    ) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("输出上限必须为正整数")
        self._stream = stream
        self._limit = limit
        self._on_failure = on_failure
        self._output = bytearray()
        self._exceeded = False
        self._error: Exception | None = None
        self._failure_signaled = False

    @property
    def output(self) -> bytes:
        return bytes(self._output)

    @property
    def exceeded(self) -> bool:
        return self._exceeded

    @property
    def error(self) -> Exception | None:
        return self._error

    def read_to_eof(self) -> None:
        try:
            while True:
                chunk = self._stream.read(OUTPUT_READ_CHUNK_BYTES)
                if not chunk:
                    return
                remaining = self._limit + 1 - len(self._output)
                if remaining > 0:
                    self._output.extend(chunk[:remaining])
                if len(self._output) > self._limit or len(chunk) > remaining:
                    self._exceeded = True
                    self._signal_failure()
        except Exception as error:
            self._error = error
            self._signal_failure()

    def _signal_failure(self) -> None:
        if self._failure_signaled:
            return
        self._failure_signaled = True
        try:
            self._on_failure()
        except Exception:
            pass


class SubprocessGitRunner:
    """以双 PIPE reader、300 秒和每流 64 MiB 默认上限执行 argv。"""

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
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("Git 超时必须为有限正数")
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
        try:
            process = subprocess.Popen(
                list(argv),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError:
            raise GitProcessNotStartedError("Git 进程未启动") from None
        threads: list[threading.Thread] = []
        if process.stdout is None or process.stderr is None:
            partial_streams = tuple(
                cast(BinaryIO, stream)
                for stream in (process.stdout, process.stderr)
                if stream is not None
            )
            self._cleanup_started_process(process, partial_streams, threads)
            raise GitProcessUncertainError("Git 进程状态不确定")
        stdout_stream = cast(BinaryIO, process.stdout)
        stderr_stream = cast(BinaryIO, process.stderr)
        streams = (stdout_stream, stderr_stream)

        failure = threading.Event()
        kill_lock = threading.Lock()
        kill_requested = False

        def signal_failure() -> None:
            nonlocal kill_requested
            failure.set()
            with kill_lock:
                if kill_requested:
                    return
                kill_requested = True
                self._kill_best_effort(process)

        stdout_reader = CappedOutputReader(
            stdout_stream,
            limit=self._max_stdout_bytes,
            on_failure=signal_failure,
        )
        stderr_reader = CappedOutputReader(
            stderr_stream,
            limit=self._max_stderr_bytes,
            on_failure=signal_failure,
        )
        readers = (stdout_reader, stderr_reader)
        threads = [
            threading.Thread(
                target=reader.read_to_eof,
                name=f"git-output-{name}",
                daemon=True,
            )
            for name, reader in zip(("stdout", "stderr"), readers, strict=True)
        ]
        try:
            for thread in threads:
                thread.start()
            self._wait_bounded(process, failure)
            self._join_readers(threads)
            if (
                failure.is_set()
                or any(reader.exceeded or reader.error is not None for reader in readers)
                or process.returncode is None
            ):
                raise RuntimeError("Git 进程输出或状态不确定")
            result = CommandResult(
                returncode=process.returncode,
                stdout=stdout_reader.output,
                stderr=stderr_reader.output,
            )
            self._close_streams_strict(streams)
            return result
        except Exception:
            self._cleanup_started_process(process, streams, threads)
            raise GitProcessUncertainError("Git 进程状态不确定") from None

    def _wait_bounded(
        self,
        process: subprocess.Popen[bytes],
        failure: threading.Event,
    ) -> None:
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            if failure.is_set():
                raise RuntimeError("Git 输出读取失败或超过上限")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, self._timeout_seconds)
            try:
                process.wait(timeout=min(_WAIT_POLL_SECONDS, remaining))
                return
            except subprocess.TimeoutExpired:
                continue

    @staticmethod
    def _join_readers(threads: Sequence[threading.Thread]) -> None:
        deadline = time.monotonic() + _CLEANUP_TIMEOUT_SECONDS
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            raise RuntimeError("Git 输出 reader 未结束")

    @classmethod
    def _cleanup_started_process(
        cls,
        process: subprocess.Popen[bytes],
        streams: Sequence[BinaryIO],
        threads: Sequence[threading.Thread],
    ) -> None:
        cls._kill_best_effort(process)
        try:
            process.wait(timeout=_CLEANUP_TIMEOUT_SECONDS)
        except Exception:
            pass
        cls._join_best_effort(threads)
        cls._close_streams_best_effort(streams)
        cls._join_best_effort(threads)

    @staticmethod
    def _kill_best_effort(process: subprocess.Popen[bytes]) -> None:
        try:
            process.kill()
        except Exception:
            pass

    @staticmethod
    def _join_best_effort(threads: Sequence[threading.Thread]) -> None:
        for thread in threads:
            try:
                thread.join(timeout=_CLEANUP_TIMEOUT_SECONDS)
            except Exception:
                pass

    @staticmethod
    def _close_streams_strict(streams: Sequence[BinaryIO]) -> None:
        first_error: Exception | None = None
        for stream in streams:
            try:
                stream.close()
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    @classmethod
    def _close_streams_best_effort(cls, streams: Sequence[BinaryIO]) -> None:
        try:
            cls._close_streams_strict(streams)
        except Exception:
            pass
