from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
import re
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.agent.state_machine import StateMachine, recover_task
from coding_agent_harness.domain.actions import CompleteAction, TaskState, ToolAction
from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.domain.models import Task
from coding_agent_harness.feedback.engine import FeedbackEngine
from coding_agent_harness.feedback.models import FailureCategory, FeedbackObservation, VerificationRun
from coding_agent_harness.providers.base import LLMProvider, LLMRequest
from coding_agent_harness.storage.event_store import EventStore
from coding_agent_harness.storage.repositories import TaskRepository
from coding_agent_harness.tools.models import ToolResult


class ToolExecutor(Protocol):
    async def execute(self, action: ToolAction) -> ToolResult: ...


class TaskStateError(RuntimeError):
    """调用方在不适用的任务阶段请求了操作。"""


class AgentOrchestrator:
    """由事件驱动且可离线重放的最小 Agent 主循环。"""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        parser: ActionParser,
        tools: ToolExecutor,
        event_store: EventStore,
        tasks: TaskRepository,
        feedback: FeedbackEngine | None = None,
    ) -> None:
        self._provider = provider
        self._parser = parser
        self._tools = tools
        self._event_store = event_store
        self._tasks = tasks
        self._feedback = feedback or FeedbackEngine()
        self._state_machine = StateMachine()
        self._actions: list[ToolAction] = []

    @property
    def actions(self) -> tuple[ToolAction, ...]:
        return tuple(self._actions)

    async def task(self, task_id: UUID) -> Task:
        task = await self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"任务不存在：{task_id}")
        recovered = recover_task(await self._event_store.list_for_task(task.id))
        if recovered.state is not task.state:
            return await self._tasks.update_state(task.id, recovered.state)
        return task

    async def propose_plan(self, task_id: UUID) -> Task:
        task = await self.task(task_id)
        if task.state is not TaskState.CREATED:
            raise TaskStateError("只能为新建任务生成计划")
        task = await self._emit(task, "SCAN_STARTED", {"source": "orchestrator"})
        task = await self._emit(task, "PLAN_STARTED", {"source": "orchestrator"})
        response = await self._ask(task, "plan")
        return await self._emit(task, "PLAN_PROPOSED", {"plan": response})

    async def approve_plan(self, task_id: UUID) -> Task:
        task = await self.task(task_id)
        if task.state is not TaskState.WAITING_PLAN_APPROVAL:
            raise TaskStateError("任务当前不等待计划批准")
        return await self._emit(task, "PLAN_APPROVED", {"approved_by": "user"})

    async def approve_final(self, task_id: UUID) -> Task:
        task = await self.task(task_id)
        if task.state is not TaskState.WAITING_FINAL_REVIEW:
            raise TaskStateError("任务当前不等待最终审查")
        return await self._emit(task, "FINAL_REVIEW_APPROVED", {"approved_by": "user"})

    async def run_until_wait(self, task_id: UUID) -> Task:
        while True:
            task = await self.task(task_id)
            if task.state in {
                TaskState.WAITING_PLAN_APPROVAL,
                TaskState.WAITING_ACTION_APPROVAL,
                TaskState.WAITING_FINAL_REVIEW,
                TaskState.WAITING_USER,
                TaskState.COMPLETED,
                TaskState.FAILED,
                TaskState.CANCELLED,
            }:
                return task
            if task.state is TaskState.CORRECTING:
                await self._emit(task, "CORRECTION_READY", {"source": "feedback"})
                continue
            if task.state is TaskState.VERIFYING:
                await self._emit(task, "VERIFICATION_READY", {"source": "orchestrator"})
                continue
            if task.state is not TaskState.DECIDING:
                raise TaskStateError(f"无法在 {task.state} 驱动 Agent 循环")
            if await self._budget_exhausted(task):
                return await self._emit(task, "USER_INPUT_REQUIRED", {"reason_code": "STEP_BUDGET"})
            raw_action = await self._ask(task, "action")
            try:
                action = self._parser.parse(raw_action)
            except (TypeError, ValueError):
                task = await self._emit(task, "ACTION_PARSE_FAILED", {"raw": raw_action})
                return await self._emit(
                    task,
                    "USER_INPUT_REQUIRED",
                    {"reason_code": "ACTION_PARSE_FAILED"},
                )
            task = await self._emit(task, "ACTION_PARSED", {"action": action.model_dump()})
            if isinstance(action, CompleteAction):
                if await self._has_successful_verification(task.id):
                    task = await self._emit(
                        task,
                        "FINAL_SUMMARY_RECORDED",
                        {"summary": action.summary},
                    )
                    return await self._emit(
                        task,
                        "FINAL_SUMMARY_PROPOSED",
                        {"summary": action.summary},
                    )
                return await self._emit(
                    task,
                    "USER_INPUT_REQUIRED",
                    {"reason_code": "VERIFICATION_REQUIRED", "summary": action.summary},
                )
            self._actions.append(action)
            if self._blocked_by_governance(action):
                task = await self._emit(
                    task,
                    "GOVERNANCE_BLOCKED",
                    {"action": action.model_dump(), "reason_code": "DELETE_PATH"},
                )
                return await self._emit(
                    task,
                    "USER_INPUT_REQUIRED",
                    {"reason_code": "DELETE_PATH"},
                )
            task = await self._emit(task, "GOVERNANCE_ALLOWED", {"action": action.model_dump()})
            task = await self._emit(task, "ACTION_PROPOSED", {"action": action.model_dump()})
            task = await self._execute(task, action)
            if task.state is TaskState.WAITING_USER:
                return task

    async def _execute(self, task: Task, action: ToolAction) -> Task:
        execution_id = f"{task.id}:{await self._next_sequence(task.id)}"
        task = await self._emit(
            task,
            "TOOL_EXECUTION_STARTED",
            {"execution_id": execution_id, "action": action.model_dump()},
        )
        result = await self._tools.execute(action)
        finished_event = "TOOL_EXECUTION_COMPLETED" if result.ok else "TOOL_EXECUTION_FAILED"
        task = await self._emit(
            task,
            finished_event,
            {"execution_id": execution_id, "result": result.model_dump(mode="json")},
        )
        if action.tool in {"read_file", "search", "git_status", "git_diff"} and result.ok:
            return await self._emit(task, "READ_TOOL_COMPLETED", {"tool": action.tool})
        task = await self._emit(task, "TOOL_COMPLETED", {"tool": action.tool})
        if action.tool != "run_verification":
            return task
        run = VerificationRun(
            name=self._verification_name(action),
            ok=result.ok,
            output=result.output or result.code,
            failure_count=self._failure_count(result.output),
        )
        task = await self._emit(
            task,
            "VERIFICATION_RECORDED",
            {"run": run.model_dump(mode="json")},
        )
        if result.ok:
            return await self._emit(
                task,
                "VERIFICATION_SUCCEEDED",
                {"run": run.model_dump(mode="json")},
            )
        decision = self._feedback.evaluate(await self._feedback_history(task.id), run)
        task = await self._emit(
            task,
            "FEEDBACK_RECORDED",
            {
                "observation": decision.observation.model_dump(mode="json"),
                "reason_code": decision.reason_code,
                "output": run.output,
            },
        )
        if decision.next_state is TaskState.WAITING_USER:
            return await self._emit(
                task,
                "USER_INPUT_REQUIRED",
                {"reason_code": decision.reason_code},
            )
        return await self._emit(task, "VERIFICATION_FAILED", {"reason_code": decision.reason_code})

    async def _ask(self, task: Task, phase: str) -> str:
        task = await self._emit(task, "LLM_REQUESTED", {"phase": phase})
        response = await self._provider.complete(LLMRequest(messages=await self._messages(task)))
        await self._emit(task, "LLM_RESPONSE_RECEIVED", {"phase": phase, "content": response.content})
        return response.content

    async def _messages(self, task: Task) -> list[dict[str, JsonValue]]:
        messages: list[dict[str, JsonValue]] = [
            {"role": "user", "content": task.requirement}
        ]
        for event in await self._event_store.list_for_task(task.id):
            content = event.payload.get("content")
            if isinstance(content, str):
                messages.append({"role": "assistant", "content": content})
            output = event.payload.get("output")
            if isinstance(output, str):
                messages.append({"role": "user", "content": f"验证反馈：{output}"})
        return messages

    async def _emit(
        self,
        task: Task,
        event_type: str,
        payload: dict[str, JsonValue],
    ) -> Task:
        events = await self._event_store.list_for_task(task.id)
        target = self._state_machine.transition(task.state, event_type)
        await self._event_store.append(
            TaskEvent(
                task_id=task.id,
                sequence=0,
                event_type=event_type,
                payload=payload,
                state_before=task.state,
                state_after=target,
                occurred_at=datetime.now(UTC),
            ),
            expected_sequence=len(events),
        )
        return await self._tasks.update_state(task.id, target)

    async def _next_sequence(self, task_id: UUID) -> int:
        return len(await self._event_store.list_for_task(task_id)) + 1

    async def _feedback_history(self, task_id: UUID) -> Sequence[FeedbackObservation]:
        observations: list[FeedbackObservation] = []
        for event in await self._event_store.list_for_task(task_id):
            if event.event_type != "FEEDBACK_RECORDED":
                continue
            raw = event.payload.get("observation")
            if isinstance(raw, dict):
                category = raw.get("category")
                fingerprint = raw.get("fingerprint")
                failure_count = raw.get("failure_count")
                if (
                    isinstance(category, str)
                    and isinstance(fingerprint, str)
                    and (isinstance(failure_count, int) and not isinstance(failure_count, bool) or failure_count is None)
                ):
                    observations.append(
                        FeedbackObservation(
                            category=FailureCategory(category),
                            fingerprint=fingerprint,
                            failure_count=failure_count,
                        )
                    )
        return observations

    async def _budget_exhausted(self, task: Task) -> bool:
        time_budget_deadline = task.created_at + timedelta(seconds=task.time_budget_seconds)
        deadline = min(
            (candidate for candidate in (time_budget_deadline, task.deadline_at) if candidate is not None),
        )
        if datetime.now(UTC) >= deadline:
            return True
        events = await self._event_store.list_for_task(task.id)
        return sum(event.event_type == "ACTION_PARSED" for event in events) >= task.step_budget

    @staticmethod
    def _blocked_by_governance(action: ToolAction) -> bool:
        return action.tool == "delete_file"

    @staticmethod
    def _verification_name(action: ToolAction) -> str:
        name = action.arguments.get("name")
        return name if isinstance(name, str) and name else "verification"

    async def _has_successful_verification(self, task_id: UUID) -> bool:
        for event in reversed(await self._event_store.list_for_task(task_id)):
            if event.event_type == "VERIFICATION_SUCCEEDED":
                return True
            if event.event_type == "TOOL_EXECUTION_COMPLETED":
                result = event.payload.get("result")
                if isinstance(result, dict):
                    changed_paths = result.get("changed_paths")
                    if isinstance(changed_paths, list) and changed_paths:
                        return False
        return False

    @staticmethod
    def _failure_count(output: str) -> int | None:
        matches = re.findall(r"\b(\d+)\s+(?:failed|errors?)\b", output, flags=re.IGNORECASE)
        if len(matches) != 1:
            return None
        return int(matches[0])
