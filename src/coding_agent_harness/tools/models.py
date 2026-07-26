from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from coding_agent_harness.governance.policy import PolicyContext, PolicyEngine
from coding_agent_harness.governance.approvals import ApprovalManager
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
    verification: VerificationEvidence | None = None


class VerificationApproval(BaseModel):
    """用户已批准的验证配置绑定，不由探测结果隐式派生。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    approval_id: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    trust_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class VerificationEvidence(BaseModel):
    """一次成功验证所绑定的当前配置和受限 worktree 快照。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    trust_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    worktree_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_checks: tuple[str, ...] = Field(min_length=1)


@dataclass(frozen=True)
class ToolContext:
    """注册表所需的注入式运行时依赖。"""

    workspace_root: Path
    state_root: Path | None = None
    repository_map: RepositoryMap | None = None
    profile: ProjectProfile | None = None
    policy: PolicyEngine | None = None
    policy_context: PolicyContext | None = None
    safe_git: SafeGit | None = None
    runner: ProcessRunner | None = None
    approval_manager: ApprovalManager | None = None
    approval_task_id: UUID | None = None
    verification_config_version: str | None = None
    verification_approval: VerificationApproval | None = None
