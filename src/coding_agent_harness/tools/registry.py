from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.governance.policy import PolicyDecision, normalized_delete_scope
from coding_agent_harness.governance.approvals import ApprovalContext, ApprovalError
from coding_agent_harness.tools import files, git, search, verification
from coding_agent_harness.tools.models import (
    ToolContext,
    ToolObservation,
    ToolResult,
    VerificationEvidence,
)
from coding_agent_harness.workspace.files import (
    BoundedFileReadError,
    BoundedFileReader,
    BoundedFileTooLargeError,
    UnsafeBoundedFileError,
)


_MAX_READ_FILE_BYTES = 64 * 1024


class _ApplyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    expected_sha256: str | None
    content: str


class _DeleteFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    expected_sha256: str
    approval_id: str | None = None


class _Search(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str


class _ReadFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str


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
        result = await self._execute_unobserved(action, context)
        return self._with_observation(action, result)

    async def _execute_unobserved(
        self, action: ToolAction, context: ToolContext | None = None
    ) -> ToolResult:
        if context is not None and context != self._context:
            return ToolResult(ok=False, code="CONTEXT_MISMATCH")
        policy_action = action
        if action.tool == "delete_file":
            try:
                request = _DeleteFile.model_validate(action.arguments)
            except ValidationError:
                return ToolResult(ok=False, code="INVALID_ARGUMENTS")
            policy_action = ToolAction(
                tool="delete_file",
                arguments={"path": request.path, "expected_sha256": request.expected_sha256},
                idempotency_key=action.idempotency_key,
            )
        if self._context.policy is not None and self._context.policy_context is not None:
            decision = self._context.policy.evaluate(policy_action, self._context.policy_context)
            if decision.decision is PolicyDecision.DENY:
                return ToolResult(ok=False, code=decision.reason_code)
            if decision.decision is PolicyDecision.REQUIRE_APPROVAL and action.tool != "delete_file":
                return ToolResult(ok=False, code="APPROVAL_REQUIRED")
        if action.tool == "delete_file":
            return await self._delete_file(policy_action, action)
        handlers = {
            "apply_patch": self._apply_patch,
            "read_file": self._read_file,
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

    def normalized_governance_scope(self, action: ToolAction) -> str | None:
        """以注册表真实 worktree 根生成只读展示范围，不参与授权。"""

        if action.tool != "delete_file":
            return None
        try:
            request = _DeleteFile.model_validate(action.arguments)
        except ValidationError:
            return None
        path = self._path(request.path)
        if path is None:
            return None
        try:
            return normalized_delete_scope(
                self._guard.root,
                path,
                request.expected_sha256,
            )
        except ValueError:
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

    async def _read_file(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            request = _ReadFile.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        path = self._path(request.path)
        if path is None:
            return ToolResult(ok=False, code="PATH_ESCAPE")
        try:
            content = BoundedFileReader().read(path, _MAX_READ_FILE_BYTES)
        except BoundedFileTooLargeError:
            return ToolResult(ok=False, code="FILE_TOO_LARGE")
        except UnsafeBoundedFileError:
            return ToolResult(ok=False, code="UNSAFE_FILE")
        except BoundedFileReadError:
            return ToolResult(ok=False, code="FILE_UNREADABLE")
        try:
            output = content.decode("utf-8")
        except UnicodeDecodeError:
            return ToolResult(ok=False, code="INVALID_TEXT")
        return ToolResult(
            ok=True,
            code="OK",
            output=output,
            observation=ToolObservation(
                tool="read_file",
                kind="file",
                code="OK",
                path=request.path,
                sha256=hashlib.sha256(content).hexdigest(),
                content=output,
            ),
        )

    async def _delete_file(self, policy_action: ToolAction, action: ToolAction) -> ToolResult:
        try:
            request = _DeleteFile.model_validate(action.arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        path = self._path(request.path)
        if path is None:
            return ToolResult(ok=False, code="PATH_ESCAPE")
        manager = self._context.approval_manager
        task_id = self._context.approval_task_id
        policy_context = self._context.policy_context
        if manager is None or task_id is None or policy_context is None or request.approval_id is None:
            return ToolResult(ok=False, code="APPROVAL_REQUIRED")
        try:
            approval_id = UUID(request.approval_id)
        except ValueError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        if self._context.policy is None:
            return ToolResult(ok=False, code="APPROVAL_REQUIRED")
        decision = self._context.policy.evaluate(policy_action, policy_context)
        try:
            scope = normalized_delete_scope(self._guard.root, path, request.expected_sha256)
        except ValueError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        if decision.decision is not PolicyDecision.REQUIRE_APPROVAL or decision.normalized_scope != scope:
            return ToolResult(ok=False, code="APPROVAL_REQUIRED")
        try:
            await manager.consume(
                approval_id,
                ApprovalContext(
                    action_id=action.idempotency_key,
                    event_sequence=policy_context.event_sequence,
                    normalized_scope=scope,
                    task_state=policy_context.task_state,
                    config_version=policy_context.config_version,
                ),
                expected_task_id=task_id,
            )
        except ApprovalError as error:
            return ToolResult(ok=False, code=error.reason_code)
        code = files.delete_regular_file(path, request.expected_sha256)
        return ToolResult(ok=code == "OK", code=code, changed_paths=(request.path,) if code == "OK" else ())

    async def _search(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            request = _Search.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        if self._context.repository_map is None:
            return ToolResult(ok=False, code="REPOSITORY_MAP_REQUIRED")
        if self._context.repository_map.root.resolve(strict=False) != self._guard.root:
            return ToolResult(ok=False, code="PATH_ESCAPE")
        return ToolResult(
            ok=True,
            code="OK",
            output=search.search(self._context.repository_map, request.query, self._guard),
        )

    async def _verification(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            request = _Verification.model_validate(arguments)
        except ValidationError:
            return ToolResult(ok=False, code="INVALID_ARGUMENTS")
        if request.name not in {"test", "lint", "typecheck", "build"} or self._context.profile is None:
            return ToolResult(ok=False, code="UNAVAILABLE_VERIFICATION")
        execution = verification.run_verification(
            self._guard.root,
            self._context.profile,
            request.name,
            self._context.runner,
            repository_map=self._context.repository_map,
            approval=self._context.verification_approval,
            config_version=self._context.verification_config_version,
            policy=self._context.policy,
            policy_context=self._context.policy_context,
            state_root=self._context.state_root,
        )
        return ToolResult(
            ok=execution.code == "OK",
            code=execution.code,
            output=execution.output,
            retryable=execution.code
            in {"VERIFICATION_FAILED", "WORKTREE_CHANGED_DURING_VERIFICATION"},
            verification=execution.evidence,
        )

    async def current_verification_evidence(self) -> VerificationEvidence | None:
        if self._context.profile is None:
            return None
        return verification.current_verification_evidence(
            self._guard.root,
            self._context.profile,
            self._context.repository_map,
            self._context.verification_approval,
            self._context.verification_config_version,
            self._context.state_root,
        )

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

    @staticmethod
    def _with_observation(action: ToolAction, result: ToolResult) -> ToolResult:
        if result.observation is not None:
            return result
        if not result.ok:
            diagnostic = result.output or result.code
            if action.tool == "run_verification" and result.output:
                diagnostic = f"UNTRUSTED_RUNNER_OUTPUT:\n{result.output}"
            observation = ToolObservation(
                tool=action.tool,
                kind="failure",
                code=result.code,
                diagnostic=diagnostic,
            )
        elif action.tool in {"search", "git_status", "git_diff"}:
            observation = ToolObservation(
                tool=action.tool,
                kind="output",
                code=result.code,
                output=result.output,
            )
        else:
            return result
        return result.model_copy(update={"observation": observation})
