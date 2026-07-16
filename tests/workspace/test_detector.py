from collections.abc import Callable, Iterator
from contextlib import contextmanager
import hashlib
from io import BufferedReader
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from coding_agent_harness.workspace.detector import (
    ProjectConfigurationError,
    ProjectDetector,
)
from coding_agent_harness.workspace.files import (
    BoundedFileReader,
    UnsafeBoundedFileError,
)
from coding_agent_harness.workspace.models import (
    ProjectProfile,
    VerificationCommands,
    Workspace,
)

_FIXTURES = Path(__file__).parents[1] / "fixtures"
_SOURCE_NAMES = (".harness.yml", "package.json", "pyproject.toml")


def copy_fixture(name: str, tmp_path: Path) -> Path:
    return Path(
        shutil.copytree(
            _FIXTURES / name,
            tmp_path / name,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                "node_modules",
            ),
        )
    )


def clean_test_env() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("NODE_PATH", None)
    environment["PATH"] = os.pathsep.join(
        (str(Path(sys.executable).parent), environment.get("PATH", ""))
    )
    return environment


def expected_trust_fingerprint(root: Path, profile: ProjectProfile) -> str:
    source_digests = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        if (root / name).is_file()
        else None
        for name in _SOURCE_NAMES
    }
    manifest = {
        "schema": "verification-trust/v1",
        "sources": source_digests,
        "effective": {
            "commands": profile.commands.model_dump(mode="json"),
            "env_allowlist": list(profile.env_allowlist),
            "timeout_seconds": profile.command_timeout_seconds,
        },
    }
    encoded = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(
        b"coding-agent-harness\0verification-trust\0v1\0" + encoded
    ).hexdigest()


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


class RejectingRecordingFileOpener:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    @contextmanager
    def __call__(self, path: Path) -> Iterator[RecordingBinaryFile]:
        self.calls.append(path)
        raise AssertionError("符号链接配置不得传递给 opener")
        yield  # pragma: no cover


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

    assert profile.languages == ("python", "node")
    assert profile.commands.test == ("python", "-m", "pytest")
    assert profile.commands.lint == ("python", "-m", "ruff", "check", ".")
    assert profile.commands.typecheck == ("python", "-m", "mypy", ".")
    npm = "npm.cmd" if os.name == "nt" else "npm"
    assert profile.commands.build == (npm, "run", "build")
    assert profile.requires_trust is True
    assert profile.trust_fingerprint == expected_trust_fingerprint(tmp_path, profile)


def test_detects_all_python_fixture_commands() -> None:
    profile = ProjectDetector().detect(_FIXTURES / "python_project")

    assert profile.languages == ("python",)
    assert profile.commands.test == ("python", "-m", "pytest")
    assert profile.commands.lint == ("python", "-m", "ruff", "check", ".")
    assert profile.commands.typecheck == ("python", "-m", "mypy", ".")
    assert profile.commands.build == ("python", "-m", "build")


def test_detects_all_node_fixture_scripts() -> None:
    profile = ProjectDetector().detect(_FIXTURES / "node_project")
    npm = "npm.cmd" if os.name == "nt" else "npm"

    assert profile.languages == ("node",)
    assert profile.commands.test == (npm, "run", "test")
    assert profile.commands.lint == (npm, "run", "lint")
    assert profile.commands.typecheck == (npm, "run", "typecheck")
    assert profile.commands.build == (npm, "run", "build")


def test_custom_commands_are_argv_only_and_require_trust(tmp_path: Path) -> None:
    (tmp_path / ".harness.yml").write_text(
        "test: [python, -m, pytest, -q]\n"
        "lint: [python, -m, ruff, check, .]\n"
        "timeout: 90\n"
        "env_allowlist: [CI, TEST_MODE]\n",
        encoding="utf-8",
    )

    profile = ProjectDetector().detect(tmp_path)

    assert profile.commands.test == ("python", "-m", "pytest", "-q")
    assert profile.commands.lint == ("python", "-m", "ruff", "check", ".")
    assert profile.command_timeout_seconds == 90
    assert profile.env_allowlist == ("CI", "TEST_MODE")
    assert profile.requires_trust is True
    assert profile.trust_fingerprint == expected_trust_fingerprint(tmp_path, profile)


