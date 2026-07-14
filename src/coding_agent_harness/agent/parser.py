import json
from collections.abc import Collection

from pydantic import TypeAdapter, ValidationError
from pydantic_core import PydanticCustomError

from coding_agent_harness.domain.actions import AgentAction, ToolAction


def _reject_non_json_constant(constant: str) -> None:
    raise json.JSONDecodeError(f"Invalid JSON constant: {constant}", constant, 0)


class ActionParser:
    _adapter: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)

    def __init__(self, allowed_tools: Collection[str]) -> None:
        self._allowed_tools = frozenset(allowed_tools)

    def parse(self, raw: str) -> AgentAction:
        payload = json.loads(raw, parse_constant=_reject_non_json_constant)
        action = self._adapter.validate_python(payload)
        if isinstance(action, ToolAction) and action.tool not in self._allowed_tools:
            raise ValidationError.from_exception_data(
                "AgentAction",
                [
                    {
                        "type": PydanticCustomError(
                            "unknown_tool",
                            "Tool '{tool}' is not allowed",
                            {"tool": action.tool},
                        ),
                        "loc": ("tool",),
                        "input": action.tool,
                    }
                ],
            )
        return action
