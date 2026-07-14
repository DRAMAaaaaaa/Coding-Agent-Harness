import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.governance.redaction import Redactor


_PATH_FIELDS = ("path", "cwd", "source", "destination", "target")
_NETWORK_FIELDS = ("url", "uri")
_WINDOWS_LAUNCHER_SUFFIXES = (".exe", ".cmd", ".bat", ".com", ".ps1")
_INSTALL_COMMANDS = frozenset({"pip", "pip3", "npm", "pnpm", "yarn", "poetry", "uv"})
_INSTALL_OPERATIONS = frozenset({"install", "add"})
_NETWORK_COMMANDS = frozenset({"curl", "wget"})
_WEB_POWERSHELL = frozenset({"invoke-webrequest", "invoke-restmethod", "iwr", "irm"})
_PUBLISH_COMMANDS = frozenset({"twine", "docker", "gh", "npm"})
_GIT_REMOTE_OPERATIONS = frozenset({"push", "merge"})
_DELETE_COMMANDS = frozenset({"rm", "rmdir", "del", "erase", "remove-item"})
_DESTRUCTIVE_COMMANDS = frozenset(
    {"mkfs", "mkfs.ext4", "format", "format.com", "dd", "shutdown", "reboot", "halt"}
)
_SHELL_INTERPRETERS = frozenset({"bash", "sh", "zsh", "cmd", "powershell", "pwsh"})
_SHELL_CODE_SWITCHES = frozenset({"-c", "/c", "-command"})


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class PolicyContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    workspace_root: Path
    task_state: TaskState
    event_sequence: int
    config_version: str
    llm_api_authorized: bool


class PolicyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    decision: PolicyDecision
    reason_code: str
    normalized_scope: str
    event_sequence: int


