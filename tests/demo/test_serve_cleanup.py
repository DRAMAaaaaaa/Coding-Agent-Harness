from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import threading

import pytest

from scripts import serve_demo


@pytest.mark.parametrize(
    ("host", "origin"),
    [
        (None, "http://47.76.86.198"),
        ("47.76.86.198", None),
        ("47.76.86.199", "http://47.76.86.199"),
        ("example.com", "http://example.com"),
        ("47.76.86.198:80", "http://47.76.86.198:80"),
        ("47.76.86.198", "https://47.76.86.198"),
    ],
)
def test_public_demo_targets_fail_closed(host: str | None, origin: str | None) -> None:
    with pytest.raises(ValueError, match="公网演示"):
        serve_demo._trusted_request_targets(8000, host, origin)


def test_public_demo_targets_append_exact_http_ipv4() -> None:
    hosts, origins = serve_demo._trusted_request_targets(
        8000, "47.76.86.198", "http://47.76.86.198",
    )

    assert hosts == ("127.0.0.1:8000", "localhost:8000", "47.76.86.198")
    assert origins == (
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://47.76.86.198",
    )


def test_main_reads_public_target_environment_into_serve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_serve(*_args: object, **options: object) -> int:
        captured.update(options)
        return 0

    monkeypatch.setattr(serve_demo, "_serve", fake_serve)
    monkeypatch.setenv("HARNESS_PUBLIC_HOST", "47.76.86.198")
    monkeypatch.setenv("HARNESS_PUBLIC_ORIGIN", "http://47.76.86.198")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "serve_demo.py",
            "--ready-file",
            str(tmp_path / "ready.json"),
            "--runtime-root",
            str(tmp_path / "runtime"),
        ],
    )

    assert serve_demo.main() == 0
    assert captured["public_host"] == "47.76.86.198"
    assert captured["public_origin"] == "http://47.76.86.198"
    assert captured["shutdown_on_stdin_close"] is False


def test_main_passes_explicit_stdin_shutdown_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_serve(*_args: object, **options: object) -> int:
        captured.update(options)
        return 0

    monkeypatch.setattr(serve_demo, "_serve", fake_serve)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "serve_demo.py",
            "--ready-file",
            str(tmp_path / "ready.json"),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--shutdown-on-stdin-close",
        ],
    )

    assert serve_demo.main() == 0
    assert captured["shutdown_on_stdin_close"] is True


def test_main_accepts_zero_max_seconds_for_long_running_demo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_serve(*args: object, **_options: object) -> int:
        captured["max_seconds"] = args[2]
        return 0

    monkeypatch.setattr(serve_demo, "_serve", fake_serve)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "serve_demo.py",
            "--ready-file",
            str(tmp_path / "ready.json"),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--max-seconds",
            "0",
        ],
    )

    assert serve_demo.main() == 0
    assert captured["max_seconds"] == 0


class _Server:
    should_exit = False


class _Listener:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Database:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _Router:
    def __init__(self, *, fail: bool = False) -> None:
        self.cleaned = False
        self._fail = fail
        self.provider_registry = _Providers()

    async def provider_for_task(self, task: object) -> object:
        return await self.provider_registry.build_for_task(task)

    def cleanup(self) -> None:
        self.cleaned = True
        if self._fail:
            raise RuntimeError("router cleanup failed")


class _Providers:
    async def build_for_task(self, task: object) -> object:
        raise AssertionError("serve cleanup stub must not build a provider")


class _DemoServer:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.started = True
        self.should_exit = False

    async def serve(self, **_kwargs: object) -> None:
        while not self.should_exit:
            await asyncio.sleep(0)


