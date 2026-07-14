"""Harness 的类型化配置。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HarnessSettings(BaseSettings):
    """提供有界且适合本地开发的安全默认值。"""

    model_config = SettingsConfigDict(env_prefix="HARNESS_", extra="forbid")

    bind_host: str = "127.0.0.1"
    command_timeout_seconds: int = Field(default=300, ge=1)
    max_task_cycles: int = Field(default=8, ge=1)
    max_same_fingerprint: int = Field(default=3, ge=1)
    no_progress_limit: int = Field(default=2, ge=1)
    max_concurrent_tasks: int = Field(default=3, ge=1)
