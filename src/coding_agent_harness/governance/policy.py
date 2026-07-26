import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    "pnpm": frozenset({"publish"}),
    "yarn": frozenset({"publish"}),
}
_GIT_REMOTE_OPERATIONS = frozenset({"push", "merge"})
_DELETE_COMMANDS = frozenset({"rm", "rmdir", "del", "erase", "remove-item"})
_DESTRUCTIVE_COMMANDS = frozenset(
    {"mkfs", "mkfs.ext4", "format", "dd", "shutdown", "reboot", "halt"}
)
_SHELL_INTERPRETERS = frozenset({"bash", "sh", "zsh", "cmd", "powershell", "pwsh"})
_PATCH_HEADER = re.compile(
    r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (?P<path>.+)$",
    re.MULTILINE,
)
_PATCH_HEADER_LIKE = re.compile(
    r"^\*\*\* (?:Add|Update|Delete|Move)\b",
    re.MULTILINE,
)
_MAX_WRAPPER_DEPTH = 4
_PACKAGE_NO_VALUE_OPTIONS = {
    "npm": frozenset({"--silent"}),
    "pnpm": frozenset({"--silent"}),
    "yarn": frozenset({"--silent"}),
    "pip": frozenset({"--disable-pip-version-check", "--isolated", "--no-input"}),
    "pip3": frozenset({"--disable-pip-version-check", "--isolated", "--no-input"}),
    "uv": frozenset({"--offline", "--no-cache"}),
    "poetry": frozenset({"--no-ansi", "--no-interaction"}),
}
_PACKAGE_VALUE_OPTIONS = {
    "npm": frozenset({"--prefix", "--workspace"}),
    "pnpm": frozenset({"--dir", "--filter", "--workspace-dir"}),
    "yarn": frozenset({"--cwd"}),
    "pip": frozenset(
        {
            "--proxy",
            "--index-url",
            "--extra-index-url",
            "--trusted-host",
            "--cert",
            "--client-cert",
            "--timeout",
            "--retries",
            "--cache-dir",
        }
    ),
    "pip3": frozenset(
        {
            "--proxy",
            "--index-url",
            "--extra-index-url",
            "--trusted-host",
            "--cert",
            "--client-cert",
            "--timeout",
            "--retries",
            "--cache-dir",
        }
    ),
    "uv": frozenset({"--project", "--directory", "--config-file"}),
    "poetry": frozenset({"--directory", "--project", "-C", "-P"}),
}
_REMOTE_NO_VALUE_OPTIONS = {
    "git": frozenset(
        {
            "--bare",
            "--glob-pathspecs",
            "--icase-pathspecs",
            "--literal-pathspecs",
            "--no-optional-locks",
            "--no-pager",
            "--no-replace-objects",
            "--noglob-pathspecs",
            "--paginate",
        }
    ),
    "twine": frozenset(
        {"--disable-progress-bar", "--non-interactive", "--verbose", "--version"}
    ),
    "docker": frozenset({"--debug", "-D", "--tls", "--tlsverify", "--version"}),
    "gh": frozenset({"--help", "--version"}),
}
_REMOTE_VALUE_OPTIONS = {
    "git": frozenset(
        {
            "-C",
            "-c",
            "--config-env",
            "--exec-path",
            "--git-dir",
            "--namespace",
            "--super-prefix",
            "--work-tree",
        }
    ),
    "twine": frozenset(
        {
            "--cert",
            "--client-cert",
            "--config-file",
            "--password",
            "--repository",
            "--repository-url",
            "--username",
        }
    ),
    "docker": frozenset(
        {
            "-H",
            "--config",
            "--context",
            "--host",
            "--log-level",
            "--tlscacert",
            "--tlscert",
            "--tlskey",
        }
    ),
    "gh": frozenset({"-R", "--hostname", "--repo"}),
}


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class HostTransferAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tool: Literal["host_import", "host_export"]
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


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
        if self._executable(action.tool) in {"host_import", "host_export"}:
            return self._result(PolicyDecision.DENY, "INVALID_ACTION", "", context)
        parsed = self._parse_action(action)
        if parsed is None:
            return self._result(PolicyDecision.DENY, "INVALID_ACTION", "", context)
        if parsed.escaped:
            return self._result(PolicyDecision.DENY, "PATH_ESCAPE", "", context)

        scope = self._scope(action, parsed.argv, parsed.paths)
        tool = self._executable(action.tool)
        command = self._unwrap_command(parsed.argv)

        if tool in {"delete_path", "delete_file"}:
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
        if self._is_git_remote(command.argv):
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

    def evaluate_internal(
        self,
        action: HostTransferAction,
        context: PolicyContext,
    ) -> PolicyResult:
        workspace_candidate = (
            action.target if action.tool == "host_import" else action.source
        )
        try:
            workspace_path = self._path_guard.resolve(workspace_candidate)
        except PathEscapeError:
            return self._result(PolicyDecision.DENY, "PATH_ESCAPE", "", context)
        scope = self._host_transfer_scope(
            action.tool,
            action.source,
            action.target,
            workspace_path,
        )
        return self._result(
            PolicyDecision.REQUIRE_APPROVAL,
            "EXTERNAL_TRANSFER",
            scope,
            context,
        )

    def _parse_action(self, action: ToolAction) -> _ParsedAction | None:
        tool = self._executable(action.tool)
        arguments = action.arguments
        if any(field in arguments and not isinstance(arguments[field], str) for field in _NETWORK_FIELDS):
            return None

        argv: tuple[str, ...] = ()
        candidates: list[tuple[str, str]] = []
        if tool in {"read_file", "delete_path"}:
            path = arguments.get("path")
            if not isinstance(path, str):
                return None
            candidates.append(("path", path))
        elif tool == "search":
            if set(arguments) != {"query"} or not isinstance(arguments.get("query"), str):
                return None
        elif tool == "delete_file":
            path = arguments.get("path")
            digest = arguments.get("expected_sha256")
            if (
                set(arguments) != {"path", "expected_sha256"}
                or not isinstance(path, str)
                or not isinstance(digest, str)
            ):
                return None
            candidates.append(("path", path))
        elif tool == "apply_patch":
            path = arguments.get("path")
            expected = arguments.get("expected_sha256")
            content = arguments.get("content")
            if set(arguments) == {"path", "expected_sha256", "content"}:
                if (
                    not isinstance(path, str)
                    or not isinstance(expected, str | None)
                    or not isinstance(content, str)
                ):
                    return None
                candidates.append(("path", path))
                return self._resolve_candidates(argv, candidates)
            patch = arguments.get("patch")
            if not isinstance(patch, str):
                return None
            matches = tuple(_PATCH_HEADER.finditer(patch))
            if not matches or len(matches) != len(tuple(_PATCH_HEADER_LIKE.finditer(patch))):
                return None
            candidates.extend(("patch", match.group("path")) for match in matches)
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

        return self._resolve_candidates(argv, candidates)

    def _resolve_candidates(
        self,
        argv: tuple[str, ...],
        candidates: list[tuple[str, str]],
    ) -> _ParsedAction:
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

    @classmethod
    def _path_tokens(cls, argv: Sequence[str]) -> tuple[str, ...]:
        paths: list[str] = []
        cmd_option_indexes = cls._cmd_slash_option_indexes(tuple(argv))
        for index, token in enumerate(argv[1:], start=1):
            if (
                cls._is_url(token)
                or token.startswith("-")
                or index in cmd_option_indexes
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

    @classmethod
    def _cmd_slash_option_indexes(cls, argv: tuple[str, ...]) -> frozenset[int]:
        command = cls._unwrap_command(argv)
        if not command.argv or cls._executable(command.argv[0]) != "cmd":
            return frozenset()
        offset = len(argv) - len(command.argv)
        if offset < 0 or argv[offset:] != command.argv:
            return frozenset()
        indexes: set[int] = set()
        for index, token in enumerate(command.argv[1:], start=1):
            normalized = token.casefold()
            if normalized in {"/d", "/s"}:
                indexes.add(offset + index)
                continue
            if normalized == "/c":
                indexes.add(offset + index)
            break
        return frozenset(indexes)

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

    def _host_transfer_scope(
        self,
        tool: str,
        source: str,
        target: str,
        workspace_path: Path,
    ) -> str:
        if tool == "host_import":
            source = self._normalize_external_path(source)
            target = str(workspace_path)
            direction = "import"
        else:
            source = str(workspace_path)
            target = self._normalize_external_path(target)
            direction = "export"
        sanitized = self._redactor.sanitize(
            {"direction": direction, "source": source, "target": target}
        ).value
        return json.dumps(
            sanitized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _normalize_external_path(candidate: str) -> str:
        windows = PureWindowsPath(candidate)
        if windows.is_absolute() or windows.drive or candidate.startswith("\\\\"):
            return str(windows)
        return str(PurePosixPath(candidate))

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
                current, read_only = cls._unwrap_command_builtin(current)
                if read_only:
                    return _Command(())
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

    @staticmethod
    def _unwrap_command_builtin(
        argv: tuple[str, ...],
    ) -> tuple[tuple[str, ...] | None, bool]:
        index = 1
        while index < len(argv):
            token = argv[index]
            if token == "-p":
                index += 1
                continue
            if token in {"-v", "-V"}:
                return None, True
            if token == "--":
                index += 1
                break
            if token.startswith("-"):
                return None, False
            break
        return (argv[index:] or None), False

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
        operation, remaining, reliable = cls._package_operation(argv, command)
        if not reliable:
            if command in _PUBLISH_OPERATIONS and any(
                token.casefold() == "publish" for token in argv[1:]
            ):
                return False
            return command in _PACKAGE_NO_VALUE_OPTIONS
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
                nested = ("pip", *remaining)
                nested_operation, _, nested_reliable = cls._package_operation(
                    nested, "pip"
                )
                return not nested_reliable or nested_operation == "install"
        if command == "poetry":
            return operation in {"install", "add"}
        return False

    @classmethod
    def _package_operation(
        cls,
        argv: tuple[str, ...],
        command: str,
    ) -> tuple[str, tuple[str, ...], bool]:
        if command not in _PACKAGE_NO_VALUE_OPTIONS:
            return "", (), True
        return cls._parse_operation(
            argv,
            command,
            _PACKAGE_NO_VALUE_OPTIONS[command],
            _PACKAGE_VALUE_OPTIONS[command],
        )

    @classmethod
    def _parse_operation(
        cls,
        argv: tuple[str, ...],
        command: str,
        no_value: frozenset[str],
        with_value: frozenset[str],
    ) -> tuple[str, tuple[str, ...], bool]:
        if not argv or cls._executable(argv[0]) != command:
            return "", (), True
        index = 1
        while index < len(argv):
            token = argv[index]
            if token == "--":
                index += 1
                break
            if token in no_value:
                index += 1
                continue
            option = token.split("=", 1)[0]
            if option in with_value:
                if "=" in token:
                    if not token.split("=", 1)[1]:
                        return "", (), False
                    index += 1
                    continue
                if index + 1 >= len(argv):
                    return "", (), False
                index += 2
                continue
            if token.startswith("-"):
                return "", (), False
            break
        if index >= len(argv):
            return "", (), True
        return argv[index].casefold(), argv[index + 1 :], True

    @classmethod
    def _is_network(cls, argv: tuple[str, ...]) -> bool:
        return bool(argv) and cls._executable(argv[0]) in _NETWORK_COMMANDS

    @classmethod
    def _is_git_remote(cls, argv: tuple[str, ...]) -> bool:
        operation, _, reliable = cls._remote_operation(argv, "git")
        return not reliable or operation in _GIT_REMOTE_OPERATIONS

    @classmethod
    def _remote_operation(
        cls,
        argv: tuple[str, ...],
        command: str,
    ) -> tuple[str, tuple[str, ...], bool]:
        if command in _PACKAGE_NO_VALUE_OPTIONS:
            return cls._package_operation(argv, command)
        if command not in _REMOTE_NO_VALUE_OPTIONS:
            return "", (), True
        return cls._parse_operation(
            argv,
            command,
            _REMOTE_NO_VALUE_OPTIONS[command],
            _REMOTE_VALUE_OPTIONS[command],
        )

    @classmethod
    def _is_publish(cls, argv: tuple[str, ...]) -> bool:
        if not argv:
            return False
        command = cls._executable(argv[0])
        operations = _PUBLISH_OPERATIONS.get(command)
        if operations is None:
            return False
        operation, _, reliable = cls._remote_operation(argv, command)
        return not reliable or operation in operations

    @classmethod
    def _is_dangerous_command(cls, argv: tuple[str, ...]) -> bool:
        if not argv:
            return False
        command = cls._executable(argv[0])
        return command in _DELETE_COMMANDS or command in _DESTRUCTIVE_COMMANDS
