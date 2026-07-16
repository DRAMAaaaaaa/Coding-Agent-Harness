from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from coding_agent_harness.workspace.git import SafeGit, UnsupportedGitFilterError
from coding_agent_harness.workspace.detector import ProjectDetector
from coding_agent_harness.workspace.models import Workspace
from coding_agent_harness.workspace.processes import CommandResult, ProcessRequest
from coding_agent_harness.workspace.scanner import WorkspaceScanner
from coding_agent_harness.workspace.worktrees import WorktreeManager


def _git(root: Path, *args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        input=input,
        check=True,
        capture_output=True,
    ).stdout


def _install_sentinel(root: Path, name: str) -> tuple[Path, Path]:
    marker = root.parent / f"{name}-invoked"
    script = root.parent / f"{name}-sentinel.sh"
    marker_for_shell = marker.as_posix().replace("'", "'\\''")
    script.write_text(
        "#!/bin/sh\n"
        f"printf invoked > '{marker_for_shell}'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    return script, marker


def _install_fake_signed_head(root: Path) -> None:
    tree = _git(root, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    parent = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    commit = (
        f"tree {tree}\n"
        f"parent {parent}\n"
        "author Harness Tests <harness@example.invalid> 1700000000 +0000\n"
        "committer Harness Tests <harness@example.invalid> 1700000000 +0000\n"
        "gpgsig -----BEGIN PGP SIGNATURE-----\n"
        " fake-signature\n"
        " -----END PGP SIGNATURE-----\n"
        "\n"
        "sentinel signed commit\n"
    ).encode("ascii")
    oid = _git(root, "hash-object", "-t", "commit", "-w", "--stdin", input=commit)
    _git(root, "update-ref", "HEAD", oid.strip())


class RecordingProcessRunner:
    def __init__(self) -> None:
        self.requests: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.requests.append(request)
        return CommandResult(0, b"", b"")


class RecordingDelegateRunner:
    def __init__(self) -> None:
        from coding_agent_harness.workspace.processes import SubprocessGitRunner

        self._delegate = SubprocessGitRunner()
        self.requests: list[ProcessRequest] = []

    def run(self, request: ProcessRequest) -> CommandResult:
        self.requests.append(request)
        return self._delegate.run(request)


def _request_command(request: ProcessRequest) -> list[str]:
    argv = list(request.argv)
    return argv[argv.index("-C") + 2 :]


def test_safe_git_uses_absolute_executable_empty_fsmonitor_and_clean_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dangerous = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "alias.status",
        "GIT_CONFIG_VALUE_0": "!malicious",
        "GIT_DIR": "outside.git",
        "GIT_WORK_TREE": "outside",
        "GIT_INDEX_FILE": "outside.index",
        "GIT_OBJECT_DIRECTORY": "objects",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": "alternates",
        "GIT_EXTERNAL_DIFF": "malicious-diff",
        "GIT_DIFF_OPTS": "--unsafe",
        "GIT_SSH": "malicious-ssh",
        "GIT_SSH_COMMAND": "malicious-ssh-command",
        "GIT_ASKPASS": "malicious-askpass",
        "SSH_ASKPASS": "malicious-ssh-askpass",
        "GIT_EXEC_PATH": "malicious-exec-path",
    }
    for key, value in dangerous.items():
        monkeypatch.setenv(key, value)
    runner = RecordingProcessRunner()
    git_executable = Path(sys.executable).resolve()
    safe_git = SafeGit(
        tmp_path / "state",
        git_executable=git_executable,
        runner=runner,
    )

    safe_git.run(tmp_path, ["status", "--porcelain=v1"])

    request = runner.requests[0]
    assert Path(request.argv[0]).is_absolute()
    assert Path(request.argv[0]) == git_executable
    assert "core.fsmonitor=" in request.argv
    assert "core.fsmonitor=false" not in request.argv
    assert request.env is not None
    assert request.env["GIT_ALLOW_PROTOCOL"] == ":"
    assert request.env["GIT_PROTOCOL_FROM_USER"] == "0"
    assert request.env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert request.env["GIT_ATTR_NOSYSTEM"] == "1"
    assert all(key not in request.env for key in dangerous)
    safety = tmp_path / "state" / "git-safety"
    assert (safety / "hooks").is_dir()
    assert list((safety / "hooks").iterdir()) == []
    assert (safety / "global.gitconfig").read_bytes() == b""
    assert (safety / "global.gitattributes").read_bytes() == b""


def test_scanner_does_not_execute_fsmonitor_or_gpg(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
) -> None:
    root = git_repository_factory("git-safety-scanner", {"README.md": "safe\n"})
    fsmonitor, fsmonitor_marker = _install_sentinel(root, "fsmonitor")
    gpg, gpg_marker = _install_sentinel(root, "gpg")
    _install_fake_signed_head(root)
    _git(root, "config", "core.fsmonitor", fsmonitor.as_posix())
    _git(root, "config", "log.showSignature", "true")
    _git(root, "config", "gpg.program", gpg.as_posix())

    WorkspaceScanner().scan(root)

    assert not fsmonitor_marker.exists()
    assert not gpg_marker.exists()


def test_filter_gate_rejects_attributes_without_executing_filter(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory(
        "git-filter-gate",
        {".gitattributes": "*.dat filter=evil\n", "payload.dat": "safe\n"},
    )
    clean, clean_marker = _install_sentinel(root, "clean")
    smudge, smudge_marker = _install_sentinel(root, "smudge")
    process, process_marker = _install_sentinel(root, "process")
    _git(root, "config", "filter.evil.clean", clean.as_posix())
    _git(root, "config", "filter.evil.smudge", smudge.as_posix())
    _git(root, "config", "filter.evil.process", process.as_posix())
    safe_git = SafeGit(tmp_path / "state")
    tracked = safe_git.run(root, ["ls-tree", "-r", "--name-only", "-z", "HEAD"])

    try:
        with pytest.raises(UnsupportedGitFilterError):
            safe_git.assert_filter_free(root, "HEAD", tracked.stdout)
    except AttributeError:
        pytest.fail("SafeGit 尚未提供 filter gate")

    assert not clean_marker.exists()
    assert not smudge_marker.exists()
    assert not process_marker.exists()


def test_scanner_rejects_filter_before_status_can_run_clean_filter(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
) -> None:
    root = git_repository_factory(
        "git-filter-scanner",
        {".gitattributes": "*.dat filter=evil\n", "payload.dat": "safe\n"},
    )
    clean, clean_marker = _install_sentinel(root, "scanner-clean")
    _git(root, "config", "filter.evil.clean", clean.as_posix())
    (root / "payload.dat").write_text("changed\n", encoding="utf-8")

    with pytest.raises(UnsupportedGitFilterError):
        WorkspaceScanner().scan(root)

    assert not clean_marker.exists()


def test_worktree_rejects_filter_before_marker_branch_target_hook_or_filter(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory(
        "git-filter-worktree",
        {".gitattributes": "*.dat filter=evil\n", "payload.dat": "safe\n"},
    )
    smudge, smudge_marker = _install_sentinel(root, "worktree-smudge")
    process, process_marker = _install_sentinel(root, "worktree-process")
    hooks = tmp_path / "malicious-hooks"
    hooks.mkdir()
    hook_marker = tmp_path / "post-checkout-invoked"
    hook = hooks / "post-checkout"
    hook.write_text(
        "#!/bin/sh\n"
        f"printf invoked > '{hook_marker.as_posix()}'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    _git(root, "config", "core.hooksPath", hooks.as_posix())
    _git(root, "config", "filter.evil.smudge", smudge.as_posix())
    _git(root, "config", "filter.evil.process", process.as_posix())
    workspace = Workspace(
        id=uuid4(),
        root=root.resolve(),
        git_root=root.resolve(),
        default_branch="main",
        profile=ProjectDetector().detect(root),
    )
    state_root = tmp_path / "state"
    task_id = uuid4()
    manager = WorktreeManager(workspace, state_root)

    with pytest.raises(UnsupportedGitFilterError):
        manager.create(task_id, "HEAD")

    branch = f"harness/task-{task_id.hex[:8]}"
    assert subprocess.run(
        ["git", "-C", str(root), "show-ref", "--verify", f"refs/heads/{branch}"],
        check=False,
        capture_output=True,
    ).returncode != 0
    target = state_root / "worktrees" / str(workspace.id) / str(task_id)
    marker = target.parent / ".active"
    assert not target.exists()
    assert not marker.exists()
    assert not hook_marker.exists()
    assert not smudge_marker.exists()
    assert not process_marker.exists()


@pytest.mark.parametrize("attribute_state", ["working-tree", "index"])
def test_release_rechecks_filter_and_preserves_worktree_and_marker(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
    attribute_state: str,
) -> None:
    root = git_repository_factory(
        f"git-filter-release-{attribute_state}",
        {".gitattributes": "*.dat -filter\n", "payload.dat": "safe\n"},
    )
    smudge, smudge_marker = _install_sentinel(root, f"release-{attribute_state}")
    _git(root, "config", "filter.evil.smudge", smudge.as_posix())
    workspace = Workspace(
        id=uuid4(),
        root=root.resolve(),
        git_root=root.resolve(),
        default_branch="main",
        profile=ProjectDetector().detect(root),
    )
    state_root = tmp_path / f"state-{attribute_state}"
    task_id = uuid4()
    manager = WorktreeManager(workspace, state_root)
    info = manager.create(task_id, "HEAD")
    attributes = info.path / ".gitattributes"
    attributes.write_text("*.dat filter=evil\n", encoding="utf-8")
    if attribute_state == "index":
        _git(info.path, "add", ".gitattributes")

    with pytest.raises(UnsupportedGitFilterError):
        manager.release(task_id)

    marker = info.path.parent / ".active"
    assert info.path.is_dir()
    assert marker.read_text(encoding="ascii") == str(task_id)
    assert not smudge_marker.exists()

    attributes.write_text("*.dat -filter\n", encoding="utf-8")
    if attribute_state == "index":
        _git(info.path, "reset", "--hard", "HEAD")
    manager.release(task_id)


def test_safe_materialize_and_release_never_run_hooks_or_inactive_filters(
    git_repository_factory: Callable[[str, Mapping[str, str]], Path],
    tmp_path: Path,
) -> None:
    root = git_repository_factory(
        "git-safe-materialize",
        {".gitattributes": "*.dat -filter\n", "payload.dat": "safe\n"},
    )
    sentinels = {
        name: _install_sentinel(root, f"materialize-{name}")
        for name in ("clean", "smudge", "process")
    }
    hooks = tmp_path / "materialize-hooks"
    hooks.mkdir()
    hook_marker = tmp_path / "materialize-hook-invoked"
    (hooks / "post-checkout").write_text(
        "#!/bin/sh\n"
        f"printf invoked > '{hook_marker.as_posix()}'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    _git(root, "config", "core.hooksPath", hooks.as_posix())
    for name, (script, _) in sentinels.items():
        _git(root, "config", f"filter.evil.{name}", script.as_posix())
    workspace = Workspace(
        id=uuid4(),
        root=root.resolve(),
        git_root=root.resolve(),
        default_branch="main",
        profile=ProjectDetector().detect(root),
    )
    runner = RecordingDelegateRunner()
    manager = WorktreeManager(workspace, tmp_path / "state-materialize", runner=runner)
    task_id = uuid4()

    info = manager.create(task_id, "HEAD")
    assert (info.path / "payload.dat").read_text(encoding="utf-8") == "safe\n"
    manager.release(task_id)

    commands = [_request_command(request) for request in runner.requests]
    add = next(command for command in commands if command[:2] == ["worktree", "add"])
    assert "--no-checkout" in add
    assert ["checkout-index", "--all"] in commands
    remove_index = next(
        index
        for index, command in enumerate(commands)
        if command[:2] == ["worktree", "remove"]
    )
    filter_indexes = [
        index
        for index, command in enumerate(commands)
        if command[:1] == ["check-attr"]
    ]
    assert len(filter_indexes) >= 5
    assert max(filter_indexes) < remove_index
    assert not hook_marker.exists()
    assert all(not marker.exists() for _, marker in sentinels.values())
