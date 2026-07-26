"""Harness 的类型化配置。"""

from pathlib import Path
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_state_root(platform_name: str, environ: dict[str, str], home: Path) -> Path:
    """纯函数：为平台选择私有应用数据目录。"""
    if platform_name == "nt":
        base = environ.get("LOCALAPPDATA")
        return Path(base) / "CodingAgentHarness" if base else home / "AppData" / "Local" / "CodingAgentHarness"
    base = environ.get("XDG_DATA_HOME")
    return Path(base) / "coding-agent-harness" if base else home / ".local" / "share" / "coding-agent-harness"


def _default_state_root() -> Path:
    return default_state_root(os.name, dict(os.environ), Path.home())


class HarnessSettings(BaseSettings):
    """提供有界且适合本地开发的安全默认值。"""

    model_config = SettingsConfigDict(env_prefix="HARNESS_", extra="forbid")

    bind_host: str = "127.0.0.1"
    state_root: Path = Field(default_factory=_default_state_root)
    database_path: Path | None = None
    command_timeout_seconds: int = Field(default=300, ge=1)
    max_task_cycles: int = Field(default=8, ge=1)
    max_same_fingerprint: int = Field(default=3, ge=1)
    no_progress_limit: int = Field(default=2, ge=1)
    max_concurrent_tasks: int = Field(default=3, ge=1)

    def resolved_database_path(self) -> Path:
        return self.database_path or self.state_root / "harness.db"
