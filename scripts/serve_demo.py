from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Callable, Protocol


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn  # noqa: E402

from coding_agent_harness.api.app import create_app  # noqa: E402
from coding_agent_harness.api.dependencies import (  # noqa: E402
    ApiDependencies,
    BlockingWorker,
    LocalTaskRunner,
    SafeBranchResolver,
)
from coding_agent_harness.config import HarnessSettings  # noqa: E402
from coding_agent_harness.demo import DemoOrchestratorRouter, demo_script  # noqa: E402
from coding_agent_harness.providers.mock import ScriptedMockProvider  # noqa: E402
from coding_agent_harness.storage.database import Database  # noqa: E402
from coding_agent_harness.storage.event_store import EventStore  # noqa: E402
from coding_agent_harness.storage.repositories import TaskRepository  # noqa: E402
from coding_agent_harness.storage.workspaces import WorkspaceRepository  # noqa: E402
from coding_agent_harness.workspace.detector import ProjectDetector  # noqa: E402
from coding_agent_harness.workspace.git import SafeGit  # noqa: E402
from coding_agent_harness.workspace.scanner import WorkspaceScanner  # noqa: E402


_CLEANUP_TIMEOUT_SECONDS = 10.0


class _ServerLike(Protocol):
    should_exit: bool


class _ListenerLike(Protocol):
    def close(self) -> None: ...


class _RouterLike(Protocol):
    def cleanup(self) -> None: ...


class _DatabaseLike(Protocol):
    async def close(self) -> None: ...


def _git_environment(home: Path) -> dict[str, str]:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    return {key: value for key, value in environment.items() if value}


