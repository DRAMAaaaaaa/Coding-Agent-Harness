from pathlib import Path

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.tools.models import ToolContext
from coding_agent_harness.tools.registry import ToolRegistry


async def test_only_status_and_diff_are_registered(tmp_path: Path) -> None:
    registry = ToolRegistry(ToolContext(workspace_root=tmp_path))
    result = await registry.execute(ToolAction.model_validate({"kind": "tool", "tool": "git_push", "arguments": {}, "idempotency_key": "g"}))
    assert result.code == "UNSUPPORTED_TOOL"
