from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scripts import serve_demo


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

    def cleanup(self) -> None:
        self.cleaned = True
        if self._fail:
            raise RuntimeError("router cleanup failed")


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
