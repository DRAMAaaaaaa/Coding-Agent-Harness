from collections.abc import Callable, Iterator
from contextlib import contextmanager
from io import BufferedReader
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from coding_agent_harness.workspace.detector import (
    ProjectConfigurationError,
    ProjectDetector,
)
from coding_agent_harness.workspace.models import Workspace

_FIXTURES = Path(__file__).parents[1] / "fixtures"


class RecordingBinaryFile:
    def __init__(self, raw: BufferedReader, read_sizes: list[int]) -> None:
        self._raw = raw
        self._read_sizes = read_sizes

    def fileno(self) -> int:
        return self._raw.fileno()

    def read(self, size: int = -1) -> bytes:
        self._read_sizes.append(size)
        return self._raw.read(size)


class ControlledFileOpener:
    def __init__(
        self,
        *,
        after_open: Callable[[Path], None] | None = None,
        redirect_to: Path | None = None,
    ) -> None:
        self._after_open = after_open
        self._redirect_to = redirect_to
        self.read_sizes: list[int] = []

    @contextmanager
    def __call__(self, path: Path) -> Iterator[RecordingBinaryFile]:
        opened_path = self._redirect_to or path
        with opened_path.open("rb") as raw:
            if self._after_open is not None:
                self._after_open(path)
            yield RecordingBinaryFile(raw, self.read_sizes)


def test_detects_python_and_node_commands(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n[tool.ruff]\n[tool.mypy]\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest run","build":"vite build"}}',
        encoding="utf-8",
    )

    profile = ProjectDetector().detect(tmp_path)

    assert profile.languages == ["python", "node"]
    assert profile.commands.test == ["python", "-m", "pytest"]
    assert profile.commands.lint == ["python", "-m", "ruff", "check", "."]
    assert profile.commands.typecheck == ["python", "-m", "mypy", "."]
    assert profile.commands.build == ["npm", "run", "build"]
    assert profile.requires_trust is False
    assert profile.trust_fingerprint is None


def test_detects_all_python_fixture_commands() -> None:
    profile = ProjectDetector().detect(_FIXTURES / "python_project")

    assert profile.languages == ["python"]
    assert profile.commands.test == ["python", "-m", "pytest"]
    assert profile.commands.lint == ["python", "-m", "ruff", "check", "."]
    assert profile.commands.typecheck == ["python", "-m", "mypy", "."]
    assert profile.commands.build == ["python", "-m", "build"]


def test_detects_all_node_fixture_scripts() -> None:
    profile = ProjectDetector().detect(_FIXTURES / "node_project")

    assert profile.languages == ["node"]
    assert profile.commands.test == ["npm", "run", "test"]
    assert profile.commands.lint == ["npm", "run", "lint"]
    assert profile.commands.typecheck == ["npm", "run", "typecheck"]
    assert profile.commands.build == ["npm", "run", "build"]


def test_custom_commands_are_argv_only_and_require_trust(tmp_path: Path) -> None:
    (tmp_path / ".harness.yml").write_text(
        "test: [python, -m, pytest, -q]\n"
        "lint: [python, -m, ruff, check, .]\n"
        "timeout: 90\n"
        "env_allowlist: [CI, TEST_MODE]\n",
        encoding="utf-8",
    )

    profile = ProjectDetector().detect(tmp_path)

    assert profile.commands.test == ["python", "-m", "pytest", "-q"]
    assert profile.commands.lint == ["python", "-m", "ruff", "check", "."]
    assert profile.command_timeout_seconds == 90
    assert profile.env_allowlist == ["CI", "TEST_MODE"]
    assert profile.requires_trust is True
    assert profile.trust_fingerprint is not None
    assert len(profile.trust_fingerprint) == 64


@pytest.mark.parametrize(
    "configuration",
    [
        "test: pytest -q\n",
        "test: []\n",
        "test: [python, 3]\n",
        "unknown: true\n",
        "timeout: 0\n",
        "env_allowlist: [GOOD, bad-name]\n",
        "- not-a-mapping\n",
    ],
)
def test_rejects_invalid_custom_command_schema(
    tmp_path: Path,
    configuration: str,
) -> None:
    (tmp_path / ".harness.yml").write_text(configuration, encoding="utf-8")

    with pytest.raises(ProjectConfigurationError, match="^项目配置无效$"):
        ProjectDetector().detect(tmp_path)


def test_rejects_oversized_configuration(tmp_path: Path) -> None:
    config = tmp_path / ".harness.yml"
    config.write_bytes(b"#" * 257)
    with pytest.raises(ProjectConfigurationError, match="^项目配置超过大小限制$"):
        ProjectDetector(max_config_bytes=256).detect(tmp_path)


def test_rejects_symlinked_configuration(tmp_path: Path) -> None:
    config = tmp_path / ".harness.yml"
    outside = tmp_path.parent / "outside-harness.yml"
    outside.write_text("test: [python, -m, pytest]\n", encoding="utf-8")
    try:
        config.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"当前系统无法创建符号链接：{type(error).__name__}")
    with pytest.raises(ProjectConfigurationError, match="^项目配置不得使用符号链接$"):
        ProjectDetector().detect(tmp_path)


def test_workspace_model_is_strict_and_forbids_extra_fields(tmp_path: Path) -> None:
    profile = ProjectDetector().detect(tmp_path)

    with pytest.raises(ValidationError):
        Workspace.model_validate(
            {
                "id": str(uuid4()),
                "root": str(tmp_path),
                "git_root": str(tmp_path),
                "default_branch": "main",
                "profile": profile,
                "unexpected": True,
            }
        )


def test_configuration_growth_after_open_reads_only_limit_plus_one(tmp_path: Path) -> None:
    config = tmp_path / ".harness.yml"
    config.write_text("test: [python]\n", encoding="utf-8")

    def grow(path: Path) -> None:
        with path.open("ab") as stream:
            stream.write(b"x" * 100)

    opener = ControlledFileOpener(after_open=grow)
    with pytest.raises(ProjectConfigurationError, match="^项目配置超过大小限制$"):
        ProjectDetector(max_config_bytes=16, file_opener=opener).detect(tmp_path)

    assert opener.read_sizes == [17]


def test_configuration_opener_cannot_redirect_to_replaced_file(tmp_path: Path) -> None:
    config = tmp_path / ".harness.yml"
    config.write_text("test: [python]\n", encoding="utf-8")
    outside = tmp_path / "outside.yml"
    outside.write_text("test: [outside]\n", encoding="utf-8")
    opener = ControlledFileOpener(redirect_to=outside)

    with pytest.raises(
        ProjectConfigurationError,
        match="^项目配置不得使用符号链接或替换$",
    ):
        ProjectDetector(file_opener=opener).detect(tmp_path)

    assert opener.read_sizes == []
