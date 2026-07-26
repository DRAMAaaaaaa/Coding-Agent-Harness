"""可注入的 FastAPI 工厂。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from coding_agent_harness.api.dependencies import (
    ApiDependencies, SafeBranchResolver, UnavailableTaskRunner,
)
from coding_agent_harness.api.routes import create_router
from coding_agent_harness.api.session import SessionGuard
from coding_agent_harness.config import HarnessSettings
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.storage.workspaces import WorkspaceRepository
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.scanner import WorkspaceScanner
from coding_agent_harness.workspace.git import SafeGit


def create_app(*, settings: HarnessSettings | None = None, dependencies: ApiDependencies | None = None) -> FastAPI:
    settings = settings or HarnessSettings()
    sessions = SessionGuard()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database: Database | None = None
        if dependencies is None:
            database = await Database.open(settings.resolved_database_path())
            workspaces = WorkspaceRepository(database)
            tasks = TaskRepository(database)
            events = EventStore(database)
            app.state.dependencies = ApiDependencies(
                workspaces=workspaces, tasks=tasks, event_store=events,
                detector=ProjectDetector(), scanner=WorkspaceScanner(state_root=settings.state_root),
                state_root=settings.state_root,
                orchestrator_factory=None,
                task_runner=UnavailableTaskRunner(),
                branch_resolver=SafeBranchResolver(SafeGit(settings.state_root)),
            )
        else:
            app.state.dependencies = dependencies
        current: ApiDependencies = app.state.dependencies
        app.state.event_store = current.event_store
        app.state.tasks = current.tasks
        try:
            yield
        finally:
            if database is not None:
                await database.close()

    app = FastAPI(lifespan=lifespan)
    app.include_router(create_router(None, sessions))

    @app.get("/")
    async def index() -> PlainTextResponse:
        return PlainTextResponse("Coding Agent Harness", headers={"X-Harness-Session": sessions.token})

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, error: Exception) -> JSONResponse:
        Redactor().sanitize(error)
        return JSONResponse(status_code=500, content=_error_body("INTERNAL_ERROR", "服务内部错误"))

    @app.exception_handler(StarletteHTTPException)
    async def known_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        if isinstance(error.detail, dict) and set(error.detail) == {"code", "message", "details", "event_id"}:
            return JSONResponse(status_code=error.status_code, content=Redactor().sanitize(error.detail).value)
        return JSONResponse(status_code=error.status_code, content=_error_body("REQUEST_REJECTED", "请求被拒绝"))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        Redactor().sanitize(error.errors())
        return JSONResponse(status_code=422, content=_error_body("VALIDATION_ERROR", "请求格式无效"))

    return app


def _error_body(code: str, message: str) -> dict[str, object]:
    return {"code": code, "message": message, "details": {}, "event_id": None}