class PolicyEngine:
    def __init__(self, path_guard: PathGuard, redactor: Redactor) -> None:
        self._path_guard = path_guard
        self._redactor = redactor

    def evaluate(self, action: ToolAction, context: PolicyContext) -> PolicyResult:
        if not self._known_arguments_are_valid(action):
            return self._result(PolicyDecision.DENY, "INVALID_ACTION", "", context)
        parsed = self._parse_arguments(action.arguments)
        if parsed is None:
            return self._result(PolicyDecision.DENY, "INVALID_ACTION", "", context)
        argv, safe_paths, escaped = parsed
        if escaped:
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL,
                "PATH_ESCAPE",
                "path:escape",
                context,
            )

        scope = self._scope(action, argv, safe_paths)
        tool = self._token(action.tool)
        tokens = tuple(self._token(token) for token in argv)

        if tool == "delete_path":
            return self._result(PolicyDecision.REQUIRE_APPROVAL, "DELETE_PATH", scope, context)
        if self._is_install(tokens):
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "DEPENDENCY_INSTALL", scope, context
            )
        if self._is_network(tokens):
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "TOOL_NETWORK", scope, context
            )
        if self._is_direct_network(tool, action.arguments):
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "TOOL_NETWORK", scope, context
            )
        if tool == "git" and self._git_operation(action) in _GIT_REMOTE_OPERATIONS:
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "GIT_REMOTE_CHANGE", scope, context
            )
        if self._is_shell_git_remote(tokens):
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "GIT_REMOTE_CHANGE", scope, context
            )
        if self._is_publish(tokens):
            return self._result(PolicyDecision.REQUIRE_APPROVAL, "PUBLISH", scope, context)
        if tool == "shell" and self._is_high_risk_shell(tokens):
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "HIGH_RISK_SHELL", scope, context
            )
        return self._result(PolicyDecision.ALLOW, "SAFE", "", context)

    def _parse_arguments(
        self, arguments: Mapping[str, object]
    ) -> tuple[list[str], dict[str, Path], bool] | None:
        raw_argv = arguments.get("argv", [])
        if not isinstance(raw_argv, list) or not all(
            isinstance(token, str) for token in raw_argv
        ):
            return None
        argv = list(raw_argv)
        paths: dict[str, Path] = {}
        escaped = False
        for field in _PATH_FIELDS:
            if field not in arguments:
                continue
            candidate = arguments[field]
            if not isinstance(candidate, str):
                return None
            try:
                paths[field] = self._path_guard.resolve(candidate)
            except PathEscapeError:
                escaped = True
        return argv, paths, escaped

    def _scope(
        self,
        action: ToolAction,
        argv: list[str],
        paths: dict[str, Path],
    ) -> str:
        values: dict[str, object] = {}
        if argv:
            values["argv"] = argv
        if paths:
            values["paths"] = {key: str(value) for key, value in sorted(paths.items())}
        if self._token(action.tool) == "git":
            operation = action.arguments.get("operation")
            if isinstance(operation, str):
                values["operation"] = operation
        for field in _NETWORK_FIELDS:
            value = action.arguments.get(field)
            if isinstance(value, str):
                values[field] = value
        sanitized = self._redactor.sanitize(values).value
        return json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _result(
        self,
        decision: PolicyDecision,
        reason_code: str,
        scope: str,
        context: PolicyContext,
    ) -> PolicyResult:
        return PolicyResult(
            decision=decision,
            reason_code=reason_code,
            normalized_scope=scope,
            event_sequence=context.event_sequence,
        )

    @staticmethod
    def _token(token: str) -> str:
        normalized = Path(token).name.casefold()
        for suffix in _WINDOWS_LAUNCHER_SUFFIXES:
            if normalized.endswith(suffix):
                return normalized[: -len(suffix)]
        return normalized

    @staticmethod
    def _git_operation(action: ToolAction) -> str:
        operation = action.arguments.get("operation")
        return operation.casefold() if isinstance(operation, str) else ""

    @staticmethod
    def _known_arguments_are_valid(action: ToolAction) -> bool:
        tool = PolicyEngine._token(action.tool)
        if tool == "git":
            return isinstance(action.arguments.get("operation"), str)
        if tool == "delete_path":
            return isinstance(action.arguments.get("path"), str)
        if tool == "read_file":
            return any(
                isinstance(action.arguments.get(field), str) for field in _PATH_FIELDS
            )
        if tool == "shell":
            argv = action.arguments.get("argv")
            return isinstance(argv, list) and bool(argv)
        return True

    @staticmethod
    def _is_shell_git_remote(tokens: tuple[str, ...]) -> bool:
        return PolicyEngine._command_has_operation(
            tokens,
            frozenset({"git"}),
            _GIT_REMOTE_OPERATIONS,
        )

    @staticmethod
    def _is_install(tokens: tuple[str, ...]) -> bool:
        return PolicyEngine._command_has_operation(
            tokens,
            _INSTALL_COMMANDS,
            _INSTALL_OPERATIONS,
        )

    @staticmethod
    def _is_network(tokens: tuple[str, ...]) -> bool:
        if not tokens:
            return False
        if any(token in _NETWORK_COMMANDS for token in tokens):
            return True
        return any(token in _WEB_POWERSHELL for token in tokens)

    @staticmethod
    def _is_publish(tokens: tuple[str, ...]) -> bool:
        operations = {
            "twine": frozenset({"upload"}),
            "docker": frozenset({"push"}),
            "gh": frozenset({"release"}),
            "npm": frozenset({"publish"}),
        }
        return any(
            PolicyEngine._command_has_operation(
                tokens,
                frozenset({command}),
                risky_operations,
            )
            for command, risky_operations in operations.items()
        )

    @staticmethod
    def _is_direct_network(tool: str, arguments: Mapping[str, object]) -> bool:
        return tool in _NETWORK_COMMANDS or any(
            isinstance(arguments.get(field), str) for field in _NETWORK_FIELDS
        )

    @staticmethod
    def _command_has_operation(
        tokens: tuple[str, ...],
        commands: frozenset[str],
        operations: frozenset[str],
    ) -> bool:
        return any(
            command in commands
            and any(token in operations for token in tokens[index + 1 :])
            for index, command in enumerate(tokens)
        )

    @staticmethod
    def _is_high_risk_shell(tokens: tuple[str, ...]) -> bool:
        if not tokens:
            return False
        if any(
            token in _DELETE_COMMANDS or token in _DESTRUCTIVE_COMMANDS
            for token in tokens
        ):
            return True
        return any(
            command in _SHELL_INTERPRETERS and switch in _SHELL_CODE_SWITCHES
            for command, switch in zip(tokens, tokens[1:], strict=False)
        )
