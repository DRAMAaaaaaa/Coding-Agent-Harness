"""有界读取 Python、Node.js 和 Harness 项目配置。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tomllib
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]

from coding_agent_harness.workspace.models import ProjectProfile, VerificationCommands
from coding_agent_harness.workspace.files import (
    BinaryFileOpener,
    BoundedFileReadError,
    BoundedFileReader,
    BoundedFileTooLargeError,
    UnsafeBoundedFileError,
    is_symlink_or_reparse,
)

_COMMAND_NAMES = ("test", "lint", "typecheck", "build")
_ALLOWED_CONFIG_KEYS = frozenset((*_COMMAND_NAMES, "timeout", "env_allowlist"))
_ENVIRONMENT_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_TRUST_DOMAIN = b"coding-agent-harness\0verification-trust\0v1\0"


class ProjectDetectionError(ValueError):
    """项目目录不存在或不可读取。"""


class ProjectConfigurationError(ProjectDetectionError):
    """项目配置不满足有界严格 schema。"""


class ProjectDetector:
    """在不执行项目代码的前提下建议验证命令。"""

    def __init__(
        self,
        *,
        max_config_bytes: int = 128 * 1024,
        file_opener: BinaryFileOpener | None = None,
    ) -> None:
        if max_config_bytes < 1:
            raise ValueError("配置大小上限必须为正数")
        self._max_config_bytes = max_config_bytes
        self._file_reader = BoundedFileReader(file_opener)

    def detect(self, root: str | Path) -> ProjectProfile:
        project_root = self._resolve_root(root)
        languages: list[Literal["python", "node"]] = []
        commands: dict[str, tuple[str, ...] | None] = dict.fromkeys(_COMMAND_NAMES)
        source_digests: dict[str, str | None] = {
            ".harness.yml": None,
            "package.json": None,
            "pyproject.toml": None,
        }

        pyproject = project_root / "pyproject.toml"
        if self._is_regular_configuration(pyproject, project_root):
            raw_pyproject = self._read_bounded(pyproject)
            source_digests["pyproject.toml"] = hashlib.sha256(raw_pyproject).hexdigest()
            python_config = self._parse_pyproject(raw_pyproject)
            languages.append("python")
            commands["test"] = ("python", "-m", "pytest")
            if "ruff" in python_config.get("tool", {}):
                commands["lint"] = ("python", "-m", "ruff", "check", ".")
            if "mypy" in python_config.get("tool", {}):
                commands["typecheck"] = ("python", "-m", "mypy", ".")
            if "build-system" in python_config:
                commands["build"] = ("python", "-m", "build")

        package_json = project_root / "package.json"
        if self._is_regular_configuration(package_json, project_root):
            raw_package = self._read_bounded(package_json)
            source_digests["package.json"] = hashlib.sha256(raw_package).hexdigest()
            scripts = self._parse_package_json(raw_package)
            languages.append("node")
            npm = "npm.cmd" if os.name == "nt" else "npm"
            for name in _COMMAND_NAMES:
                if commands[name] is None and name in scripts:
                    commands[name] = (npm, "run", name)

        timeout = 300
        env_allowlist: tuple[str, ...] = ()
        harness_config = project_root / ".harness.yml"
        if self._is_regular_configuration(harness_config, project_root):
            raw_config = self._read_bounded(harness_config)
            source_digests[".harness.yml"] = hashlib.sha256(raw_config).hexdigest()
            parsed = self._parse_harness_config(raw_config)
            for name in _COMMAND_NAMES:
                if name in parsed:
                    commands[name] = tuple(parsed[name])
            timeout = parsed.get("timeout", timeout)
            env_allowlist = tuple(parsed.get("env_allowlist", env_allowlist))

        verification_commands = VerificationCommands(**commands)
        requires_trust = any(
            command is not None
            for command in (
                verification_commands.test,
                verification_commands.lint,
                verification_commands.typecheck,
                verification_commands.build,
            )
        )
        trust_fingerprint = (
            self._trust_fingerprint(
                source_digests,
                verification_commands,
                env_allowlist,
                timeout,
            )
            if requires_trust
            else None
        )

        return ProjectProfile(
            languages=tuple(languages),
            commands=verification_commands,
            command_timeout_seconds=timeout,
            env_allowlist=env_allowlist,
            requires_trust=requires_trust,
            trust_fingerprint=trust_fingerprint,
        )

    @staticmethod
    def _is_regular_configuration(path: Path, project_root: Path) -> bool:
        if path.parent != project_root:
            raise ProjectConfigurationError("项目配置路径越界")
        try:
            path_stat = path.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            raise ProjectConfigurationError("项目配置不可读取") from None
        if is_symlink_or_reparse(path_stat):
            raise ProjectConfigurationError("项目配置不得使用符号链接")
        if not stat.S_ISREG(path_stat.st_mode):
            raise ProjectConfigurationError("项目配置不得使用符号链接或替换")
        return True

    @staticmethod
    def _trust_fingerprint(
        source_digests: dict[str, str | None],
        commands: VerificationCommands,
        env_allowlist: tuple[str, ...],
        timeout_seconds: int,
    ) -> str:
        manifest = {
            "schema": "verification-trust/v1",
            "sources": source_digests,
            "effective": {
                "commands": commands.model_dump(mode="json"),
                "env_allowlist": list(env_allowlist),
                "timeout_seconds": timeout_seconds,
            },
        }
        encoded = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(_TRUST_DOMAIN + encoded).hexdigest()

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
        try:
            return self._file_reader.read(path, self._max_config_bytes)
        except BoundedFileTooLargeError:
            raise ProjectConfigurationError("项目配置超过大小限制")
        except UnsafeBoundedFileError:
            raise ProjectConfigurationError("项目配置不得使用符号链接或替换") from None
        except BoundedFileReadError:
            raise ProjectConfigurationError("项目配置不可读取") from None

    @staticmethod
    def _parse_pyproject(raw: bytes) -> dict[str, Any]:
        try:
            parsed = tomllib.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            raise ProjectConfigurationError("项目配置无效") from None
        return parsed

    @staticmethod
    def _parse_package_json(raw: bytes) -> dict[str, str]:
        try:
            parsed = json.loads(raw)
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
