import os
from pathlib import Path
from typing import Any

import pytest

from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.governance import policy as policy_module
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


def _host_transfer_action(tool: str, source: str, target: str) -> Any:
    action_type = getattr(policy_module, "HostTransferAction", None)
    assert action_type is not None
    return action_type.model_validate(
        {"tool": tool, "source": source, "target": target},
        strict=True,
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
        ["shutdown"],
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
    ("argv", "reason_code"),
    [
        (["npm", "--prefix", "subdir", "publish"], "PUBLISH"),
        (["npm", "--workspace", "pkg", "publish"], "PUBLISH"),
        (["pnpm", "--dir", "subdir", "publish"], "PUBLISH"),
        (["yarn", "--cwd", "subdir", "publish"], "PUBLISH"),
        (
            ["twine", "--repository-url", "https://example.invalid", "upload"],
            "PUBLISH",
        ),
        (["docker", "--config", "cfg", "push", "image"], "PUBLISH"),
        (["gh", "--repo", "owner/repo", "release", "create", "v1"], "PUBLISH"),
        (["git", "--git-dir", ".git", "push", "origin", "main"], "GIT_REMOTE_CHANGE"),
        (["git", "--work-tree", ".", "push", "origin", "main"], "GIT_REMOTE_CHANGE"),
        (["npm", "--prefix=subdir", "publish"], "PUBLISH"),
        (["gh", "--repo=owner/repo", "release", "create", "v1"], "PUBLISH"),
        (["git", "--git-dir=.git", "push", "origin", "main"], "GIT_REMOTE_CHANGE"),
    ],
)
def test_command_specific_global_options_cannot_hide_remote_mutations(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
    reason_code: str,
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == reason_code


@pytest.mark.parametrize(
    ("argv", "reason_code"),
    [
        (["git", "--mystery", "value", "push"], "GIT_REMOTE_CHANGE"),
        (["git", "--git-dir"], "GIT_REMOTE_CHANGE"),
        (["twine", "--mystery", "value", "upload"], "PUBLISH"),
        (["twine", "--repository-url"], "PUBLISH"),
        (["npm", "--mystery", "publish"], "PUBLISH"),
        (["docker", "--config"], "PUBLISH"),
        (["gh", "--repo"], "PUBLISH"),
    ],
)
def test_unreliable_remote_mutation_options_fail_closed(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
    reason_code: str,
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == reason_code


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "--git-dir", ".git", "status"],
        ["npm", "--prefix", "subdir", "test"],
        ["pnpm", "--dir", "subdir", "test"],
        ["yarn", "--cwd", "subdir", "test"],
        ["twine", "--version"],
        ["docker", "--config", "cfg", "images"],
        ["gh", "--repo", "owner/repo", "issue", "list"],
    ],
)
def test_safe_operations_with_command_specific_options_remain_allowed(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.ALLOW
    assert result.reason_code == "SAFE"


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
    expected_code = "INVALID_ACTION" if tool == "search" else "PATH_ESCAPE"
    assert result.reason_code == expected_code


@pytest.mark.parametrize(
    ("tool", "source", "target", "direction"),
    [
        ("host_import", "C:/host/input.py", "src/input.py", "import"),
        ("host_export", "src/output.py", "C:/host/output.py", "export"),
    ],
)
def test_host_transfer_uses_separate_exact_approval(
    policy: PolicyEngine,
    tmp_path: Path,
    tool: str,
    source: str,
    target: str,
    direction: str,
) -> None:
    result = policy.evaluate_internal(
        _host_transfer_action(tool, source, target),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == "EXTERNAL_TRANSFER"
    assert f'"direction":"{direction}"' in result.normalized_scope
    assert '"source":' in result.normalized_scope
    assert '"target":' in result.normalized_scope


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("host_import", {"source": "C:/host/input.py", "target": "../outside.py"}),
        ("host_export", {"source": "../outside.py", "target": "C:/host/output.py"}),
    ],
)
def test_host_transfer_guards_only_its_workspace_side(
    policy: PolicyEngine,
    tmp_path: Path,
    tool: str,
    arguments: dict[str, object],
) -> None:
    result = policy.evaluate_internal(
        _host_transfer_action(
            tool,
            str(arguments["source"]),
            str(arguments["target"]),
        ),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"


@pytest.mark.parametrize("tool", ["host_import", "host_export"])
def test_agent_tool_action_cannot_claim_internal_host_provenance(
    policy: PolicyEngine,
    tmp_path: Path,
    tool: str,
) -> None:
    result = policy.evaluate(
        _action(tool, {"source": "src/input.py", "target": "src/output.py"}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "INVALID_ACTION"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("read_file", {"path": "../outside.py", "approval_id": "transfer-approval"}),
        (
            "apply_patch",
            {
                "patch": "*** Update File: ../outside.py",
                "approval_id": "transfer-approval",
            },
        ),
        (
            "shell",
            {
                "argv": ["rm", "../outside.py"],
                "approval_id": "transfer-approval",
            },
        ),
    ],
)
def test_transfer_approval_never_grants_external_paths_to_agent_tools(
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


def test_apply_patch_move_to_target_is_also_path_guarded(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    patch = """*** Begin Patch
*** Update File: src/inside.py
*** Move to: ../outside.py
*** End Patch"""

    result = policy.evaluate(
        _action("apply_patch", {"patch": patch}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"


@pytest.mark.parametrize(
    "patch",
    [
        "*** Begin Patch\n*** End Patch",
        "*** Begin Patch\n*** Move to File: src/not-real.py\n*** End Patch",
        "*** Begin Patch\n*** Add File src/missing-colon.py\n*** End Patch",
    ],
)
def test_apply_patch_without_only_valid_file_headers_is_denied(
    policy: PolicyEngine,
    tmp_path: Path,
    patch: str,
) -> None:
    result = policy.evaluate(
        _action("apply_patch", {"patch": patch}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "INVALID_ACTION"


def test_command_read_only_flags_are_only_wrapper_prefix_options(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    dangerous = policy.evaluate(
        _action("shell", {"argv": ["command", "rm", "-v", "src/a.py"]}),
        _context(tmp_path / "workspace"),
    )
    read_only = policy.evaluate(
        _action("shell", {"argv": ["command", "-v", "rm"]}),
        _context(tmp_path / "workspace"),
    )

    assert dangerous.decision is PolicyDecision.REQUIRE_APPROVAL
    assert dangerous.reason_code == "HIGH_RISK_SHELL"
    assert read_only.decision is PolicyDecision.ALLOW


@pytest.mark.parametrize(
    "argv",
    [
        ["npm", "--prefix", "subdir", "install", "x"],
        ["pnpm", "--filter", "workspace-a", "add", "x"],
        ["pip", "--proxy", "https://proxy.example", "install", "x"],
        ["uv", "--project", "subdir", "sync"],
        ["poetry", "--directory", "subdir", "add", "x"],
        ["npm", "--unknown-option", "test"],
    ],
)
def test_package_manager_value_or_unknown_options_cannot_hide_install(
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
        ["npm", "--prefix", "subdir", "test"],
        ["pip", "--proxy", "https://proxy.example", "list"],
    ],
)
def test_safe_package_manager_operations_with_known_value_options_remain_allowed(
    policy: PolicyEngine,
    tmp_path: Path,
    argv: list[str],
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": argv}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.ALLOW


@pytest.mark.parametrize("command", ["echo", "rm"])
def test_slash_paths_are_not_global_command_options(
    policy: PolicyEngine,
    tmp_path: Path,
    command: str,
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": [command, "/s"]}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows anchor 语义")
def test_policy_denies_different_unc_anchor_without_identity_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    policy = PolicyEngine(PathGuard(root), Redactor())
    calls: list[str] = []
    candidate = Path(r"\\untrusted.invalid\share\payload")
    relevant = {str(root), str(root.resolve()), str(candidate)}
    original_resolve = Path.resolve
    original_samefile = Path.samefile
    original_stat = Path.stat

    def record_resolve(self: Path, strict: bool = False) -> Path:
        if str(self) in relevant:
            calls.append(f"resolve:{self}")
            return self
        return original_resolve(self, strict=strict)

    def record_samefile(self: Path, other: object) -> bool:
        if str(self) in relevant or str(other) in relevant:
            calls.append(f"samefile:{self}:{other}")
            return False
        return original_samefile(self, other)

    def record_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if str(self) in relevant:
            calls.append(f"stat:{self}")
            raise AssertionError("不同 anchor 不得探测文件系统")
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "resolve", record_resolve)
    monkeypatch.setattr(Path, "samefile", record_samefile)
    monkeypatch.setattr(Path, "stat", record_stat)

    result = policy.evaluate(
        _action("read_file", {"path": r"\\untrusted.invalid\share\payload"}),
        _context(root),
    )
    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"
    assert calls == []


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows drive-relative 语义")
def test_policy_denies_drive_relative_path_without_identity_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    policy = PolicyEngine(PathGuard(root), Redactor())
    calls: list[str] = []

    def reject_resolve(self: Path, strict: bool = False) -> Path:
        del strict
        calls.append(f"resolve:{self}")
        raise AssertionError("drive-relative 路径不得探测文件系统")

    monkeypatch.setattr(Path, "resolve", reject_resolve)

    result = policy.evaluate(
        _action("read_file", {"path": r"Z:payload"}),
        _context(root),
    )
    assert result.decision is PolicyDecision.DENY
    assert result.reason_code == "PATH_ESCAPE"
    assert calls == []


def test_cmd_slash_options_remain_valid_only_in_cmd_prefix(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    result = policy.evaluate(
        _action("shell", {"argv": ["cmd", "/d", "/s", "/c", "echo safe"]}),
        _context(tmp_path / "workspace"),
    )

    assert result.decision is PolicyDecision.REQUIRE_APPROVAL
    assert result.reason_code == "HIGH_RISK_SHELL"


def test_structured_file_tools_guard_paths_and_require_delete_approval(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path / "workspace")
    patch = policy.evaluate(
        _action(
            "apply_patch",
            {"path": "../outside.py", "expected_sha256": None, "content": "x\n"},
        ),
        context,
    )
    delete = policy.evaluate(
        _action(
            "delete_file",
            {"path": "src/file.py", "expected_sha256": "0" * 64},
        ),
        context,
    )

    assert patch.decision is PolicyDecision.DENY
    assert patch.reason_code == "PATH_ESCAPE"
    assert delete.decision is PolicyDecision.REQUIRE_APPROVAL
    assert delete.reason_code == "DELETE_PATH"


def test_search_accepts_only_the_registry_query_protocol(
    policy: PolicyEngine,
    tmp_path: Path,
) -> None:
    context = _context(tmp_path / "workspace")
    allowed = policy.evaluate(_action("search", {"query": "needle"}), context)
    rejected = policy.evaluate(
        _action("search", {"query": "needle", "path": "src/app.py"}), context
    )

    assert allowed.decision is PolicyDecision.ALLOW
    assert rejected.decision is PolicyDecision.DENY
    assert rejected.reason_code == "INVALID_ACTION"
