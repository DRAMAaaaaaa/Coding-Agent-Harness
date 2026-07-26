from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from coding_agent_harness.governance.policy import PolicyContext, PolicyEngine
from coding_agent_harness.workspace.git import SafeGit
from coding_agent_harness.workspace.models import ProjectProfile, RepositoryMap
from coding_agent_harness.workspace.processes import ProcessRunner


class ToolResult(BaseModel):
    """工具调用的稳定、可审计结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ok: bool
    code: str = Field(min_length=1)
    output: str = ""
    changed_paths: tuple[str, ...] = ()
    retryable: bool = False


ApprovalConsumer = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class ToolContext:
    """注册表所需的注入式运行时依赖。"""

    workspace_root: Path
    repository_map: RepositoryMap | None = None
    profile: ProjectProfile | None = None
    policy: PolicyEngine | None = None
    policy_context: PolicyContext | None = None
    safe_git: SafeGit | None = None
    runner: ProcessRunner | None = None
    approval_consumer: ApprovalConsumer | None = None
