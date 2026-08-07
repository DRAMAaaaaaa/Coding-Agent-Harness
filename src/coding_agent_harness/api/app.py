"""可注入的 FastAPI 工厂。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from coding_agent_harness.api.dependencies import (
    ApiDependencies, BlockingWorker, LocalTaskRunner, SafeBranchResolver, UnavailableTaskRunner,
)
from coding_agent_harness.api.routes import create_router
from coding_agent_harness.api.provider_routes import create_provider_router
from coding_agent_harness.api.session import SessionGuard
from coding_agent_harness.config import HarnessSettings
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.storage.workspaces import WorkspaceRepository
from coding_agent_harness.storage.provider_profiles import ProviderProfileRepository
from coding_agent_harness.providers.credentials import CredentialBroker, SessionOnlyCredentialStore
from coding_agent_harness.providers.registry import ProviderRegistry
from coding_agent_harness.providers.binding import ProviderBindingCoordinator
from coding_agent_harness.runtime import RuntimeOrchestratorRouter
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.scanner import WorkspaceScanner
from coding_agent_harness.workspace.git import SafeGit

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(*, settings: HarnessSettings | None = None, dependencies: ApiDependencies | None = None) -> FastAPI:
    settings = settings or HarnessSettings()
    if settings.trusted_hosts is None or settings.trusted_origins is None:
        raise ValueError("可信 Host 与 Origin 未配置")
    sessions = SessionGuard(
        trusted_hosts=settings.trusted_hosts,
        trusted_origins=settings.trusted_origins,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if dependencies is not None:
            app.state.dependencies = dependencies
            app.state.event_store = dependencies.event_store
            app.state.tasks = dependencies.tasks
            yield
            return

        database = await Database.open(settings.resolved_database_path())
        client = httpx.AsyncClient(trust_env=False, follow_redirects=False)
        try:
            workspaces = WorkspaceRepository(database)
            tasks = TaskRepository(database)
            events = EventStore(database)
            worker = BlockingWorker()
            binding = ProviderBindingCoordinator()
            profiles = ProviderProfileRepository(database, coordinator=binding)
            credentials = CredentialBroker(SessionOnlyCredentialStore(), worker)
            registry = ProviderRegistry(profiles, credentials, client_factory=lambda: client)
            app.state.dependencies = ApiDependencies(
                workspaces=workspaces, tasks=tasks, event_store=events,
                detector=ProjectDetector(), scanner=WorkspaceScanner(state_root=settings.state_root),
                state_root=settings.state_root,
                private_roots=settings.private_state_roots(),
                orchestrator_factory=None,
                task_runner=UnavailableTaskRunner(),
                branch_resolver=SafeBranchResolver(SafeGit(settings.state_root)),
                worker=worker,
                profiles=profiles,
                credentials=credentials,
                provider_registry=registry,
                require_provider_profile=True,
                provider_binding=binding,
            )
            app.state.dependencies.orchestrator_factory = lambda: RuntimeOrchestratorRouter(app.state.dependencies)
            app.state.dependencies.task_runner = LocalTaskRunner(
                tasks, settings.state_root, step_budget=settings.max_task_cycles,
                time_budget_seconds=settings.command_timeout_seconds, worker=worker,
            )
            app.state.event_store = events
            app.state.tasks = tasks
            yield
        finally:
            await client.aclose()
            if dependencies is None:
                credentials.clear_session()
            await database.close()

    app = FastAPI(lifespan=lifespan)
    api_router = create_router(None, sessions)
    api_router.include_router(create_provider_router(sessions))
    app.include_router(api_router)

    @app.middleware("http")
    async def require_trusted_host(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not sessions.is_trusted_host(request):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=_error_body("UNTRUSTED_HOST", "请求 Host 不受信任"),
            )
        if request.url.path == "/api" or request.url.path.startswith("/api/"):
            matches = [
                (route, route.matches(request.scope)[0])
                for route in api_router.routes
            ]
            if not any(match is Match.FULL for _, match in matches):
                allowed = sorted(
                    {
                        method
                        for route, match in matches
                        if match is Match.PARTIAL
                        for method in (getattr(route, "methods", None) or ())
                    }
                )
                response_status = (
                    status.HTTP_405_METHOD_NOT_ALLOWED
                    if allowed
                    else status.HTTP_404_NOT_FOUND
                )
                headers = {"Allow": ", ".join(allowed)} if allowed else None
                return JSONResponse(
                    status_code=response_status,
                    content=_error_body("REQUEST_REJECTED", "请求被拒绝"),
                    headers=headers,
                )
        return await call_next(request)

    @app.get("/")
    async def index() -> Response:
        index_file = WEB_DIST / "index.html"
        if index_file.is_file():
            return FileResponse(
                index_file,
                headers={"Cache-Control": "no-store", "X-Harness-Session": sessions.token},
            )
        return PlainTextResponse(
            "Coding Agent Harness WebUI build not found. Run the web build before starting the service.",
            headers={
                "Cache-Control": "no-store",
                "X-Harness-Session": sessions.token,
            },
        )

    @app.get("/{asset_path:path}", include_in_schema=False)
    async def static_asset(asset_path: str) -> FileResponse:
        dist_root = WEB_DIST.resolve(strict=False)
        try:
            target = (dist_root / asset_path).resolve(strict=True)
            target.relative_to(dist_root)
        except (OSError, RuntimeError, ValueError):
            raise StarletteHTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
        if not target.is_file():
            raise StarletteHTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return FileResponse(target)

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