def _run_git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        env=_git_environment(root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError("临时演示仓库初始化失败")
    return result.stdout.decode("utf-8").strip()


def _create_fixture(runtime_root: Path) -> tuple[Path, str]:
    fixture = runtime_root / "fixture"
    shutil.copytree(ROOT / "examples" / "python_demo", fixture)
    _run_git(fixture, "init", "-b", "main")
    _run_git(fixture, "config", "user.name", "Harness Demo")
    _run_git(fixture, "config", "user.email", "harness@example.invalid")
    _run_git(fixture, "config", "core.autocrlf", "false")
    _run_git(fixture, "add", ".")
    _run_git(fixture, "commit", "-m", "demo fixture")
    return fixture, _run_git(fixture, "rev-parse", "HEAD")


def _reserve_local_socket() -> tuple[socket.socket, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    return listener, int(listener.getsockname()[1])


def _write_ready(path: Path, payload: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


async def _stop_server(
    server: _ServerLike | None,
    server_task: asyncio.Task[object] | None,
    *,
    timeout: float,
) -> None:
    if server is not None:
        server.should_exit = True
    if server_task is None:
        return
    graceful_timeout = timeout / 2
    forced_timeout = timeout - graceful_timeout
    done, _ = await asyncio.wait({server_task}, timeout=graceful_timeout)
    if not done:
        server_task.cancel()
        done, _ = await asyncio.wait({server_task}, timeout=forced_timeout)
    if not done:
        raise TimeoutError("演示服务在取消后仍未停止")
    if server_task.cancelled():
        return
    server_task.result()


async def _cleanup_resources(
    *,
    server: _ServerLike | None,
    server_task: asyncio.Task[object] | None,
    listener: _ListenerLike | None,
    router: _RouterLike | None,
    database: _DatabaseLike | None,
    state_root: Path,
    timeout: float = _CLEANUP_TIMEOUT_SECONDS,
) -> None:
    errors: list[BaseException] = []

    async def attempt(operation: object) -> None:
        try:
            if asyncio.iscoroutine(operation):
                await asyncio.wait_for(operation, timeout=timeout)
        except BaseException as error:
            errors.append(error)

    async def join_thread(operation: Callable[[], object], *, label: str) -> None:
        task = asyncio.create_task(asyncio.to_thread(operation))
        wait_error: BaseException | None = None
        try:
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if not done:
                errors.append(TimeoutError(f"{label} exceeded {timeout} seconds"))
        except BaseException as error:
            wait_error = error
        result_observed = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as error:
                if task.cancelled():
                    errors.append(error)
                    result_observed = True
                    break
                errors.append(error)
            except BaseException as error:
                errors.append(error)
                result_observed = True
                break
        if not result_observed:
            try:
                task.result()
            except BaseException as error:
                errors.append(error)
        if wait_error is not None:
            errors.append(wait_error)

    try:
        await _stop_server(server, server_task, timeout=timeout)
    except BaseException as error:
        errors.append(error)
    if listener is not None:
        try:
            listener.close()
        except BaseException as error:
            errors.append(error)
    if router is not None:
        await join_thread(router.cleanup, label="router cleanup")
    if database is not None:
        await attempt(database.close())
    if state_root.exists():
        await join_thread(
            lambda: shutil.rmtree(state_root, ignore_errors=False),
            label="state cleanup",
        )
    if errors:
        summaries = "; ".join(str(error) or type(error).__name__ for error in errors)
        raise BaseExceptionGroup(f"演示服务清理失败: {summaries}", errors)


async def _serve(runtime_root: Path, ready_file: Path, max_seconds: float) -> int:
    state_root = runtime_root / "state"
    database: Database | None = None
    listener: socket.socket | None = None
    router: DemoOrchestratorRouter | None = None
    server: uvicorn.Server | None = None
    server_task: asyncio.Task[object] | None = None
    result = 1
    primary_error: BaseException | None = None
    try:
        fixture, initial_head = _create_fixture(runtime_root)
        database = await Database.open(state_root / "harness.db")
        listener, port = _reserve_local_socket()
        completed = asyncio.Event()
        workspaces = WorkspaceRepository(database)
        tasks = TaskRepository(database)
        event_store = EventStore(database)
        worker = BlockingWorker()
        router = DemoOrchestratorRouter(
            provider=ScriptedMockProvider(demo_script()),
            tasks=tasks,
            workspaces=workspaces,
            event_store=event_store,
            state_root=state_root,
            on_completed=completed.set,
        )
        settings = HarnessSettings(
            bind_host="127.0.0.1",
            bind_port=port,
            state_root=state_root,
            database_path=state_root / "harness.db",
            trusted_hosts=(f"127.0.0.1:{port}",),
            trusted_origins=(f"http://127.0.0.1:{port}",),
        )
        dependencies = ApiDependencies(
            workspaces=workspaces,
            tasks=tasks,
            event_store=event_store,
            detector=ProjectDetector(),
            scanner=WorkspaceScanner(state_root=state_root),
            state_root=state_root,
            private_roots=settings.private_state_roots(),
            orchestrator_factory=lambda: router,
            task_runner=LocalTaskRunner(
                tasks,
                state_root,
                step_budget=8,
                time_budget_seconds=120,
                worker=worker,
            ),
            branch_resolver=SafeBranchResolver(SafeGit(state_root)),
            worker=worker,
        )
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(settings=settings, dependencies=dependencies),
                host="127.0.0.1",
                port=port,
                log_level="error",
                access_log=False,
            )
        )
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            if server_task.done():
                await server_task
                raise RuntimeError("演示服务启动失败")
            await asyncio.sleep(0.01)
        _write_ready(
            ready_file,
            {
                "url": f"http://127.0.0.1:{port}",
                "fixture": str(fixture),
                "initial_head": initial_head,
                "worktree_root": str(state_root),
            },
        )
        try:
            await asyncio.wait_for(completed.wait(), timeout=max_seconds)
        except TimeoutError:
            result = 1
        else:
            await asyncio.sleep(0.5)
            result = 0
    except BaseException as error:
        primary_error = error
    cleanup_error: BaseException | None = None
    try:
        await _cleanup_resources(
            server=server,
            server_task=server_task,
            listener=listener,
            router=router,
            database=database,
            state_root=state_root,
        )
    except BaseException as error:
        cleanup_error = error
    if primary_error is not None and cleanup_error is not None:
        raise BaseExceptionGroup(
            "演示服务运行和清理均失败", [primary_error, cleanup_error]
        )
    if primary_error is not None:
        raise primary_error
    if cleanup_error is not None:
        raise cleanup_error
    return result


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动完全离线的 localhost Harness 演示")
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--max-seconds", type=float, default=120.0)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    if arguments.max_seconds <= 0:
        return 2
    if arguments.runtime_root is not None:
        runtime_root = arguments.runtime_root.resolve(strict=False)
        runtime_root.mkdir(parents=True, exist_ok=False)
        return asyncio.run(_serve(runtime_root, arguments.ready_file, arguments.max_seconds))
    with TemporaryDirectory(prefix="harness-web-demo-") as directory:
        return asyncio.run(_serve(Path(directory), arguments.ready_file, arguments.max_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
