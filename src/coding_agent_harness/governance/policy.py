import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath

from pydantic import BaseModel, ConfigDict

from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.governance.redaction import Redactor


_NETWORK_FIELDS = ("url", "uri")
_WINDOWS_LAUNCHER_SUFFIXES = (".exe", ".cmd", ".bat", ".com", ".ps1")
_NETWORK_COMMANDS = frozenset({"curl", "wget"})
_PUBLISH_OPERATIONS = {
    "twine": frozenset({"upload"}),
    "docker": frozenset({"push"}),
    "gh": frozenset({"release"}),
    "npm": frozenset({"publish"}),
}
_GIT_REMOTE_OPERATIONS = frozenset({"push", "merge"})
_DELETE_COMMANDS = frozenset({"rm", "rmdir", "del", "erase", "remove-item"})
_DESTRUCTIVE_COMMANDS = frozenset(
    {"mkfs", "mkfs.ext4", "format", "dd", "shutdown", "reboot", "halt"}
)
_SHELL_INTERPRETERS = frozenset({"bash", "sh", "zsh", "cmd", "powershell", "pwsh"})
_PATCH_HEADER = re.compile(
    r"^\*\*\* (?:Add|Update|Delete|Move to) File: (?P<path>.+)$",
    re.MULTILINE,
)
_MAX_WRAPPER_DEPTH = 4
_KNOWN_SLASH_OPTIONS = frozenset({"/c", "/d", "/s"})


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


@dataclass(frozen=True)
class _ParsedAction:
    argv: tuple[str, ...]
    paths: dict[str, Path]
    escaped: bool


@dataclass(frozen=True)
class _Command:
    argv: tuple[str, ...]
    high_risk: bool = False


