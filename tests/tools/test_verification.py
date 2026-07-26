from pathlib import Path

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.tools.models import ToolContext
from coding_agent_harness.tools.registry import ToolRegistry
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.processes import CommandResult, ProcessRequest


class FailingRunner:
    def __init__(self) -> None:
        self.calls: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.calls.append(request)
        raise AssertionError("失效配置不得执行 runner")


async def test_verification_refuses_stale_profile_without_running(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires=[]\nbuild-backend='x'\n", encoding="utf-8")
    profile = ProjectDetector().detect(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='changed'\n", encoding="utf-8")
    runner = FailingRunner()
    result = await ToolRegistry(ToolContext(workspace_root=tmp_path, profile=profile, runner=runner)).execute(ToolAction.model_validate({"kind": "tool", "tool": "run_verification", "arguments": {"name": "test"}, "idempotency_key": "v"}))
    assert result.code == "STALE_CONFIG"
    assert runner.calls == []
