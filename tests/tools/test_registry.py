from pathlib import Path

import pytest

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.tools.models import ToolContext
from coding_agent_harness.tools.registry import ToolRegistry


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
    from hashlib import sha256

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


async def test_read_file_rejects_oversized_content(registry: ToolRegistry, worktree: Path) -> None:
    (worktree / "src" / "large.py").write_bytes(b"x" * (64 * 1024 + 1))

    result = await registry.execute(tool("read_file", {"path": "src/large.py"}))

    assert result.ok is False
    assert result.code == "FILE_TOO_LARGE"
    assert result.output == ""