def test_package_script_change_invalidates_fingerprint(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text('{"scripts":{"test":"node --test"}}', encoding="utf-8")
    first = ProjectDetector().detect(tmp_path)

    package.write_text(
        '{"scripts":{"test":"node --test --watch=false"}}',
        encoding="utf-8",
    )
    second = ProjectDetector().detect(tmp_path)

    assert first.requires_trust and second.requires_trust
    assert first.commands.test == second.commands.test
    assert first.trust_fingerprint != second.trust_fingerprint


def test_pyproject_change_invalidates_fingerprint(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    first = ProjectDetector().detect(tmp_path)

    pyproject.write_text("[tool.pytest.ini_options]\naddopts = '-q'\n", encoding="utf-8")
    second = ProjectDetector().detect(tmp_path)

    assert first.requires_trust and second.requires_trust
    assert first.commands == second.commands
    assert first.trust_fingerprint != second.trust_fingerprint


def test_fingerprint_is_stable_and_binds_missing_sources_and_effective_config(
    tmp_path: Path,
) -> None:
    (tmp_path / ".harness.yml").write_text(
        "test: [python, -m, pytest]\n"
        "timeout: 45\n"
        "env_allowlist: [CI, TEST_MODE]\n",
        encoding="utf-8",
    )

    first = ProjectDetector().detect(tmp_path)
    second = ProjectDetector().detect(tmp_path)

    assert first.trust_fingerprint == second.trust_fingerprint
    assert first.trust_fingerprint == expected_trust_fingerprint(tmp_path, first)


def test_adding_raw_source_invalidates_fingerprint_without_changing_commands(
    tmp_path: Path,
) -> None:
    (tmp_path / ".harness.yml").write_text(
        "test: [python, -m, pytest]\n",
        encoding="utf-8",
    )
    first = ProjectDetector().detect(tmp_path)

    (tmp_path / "package.json").write_text('{"scripts":{}}', encoding="utf-8")
    second = ProjectDetector().detect(tmp_path)

    assert first.commands == second.commands
    assert first.command_timeout_seconds == second.command_timeout_seconds
    assert first.env_allowlist == second.env_allowlist
    assert first.trust_fingerprint != second.trust_fingerprint


def test_profile_without_verification_commands_does_not_require_trust(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{}}', encoding="utf-8")
    (tmp_path / ".harness.yml").write_text("timeout: 45\n", encoding="utf-8")

    profile = ProjectDetector().detect(tmp_path)

    assert profile.commands == VerificationCommands()
    assert profile.requires_trust is False
    assert profile.trust_fingerprint is None


@pytest.mark.parametrize(
    ("commands", "requires_trust", "trust_fingerprint"),
    [
        (VerificationCommands(test=("python", "-m", "pytest")), False, None),
        (VerificationCommands(test=("python", "-m", "pytest")), True, None),
        (VerificationCommands(), True, "0" * 64),
        (VerificationCommands(), False, "0" * 64),
    ],
)
def test_profile_rejects_inconsistent_trust_state(
    commands: VerificationCommands,
    requires_trust: bool,
    trust_fingerprint: str | None,
) -> None:
    with pytest.raises(ValidationError):
        ProjectProfile(
            languages=(),
            commands=commands,
            requires_trust=requires_trust,
            trust_fingerprint=trust_fingerprint,
        )


def test_python_fixture_detected_test_really_runs(tmp_path: Path) -> None:
    root = copy_fixture("python_project", tmp_path)
    command = ProjectDetector().detect(root).commands.test

    assert command is not None
    result = subprocess.run(
        command,
        executable=sys.executable,
        cwd=root,
        env=clean_test_env(),
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_node_fixture_detected_commands_really_run(tmp_path: Path) -> None:
    root = copy_fixture("node_project", tmp_path)
    commands = ProjectDetector().detect(root).commands

    for name in ("test", "lint", "typecheck", "build"):
        command = getattr(commands, name)
        assert command is not None
        result = subprocess.run(
            command,
            cwd=root,
            env=clean_test_env(),
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"{name}: {result.stdout.decode(errors='replace')}\n"
            f"{result.stderr.decode(errors='replace')}"
        )


def test_trusted_profile_sequences_are_deeply_immutable_and_json_stays_arrays(
    tmp_path: Path,
) -> None:
    (tmp_path / ".harness.yml").write_text(
        "test: [python, -m, pytest]\n"
        "env_allowlist: [CI]\n",
        encoding="utf-8",
    )
    profile = ProjectDetector().detect(tmp_path)
    fingerprint = profile.trust_fingerprint

    assert not hasattr(profile.languages, "append")
    assert profile.commands.test is not None
    assert not hasattr(profile.commands.test, "append")
    assert not hasattr(profile.env_allowlist, "append")
    with pytest.raises(TypeError):
        profile.commands.test[0] = "untrusted"  # type: ignore[index]
    assert profile.trust_fingerprint == fingerprint
    dumped = profile.model_dump(mode="json")
    assert dumped["languages"] == []
    assert dumped["commands"]["test"] == ["python", "-m", "pytest"]
    assert dumped["env_allowlist"] == ["CI"]


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


@pytest.mark.parametrize(
    ("source_name", "content"),
    [
        (".harness.yml", "test: [python, -m, pytest]\n"),
        ("package.json", '{"scripts":{"test":"node --test"}}'),
        ("pyproject.toml", "[tool.pytest.ini_options]\n"),
    ],
)
@pytest.mark.parametrize("path_kind", ["symlink", "reparse"])
def test_rejects_each_link_configuration_before_follow_probe_or_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_name: str,
    content: str,
    path_kind: str,
) -> None:
    source = tmp_path / source_name
    source.write_text(content, encoding="utf-8")
    original_lstat = Path.lstat
    original_exists = Path.exists
    original_stat = Path.stat

    def classify_source_without_following(path: Path) -> os.stat_result:
        result = original_lstat(path)
        if path == source:
            if path_kind == "symlink":
                return os.stat_result((stat.S_IFLNK | 0o777, *result[1:]))
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600,
                st_file_attributes=0x400,
            )  # type: ignore[return-value]
        return result

    def reject_following_exists(path: Path) -> bool:
        if path == source:
            raise AssertionError("不得对符号链接配置执行 follow-target exists")
        return original_exists(path)

    def reject_following_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if path == source and follow_symlinks:
            raise AssertionError("不得对符号链接配置执行 follow-target stat")
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "lstat", classify_source_without_following)
    monkeypatch.setattr(Path, "exists", reject_following_exists)
    monkeypatch.setattr(Path, "stat", reject_following_stat)
    opener = RejectingRecordingFileOpener()

    with pytest.raises(ProjectConfigurationError, match="^项目配置不得使用符号链接$"):
        ProjectDetector(file_opener=opener).detect(tmp_path)

    assert opener.calls == []


