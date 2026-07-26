from pathlib import Path

import pytest

from coding_agent_harness.domain.actions import TaskState, ToolAction
from coding_agent_harness.governance.paths import PathGuard
from coding_agent_harness.governance.policy import PolicyContext, PolicyEngine
from coding_agent_harness.governance.redaction import Redactor
from coding_agent_harness.tools.models import (
    ToolContext,
    ToolResult,
    VerificationApproval,
)
from coding_agent_harness.tools.registry import ToolRegistry
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.models import ProjectProfile, RepositoryMap
from coding_agent_harness.workspace.processes import (
    CommandResult,
    ProcessRequest,
    ProcessRunner,
)


class FailingRunner:
    def __init__(self) -> None:
        self.calls: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.calls.append(request)
        raise AssertionError("拒绝的验证不得执行 runner")


class SuccessfulRunner:
    def __init__(self) -> None:
        self.calls: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.calls.append(request)
        return CommandResult(returncode=0, stdout=b"1 passed\n", stderr=b"")


class MutatingSuccessfulRunner:
    def __init__(self, root: Path, mutation: str) -> None:
        self._root = root
        self._mutation = mutation
        self.calls: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.calls.append(request)
        if self._mutation == "tracked":
            (self._root / "src.py").write_text("VALUE = 2\n", encoding="utf-8")
        elif self._mutation == "untracked":
            (self._root / "external.py").write_text("external\n", encoding="utf-8")
        else:
            (self._root / ".harness.yml").write_text(
                "test:\n  - python\n  - -m\n  - pytest\n", encoding="utf-8"
            )
        return CommandResult(returncode=0, stdout=b"1 passed\n", stderr=b"")


def approved_context(
    tmp_path: Path,
    profile: ProjectProfile,
    runner: ProcessRunner,
    *,
    tracked_files: tuple[str, ...] = ("pyproject.toml",),
) -> ToolContext:
    return ToolContext(
        workspace_root=tmp_path,
        repository_map=RepositoryMap(
            root=tmp_path,
            tracked_files=tracked_files,
            documents=(),
            test_paths=(),
            recent_commits=(),
            dirty_paths=(),
        ),
        profile=profile,
        runner=runner,
        policy=PolicyEngine(PathGuard(tmp_path), Redactor()),
        policy_context=PolicyContext(
            workspace_root=tmp_path,
            task_state=TaskState.EXECUTING,
            event_sequence=1,
            config_version="verification-v1",
            llm_api_authorized=True,
        ),
        verification_config_version="verification-v1",
        verification_approval=VerificationApproval(
            approval_id="approved-test",
            config_version="verification-v1",
            trust_fingerprint=profile.trust_fingerprint,
        ),
    )


def verification_action(key: str = "v") -> ToolAction:
    return ToolAction.model_validate(
        {
            "kind": "tool",
            "tool": "run_verification",
            "arguments": {"name": "test"},
            "idempotency_key": key,
        }
    )


def assert_failure_observation(result: ToolResult, code: str) -> None:
    assert result.observation is not None
    assert result.observation.kind == "failure"
    assert result.observation.code == code
    assert result.observation.diagnostic


