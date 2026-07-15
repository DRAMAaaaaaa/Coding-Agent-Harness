"""有界读取 Python、Node.js 和 Harness 项目配置。"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]

from coding_agent_harness.workspace.models import ProjectProfile, VerificationCommands

_COMMAND_NAMES = ("test", "lint", "typecheck", "build")
_ALLOWED_CONFIG_KEYS = frozenset((*_COMMAND_NAMES, "timeout", "env_allowlist"))
_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class ProjectDetectionError(ValueError):
    """项目目录不存在或不可读取。"""


class ProjectConfigurationError(ProjectDetectionError):
    """项目配置不满足有界严格 schema。"""


class ProjectDetector:
    """在不执行项目代码的前提下建议验证命令。"""

    def __init__(self, *, max_config_bytes: int = 128 * 1024) -> None:
        if max_config_bytes < 1:
            raise ValueError("配置大小上限必须为正数")
        self._max_config_bytes = max_config_bytes

    def detect(self, root: str | Path) -> ProjectProfile:
        project_root = self._resolve_root(root)
        languages: list[Literal["python", "node"]] = []
        commands: dict[str, list[str] | None] = dict.fromkeys(_COMMAND_NAMES)

        pyproject = project_root / "pyproject.toml"
        if pyproject.exists() or pyproject.is_symlink():
            python_config = self._parse_pyproject(pyproject)
            languages.append("python")
            commands["test"] = ["python", "-m", "pytest"]
            if "ruff" in python_config.get("tool", {}):
                commands["lint"] = ["python", "-m", "ruff", "check", "."]
            if "mypy" in python_config.get("tool", {}):
                commands["typecheck"] = ["python", "-m", "mypy", "."]
            if "build-system" in python_config:
                commands["build"] = ["python", "-m", "build"]

        package_json = project_root / "package.json"
        if package_json.exists() or package_json.is_symlink():
            scripts = self._parse_package_json(package_json)
            languages.append("node")
            for name in _COMMAND_NAMES:
                if commands[name] is None and name in scripts:
                    commands[name] = ["npm", "run", name]

        timeout = 300
        env_allowlist: list[str] = []
        requires_trust = False
        trust_fingerprint: str | None = None
        harness_config = project_root / ".harness.yml"
        if harness_config.exists() or harness_config.is_symlink():
            raw_config = self._read_bounded(harness_config)
            parsed = self._parse_harness_config(raw_config)
            for name in _COMMAND_NAMES:
                if name in parsed:
                    commands[name] = parsed[name]
            timeout = parsed.get("timeout", timeout)
            env_allowlist = parsed.get("env_allowlist", env_allowlist)
            requires_trust = True
            trust_fingerprint = hashlib.sha256(raw_config).hexdigest()

        return ProjectProfile(
            languages=languages,
            commands=VerificationCommands(**commands),
            command_timeout_seconds=timeout,
            env_allowlist=env_allowlist,
            requires_trust=requires_trust,
            trust_fingerprint=trust_fingerprint,
        )

    @staticmethod
    def _resolve_root(root: str | Path) -> Path:
        try:
            resolved = Path(root).resolve(strict=True)
        except (OSError, RuntimeError):
            raise ProjectDetectionError("项目目录无效") from None
        if not resolved.is_dir():
            raise ProjectDetectionError("项目目录无效")
        return resolved

    def _read_bounded(self, path: Path) -> bytes:
        if path.is_symlink():
            raise ProjectConfigurationError("项目配置不得使用符号链接")
        try:
            size = path.stat().st_size
        except OSError:
            raise ProjectConfigurationError("项目配置不可读取") from None
        if size > self._max_config_bytes:
            raise ProjectConfigurationError("项目配置超过大小限制")
        try:
            return path.read_bytes()
        except OSError:
            raise ProjectConfigurationError("项目配置不可读取") from None

    def _parse_pyproject(self, path: Path) -> dict[str, Any]:
        try:
            parsed = tomllib.loads(self._read_bounded(path).decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            raise ProjectConfigurationError("项目配置无效") from None
        return parsed

    def _parse_package_json(self, path: Path) -> dict[str, str]:
        try:
            parsed = json.loads(self._read_bounded(path))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProjectConfigurationError("项目配置无效") from None
        if not isinstance(parsed, dict):
            raise ProjectConfigurationError("项目配置无效")
        scripts = parsed.get("scripts", {})
        if not isinstance(scripts, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in scripts.items()
        ):
            raise ProjectConfigurationError("项目配置无效")
        return scripts

    @staticmethod
    def _parse_harness_config(raw: bytes) -> dict[str, Any]:
        try:
            parsed = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            raise ProjectConfigurationError("项目配置无效") from None
        if not isinstance(parsed, dict) or not set(parsed).issubset(_ALLOWED_CONFIG_KEYS):
            raise ProjectConfigurationError("项目配置无效")
        for name in _COMMAND_NAMES:
            if name not in parsed:
                continue
            argv = parsed[name]
            if not isinstance(argv, list) or not argv or any(
                not isinstance(item, str) or not item or "\x00" in item for item in argv
            ):
                raise ProjectConfigurationError("项目配置无效")
        timeout = parsed.get("timeout", 300)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            raise ProjectConfigurationError("项目配置无效")
        env_allowlist = parsed.get("env_allowlist", [])
        if not isinstance(env_allowlist, list) or any(
            not isinstance(name, str) or _ENVIRONMENT_NAME.fullmatch(name) is None
            for name in env_allowlist
        ):
            raise ProjectConfigurationError("项目配置无效")
        if len(set(env_allowlist)) != len(env_allowlist):
            raise ProjectConfigurationError("项目配置无效")
        return parsed
