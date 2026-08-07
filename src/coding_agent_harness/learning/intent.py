"""将 TaskEvent 确定性投影为有限的意图卡片。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from coding_agent_harness.domain.events import TaskEvent
from coding_agent_harness.governance.redaction import Redactor


MAX_CARD_TEXT_BYTES = 8 * 1024


class IntentKind(StrEnum):
    PLAN = "plan"
    FIRST_EDIT = "first_edit"
    VERIFICATION_FAILURE = "verification_failure"
    FINAL_DELIVERY = "final_delivery"


class IntentCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str
    task_id: UUID
    kind: IntentKind
    intent: str
    evidence_sequences: tuple[int, ...]
    action: str
    expected_result: str
    actual_result: str
    status: str
    source_event_sequence: int
    learning_card_id: UUID | None = None


class IntentProjector:
    def __init__(self, redactor: Redactor | None = None) -> None:
        self._redactor = redactor or Redactor()

    def project(self, task_id: UUID, events: Sequence[TaskEvent]) -> tuple[IntentCard, ...]:
        unique = {event.sequence: event for event in events if event.task_id == task_id}
        ordered = tuple(unique[key] for key in sorted(unique))
        cards: list[IntentCard] = []
        plan = _first(ordered, "PLAN_PROPOSED")
        if plan is not None:
            cards.append(self._card(task_id, IntentKind.PLAN, plan, (plan.sequence,)))
        edit = next((event for event in ordered if event.event_type == "TOOL_EXECUTION_COMPLETED" and _changed_paths(event)), None)
        if edit is not None:
            cards.append(self._card(task_id, IntentKind.FIRST_EDIT, edit, (edit.sequence,)))
        failure = _first(ordered, "VERIFICATION_FAILED")
        if failure is not None:
            supporting = next((event for event in reversed(ordered) if event.sequence < failure.sequence and event.event_type in {"VERIFICATION_RECORDED", "FEEDBACK_RECORDED"}), None)
            evidence = ((supporting.sequence,) if supporting else ()) + (failure.sequence,)
            cards.append(self._card(task_id, IntentKind.VERIFICATION_FAILURE, failure, evidence))
        final = _first(ordered, "FINAL_SUMMARY_PROPOSED")
        if final is not None:
            cards.append(self._card(task_id, IntentKind.FINAL_DELIVERY, final, (final.sequence,)))
        return tuple(cards)

    def _card(self, task_id: UUID, kind: IntentKind, event: TaskEvent, evidence: tuple[int, ...]) -> IntentCard:
        actual = _safe_text(self._redactor, event.payload)
        return IntentCard(
            id=f"{task_id}:{kind}:{event.sequence}", task_id=task_id, kind=kind,
            intent=kind.value, evidence_sequences=evidence, action=event.event_type,
            expected_result=_expected(kind), actual_result=actual, status="recorded",
            source_event_sequence=event.sequence,
        )


def _first(events: Sequence[TaskEvent], event_type: str) -> TaskEvent | None:
    return next((event for event in events if event.event_type == event_type), None)


def _changed_paths(event: TaskEvent) -> bool:
    result = event.payload.get("result")
    return isinstance(result, dict) and isinstance(result.get("changed_paths"), list) and bool(result["changed_paths"])


def _safe_text(redactor: Redactor, value: object) -> str:
    sanitized = redactor.sanitize(value).value
    text = sanitized if isinstance(sanitized, str) else json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _clip(text)


def _clip(value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= MAX_CARD_TEXT_BYTES:
        return value
    return encoded[:MAX_CARD_TEXT_BYTES].decode("utf-8", "ignore")


def _expected(kind: IntentKind) -> str:
    return {
        IntentKind.PLAN: "计划已提出", IntentKind.FIRST_EDIT: "首次修改已完成",
        IntentKind.VERIFICATION_FAILURE: "验证通过", IntentKind.FINAL_DELIVERY: "最终摘要已提出",
    }[kind]
