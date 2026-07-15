from pathlib import Path

import pytest

from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.governance.paths import PathGuard
from coding_agent_harness.governance.policy import (
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
)
from coding_agent_harness.governance.redaction import Redactor


def _action(tool: str, arguments: dict[str, object]) -> ToolAction:
    return ToolAction.model_validate(
        {
            "tool": tool,
            "arguments": arguments,
            "idempotency_key": f"action-{tool}",
        },
        strict=True,
    )


def _internal_action(tool: str, arguments: dict[str, object]) -> ToolAction:
    return ToolAction.model_construct(
        tool=tool,
        arguments=arguments,
        idempotency_key=f"internal-{tool}",
    )


def _context(root: Path, *, llm_api_authorized: bool = True) -> PolicyContext:
    return PolicyContext(
        workspace_root=root,
        task_state=TaskState.EXECUTING,
        event_sequence=17,
        config_version="cfg-2",
        llm_api_authorized=llm_api_authorized,
    )


@pytest.fixture
def policy(tmp_path: Path) -> PolicyEngine:
    root = tmp_path / "workspace"
    root.mkdir()
    return PolicyEngine(PathGuard(root), Redactor())


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("delete_path", {"path": "src/a.py"}),
        ("shell", {"argv": ["pip", "install", "x"]}),
        ("shell", {"argv": ["curl", "https://example.com"]}),
        ("git", {"operation": "push"}),
    ],
)
def test_dangerous_actions_require_approval(
    policy: PolicyEngine,
    tmp_path: Path,
    tool: str,
    arguments: dict[str, object],
) -> None:
    result = policy.evaluate(_action(tool, arguments), _context(tmp_path / "workspace"))

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.event_sequence == 17


