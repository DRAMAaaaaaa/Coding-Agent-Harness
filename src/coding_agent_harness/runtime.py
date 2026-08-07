"""真实 Provider 任务的最小编排适配器。"""

from __future__ import annotations

from uuid import UUID

from coding_agent_harness.agent.orchestrator import AgentOrchestrator
from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.api.dependencies import ApiDependencies, OrchestratorPort, RuntimeUnavailableError
from coding_agent_harness.domain.models import Task
from coding_agent_harness.governance.path_identity import trusted_paths_overlap
from coding_agent_harness.governance.paths import PathGuard
from coding_agent_harness.governance.policy import PolicyContext, PolicyEngine
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.tools.models import ToolContext
from coding_agent_harness.tools.registry import ToolRegistry
from coding_agent_harness.workspace.git import SafeGit


_ALLOWED_TOOLS = ("read_file", "search", "apply_patch", "run_verification", "git_status", "git_diff")


class RuntimeOrchestratorRouter(OrchestratorPort):
    """每次 API 调用都依据持久化 Task 重建受限的真实运行时。"""

    def __init__(self, dependencies: ApiDependencies) -> None:
        self._dependencies = dependencies

    async def propose_plan(self, task_id: UUID) -> Task:
        return await (await self._for(task_id)).propose_plan(task_id)

    async def record_runtime_failure(self, task_id: UUID, reason_code: str) -> Task:
        return await (await self._for(task_id)).record_runtime_failure(task_id, reason_code)

    async def approve_plan(self, task_id: UUID) -> Task:
        return await (await self._for(task_id)).approve_plan(task_id)

    async def run_until_wait(self, task_id: UUID) -> Task:
        return await (await self._for(task_id)).run_until_wait(task_id)

    async def approve_final(self, task_id: UUID) -> Task:
        return await (await self._for(task_id)).approve_final(task_id)

    async def _for(self, task_id: UUID) -> AgentOrchestrator:
        dependencies = self._dependencies
        if dependencies.provider_registry is None:
            raise RuntimeUnavailableError("Provider 运行时未配置")
        task = await dependencies.tasks.get(task_id)
        if task is None:
            raise KeyError("任务不存在")
        workspace = await dependencies.workspaces.get(task.workspace_id)
        if workspace is None:
            raise KeyError("Workspace 不存在")
        root = dependencies.state_root / "worktrees" / str(task.workspace_id) / str(task.id)
        if trusted_paths_overlap(root, workspace.workspace.root):
            raise RuntimeUnavailableError("任务工作树边界无效")
        repository_map = await dependencies.worker.run(dependencies.scanner.scan, root)
        profile = await dependencies.worker.run(dependencies.detector.detect, root)
        safe_git = SafeGit(dependencies.state_root)
        context = ToolContext(
            workspace_root=root,
            state_root=dependencies.state_root,
            repository_map=repository_map,
            profile=profile,
            policy=PolicyEngine(PathGuard(root), Redactor()),
            policy_context=PolicyContext(
                workspace_root=root, task_state=task.state, event_sequence=0,
                config_version="runtime-v1", llm_api_authorized=True,
            ),
            safe_git=safe_git,
        )
        return AgentOrchestrator(
            provider=await dependencies.provider_registry.build_for_task(task),
            parser=ActionParser(_ALLOWED_TOOLS),
            tools=ToolRegistry(context),
            event_store=dependencies.event_store,
            tasks=dependencies.tasks,
        )
