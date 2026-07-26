"""同源会话校验，不把 token 写入持久化存储。"""

from __future__ import annotations

import secrets
from hmac import compare_digest

from fastapi import HTTPException, Request, status


class SessionGuard:
    def __init__(
        self,
        *,
        trusted_hosts: tuple[str, ...],
        trusted_origins: tuple[str, ...],
    ) -> None:
        self.token = secrets.token_urlsafe(32)
        self._token = self.token.encode("ascii")
        self._trusted_hosts = tuple(host.encode("ascii") for host in trusted_hosts)
        self._trusted_origins = tuple(origin.encode("ascii") for origin in trusted_origins)

    def is_trusted_host(self, request: Request) -> bool:
        hosts = request.headers.getlist("host")
        return len(hosts) == 1 and _matches_any(hosts[0].casefold(), self._trusted_hosts)

    def require_mutation(self, request: Request) -> None:
        origins = request.headers.getlist("origin")
        provided = request.headers.getlist("x-harness-session")
        if (
            not self.is_trusted_host(request)
            or len(origins) != 1
            or not _matches_any(origins[0].casefold(), self._trusted_origins)
            or len(provided) != 1
            or not _matches(provided[0], self._token)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "SESSION_REQUIRED",
                    "message": "请求会话无效",
                    "details": {},
                    "event_id": None,
                },
            )


def _matches_any(value: str, expected_values: tuple[bytes, ...]) -> bool:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return any(compare_digest(encoded, expected) for expected in expected_values)


def _matches(value: str, expected: bytes) -> bool:
    try:
        return compare_digest(value.encode("ascii"), expected)
    except UnicodeEncodeError:
        return False