class PolicyEngine:
    def __init__(self, path_guard: PathGuard, redactor: Redactor) -> None:
        self._path_guard = path_guard
        self._redactor = redactor

    def evaluate(self, action: ToolAction, context: PolicyContext) -> PolicyResult:
        parsed = self._parse_action(action)
        if parsed is None:
            return self._result(PolicyDecision.DENY, "INVALID_ACTION", "", context)
        if parsed.escaped:
            return self._result(PolicyDecision.DENY, "PATH_ESCAPE", "", context)

        scope = self._scope(action, parsed.argv, parsed.paths)
        tool = self._executable(action.tool)
        command = self._unwrap_command(parsed.argv)

        if tool == "delete_path":
            return self._result(PolicyDecision.REQUIRE_APPROVAL, "DELETE_PATH", scope, context)
        if command.high_risk:
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "HIGH_RISK_SHELL", scope, context
            )
        if self._is_install(command.argv):
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "DEPENDENCY_INSTALL", scope, context
            )
        if self._is_network(command.argv):
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
        if self._operation(command.argv, "git", {"-c": 1, "-C": 1}) in _GIT_REMOTE_OPERATIONS:
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "GIT_REMOTE_CHANGE", scope, context
            )
        if self._is_publish(command.argv):
            return self._result(PolicyDecision.REQUIRE_APPROVAL, "PUBLISH", scope, context)
        if self._is_dangerous_command(command.argv):
            return self._result(
                PolicyDecision.REQUIRE_APPROVAL, "HIGH_RISK_SHELL", scope, context
            )
        return self._result(PolicyDecision.ALLOW, "SAFE", "", context)

    def _parse_action(self, action: ToolAction) -> _ParsedAction | None:
        tool = self._executable(action.tool)
        arguments = action.arguments
        if any(field in arguments and not isinstance(arguments[field], str) for field in _NETWORK_FIELDS):
            return None

        argv: tuple[str, ...] = ()
        candidates: list[tuple[str, str]] = []
        if tool in {"read_file", "search", "delete_path"}:
            path = arguments.get("path")
            if not isinstance(path, str):
                return None
            candidates.append(("path", path))
        elif tool == "apply_patch":
            patch = arguments.get("patch")
            if not isinstance(patch, str):
                return None
            candidates.extend(("patch", match.group("path")) for match in _PATCH_HEADER.finditer(patch))
        elif tool == "shell":
            raw_argv = arguments.get("argv")
            if not isinstance(raw_argv, list) or not raw_argv or not all(
                isinstance(token, str) for token in raw_argv
            ):
                return None
            argv = tuple(token for token in raw_argv if isinstance(token, str))
            cwd = arguments.get("cwd")
            if cwd is not None:
                if not isinstance(cwd, str):
                    return None
                candidates.append(("cwd", cwd))
            candidates.extend(("argv", token) for token in self._path_tokens(argv))
        elif tool == "git":
            if not isinstance(arguments.get("operation"), str):
                return None
        elif tool in {"git_status", "git_diff", "checkpoint"}:
            if arguments:
                return None

        paths: dict[str, Path] = {}
        escaped = False
        for index, (field, candidate) in enumerate(candidates):
            try:
                resolved = self._path_guard.resolve(candidate)
                if field == "cwd" and resolved != self._path_guard.root:
                    escaped = True
                paths[f"{field}:{index}"] = resolved
            except PathEscapeError:
                escaped = True
        return _ParsedAction(argv=argv, paths=paths, escaped=escaped)

    @staticmethod
    def _path_tokens(argv: Sequence[str]) -> tuple[str, ...]:
        paths: list[str] = []
        for token in argv[1:]:
            if (
                PolicyEngine._is_url(token)
                or token.startswith("-")
                or token.casefold() in _KNOWN_SLASH_OPTIONS
            ):
                continue
            windows = PureWindowsPath(token)
            has_parent = ".." in windows.parts or ".." in Path(token).parts
            if (
                has_parent
                or windows.is_absolute()
                or PurePosixPath(token).is_absolute()
            ):
                paths.append(token)
        return tuple(paths)

    @staticmethod
    def _is_url(token: str) -> bool:
        return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", token))

    def _scope(
        self,
        action: ToolAction,
        argv: tuple[str, ...],
        paths: dict[str, Path],
    ) -> str:
        values: dict[str, object] = {}
        if argv:
            values["argv"] = list(argv)
        if paths:
            values["paths"] = {key: str(value) for key, value in sorted(paths.items())}
        if self._executable(action.tool) == "git":
            operation = action.arguments.get("operation")
            if isinstance(operation, str):
                values["operation"] = operation
        for field in _NETWORK_FIELDS:
            value = action.arguments.get(field)
            if isinstance(value, str):
                values[field] = value
        sanitized = self._redactor.sanitize(values).value
        return json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _result(
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
    def _executable(token: str) -> str:
        normalized = PureWindowsPath(token).name.casefold()
        for suffix in _WINDOWS_LAUNCHER_SUFFIXES:
            if normalized.endswith(suffix):
                return normalized[: -len(suffix)]
        return normalized

    @staticmethod
    def _git_operation(action: ToolAction) -> str:
        operation = action.arguments.get("operation")
        return operation.casefold() if isinstance(operation, str) else ""

    @staticmethod
    def _is_direct_network(tool: str, arguments: Mapping[str, object]) -> bool:
        return tool in _NETWORK_COMMANDS or any(field in arguments for field in _NETWORK_FIELDS)

    @classmethod
    def _unwrap_command(cls, argv: tuple[str, ...]) -> _Command:
        current: tuple[str, ...] | None = argv
        for _ in range(_MAX_WRAPPER_DEPTH + 1):
            if not current:
                return _Command(())
            command = cls._executable(current[0])
            if command in _SHELL_INTERPRETERS:
                return _Command(current, high_risk=True)
            if command == "sudo":
                current = cls._unwrap_options(
                    current,
                    no_value={"-E", "-H", "-K", "-k", "-n", "-S", "-V", "-v"},
                    with_value={
                        "-u", "--user", "-g", "--group", "-h", "--host", "-p",
                        "--prompt", "-C", "--chdir", "-R", "--chroot", "-T",
                        "--command-timeout",
                    },
                )
            elif command == "env":
                if any(token in {"-S", "--split-string"} for token in current[1:]):
                    return _Command(current, high_risk=True)
                current = cls._unwrap_options(
                    current,
                    no_value={"-i", "--ignore-environment", "-0", "--null"},
                    with_value={"-u", "--unset", "-C", "--chdir"},
                    assignments=True,
                )
            elif command == "command":
                if any(token in {"-v", "-V"} for token in current[1:]):
                    return _Command(())
                current = cls._unwrap_options(current, no_value={"-p"}, with_value=set())
            elif command == "nohup":
                current = cls._unwrap_options(current, no_value=set(), with_value=set())
            elif command == "corepack":
                current = current[1:]
                if not current or cls._executable(current[0]) not in {"npm", "pnpm", "yarn"}:
                    return _Command(current, high_risk=True)
            elif command in {"python", "python3", "py"}:
                current = cls._unwrap_python(current)
            else:
                return _Command(current)
            if current is None:
                return _Command((), high_risk=True)
        return _Command(current or (), high_risk=True)

    @classmethod
    def _unwrap_options(
        cls,
        argv: tuple[str, ...],
        *,
        no_value: set[str],
        with_value: set[str],
        assignments: bool = False,
    ) -> tuple[str, ...] | None:
        index = 1
        while index < len(argv):
            token = argv[index]
            if token == "--":
                return argv[index + 1 :] or None
            if assignments and "=" in token and not token.startswith("-"):
                index += 1
                continue
            if token in no_value:
                index += 1
                continue
            option = token.split("=", 1)[0]
            if option in with_value:
                if "=" in token:
                    index += 1
                    continue
                if index + 1 >= len(argv):
                    return None
                index += 2
                continue
            if token.startswith("-"):
                return None
            return argv[index:]
        return None

    @classmethod
    def _unwrap_python(cls, argv: tuple[str, ...]) -> tuple[str, ...] | None:
        no_value = {"-B", "-E", "-I", "-O", "-OO", "-P", "-q", "-s", "-S", "-u", "-v", "-V", "-x"}
        index = 1
        while index < len(argv):
            token = argv[index]
            if token == "--":
                return None
            if token in no_value:
                index += 1
                continue
            if token in {"-W", "-X"}:
                if index + 1 >= len(argv):
                    return None
                index += 2
                continue
            if token.startswith("-W") or token.startswith("-X"):
                index += 1
                continue
            if token == "-m":
                return argv[index + 1 :] or None
            return None
        return None

    @classmethod
    def _is_install(cls, argv: tuple[str, ...]) -> bool:
        if not argv:
            return False
        command = cls._executable(argv[0])
        operation = cls._operation(argv, command)
        if command in {"npm", "pnpm"}:
            return operation in {"install", "i", "add", "ci"}
        if command == "yarn":
            return operation in {"", "install", "add"}
        if command in {"pip", "pip3"}:
            return operation == "install"
        if command == "uv":
            if operation in {"sync", "add"}:
                return True
            if operation == "pip":
                return cls._first_operation(argv[2:]) == "install"
        if command == "poetry":
            return operation in {"install", "add"}
        return False

    @classmethod
    def _is_network(cls, argv: tuple[str, ...]) -> bool:
        return bool(argv) and cls._executable(argv[0]) in _NETWORK_COMMANDS

    @classmethod
    def _is_publish(cls, argv: tuple[str, ...]) -> bool:
        if not argv:
            return False
        command = cls._executable(argv[0])
        operations = _PUBLISH_OPERATIONS.get(command)
        return operations is not None and cls._operation(argv, command) in operations

    @classmethod
    def _is_dangerous_command(cls, argv: tuple[str, ...]) -> bool:
        if not argv:
            return False
        command = cls._executable(argv[0])
        return command in _DELETE_COMMANDS or command in _DESTRUCTIVE_COMMANDS

    @classmethod
    def _operation(
        cls,
        argv: tuple[str, ...],
        command: str,
        value_options: Mapping[str, int] | None = None,
    ) -> str:
        if not argv or cls._executable(argv[0]) != command:
            return ""
        index = 1
        options = value_options or {
            "--config": 1,
            "--disable-pip-version-check": 0,
            "-C": 1,
            "-c": 1,
        }
        while index < len(argv):
            token = argv[index]
            if token == "--":
                index += 1
                break
            if token in options:
                index += 1 + options[token]
                continue
            if token.startswith("-"):
                index += 1
                continue
            return token.casefold()
        return cls._first_operation(argv[index:])

    @staticmethod
    def _first_operation(tokens: Sequence[str]) -> str:
        return next((token.casefold() for token in tokens if not token.startswith("-")), "")
