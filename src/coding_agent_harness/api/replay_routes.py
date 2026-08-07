"""单级纠正分支的最小 API。"""

from __future__ import annotations

from dataclasses import asdict
from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from coding_agent_harness.api.dependencies import ApiDependencies
from coding_agent_harness.api.session import SessionGuard
from coding_agent_harness.replay.branches import CorrectionBranchError


class _CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_event_sequence: int = Field(gt=0)
    correction: str = Field(min_length=1, max_length=8192)


def create_replay_router(sessions: SessionGuard) -> APIRouter:
    router = APIRouter()

    @router.post("/api/tasks/{task_id}/correction-branches", status_code=status.HTTP_201_CREATED)
    async def create_branch(request: Request, task_id: UUID, body: _CorrectionRequest) -> dict[str, object]:
        sessions.require_mutation(request)
        active: ApiDependencies = request.app.state.dependencies
        service = active.correction_branches
        if service is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            branch = await service.create(task_id, body.source_event_sequence, body.correction)
        except KeyError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
        except (CorrectionBranchError, ValueError):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT) from None
        if branch.child_task_id is not None and active.orchestrator_factory is not None:
            orchestrator = active.orchestrator_factory()
            try:
                await orchestrator.propose_plan(branch.child_task_id)
            except Exception:
                try:
                    await orchestrator.record_runtime_failure(branch.child_task_id, "RUNTIME_FAILURE")
                except Exception:
                    pass
        return cast(dict[str, object], branch.model_dump(mode="json"))

    @router.get("/api/correction-branches/{branch_id}/comparison")
    async def comparison(request: Request, branch_id: UUID) -> dict[str, object]:
        active: ApiDependencies = request.app.state.dependencies
        service = active.correction_branches
        if service is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            value = await service.compare(branch_id)
        except KeyError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
        return cast(dict[str, object], asdict(value))

    return router
