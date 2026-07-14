import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from coding_agent_harness.agent.parser import ActionParser
from coding_agent_harness.domain.actions import CompleteAction, ToolAction


def test_parser_accepts_complete_action() -> None:
    action = ActionParser(allowed_tools=set()).parse(
        '{"kind":"complete","summary":"完成"}'
    )

    assert action == CompleteAction(summary="完成")


@pytest.mark.parametrize(
    "raw",
    [
        '{"kind":"unknown","summary":"完成"}',
        '{"kind":"complete","summary":"完成","extra":1}',
        '{"kind":"tool","tool":"read_file","arguments":{}}',
    ],
)
def test_parser_rejects_invalid_discriminated_union(raw: str) -> None:
    with pytest.raises(ValidationError):
        ActionParser(allowed_tools={"read_file"}).parse(raw)


def test_parser_rejects_unknown_tool() -> None:
    raw = json.dumps(
        {
            "kind": "tool",
            "tool": "shell",
            "arguments": {},
            "idempotency_key": "shell-1",
        }
    )

    with pytest.raises(ValidationError):
        ActionParser(allowed_tools={"read_file"}).parse(raw)


def test_parser_rejects_invalid_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        ActionParser(allowed_tools=set()).parse("not-json")


def test_parser_rejects_non_json_constants() -> None:
    raw = '{"kind":"tool","tool":"read_file","arguments":{"line":NaN},' \
        '"idempotency_key":"read-1"}'

    with pytest.raises(json.JSONDecodeError):
        ActionParser(allowed_tools={"read_file"}).parse(raw)


def test_parser_treats_shell_text_as_data_without_side_effects(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist.txt"
    raw = json.dumps(
        {
            "kind": "tool",
            "tool": "shell",
            "arguments": {"command": f"Set-Content -Path '{marker}' -Value exploited"},
            "idempotency_key": "shell-1",
        }
    )

    action = ActionParser(allowed_tools={"shell"}).parse(raw)

    assert action == ToolAction(
        tool="shell",
        arguments={"command": f"Set-Content -Path '{marker}' -Value exploited"},
        idempotency_key="shell-1",
    )
    assert not marker.exists()
