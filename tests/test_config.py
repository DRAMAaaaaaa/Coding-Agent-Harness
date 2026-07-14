import pytest
from pydantic import ValidationError

from coding_agent_harness.config import HarnessSettings


def test_safe_defaults_are_bounded() -> None:
    settings = HarnessSettings()
    assert settings.bind_host == "127.0.0.1"
    assert settings.command_timeout_seconds == 300
    assert settings.max_task_cycles == 8
    assert settings.max_same_fingerprint == 3
    assert settings.no_progress_limit == 2
    assert settings.max_concurrent_tasks == 3


@pytest.mark.parametrize(
    "field_name",
    [
        "command_timeout_seconds",
        "max_task_cycles",
        "max_same_fingerprint",
        "no_progress_limit",
        "max_concurrent_tasks",
    ],
)
def test_integer_limits_reject_zero(field_name: str) -> None:
    with pytest.raises(ValidationError):
        HarnessSettings(**{field_name: 0})