async def test_verification_refuses_stale_profile_without_running(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\nrequires=[]\nbuild-backend='x'\n", encoding="utf-8"
    )
    profile = ProjectDetector().detect(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='changed'\n", encoding="utf-8")
    runner = FailingRunner()

    result = await ToolRegistry(approved_context(tmp_path, profile, runner)).execute(
        verification_action()
    )

    assert result.code == "STALE_CONFIG"
    assert runner.calls == []
    assert_failure_observation(result, "STALE_CONFIG")


async def test_verification_requires_explicit_approved_fingerprint(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\nrequires=[]\nbuild-backend='x'\n", encoding="utf-8"
    )
    profile = ProjectDetector().detect(tmp_path)
    runner = FailingRunner()
    approved = approved_context(tmp_path, profile, runner)
    context = ToolContext(
        workspace_root=approved.workspace_root,
        repository_map=approved.repository_map,
        profile=approved.profile,
        runner=approved.runner,
        policy=approved.policy,
        policy_context=approved.policy_context,
        verification_config_version=approved.verification_config_version,
    )

    result = await ToolRegistry(context).execute(verification_action("missing-approval"))

    assert result.code == "VERIFICATION_APPROVAL_REQUIRED"
    assert runner.calls == []
    assert_failure_observation(result, "VERIFICATION_APPROVAL_REQUIRED")


async def test_verification_rejects_mismatched_approved_fingerprint(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\nrequires=[]\nbuild-backend='x'\n", encoding="utf-8"
    )
    profile = ProjectDetector().detect(tmp_path)
    runner = FailingRunner()
    approved = approved_context(tmp_path, profile, runner)
    context = ToolContext(
        workspace_root=approved.workspace_root,
        repository_map=approved.repository_map,
        profile=approved.profile,
        runner=approved.runner,
        policy=approved.policy,
        policy_context=approved.policy_context,
        verification_config_version=approved.verification_config_version,
        verification_approval=approved.verification_approval.model_copy(
            update={"trust_fingerprint": "0" * 64}
        ),
    )

    result = await ToolRegistry(context).execute(verification_action("wrong-fingerprint"))

    assert result.code == "VERIFICATION_APPROVAL_STALE"
    assert runner.calls == []
    assert_failure_observation(result, "VERIFICATION_APPROVAL_STALE")


async def test_verification_routes_actual_argv_through_policy(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\nrequires=[]\nbuild-backend='x'\n", encoding="utf-8"
    )
    (tmp_path / ".harness.yml").write_text(
        "test:\n  - curl\n  - https://example.test\n", encoding="utf-8"
    )
    profile = ProjectDetector().detect(tmp_path)
    runner = FailingRunner()

    result = await ToolRegistry(
        approved_context(
            tmp_path,
            profile,
            runner,
            tracked_files=("pyproject.toml", ".harness.yml"),
        )
    ).execute(verification_action("policy-blocked"))

    assert result.code == "VERIFICATION_POLICY_BLOCKED"
    assert runner.calls == []
    assert_failure_observation(result, "VERIFICATION_POLICY_BLOCKED")


async def test_current_verification_snapshot_tracks_dynamic_file_state(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='snapshot'\n", encoding="utf-8"
    )
    (tmp_path / "src.py").write_text("VALUE = 1\n", encoding="utf-8")
    profile = ProjectDetector().detect(tmp_path)
    registry = ToolRegistry(
        approved_context(
            tmp_path,
            profile,
            FailingRunner(),
            tracked_files=("pyproject.toml", "src.py"),
        )
    )

    original = await registry.current_verification_evidence()
    (tmp_path / "src.py").write_text("VALUE = 2\n", encoding="utf-8")
    modified = await registry.current_verification_evidence()
    (tmp_path / "external.py").write_text("untracked\n", encoding="utf-8")
    untracked = await registry.current_verification_evidence()
    (tmp_path / "src.py").replace(tmp_path / "renamed.py")
    missing = await registry.current_verification_evidence()

    assert original is not None
    assert modified is not None
    assert untracked is not None
    assert original.worktree_fingerprint != modified.worktree_fingerprint
    assert modified.worktree_fingerprint != untracked.worktree_fingerprint
    assert missing is None


@pytest.mark.parametrize("mutation", ["tracked", "untracked", "config"])
async def test_verification_never_signs_snapshot_changed_while_runner_executes(
    tmp_path: Path, mutation: str
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\nrequires=[]\nbuild-backend='x'\n", encoding="utf-8"
    )
    (tmp_path / "src.py").write_text("VALUE = 1\n", encoding="utf-8")
    profile = ProjectDetector().detect(tmp_path)
    runner = MutatingSuccessfulRunner(tmp_path, mutation)
    registry = ToolRegistry(
        approved_context(
            tmp_path,
            profile,
            runner,
            tracked_files=("pyproject.toml", "src.py"),
        )
    )

    result = await registry.execute(verification_action(f"during-{mutation}"))

    assert result.ok is False
    assert result.code == "WORKTREE_CHANGED_DURING_VERIFICATION"
    assert result.retryable is True
    assert result.verification is None
    assert len(runner.calls) == 1
    assert_failure_observation(result, "WORKTREE_CHANGED_DURING_VERIFICATION")


async def test_current_verification_snapshot_rejects_too_many_empty_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='directory-budget'\n", encoding="utf-8"
    )
    profile = ProjectDetector().detect(tmp_path)
    for index in range(10_001):
        (tmp_path / f"empty-{index}").mkdir()
    registry = ToolRegistry(
        approved_context(
            tmp_path,
            profile,
            FailingRunner(),
            tracked_files=("pyproject.toml",),
        )
    )

    assert await registry.current_verification_evidence() is None


async def test_current_verification_snapshot_rejects_excessive_directory_depth(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='depth-budget'\n", encoding="utf-8"
    )
    profile = ProjectDetector().detect(tmp_path)
    nested = tmp_path
    for index in range(65):
        nested = nested / "d"
        nested.mkdir()
    registry = ToolRegistry(
        approved_context(
            tmp_path,
            profile,
            FailingRunner(),
            tracked_files=("pyproject.toml",),
        )
    )

    assert await registry.current_verification_evidence() is None


@pytest.mark.parametrize(
    ("argv", "allowed"),
    [
        (("curl", "https://example.test"), False),
        (("pip", "install", "package"), False),
        (("git", "push", "origin", "main"), False),
        (("powershell", "-Command", "Get-ChildItem"), False),
        (("python", "-m", "pytest"), True),
    ],
)
async def test_verification_policy_allows_only_safe_approved_command(
    tmp_path: Path, argv: tuple[str, ...], allowed: bool
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[build-system]\nrequires=[]\nbuild-backend='x'\n", encoding="utf-8"
    )
    (tmp_path / ".harness.yml").write_text(
        "test:\n" + "".join(f"  - {item}\n" for item in argv), encoding="utf-8"
    )
    profile = ProjectDetector().detect(tmp_path)
    runner = SuccessfulRunner()

    result = await ToolRegistry(
        approved_context(
            tmp_path,
            profile,
            runner,
            tracked_files=("pyproject.toml", ".harness.yml"),
        )
    ).execute(verification_action("command-policy"))

    assert result.ok is allowed
    assert len(runner.calls) == (1 if allowed else 0)
    if allowed:
        assert result.verification is not None
    else:
        assert result.code == "VERIFICATION_POLICY_BLOCKED"
