import pytest
from pydantic import ValidationError
from pathlib import Path

from coding_agent_harness.config import HarnessSettings, default_state_root


def test_safe_defaults_are_bounded() -> None:
    settings = HarnessSettings()
    assert settings.bind_host == "127.0.0.1"
    assert settings.bind_port == 8000
    assert settings.trusted_hosts == ("127.0.0.1:8000", "localhost:8000")
    assert settings.trusted_origins == (
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    )
    assert settings.resolved_database_path().is_relative_to(settings.state_root)
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


@pytest.mark.parametrize(
    ("platform", "environment", "home", "expected"),
    [
        ("nt", {"LOCALAPPDATA": "C:/Data"}, Path("C:/Users/test"), Path("C:/Data/CodingAgentHarness")),
        ("nt", {}, Path("C:/Users/test"), Path("C:/Users/test/AppData/Local/CodingAgentHarness")),
        ("posix", {"XDG_DATA_HOME": "/data"}, Path("/home/test"), Path("/data/coding-agent-harness")),
        ("posix", {}, Path("/home/test"), Path("/home/test/.local/share/coding-agent-harness")),
    ],
)
def test_default_state_root_is_pure_and_platform_specific(platform: str, environment: dict[str, str], home: Path, expected: Path) -> None:
    assert default_state_root(platform, environment, home) == expected


def test_explicit_host_storage_paths_override_defaults(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    database_path = state_root / "database" / "harness.db"
    settings = HarnessSettings(state_root=state_root, database_path=database_path)
    assert settings.state_root == state_root.resolve()
    assert settings.resolved_database_path() == database_path.resolve()
    assert settings.private_state_roots() == (
        state_root.resolve(),
        database_path.parent.resolve(),
    )
    with pytest.raises(ValidationError):
        settings.database_path = state_root / "other.db"  # type: ignore[misc]


def test_database_path_outside_state_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        HarnessSettings(
            state_root=tmp_path / "state",
            database_path=tmp_path / "outside" / "harness.db",
        )


def test_database_path_inside_project_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    with pytest.raises(ValidationError):
        HarnessSettings(
            state_root=tmp_path / "state",
            database_path=project / "harness.db",
        )
