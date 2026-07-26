"""同源会话校验，不把 token 写入持久化存储。"""

from __future__ import annotations

import secrets
from hmac import compare_digest

from fastapi import HTTPException, Request, status


class SessionGuard:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(32)

    def require_mutation(self, request: Request) -> None:
        origin = request.headers.get("origin")
        expected_origin = str(request.base_url).rstrip("/")
        provided = request.headers.get("x-harness-session")
        if origin != expected_origin or provided is None or not compare_digest(provided, self.token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "SESSION_REQUIRED",
                    "message": "请求会话无效",
                    "details": {},
                    "event_id": None,
                },
            )