@pytest.mark.parametrize(
    "argv",
    [
        ["npm", "install", "left-pad"],
        ["pnpm", "add", "x"],
        ["yarn", "add", "x"],
        ["poetry", "add", "x"],
        ["uv", "pip", "install", "x"],
        ["wget", "https://example.com"],
        ["powershell", "Invoke-WebRequest", "https://example.com"],
        ["dd", "if=/dev/zero", "of=/dev/sda"],
        ["shutdown", "/s"],
    ],
)
def test_shell_rules_cover_install_network_and_destructive_exact_tokens(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("git", {"operation": "merge"}),
        ("shell", {"argv": ["twine", "upload", "dist/*"]}),
        ("shell", {"argv": ["docker", "push", "example/image"]}),
        ("shell", {"argv": ["gh", "release", "create", "v1"]}),
        ("shell", {"argv": ["npm", "publish"]}),
        ("shell", {"argv": ["git", "push", "origin", "main"]}),
    ],
)
def test_remote_change_and_publish_require_approval(
    policy: PolicyEngine,
    tmp_path: Path,
    tool: str,
    arguments: dict[str, object],
) -> None:
    assert policy.evaluate(
        _action(tool, arguments), _context(tmp_path / "workspace")
    ).decision is PolicyDecision.REQUIRE_APPROVAL


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("git", {"operation": ["push"]}),
        ("delete_path", {}),
        ("read_file", {}),
        ("shell", {"argv": []}),
    ],
)
def test_known_tools_with_invalid_required_arguments_are_denied(
    policy: PolicyEngine,
    tmp_path: Path,
    tool: str,
    arguments: dict[str, object],
) -> None:
    result = policy.evaluate(
        _action(tool, arguments),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "INVALID_ACTION"


@pytest.mark.parametrize(
    "argv",
    [
        ["python", "-m", "pip", "install", "x"],
        ["sudo", "git", "push", "origin", "main"],
        ["bash", "-c", "curl https://example.com"],
    ],
)
def test_shell_wrappers_cannot_bypass_exact_token_rules(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL


def test_llm_authorization_and_spoofed_argument_do_not_authorize_tool_network(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    action = _action(
        "shell",
        {
            "argv": ["curl", "https://example.com"],
            "provider_authorized": True,
        },
    )

    for authorized in (False, True):
        result = policy.evaluate(
            action,
            _context(tmp_path / "workspace", llm_api_authorized=authorized),
        )
        assert result.decision is PolicyDecision.REQUIRE_APPROVAL


@pytest.mark.parametrize("field", ["cwd", "source", "destination", "target"])
def test_read_file_does_not_guess_unsupported_path_fields(
    policy: PolicyEngine,
    tmp_path: Path,
    field: str,
) -> None:
    result = policy.evaluate(
        _action("read_file", {field: "../outside"}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "INVALID_ACTION"


@pytest.mark.parametrize(
    "arguments",
    [
        {"argv": "pytest"},
        {"argv": ["pytest", 7]},
        {"path": ["src/a.py"]},
    ],
)
def test_invalid_argument_shape_is_denied_without_exception(
    policy: PolicyEngine,
    tmp_path: Path,
    arguments: dict[str, object],
) -> None:
    result = policy.evaluate(
        _action("shell", arguments),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "INVALID_ACTION"


def test_safe_read_and_verification_are_allowed(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path / "workspace")

    read = policy.evaluate(_action("read_file", {"path": "src/main.py"}), context)
    verify = policy.evaluate(_action("shell", {"argv": ["pytest", "-q"]}), context)

    assert (read.decision, read.reason_code) == (PolicyDecision.ALLOW, "SAFE")
    assert (verify.decision, verify.reason_code) == (PolicyDecision.ALLOW, "SAFE")


def test_normalized_scope_is_redacted_before_return(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    policy = PolicyEngine(PathGuard(root), Redactor(sensitive_env={"TOKEN": "abc-123"}))

    result = policy.evaluate(
        _action("shell", {"argv": ["curl", "Authorization: Bearer abc-123"]}),
        _context(root),
    )

    assert "abc-123" not in result.normalized_scope
    assert "[REDACTED]" in result.normalized_scope


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "-C", ".", "push", "origin", "main"],
        ["pip", "--disable-pip-version-check", "install", "x"],
        ["docker", "--config", "cfg", "push", "image"],
        ["npm.cmd", "install", "x"],
        ["pnpm.cmd", "add", "x"],
    ],
)
def test_global_options_and_windows_launchers_cannot_bypass_policy(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("curl", {"url": "https://example.com"}),
        ("fetch_artifact", {"uri": "https://example.com/artifact"}),
        ("special_network_tool", {"url": "https://example.com/api"}),
    ],
)
@pytest.mark.parametrize("llm_api_authorized", [False, True])
def test_direct_or_url_field_network_actions_always_require_approval(
    policy: PolicyEngine,
    tmp_path: Path,
    tool: str,
    arguments: dict[str, object],
    llm_api_authorized: bool,
) -> None:
    action = _action(
        tool,
        {**arguments, "provider_authorized": True},
    )

    result = policy.evaluate(
        action,
        _context(
            tmp_path / "workspace",
            llm_api_authorized=llm_api_authorized,
        ),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "status"],
        ["git", "-C", ".", "log", "--oneline"],
        ["pip", "--disable-pip-version-check", "list"],
        ["docker", "--config", "cfg", "images"],
    ],
)
def test_safe_inspection_operations_remain_allowed(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert (result.decision, result.reason_code) == (PolicyDecision.ALLOW, "SAFE")


def test_direct_windows_launcher_operation_is_bound_to_scope(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    result = policy.evaluate(
        _action("git.cmd", {"operation": "push"}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert "push" in result.normalized_scope


@pytest.mark.parametrize(
    "argv",
    [
        ["npm", "i", "x"],
        ["npm", "ci"],
        ["npm.cmd", "ci"],
        ["pnpm", "i", "x"],
        ["yarn"],
        ["uv", "sync"],
        ["python", "-m", "pip", "install", "x"],
        ["py.exe", "-m", "uv", "pip", "install", "x"],
        ["corepack", "pnpm", "add", "x"],
    ],
)
def test_package_manager_install_forms_require_approval(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == "DEPENDENCY_INSTALL"


@pytest.mark.parametrize(
    "argv",
    [
        ["bash", "--noprofile", "-c", "curl https://example.com"],
        ["bash", "--noprofile", "-c", "rm -rf /"],
        ["powershell", "-NoProfile", "-Command", "Invoke-WebRequest https://example.com"],
        ["cmd", "/d", "/c", "curl https://example.com"],
        ["powershell", "-EncodedCommand", "YwB1AHIAbAA="],
        ["env", "-S", "npm install x", "echo", "safe"],
        ["env", "--split-string", "curl https://example.com", "echo", "safe"],
    ],
)
def test_interpreter_options_cannot_hide_code_execution(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == "HIGH_RISK_SHELL"


def test_malformed_network_field_is_denied(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    result = policy.evaluate(
        _action("network_helper", {"url": ["https://example.com"]}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "INVALID_ACTION"


def test_agent_path_escape_cannot_be_approved(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    result = policy.evaluate(
        _action("read_file", {"path": "../secret", "approval_id": "forged"}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"


def test_command_names_in_plain_arguments_are_not_executed(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": ["echo", "npm", "install"]}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.ALLOW


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "status"],
        ["pip", "list"],
        ["docker", "images"],
        ["npm", "test"],
        ["python", "-m", "pytest"],
    ],
)
def test_safe_commands_remain_allowed(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.ALLOW


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("read_file", {"path": "../secret"}),
        ("search", {"path": "../outside", "query": "x"}),
        ("apply_patch", {"patch": "*** Delete File: ../outside.txt"}),
        ("delete_path", {"path": "../outside.txt"}),
        ("shell", {"argv": ["rm", "../outside.txt"]}),
        ("shell", {"argv": ["rm", "/"]}),
        ("shell", {"argv": ["mkfs.ext4", "/dev/sda"]}),
    ],
)
def test_every_real_tool_denies_path_escape_before_risk_approval(
    policy: PolicyEngine,
    tmp_path: Path,
    tool: str,
    arguments: dict[str, object],
) -> None:
    result = policy.evaluate(
        _action(tool, arguments),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"
