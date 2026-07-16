"""Task 5 的严格运行期模型。"""

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceModel(BaseModel):
    """拒绝隐式转换和未知字段的不可变模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class VerificationCommands(WorkspaceModel):
    """按 argv 保存的项目验证命令。"""

    test: tuple[str, ...] | None = None
    lint: tuple[str, ...] | None = None
    typecheck: tuple[str, ...] | None = None
    build: tuple[str, ...] | None = None

    @field_validator("test", "lint", "typecheck", "build")
    @classmethod
    def validate_argv(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is not None and (
            not value or any(not item or "\x00" in item for item in value)
        ):
            raise ValueError("命令必须是非空 argv")
        return value


class ProjectProfile(WorkspaceModel):
    """项目语言与建议验证配置。"""

    languages: tuple[Literal["python", "node"], ...]
    commands: VerificationCommands
    command_timeout_seconds: int = Field(default=300, ge=1)
    env_allowlist: tuple[str, ...] = Field(default_factory=tuple)
    requires_trust: bool = False
    trust_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class Workspace(WorkspaceModel):
    """尚未持久化的最小 Workspace 运行期记录。"""

    id: UUID
    root: Path
    git_root: Path
    default_branch: str = Field(min_length=1)
    profile: ProjectProfile


class RepositoryDocument(WorkspaceModel):
    """受大小限制读取的仓库说明或配置文件。"""

    path: str = Field(min_length=1)
    content: str


class RepositoryMap(WorkspaceModel):
    """仅由 Git 跟踪内容和有界元数据构成的仓库地图。"""

    root: Path
    tracked_files: tuple[str, ...]
    documents: tuple[RepositoryDocument, ...]
    test_paths: tuple[str, ...]
    recent_commits: tuple[str, ...]
    dirty_paths: tuple[str, ...]


class WorktreeInfo(WorkspaceModel):
    """任务隔离工作树的运行期标识。"""

    workspace_id: UUID
    task_id: UUID
    path: Path
    branch: str = Field(pattern=r"^harness/task-[0-9a-f]{8}$")
    base_commit: str = Field(min_length=1)