def _stub_serve_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[_Listener, _Database, _Router]:
    listener = _Listener()
    database = _Database()
    router = _Router()
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (tmp_path / "runtime" / "state").mkdir(parents=True)

    async def open_database(_path: Path) -> _Database:
        return database

    monkeypatch.setattr(serve_demo, "_create_fixture", lambda _root: (fixture, "head"))
    monkeypatch.setattr(serve_demo.Database, "open", open_database)
    monkeypatch.setattr(serve_demo, "_reserve_local_socket", lambda: (listener, 12345))
    monkeypatch.setattr(serve_demo, "DemoOrchestratorRouter", lambda **_kwargs: router)
    monkeypatch.setattr(serve_demo, "create_app", lambda **_kwargs: object())
    monkeypatch.setattr(serve_demo.uvicorn, "Config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(serve_demo.uvicorn, "Server", _DemoServer)
    return listener, database, router


async def test_serve_exits_zero_when_the_single_demo_task_completes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    _stub_serve_dependencies(monkeypatch, tmp_path)

    def completed_router(**kwargs: object) -> _Router:
        callback = kwargs["on_completed"]
        assert callable(callback)
        callback()
        return _Router()

    monkeypatch.setattr(serve_demo, "DemoOrchestratorRouter", completed_router)

    assert await asyncio.wait_for(
        serve_demo._serve(runtime_root, tmp_path / "ready.json", 10), timeout=2,
    ) == 0


async def test_serve_keep_alive_omits_the_single_task_completion_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_serve_dependencies(monkeypatch, tmp_path)
    captured: dict[str, object] = {}

    def keep_alive_router(**kwargs: object) -> _Router:
        captured.update(kwargs)
        raise RuntimeError("stop after construction")

    monkeypatch.setattr(serve_demo, "DemoOrchestratorRouter", keep_alive_router)

    with pytest.raises(RuntimeError, match="stop after construction"):
        await serve_demo._serve(tmp_path / "runtime", tmp_path / "ready.json", 10, keep_alive=True)
    assert captured["on_completed"] is None


async def test_zero_max_seconds_keeps_keep_alive_server_running_until_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    ready_file = tmp_path / "ready.json"
    listener, database, router = _stub_serve_dependencies(monkeypatch, tmp_path)
    serve_task = asyncio.create_task(
        serve_demo._serve(runtime_root, ready_file, 0, keep_alive=True)
    )

    try:
        for _ in range(100):
            if ready_file.exists():
                break
            await asyncio.sleep(0)
        assert ready_file.exists()

        await asyncio.sleep(0)
        assert not serve_task.done()
    finally:
        serve_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await serve_task

    assert listener.closed
    assert database.closed
    assert router.cleaned
    assert not (runtime_root / "state").exists()


async def test_keep_alive_stops_and_cleans_when_stdin_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    listener, database, router = _stub_serve_dependencies(monkeypatch, tmp_path)

    def trigger_eof(
        loop: asyncio.AbstractEventLoop,
        stdin_closed: asyncio.Event,
    ) -> None:
        loop.call_soon(stdin_closed.set)

    monkeypatch.setattr(serve_demo, "_start_stdin_eof_watcher", trigger_eof)

    assert await asyncio.wait_for(
        serve_demo._serve(
            runtime_root,
            tmp_path / "ready.json",
            10,
            keep_alive=True,
            shutdown_on_stdin_close=True,
        ),
        timeout=2,
    ) == 0
    assert listener.closed and database.closed and router.cleaned
    assert not (runtime_root / "state").exists()


async def test_cleanup_continues_after_router_failure(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "artifact").write_text("x", encoding="utf-8")
    listener = _Listener()
    database = _Database()
    router = _Router(fail=True)

    with pytest.raises(BaseExceptionGroup) as captured:
        await asyncio.wait_for(
            serve_demo._cleanup_resources(
                server=None,
                server_task=None,
                listener=listener,
                router=router,
                database=database,
                state_root=state_root,
                timeout=0.1,
            ),
            timeout=1,
        )

    assert "router cleanup failed" in str(captured.value)
    assert router.cleaned
    assert listener.closed
    assert database.closed
    assert not state_root.exists()


async def test_cleanup_cancels_server_that_ignores_graceful_exit(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    server = _Server()
    cancelled = asyncio.Event()

    async def stubborn_server() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    server_task = asyncio.create_task(stubborn_server())
    listener = _Listener()
    database = _Database()
    router = _Router()

    await asyncio.wait_for(
        serve_demo._cleanup_resources(
            server=server,
            server_task=server_task,
            listener=listener,
            router=router,
            database=database,
            state_root=state_root,
            timeout=0.1,
        ),
        timeout=1,
    )

    assert server.should_exit
    assert server_task.done()
    assert cancelled.is_set()
    assert listener.closed and database.closed and router.cleaned
    assert not state_root.exists()


async def test_cleanup_preserves_resources_while_server_swallows_cancellation(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    server = _Server()
    release = asyncio.Event()
    cancellation_swallowed = asyncio.Event()

    async def uncooperative_server() -> None:
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancellation_swallowed.set()

    server_task = asyncio.create_task(uncooperative_server())
    listener = _Listener()
    database = _Database()
    router = _Router()
    try:
        with pytest.raises(BaseExceptionGroup) as captured:
            await asyncio.wait_for(
                serve_demo._cleanup_resources(
                    server=server,
                    server_task=server_task,
                    listener=listener,
                    router=router,
                    database=database,
                    state_root=state_root,
                    timeout=0.02,
                ),
                timeout=1,
            )
        assert cancellation_swallowed.is_set()
        assert not server_task.done()
        assert not listener.closed and not database.closed and not router.cleaned
        assert state_root.exists()
        assert "server task is still running" in str(captured.value)
    finally:
        release.set()
        await asyncio.wait_for(server_task, timeout=1)

    await serve_demo._cleanup_resources(
        server=server,
        server_task=server_task,
        listener=listener,
        router=router,
        database=database,
        state_root=state_root,
        timeout=0.1,
    )
    assert listener.closed and database.closed and router.cleaned
    assert not state_root.exists()


async def test_cancelling_cleanup_during_server_wait_preserves_live_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    server = _Server()
    release = asyncio.Event()
    wait_entered = asyncio.Event()
    original_wait = asyncio.wait

    async def observed_wait(*args: object, **kwargs: object) -> object:
        wait_entered.set()
        return await original_wait(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(serve_demo.asyncio, "wait", observed_wait)

    async def live_server() -> None:
        await release.wait()

    server_task = asyncio.create_task(live_server())
    listener = _Listener()
    database = _Database()
    router = _Router()
    cleanup_task = asyncio.create_task(
        serve_demo._cleanup_resources(
            server=server,
            server_task=server_task,
            listener=listener,
            router=router,
            database=database,
            state_root=state_root,
            timeout=10,
        )
    )
    await asyncio.wait_for(wait_entered.wait(), timeout=1)
    cleanup_task.cancel()
    try:
        with pytest.raises(BaseExceptionGroup) as captured:
            await asyncio.wait_for(cleanup_task, timeout=1)
        assert not server_task.done()
        assert not listener.closed and not database.closed and not router.cleaned
        assert state_root.exists()
        assert "server task is still running" in str(captured.value)
    finally:
        release.set()
        await asyncio.wait_for(server_task, timeout=1)

    await serve_demo._cleanup_resources(
        server=server,
        server_task=server_task,
        listener=listener,
        router=router,
        database=database,
        state_root=state_root,
        timeout=0.1,
    )
    assert listener.closed and database.closed and router.cleaned
    assert not state_root.exists()


async def test_cleanup_joins_slow_router_before_deleting_state_root(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class _BlockingRouter:
        def cleanup(self) -> None:
            entered.set()
            release.wait()
            finished.set()

    cleanup_task = asyncio.create_task(
        serve_demo._cleanup_resources(
            server=None,
            server_task=None,
            listener=None,
            router=_BlockingRouter(),
            database=None,
            state_root=state_root,
            timeout=0.01,
        )
    )
    await asyncio.wait_for(asyncio.to_thread(entered.wait), timeout=1)
    try:
        await asyncio.sleep(0.02)
        assert not cleanup_task.done()
        assert state_root.exists()
        assert not finished.is_set()
    finally:
        release.set()
    with pytest.raises(BaseExceptionGroup, match="router cleanup exceeded"):
        await asyncio.wait_for(cleanup_task, timeout=1)
    assert finished.is_set()
    assert not state_root.exists()


async def test_serve_cleans_acquired_resources_when_startup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    listener, database, _ = _stub_serve_dependencies(monkeypatch, tmp_path)
    monkeypatch.setattr(
        serve_demo,
        "DemoOrchestratorRouter",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("startup failed")),
    )

    with pytest.raises(RuntimeError, match="startup failed"):
        await asyncio.wait_for(
            serve_demo._serve(runtime_root, tmp_path / "ready.json", 10),
            timeout=1,
        )

    assert listener.closed and database.closed
    assert not (runtime_root / "state").exists()


async def test_cancelling_ready_serve_stops_server_and_cleans_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    ready_file = tmp_path / "ready.json"
    listener, database, router = _stub_serve_dependencies(monkeypatch, tmp_path)
    serve_task = asyncio.create_task(serve_demo._serve(runtime_root, ready_file, 10))
    for _ in range(100):
        if ready_file.exists():
            break
        await asyncio.sleep(0)
    assert ready_file.exists()

    serve_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(serve_task, timeout=1)

    assert listener.closed and database.closed and router.cleaned
    assert not (runtime_root / "state").exists()
