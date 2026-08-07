"""仅限会话的 Provider 配置 API。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from coding_agent_harness.api.session import SessionGuard
from coding_agent_harness.providers.models import ProviderKind, ProviderProfile


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProviderRequest(_Request):
    kind: ProviderKind
    model: str

    @field_validator("kind", mode="before")
    @classmethod
    def parse_kind(cls, value: object) -> ProviderKind:
        if isinstance(value, ProviderKind):
            return value
        if not isinstance(value, str):
            raise ValueError("provider kind must be a string")
        return ProviderKind(value)


class SessionCredentialRequest(_Request):
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def key_is_a_bounded_non_nul_utf8_value(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if "\x00" in raw or len(raw.encode("utf-8")) > 192:
            raise ValueError("invalid session credential")
        return value


def create_provider_router(sessions: SessionGuard) -> APIRouter:
    router = APIRouter()

    @router.get("/api/providers")
    async def list_providers(request: Request) -> list[dict[str, object]]:
        active = request.app.state.dependencies
        if active.profiles is None or active.credentials is None:
            return []
        return [await _profile_response(profile, active.credentials) for profile in await active.profiles.list()]

    @router.post("/api/providers", status_code=status.HTTP_201_CREATED)
    async def create_provider(request: Request, body: ProviderRequest) -> dict[str, object]:
        sessions.require_mutation(request)
        active = request.app.state.dependencies
        if active.profiles is None or active.credentials is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail={"code": "RUNTIME_UNAVAILABLE", "message": "Provider 运行时未配置", "details": {}, "event_id": None})
        profile = await active.profiles.create(body.kind, body.model)
        return await _profile_response(profile, active.credentials)

    @router.put("/api/providers/{profile_id}/session-credential")
    async def put_session_credential(
        request: Request, profile_id: UUID, body: SessionCredentialRequest
    ) -> dict[str, object]:
        sessions.require_mutation(request)
        active = request.app.state.dependencies
        if active.profiles is None or active.credentials is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail={"code": "RUNTIME_UNAVAILABLE", "message": "Provider 运行时未配置", "details": {}, "event_id": None})
        profile = await active.profiles.get(profile_id)
        if profile is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail={"code": "PROVIDER_PROFILE_NOT_FOUND", "message": "Provider Profile 不存在", "details": {}, "event_id": None})
        from coding_agent_harness.providers.credentials import CredentialPersistence

        await active.credentials.put(profile_id, body.api_key, CredentialPersistence.SESSION)
        return await _profile_response(profile, active.credentials)

    return router


async def _profile_response(profile: ProviderProfile, credentials: object) -> dict[str, object]:
    status_value = await credentials.status(profile.id)  # type: ignore[attr-defined]
    return {"id": str(profile.id), "kind": profile.kind.value, "model": profile.model, "version": profile.version, "configured": status_value.configured}
