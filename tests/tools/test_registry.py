from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.tools.models import ToolContext
from coding_agent_harness.tools.registry import ToolRegistry
from coding_agent_harness.workspace.git import SafeGit
from coding_agent_harness.workspace.processes import CommandResult


def tool(name: str, arguments: dict[str, object]) -> ToolAction:
    return ToolAction.model_validate(
        {"kind": "tool", "tool": name, "arguments": arguments, "idempotency_key": name}
    )


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_bytes(b"VALUE = 1\n")
    return tmp_path


@pytest.fixture
def registry(worktree: Path) -> ToolRegistry:
    return ToolRegistry(ToolContext(workspace_root=worktree))


async def test_apply_patch_is_compare_and_swap(registry: ToolRegistry, worktree: Path) -> None:
    target = worktree / "src" / "app.py"
    before = sha256(target.read_bytes()).hexdigest()
    result = await registry.execute(
        tool("apply_patch", {"path": "src/app.py", "expected_sha256": before, "content": "VALUE = 2\n"})
    )
    assert result.ok
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"


async def test_delete_waits_for_approval_and_shell_is_absent(registry: ToolRegistry) -> None:
    delete = await registry.execute(tool("delete_file", {"path": "x.py", "expected_sha256": "0" * 64}))
    assert delete.code == "APPROVAL_REQUIRED"
    shell = await registry.execute(tool("shell", {"argv": ["curl", "https://example.test"]}))
    assert shell.code == "UNSUPPORTED_TOOL"


async def test_read_file_returns_bounded_regular_file(registry: ToolRegistry) -> None:
    result = await registry.execute(tool("read_file", {"path": "src/app.py"}))

    assert result.ok
    assert result.code == "OK"
    assert result.output == "VALUE = 1\n"
    assert result.observation is not None
    assert result.observation.tool == "read_file"
    assert result.observation.kind == "file"
    assert result.observation.path == "src/app.py"
    assert result.observation.sha256 == sha256(b"VALUE = 1\n").hexdigest()
    assert result.observation.content == "VALUE = 1\n"


async def test_read_file_rejects_oversized_content(registry: ToolRegistry, worktree: Path) -> None:
    (worktree / "src" / "large.py").write_bytes(b"x" * (64 * 1024 + 1))

    result = await registry.execute(tool("read_file", {"path": "src/large.py"}))

    assert result.ok is False
    assert result.code == "FILE_TOO_LARGE"
    assert result.output == ""
    assert result.observation is not None
    assert result.observation.kind == "failure"
    assert result.observation.code == "FILE_TOO_LARGE"
    assert result.observation.diagnostic == "FILE_TOO_LARGE"


class _ObservedGit:
    def run(
        self, root: str | Path, args: tuple[str, ...], stdin: bytes = b""
    ) -> CommandResult:
        del root, stdin
        output = b" M src/app.py\0" if args[0] == "status" else b"diff output\n"
        return CommandResult(returncode=0, stdout=output, stderr=b"")


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    [("git_status", " M src/app.py\0"), ("git_diff", "diff output\n")],
)
async def test_git_read_tools_return_structured_output_observation(
    worktree: Path, tool_name: str, expected: str
) -> None:
    registry = ToolRegistry(
        ToolContext(
            workspace_root=worktree,
            safe_git=cast(SafeGit, _ObservedGit()),
        )
    )

    result = await registry.execute(tool(tool_name, {}))

    assert result.ok
    assert result.observation is not None
    assert result.observation.tool == tool_name
    assert result.observation.kind == "output"
    assert result.observation.output == expected
