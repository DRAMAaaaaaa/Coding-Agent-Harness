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


async def _serve(runtime_root: Path, ready_file: Path, max_seconds: float) -> int:
    fixture, initial_head = _create_fixture(runtime_root)
    state_root = runtime_root / "state"
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
    try:
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
            return 1
        await asyncio.sleep(0.5)
        server.should_exit = True
        await server_task
        return 0
    finally:
        server.should_exit = True
        if not server_task.done():
            await server_task
        listener.close()
        await router.cleanup()
        await database.close()
        shutil.rmtree(state_root, ignore_errors=False)


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
