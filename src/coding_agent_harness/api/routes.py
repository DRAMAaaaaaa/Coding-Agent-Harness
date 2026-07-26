"""严格 schema 的最小项目、任务与事件端点。"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from coding_agent_harness.api.dependencies import ApiDependencies
from coding_agent_harness.api.session import SessionGuard
from coding_agent_harness.api.sse import task_events
from coding_agent_harness.domain.models import Task
from coding_agent_harness.governance.path_identity import trusted_paths_overlap
from coding_agent_harness.storage.workspaces import StoredWorkspace, WorkspaceStorageError
from coding_agent_harness.workspace.detector import ProjectDetectionError
from coding_agent_harness.workspace.scanner import RepositoryScanError
from coding_agent_harness.governance.redaction import Redactor

_SUMMARY_ITEM_LIMIT = 256
_SUMMARY_TOTAL_LIMIT = 16 * 1024


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProjectRequest(_Request):
    path: str = Field(min_length=1, max_length=4096)


class TrustRequest(_Request):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class TaskRequest(_Request):
    workspace_id: UUID
    requirement: str = Field(min_length=1, max_length=65_536)

    @field_validator("workspace_id", mode="before")
    @classmethod
    def parse_workspace_id(cls, value: object) -> UUID:
        if isinstance(value, UUID):
            return value
        if not isinstance(value, str):
            raise ValueError("workspace_id 必须是 UUID")
        try:
            return UUID(value)
        except ValueError:
            raise ValueError("workspace_id 必须是 UUID") from None


def create_router(dependencies: ApiDependencies | None, sessions: SessionGuard) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects", status_code=status.HTTP_201_CREATED)
    async def create_project(request: Request, body: ProjectRequest) -> dict[str, object]:
        sessions.require_mutation(request)
        active = dependencies or request.app.state.dependencies
        try:
            root = Path(body.path).resolve(strict=True)
            if any(
                trusted_paths_overlap(root, private_root)
                for private_root in active.private_roots
            ):
                raise ValueError("项目路径与 Harness 私有状态重叠")
            profile = active.detector.detect(root)
            repository_map = active.scanner.scan(root)
            if repository_map.root != root:
                raise ValueError("项目路径不是 Git 根目录")
            branch = active.branch_resolver.default_branch(root)
            from coding_agent_harness.workspace.models import Workspace

            stored = await active.workspaces.create(
                Workspace(id=uuid4(), root=root, git_root=root, default_branch=branch, profile=profile)
            )
            return _workspace_response(stored, repository_map)
        except WorkspaceStorageError as error:
            raise _error(409, "WORKSPACE_CONFLICT", str(error)) from None
        except (OSError, RuntimeError, ValueError, ProjectDetectionError, RepositoryScanError):
            raise _error(400, "INVALID_PROJECT", "项目路径无效或不是受支持的 Git 仓库") from None

    @router.post("/api/projects/{workspace_id}/trust")
    async def trust_project(request: Request, workspace_id: UUID, body: TrustRequest) -> dict[str, object]:
        sessions.require_mutation(request)
        active = dependencies or request.app.state.dependencies
        stored = await active.workspaces.get(workspace_id)
        if stored is None:
            raise _error(404, "WORKSPACE_NOT_FOUND", "Workspace 不存在")
        try:
            current = active.detector.detect(stored.workspace.root)
            if current.trust_fingerprint != body.fingerprint:
                raise WorkspaceStorageError("信任指纹已变化或不匹配")
            if current != stored.workspace.profile:
                raise WorkspaceStorageError("项目配置已变化")
            trusted = await active.workspaces.trust(workspace_id, body.fingerprint)
            return _workspace_response(trusted)
        except (ProjectDetectionError, WorkspaceStorageError):
            raise _error(409, "TRUST_FINGERPRINT_MISMATCH", "信任指纹已变化或不匹配") from None

    @router.post("/api/tasks", status_code=status.HTTP_201_CREATED)
    async def create_task(request: Request, body: TaskRequest) -> dict[str, object]:
        sessions.require_mutation(request)
        active = dependencies or request.app.state.dependencies
        stored = await active.workspaces.get(body.workspace_id)
        if stored is None:
            raise _error(404, "WORKSPACE_NOT_FOUND", "Workspace 不存在")
        if not stored.is_trusted:
            raise _error(409, "WORKSPACE_UNTRUSTED", "Workspace 尚未建立当前信任")
        if active.orchestrator_factory is None:
            raise _error(503, "RUNTIME_UNAVAILABLE", "Agent 运行时未配置")
        try:
            current = active.detector.detect(stored.workspace.root)
            if current != stored.workspace.profile or current.trust_fingerprint != stored.trusted_fingerprint:
                await active.workspaces.revoke_trust(stored.workspace.id)
                raise _error(409, "STALE_PROJECT_TRUST", "项目配置已变化，需要重新建立信任")
        except ProjectDetectionError:
            raise _error(409, "STALE_PROJECT_TRUST", "项目配置已变化，需要重新建立信任") from None
        try:
            task = await active.task_runner.create(stored.workspace, uuid4(), body.requirement)
        except (OSError, RuntimeError, ValueError):
            raise _error(409, "WORKSPACE_BUSY", "Workspace 无法创建独立任务工作树") from None
        proposed = await active.orchestrator_factory().propose_plan(task.id)
        return _task_response(proposed)

    @router.post("/api/tasks/{task_id}/plan/approve")
    async def approve_plan(request: Request, task_id: UUID) -> dict[str, object]:
        sessions.require_mutation(request)
        active = dependencies or request.app.state.dependencies
        return _task_response(await _orchestrator_task(active, "approve_plan", task_id))

    @router.post("/api/tasks/{task_id}/run")
    async def run_task(request: Request, task_id: UUID) -> dict[str, object]:
        sessions.require_mutation(request)
        active = dependencies or request.app.state.dependencies
        return _task_response(await _orchestrator_task(active, "run_until_wait", task_id))

    @router.post("/api/tasks/{task_id}/final/approve")
    async def approve_final(request: Request, task_id: UUID) -> dict[str, object]:
        sessions.require_mutation(request)
        active = dependencies or request.app.state.dependencies
        return _task_response(await _orchestrator_task(active, "approve_final", task_id))

    @router.get("/api/tasks/{task_id}/events")
    async def events(request: Request, task_id: UUID, after: int = Query(default=0, ge=0)) -> StreamingResponse:
        active = dependencies or request.app.state.dependencies
        if await active.tasks.get(task_id) is None:
            raise _error(404, "TASK_NOT_FOUND", "任务不存在")
        return StreamingResponse(task_events(active.event_store, task_id, after), media_type="text/event-stream")

    @router.get("/api/tasks/{task_id}")
    async def get_task(request: Request, task_id: UUID) -> dict[str, object]:
        active = dependencies or request.app.state.dependencies
        task = await active.tasks.get(task_id)
        if task is None:
            raise _error(404, "TASK_NOT_FOUND", "任务不存在")
        return _task_response(task)

    return router


async def _orchestrator_task(dependencies: ApiDependencies, method: str, task_id: UUID) -> Task:
    if await dependencies.tasks.get(task_id) is None:
        raise _error(404, "TASK_NOT_FOUND", "任务不存在")
    if dependencies.orchestrator_factory is None:
        raise _error(503, "RUNTIME_UNAVAILABLE", "Agent 运行时未配置")
    orchestrator = dependencies.orchestrator_factory()
    try:
        operation = getattr(orchestrator, method)
        return await operation(task_id)  # type: ignore[no-any-return]
    except (KeyError, RuntimeError, ValueError):
        raise _error(409, "INVALID_TASK_STATE", "任务当前状态不允许该操作") from None


def _workspace_response(
    stored: StoredWorkspace, repository_map: object | None = None
) -> dict[str, object]:
    workspace = stored.workspace
    response: dict[str, object] = {
        "id": str(workspace.id), "default_branch": workspace.default_branch,
        "languages": list(workspace.profile.languages),
        "trust_fingerprint": workspace.profile.trust_fingerprint,
        "trusted": stored.is_trusted,
    }
    if repository_map is not None:
        from coding_agent_harness.workspace.models import RepositoryMap

        if not isinstance(repository_map, RepositoryMap):
            raise TypeError("仓库地图类型无效")
        summary = {
            "tracked_count": len(repository_map.tracked_files),
            "test_count": len(repository_map.test_paths),
            "dirty_count": len(repository_map.dirty_paths),
            "tracked_paths": list(repository_map.tracked_files[:100]),
            "test_paths": list(repository_map.test_paths[:100]),
            "dirty_paths": list(repository_map.dirty_paths[:100]),
            "recent_commits": list(repository_map.recent_commits[:20]),
            "document_paths": [document.path for document in repository_map.documents[:20]],
        }
        safe_summary = Redactor().sanitize(summary).value
        if not isinstance(safe_summary, dict):
            raise TypeError("仓库摘要无效")
        encoded = str(safe_summary).encode("utf-8")
        response["repository"] = (
            safe_summary if len(encoded) <= _SUMMARY_TOTAL_LIMIT else {"summary": "[REDACTED: summary exceeds safety limit]"}
        )
    return response


def _task_response(task: Task) -> dict[str, object]:
    return {"id": str(task.id), "workspace_id": str(task.workspace_id), "state": task.state.value}


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "details": {}, "event_id": None})
