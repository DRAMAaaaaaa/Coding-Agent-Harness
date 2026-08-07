"""意图卡片与失败节点只读提问 API。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from coding_agent_harness.api.dependencies import ApiDependencies
from coding_agent_harness.api.session import SessionGuard
from coding_agent_harness.learning.intent import IntentProjector
from coding_agent_harness.learning.questions import MAX_QUESTION_BYTES, QuestionService


class _QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    card_id: str = Field(min_length=1, max_length=512)
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def validate_question_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_QUESTION_BYTES:
            raise ValueError("question exceeds byte limit")
        return value


def create_learning_router(sessions: SessionGuard) -> APIRouter:
    router = APIRouter()

    @router.get("/api/tasks/{task_id}/intent-cards")
    async def intent_cards(request: Request, task_id: UUID) -> list[dict[str, object]]:
        active: ApiDependencies = request.app.state.dependencies
        if await active.tasks.get(task_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        cards = IntentProjector().project(task_id, await active.event_store.list_for_task(task_id))
        return [card.model_dump(mode="json") for card in cards]

    @router.post("/api/tasks/{task_id}/questions")
    async def ask_question(request: Request, task_id: UUID, body: _QuestionRequest) -> dict[str, str]:
        sessions.require_mutation(request)
        active: ApiDependencies = request.app.state.dependencies
        service = active.question_service
        if service is None:
            if active.provider_registry is None:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
            service = QuestionService(active.tasks, active.event_store, provider_for_task=active.provider_registry.build_for_task)
        try:
            answer = await service.ask(task_id, body.card_id, body.question)
        except KeyError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
        except ValueError:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT) from None
        return answer.model_dump()

    return router