@pytest.mark.skipif(os.name != "posix", reason="真实 FIFO no-follow 回归只适用于 POSIX")
@pytest.mark.parametrize("source_name", _SOURCE_NAMES)
@pytest.mark.parametrize("outside_kind", ["regular", "fifo"])
def test_real_outside_symlink_is_rejected_without_blocking(
    tmp_path: Path,
    source_name: str,
    outside_kind: str,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside = tmp_path / f"outside-{source_name.lstrip('.')}"
    if outside_kind == "fifo":
        os.mkfifo(outside)
    else:
        outside.write_text("{}\n", encoding="utf-8")
    (project_root / source_name).symlink_to(outside)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path.cwd() / "src")
    script = (
        "from pathlib import Path\n"
        "from coding_agent_harness.workspace.detector import "
        "ProjectConfigurationError, ProjectDetector\n"
        "try:\n"
        "    ProjectDetector().detect(Path(__import__('sys').argv[1]))\n"
        "except ProjectConfigurationError as error:\n"
        "    raise SystemExit(0 if str(error) == '项目配置不得使用符号链接' else 2)\n"
        "raise SystemExit(3)\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script, str(project_root)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )

    assert completed.returncode == 0, (completed.stdout, completed.stderr)


def test_default_opener_rejects_reparse_before_platform_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "config"
    source.write_bytes(b"safe")
    original_lstat = Path.lstat
    open_calls: list[Path] = []

    def classify_reparse_without_following(path: Path) -> os.stat_result:
        if path == source:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600,
                st_file_attributes=0x400,
            )  # type: ignore[return-value]
        return original_lstat(path)

    def reject_platform_open(path: Path, *args: object, **kwargs: object) -> None:
        open_calls.append(path)
        raise AssertionError("reparse point 不得传递给平台 open")

    monkeypatch.setattr(Path, "lstat", classify_reparse_without_following)
    monkeypatch.setattr(Path, "open", reject_platform_open)

    with pytest.raises(UnsafeBoundedFileError, match="^文件路径不是普通文件$"):
        BoundedFileReader().read(source, 16)

    assert open_calls == []


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
