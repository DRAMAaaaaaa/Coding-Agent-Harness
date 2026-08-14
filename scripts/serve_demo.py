from __future__ import annotations

import argparse
import asyncio
from ipaddress import ip_address
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
from tempfile import TemporaryDirectory, mkdtemp
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
from coding_agent_harness.storage.project_learning import ProjectLearningRepository  # noqa: E402
from coding_agent_harness.learning.cards import ProjectLearningService  # noqa: E402
from coding_agent_harness.learning.questions import QuestionService  # noqa: E402
from coding_agent_harness.replay.branches import CorrectionBranchService  # noqa: E402
from coding_agent_harness.storage.correction_branches import CorrectionBranchRepository  # noqa: E402
from coding_agent_harness.workspace.detector import ProjectDetector  # noqa: E402
from coding_agent_harness.workspace.git import SafeGit  # noqa: E402
from coding_agent_harness.workspace.scanner import WorkspaceScanner  # noqa: E402


_CLEANUP_TIMEOUT_SECONDS = 10.0


def _trusted_request_targets(
    bind_port: int,
    public_host: str | None,
    public_origin: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    hosts = (f"127.0.0.1:{bind_port}", f"localhost:{bind_port}")
    origins = tuple(f"http://{host}" for host in hosts)
    if public_host is None and public_origin is None:
        return hosts, origins
    if public_host is None or public_origin is None:
        raise ValueError("公网演示 Host 与 Origin 必须同时配置")
    try:
        address = ip_address(public_host)
    except ValueError:
        raise ValueError("公网演示 Host 必须是无端口 IPv4 地址") from None
    if (
        address.version != 4
        or public_host != str(address)
        or public_host != "47.76.86.198"
    ):
        raise ValueError("公网演示 Host 必须是批准的固定 IPv4 地址")
    expected_origin = f"http://{public_host}"
    if public_origin != expected_origin:
        raise ValueError("公网演示 Origin 必须精确匹配 HTTP IPv4 Host")
    return (*hosts, public_host), (*origins, public_origin)


class _ServerLike(Protocol):
    should_exit: bool


class _ListenerLike(Protocol):
    def close(self) -> None: ...


class _RouterLike(Protocol):
    def cleanup(self) -> None: ...


class _DatabaseLike(Protocol):
    async def close(self) -> None: ...


class _ServerStillRunningError(TimeoutError):
    pass


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


def _create_fixture(
    runtime_root: Path,
    project_source: Path | None = None,
) -> tuple[Path, str]:
    source = project_source or ROOT / "examples" / "python_demo"
    try:
        source = source.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("演示项目源必须是现有目录") from None
    if not source.is_dir():
        raise ValueError("演示项目源必须是现有目录")
    fixture = runtime_root / "fixture"
    shutil.copytree(source, fixture, symlinks=True)
    # 演示验证会生成 Python 缓存；忽略它以保持纠正检查点只包含受控文本改动。
    (fixture / ".gitignore").write_text("__pycache__/\n", encoding="utf-8", newline="\n")
    _run_git(fixture, "init", "-b", "main")
    _run_git(fixture, "config", "user.name", "Harness Demo")
    _run_git(fixture, "config", "user.email", "harness@example.invalid")
    _run_git(fixture, "config", "core.autocrlf", "false")
    _run_git(fixture, "add", ".")
    _run_git(fixture, "commit", "-m", "demo fixture")
    return fixture, _run_git(fixture, "rev-parse", "HEAD")


def _reserve_local_socket(
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[socket.socket, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
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


def _prepare_stable_runtime_root(runtime_root: Path) -> Path:
    runtime_root.mkdir(parents=True, exist_ok=True)
    for child_name in ("fixture", "state"):
        child = runtime_root / child_name
        if child.exists():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    return runtime_root


def _start_stdin_eof_watcher(
    loop: asyncio.AbstractEventLoop,
    stdin_closed: asyncio.Event,
) -> None:
    def watch() -> None:
        try:
            sys.stdin.buffer.read()
        except (OSError, ValueError):
            pass
        try:
            loop.call_soon_threadsafe(stdin_closed.set)
        except RuntimeError:
            pass

    threading.Thread(
        target=watch,
        name="harness-demo-stdin-eof",
        daemon=True,
    ).start()


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
        raise _ServerStillRunningError("server task is still running after cancellation")
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
        if server_task is not None and not server_task.done():
            still_running = _ServerStillRunningError(
                "server task is still running after cleanup interruption"
            )
            causes = (
                [error]
                if isinstance(error, _ServerStillRunningError)
                else [error, still_running]
            )
            raise BaseExceptionGroup(
                f"演示服务仍在运行，保留清理现场: {still_running}", causes
            ) from error
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


async def _serve(
    runtime_root: Path,
    ready_file: Path,
    max_seconds: float,
    *,
    bind_host: str = "127.0.0.1",
    bind_port: int = 0,
    public_host: str | None = None,
    public_origin: str | None = None,
    project_source: Path | None = None,
    keep_alive: bool = False,
    shutdown_on_stdin_close: bool = False,
) -> int:
    state_root = runtime_root / "state"
    database: Database | None = None
    listener: socket.socket | None = None
    router: DemoOrchestratorRouter | None = None
    server: uvicorn.Server | None = None
    server_task: asyncio.Task[object] | None = None
    result = 1
    primary_error: BaseException | None = None
    try:
        fixture, initial_head = (
            _create_fixture(runtime_root)
            if project_source is None
            else _create_fixture(runtime_root, project_source)
        )
        database = await Database.open(state_root / "harness.db")
        listener, port = (
            _reserve_local_socket()
            if bind_host == "127.0.0.1" and bind_port == 0
            else _reserve_local_socket(bind_host, bind_port)
        )
        trusted_hosts, trusted_origins = _trusted_request_targets(
            port, public_host, public_origin,
        )
        completed = asyncio.Event()
        stdin_closed = asyncio.Event()
        if shutdown_on_stdin_close:
            _start_stdin_eof_watcher(asyncio.get_running_loop(), stdin_closed)
        workspaces = WorkspaceRepository(database)
        tasks = TaskRepository(database)
        event_store = EventStore(database)
        worker = BlockingWorker()
        project_learning = ProjectLearningService(
            ProjectLearningRepository(database), tasks, event_store,
        )
        router = DemoOrchestratorRouter(
            provider=ScriptedMockProvider(demo_script()),
            tasks=tasks,
            workspaces=workspaces,
            event_store=event_store,
            state_root=state_root,
            project_learning=project_learning,
            on_completed=None if keep_alive else completed.set,
        )
        settings = HarnessSettings(
            bind_host=bind_host,
            bind_port=port,
            state_root=state_root,
            database_path=state_root / "harness.db",
            trusted_hosts=trusted_hosts,
            trusted_origins=trusted_origins,
        )
        task_runner = LocalTaskRunner(
            tasks, state_root, step_budget=8, time_budget_seconds=120, worker=worker,
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
            task_runner=task_runner,
            branch_resolver=SafeBranchResolver(SafeGit(state_root)),
            worker=worker,
            provider_registry=router.provider_registry,
            question_service=QuestionService(
                tasks, event_store, provider_for_task=router.provider_for_task,
            ),
            correction_branches=CorrectionBranchService(
                branches=CorrectionBranchRepository(database), tasks=tasks,
                events=event_store, workspaces=workspaces, runner=task_runner,
                providers=router.provider_registry, state_root=state_root, worker=worker,
            ),
            project_learning=project_learning,
        )
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(settings=settings, dependencies=dependencies),
                host=bind_host,
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
        waiters: list[asyncio.Task[bool]] = []
        if not keep_alive:
            waiters.append(asyncio.create_task(completed.wait()))
        if shutdown_on_stdin_close:
            waiters.append(asyncio.create_task(stdin_closed.wait()))
        try:
            timeout = None if max_seconds == 0 else max_seconds
            if waiters:
                done, _ = await asyncio.wait(
                    waiters,
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                result = 0 if done else 1
            elif timeout is None:
                await server_task
                result = 1
            else:
                await asyncio.sleep(timeout)
                result = 1
        finally:
            for waiter in waiters:
                if not waiter.done():
                    waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)
        if result == 0:
            await asyncio.sleep(0.5)
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--project-source", type=Path)
    parser.add_argument("--public-host", default=os.environ.get("HARNESS_PUBLIC_HOST"))
    parser.add_argument("--public-origin", default=os.environ.get("HARNESS_PUBLIC_ORIGIN"))
    parser.add_argument("--keep-alive", action="store_true", help="允许同一演示会话连续创建多个任务")
    parser.add_argument("--shutdown-on-stdin-close", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    if arguments.max_seconds < 0 or not 0 <= arguments.port <= 65_535:
        return 2
    if arguments.runtime_root is not None:
        runtime_parent = arguments.runtime_root.resolve(strict=False)
        runtime_parent.mkdir(parents=True, exist_ok=True)
        runtime_root = (
            _prepare_stable_runtime_root(runtime_parent)
            if arguments.max_seconds == 0 and arguments.keep_alive
            else Path(mkdtemp(prefix="session-", dir=runtime_parent))
        )
        return asyncio.run(
            _serve(
                runtime_root,
                arguments.ready_file,
                arguments.max_seconds,
                bind_host=arguments.host,
                bind_port=arguments.port,
                public_host=arguments.public_host,
                public_origin=arguments.public_origin,
                project_source=arguments.project_source,
                keep_alive=arguments.keep_alive,
                shutdown_on_stdin_close=arguments.shutdown_on_stdin_close,
            )
        )
    with TemporaryDirectory(prefix="harness-web-demo-") as directory:
        return asyncio.run(
            _serve(
                Path(directory),
                arguments.ready_file,
                arguments.max_seconds,
                bind_host=arguments.host,
                bind_port=arguments.port,
                public_host=arguments.public_host,
                public_origin=arguments.public_origin,
                project_source=arguments.project_source,
                keep_alive=arguments.keep_alive,
                shutdown_on_stdin_close=arguments.shutdown_on_stdin_close,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
