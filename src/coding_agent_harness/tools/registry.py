from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.governance.policy import PolicyDecision
from coding_agent_harness.tools import files, git, search, verification
from coding_agent_harness.tools.models import ToolContext, ToolResult


class _ApplyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    expected_sha256: str | None
    content: str


class _DeleteFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    expected_sha256: str


class _Search(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str


class _Verification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str


class _Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ToolRegistry:
    """只将固定、受治理的动作分发至最小工具实现。"""

    def __init__(self, context: ToolContext) -> None:
        self._context = context
        self._guard = PathGuard(context.workspace_root)

    async def execute(self, action: ToolAction, context: ToolContext | None = None) -> ToolResult:
        if context is not None and context != self._context:
            return ToolResult(ok=False, code="CONTEXT_MISMATCH")
        if self._context.policy is not None and self._context.policy_context is not None:
            decision = self._context.policy.evaluate(action, self._context.policy_context)
            if decision.decision is PolicyDecision.DENY:
                return ToolResult(ok=False, code=decision.reason_code)
            if decision.decision is PolicyDecision.REQUIRE_APPROVAL and action.tool != "delete_file":
                return ToolResult(ok=False, code="APPROVAL_REQUIRED")
        handlers = {
            "apply_patch": self._apply_patch,
            "delete_file": self._delete_file,
            "search": self._search,
            "run_verification": self._verification,
            "git_status": self._git_status,
            "git_diff": self._git_diff,
        }
        handler = handlers.get(action.tool)
        if handler is None:
            return ToolResult(ok=False, code="UNSUPPORTED_TOOL")
        return await handler(action.arguments)

    def _path(self, candidate: str) -> Path | None:
        try:
            return self._guard.resolve(candidate)
        except PathEscapeError:
            return None

    async def _apply_patch(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            request = _ApplyPatch.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        path = self._path(request.path)
        if path is None:
            return ToolResult(ok=False, code="PATH_ESCAPE")
        code = files.atomic_replace(path, request.content, request.expected_sha256)
        return ToolResult(ok=code == "OK", code=code, changed_paths=(request.path,) if code == "OK" else ())

    async def _delete_file(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            request = _DeleteFile.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        path = self._path(request.path)
        if path is None:
            return ToolResult(ok=False, code="PATH_ESCAPE")
        consumer = self._context.approval_consumer
        if consumer is None or not await consumer():
            return ToolResult(ok=False, code="APPROVAL_REQUIRED")
        code = files.delete_regular_file(path, request.expected_sha256)
        return ToolResult(ok=code == "OK", code=code, changed_paths=(request.path,) if code == "OK" else ())

    async def _search(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            request = _Search.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        if self._context.repository_map is None:
            return ToolResult(ok=False, code="REPOSITORY_MAP_REQUIRED")
        return ToolResult(ok=True, code="OK", output=search.search(self._context.repository_map, request.query))

    async def _verification(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            request = _Verification.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        if request.name not in {"test", "lint", "typecheck", "build"} or self._context.profile is None:
            return ToolResult(ok=False, code="UNAVAILABLE_VERIFICATION")
        code, output = verification.run_verification(self._guard.root, self._context.profile, request.name, self._context.runner)
        return ToolResult(ok=code == "OK", code=code, output=output, retryable=code == "VERIFICATION_FAILED")

    async def _git_status(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            _Empty.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        if self._context.safe_git is None:
            return ToolResult(ok=False, code="GIT_UNAVAILABLE")
        code, output = git.status(self._context.safe_git, self._guard.root)
        return ToolResult(ok=code == "OK", code=code, output=output)

    async def _git_diff(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            _Empty.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        if self._context.safe_git is None:
            return ToolResult(ok=False, code="GIT_UNAVAILABLE")
        code, output = git.diff(self._context.safe_git, self._guard.root)
        return ToolResult(ok=code == "OK", code=code, output=output)
