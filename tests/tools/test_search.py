from pathlib import Path

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.governance.paths import PathGuard
from coding_agent_harness.governance.policy import PolicyContext, PolicyEngine
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.tools.models import ToolContext
from coding_agent_harness.tools.registry import ToolRegistry
from coding_agent_harness.workspace.models import RepositoryMap


async def test_search_only_uses_tracked_text_files(tmp_path: Path) -> None:
    (tmp_path / "tracked.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "untracked.py").write_text("needle\n", encoding="utf-8")
    context = ToolContext(workspace_root=tmp_path, repository_map=RepositoryMap(root=tmp_path, tracked_files=("tracked.py",), documents=(), test_paths=(), recent_commits=(), dirty_paths=()))
    result = await ToolRegistry(context).execute(ToolAction.model_validate({"kind": "tool", "tool": "search", "arguments": {"query": "needle"}, "idempotency_key": "s"}))
    assert result.ok
    assert "tracked.py" in result.output
    assert "untracked.py" not in result.output


async def test_search_uses_query_protocol_when_governed(tmp_path: Path) -> None:
    (tmp_path / "tracked.py").write_text("needle\n", encoding="utf-8")
    repository_map = RepositoryMap(root=tmp_path, tracked_files=("tracked.py",), documents=(), test_paths=(), recent_commits=(), dirty_paths=())
    context = ToolContext(
        workspace_root=tmp_path,
        repository_map=repository_map,
        policy=PolicyEngine(PathGuard(tmp_path), Redactor()),
        policy_context=PolicyContext(workspace_root=tmp_path, task_state=TaskState.EXECUTING, event_sequence=1, config_version="v1", llm_api_authorized=False),
    )
    action = ToolAction.model_validate({"kind": "tool", "tool": "search", "arguments": {"query": "needle"}, "idempotency_key": "governed-search"})

    result = await ToolRegistry(context).execute(action)

    assert result.ok
    assert "tracked.py" in result.output
