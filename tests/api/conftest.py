from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from coding_agent_harness.api.app import create_app
from coding_agent_harness.api.dependencies import LocalTaskRunner
from coding_agent_harness.agent.orchestrator import AgentOrchestrator
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.config import HarnessSettings
from coding_agent_harness.providers.mock import ScriptedMockProvider


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        settings=HarnessSettings(
            state_root=tmp_path / "state",
            database_path=tmp_path / "state" / "harness.db",
        )
    )
    async with app.router.lifespan_context(app):
        current = app.state.dependencies
        orchestrator = AgentOrchestrator(
            provider=ScriptedMockProvider(["最小计划"]),
            parser=ActionParser(()),
            tools=_UnusedTools(),
            event_store=current.event_store,
            tasks=current.tasks,
        )
        current.orchestrator_factory = lambda: orchestrator
        current.task_runner = LocalTaskRunner(
            current.tasks, current.state_root, step_budget=8, time_budget_seconds=300,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as value:
            yield value


async def session_headers(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.get("/")
    return {
        "Origin": "http://testserver",
        "X-Harness-Session": response.headers["x-harness-session"],
    }


class _UnusedTools:
    async def execute(self, action: object) -> object:
        raise AssertionError("计划阶段不应执行工具")
