"""Harness 的类型化配置。"""

from pathlib import Path
import os
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator
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

    model_config = SettingsConfigDict(env_prefix="HARNESS_", extra="forbid", frozen=True)

    bind_host: str = "127.0.0.1"
    bind_port: int = Field(default=8000, ge=1, le=65_535)
    trusted_hosts: tuple[str, ...] | None = None
    trusted_origins: tuple[str, ...] | None = None
    state_root: Path = Field(default_factory=_default_state_root)
    database_path: Path | None = None
    command_timeout_seconds: int = Field(default=300, ge=1)
    max_task_cycles: int = Field(default=8, ge=1)
    max_same_fingerprint: int = Field(default=3, ge=1)
    no_progress_limit: int = Field(default=2, ge=1)
    max_concurrent_tasks: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def freeze_security_boundaries(self) -> Self:
        try:
            state_root = self.state_root.expanduser().resolve(strict=False)
            database_path = (
                self.database_path.expanduser().resolve(strict=False)
                if self.database_path is not None
                else state_root / "harness.db"
            )
        except (OSError, RuntimeError):
            raise ValueError("Harness 私有状态路径无法解析") from None
        if database_path == state_root or not database_path.is_relative_to(state_root):
            raise ValueError("database_path 必须位于 state_root 内")

        hosts = self.trusted_hosts
        origins = self.trusted_origins
        if hosts is None and origins is None:
            hosts = (f"127.0.0.1:{self.bind_port}", f"localhost:{self.bind_port}")
            origins = tuple(f"http://{host}" for host in hosts)
        elif hosts is None or origins is None:
            raise ValueError("trusted_hosts 与 trusted_origins 必须同时配置")

        normalized_hosts = _normalize_trusted_hosts(hosts)
        normalized_origins = _normalize_trusted_origins(origins, normalized_hosts)
        object.__setattr__(self, "state_root", state_root)
        object.__setattr__(self, "database_path", database_path)
        object.__setattr__(self, "trusted_hosts", normalized_hosts)
        object.__setattr__(self, "trusted_origins", normalized_origins)
        return self

    def resolved_database_path(self) -> Path:
        return self.database_path or self.state_root / "harness.db"

    def private_state_roots(self) -> tuple[Path, ...]:
        database_path = self.resolved_database_path()
        database_artifacts = (
            database_path,
            Path(f"{database_path}-wal"),
            Path(f"{database_path}-shm"),
        )
        roots = (self.state_root, *(artifact.parent for artifact in database_artifacts))
        return tuple(dict.fromkeys(roots))


def _normalize_trusted_hosts(hosts: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for host in hosts:
        value = host.casefold()
        if not value or value != host.strip().casefold() or any(
            character in value for character in "/\\@"
        ):
            raise ValueError("trusted_hosts 包含无效 authority")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise ValueError("trusted_hosts 不得为空")
    return tuple(normalized)


def _normalize_trusted_origins(
    origins: tuple[str, ...],
    hosts: tuple[str, ...],
) -> tuple[str, ...]:
    normalized: list[str] = []
    for origin in origins:
        value = origin.casefold()
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise ValueError("trusted_origins 包含无效 Origin") from None
        if (
            value != origin.strip().casefold()
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or port is None and ":" in parsed.netloc
            or parsed.netloc not in hosts
        ):
            raise ValueError("trusted_origins 包含无效 Origin")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise ValueError("trusted_origins 不得为空")
    return tuple(normalized)
