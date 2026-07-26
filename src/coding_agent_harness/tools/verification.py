from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import stat

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.governance.policy import (
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
)
from coding_agent_harness.tools.models import VerificationApproval, VerificationEvidence
from coding_agent_harness.workspace.detector import ProjectDetector, ProjectDetectionError
from coding_agent_harness.workspace.files import (
    BoundedFileReadError,
    BoundedFileReader,
    BoundedFileTooLargeError,
    UnsafeBoundedFileError,
    is_symlink_or_reparse,
)
from coding_agent_harness.workspace.models import ProjectProfile, RepositoryMap
from coding_agent_harness.workspace.processes import ProcessRequest, ProcessRunner, SubprocessGitRunner


_MAX_SNAPSHOT_FILE_BYTES = 1024 * 1024
_MAX_SNAPSHOT_TOTAL_BYTES = 32 * 1024 * 1024
_MAX_SNAPSHOT_FILES = 10_000
_MAX_SNAPSHOT_DIRECTORIES = 10_000
_MAX_SNAPSHOT_ENTRIES = 10_000
_MAX_SNAPSHOT_DEPTH = 64
_CHECK_NAMES = ("test", "lint", "typecheck", "build")


@dataclass(frozen=True)
class VerificationExecution:
    code: str
    output: str
    evidence: VerificationEvidence | None = None


def run_verification(
    root: Path,
    profile: ProjectProfile,
    name: str,
    runner: ProcessRunner | None,
    *,
    repository_map: RepositoryMap | None,
    approval: VerificationApproval | None,
    config_version: str | None,
    policy: PolicyEngine | None,
    policy_context: PolicyContext | None,
    state_root: Path | None = None,
) -> VerificationExecution:
    """仅运行已批准、重新检测且被策略允许的精确 argv。"""
    code, current, snapshot = _current_context(
        root,
        profile,
        repository_map,
        approval,
        config_version,
        state_root,
    )
    if code != "OK" or current is None or snapshot is None:
        return VerificationExecution(code, "")
    assert approval is not None
    argv = getattr(current.commands, name, None)
    if argv is None:
        return VerificationExecution("UNAVAILABLE_VERIFICATION", "")
    if policy is None or policy_context is None or not _policy_root_matches(policy_context, root):
        return VerificationExecution("VERIFICATION_POLICY_REQUIRED", "")
    action = ToolAction(
        tool="shell",
        arguments={"argv": list(argv)},
        idempotency_key=f"verification:{approval.approval_id}:{name}",
    )
    decision = policy.evaluate(action, policy_context)
    if decision.decision is not PolicyDecision.ALLOW:
        return VerificationExecution("VERIFICATION_POLICY_BLOCKED", "")
    allowed_env = {key: os.environ[key] for key in current.env_allowlist if key in os.environ}
    result = (runner or SubprocessGitRunner()).run(
        ProcessRequest(argv=argv, cwd=root, env=allowed_env)
    )
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode != 0:
        return VerificationExecution("VERIFICATION_FAILED", output)
    code, current, snapshot = _current_context(
        root,
        profile,
        repository_map,
        approval,
        config_version,
        state_root,
    )
    if code != "OK" or current is None or snapshot is None:
        return VerificationExecution(code, output)
    assert config_version is not None
    assert current.trust_fingerprint is not None
    return VerificationExecution(
        "OK",
        output,
        VerificationEvidence(
            name=name,
            config_version=config_version,
            trust_fingerprint=current.trust_fingerprint,
            worktree_fingerprint=snapshot,
            required_checks=_required_checks(current),
        ),
    )


def current_verification_evidence(
    root: Path,
    profile: ProjectProfile,
    repository_map: RepositoryMap | None,
    approval: VerificationApproval | None,
    config_version: str | None,
    state_root: Path | None = None,
) -> VerificationEvidence | None:
    code, current, snapshot = _current_context(
        root,
        profile,
        repository_map,
        approval,
        config_version,
        state_root,
    )
    if code != "OK" or current is None or snapshot is None:
        return None
    assert config_version is not None
    assert current.trust_fingerprint is not None
    return VerificationEvidence(
        name="current",
        config_version=config_version,
        trust_fingerprint=current.trust_fingerprint,
        worktree_fingerprint=snapshot,
        required_checks=_required_checks(current),
    )


def _current_context(
    root: Path,
    profile: ProjectProfile,
    repository_map: RepositoryMap | None,
    approval: VerificationApproval | None,
    config_version: str | None,
    state_root: Path | None,
) -> tuple[str, ProjectProfile | None, str | None]:
    try:
        current = ProjectDetector().detect(root)
    except ProjectDetectionError:
        return "STALE_CONFIG", None, None
    if current.trust_fingerprint != profile.trust_fingerprint:
        return "STALE_CONFIG", None, None
    if approval is None or config_version is None:
        return "VERIFICATION_APPROVAL_REQUIRED", None, None
    if (
        approval.config_version != config_version
        or approval.trust_fingerprint != current.trust_fingerprint
    ):
        return "VERIFICATION_APPROVAL_STALE", None, None
    snapshot = _worktree_fingerprint(root, repository_map, state_root)
    if snapshot is None:
        return "WORKTREE_SNAPSHOT_UNAVAILABLE", None, None
    return "OK", current, snapshot


def _required_checks(profile: ProjectProfile) -> tuple[str, ...]:
    return tuple(name for name in _CHECK_NAMES if getattr(profile.commands, name) is not None)


def _policy_root_matches(context: PolicyContext, root: Path) -> bool:
    try:
        return context.workspace_root.resolve(strict=False) == root.resolve(strict=False)
    except OSError:
        return False


def _worktree_fingerprint(
    root: Path,
    repository_map: RepositoryMap | None,
    state_root: Path | None,
) -> str | None:
    if repository_map is None:
        return None
    try:
        guard = PathGuard(root)
        if repository_map.root.resolve(strict=False) != guard.root:
            return None
        if state_root is not None and state_root.resolve(strict=False).is_relative_to(guard.root):
            return None
    except (OSError, PathEscapeError):
        return None
    reader = BoundedFileReader()
    total = 0
    records: list[dict[str, str]] = []
    tracked = set(repository_map.tracked_files)
    observed: set[str] = set()
    pending: list[tuple[Path, int]] = [(guard.root, 0)]
    directory_count = 0
    entry_count = 0
    while pending:
        directory, depth = pending.pop()
        directory_count += 1
        if directory_count > _MAX_SNAPSHOT_DIRECTORIES or depth > _MAX_SNAPSHOT_DEPTH:
            return None
        try:
            children = sorted(directory.iterdir(), key=lambda candidate: candidate.name)
        except OSError:
            return None
        for candidate in children:
            if candidate.name == ".git":
                continue
            entry_count += 1
            if entry_count > _MAX_SNAPSHOT_ENTRIES:
                return None
            try:
                metadata = candidate.lstat()
            except OSError:
                return None
            if is_symlink_or_reparse(metadata):
                return None
            if stat.S_ISDIR(metadata.st_mode):
                pending.append((candidate, depth + 1))
                continue
            if not stat.S_ISREG(metadata.st_mode):
                return None
            try:
                relative = candidate.relative_to(guard.root).as_posix()
                raw = reader.read(candidate, _MAX_SNAPSHOT_FILE_BYTES)
            except (
                OSError,
                BoundedFileReadError,
                BoundedFileTooLargeError,
                UnsafeBoundedFileError,
            ):
                return None
            total += len(raw)
            if total > _MAX_SNAPSHOT_TOTAL_BYTES:
                return None
            observed.add(relative)
            records.append(
                {
                    "path": relative,
                    "kind": "tracked" if relative in tracked else "untracked",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
            if len(records) > _MAX_SNAPSHOT_FILES:
                return None
    if not tracked.issubset(observed):
        return None
    records.sort(key=lambda record: record["path"])
    manifest = {
        "schema": "worktree-snapshot/v1",
        "files": records,
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _unfollowed_path(guard: PathGuard, relative: str) -> Path | None:
    raw = Path(relative)
    if not raw.parts or raw.is_absolute() or any(part in {".", ".."} for part in raw.parts):
        return None
    candidate = guard.root
    for index, part in enumerate(raw.parts):
        candidate = candidate / part
        try:
            metadata = candidate.lstat()
        except OSError:
            return None
        if is_symlink_or_reparse(metadata):
            return None
        if index < len(raw.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            return None
    if not stat.S_ISREG(metadata.st_mode):
        return None
    try:
        return guard.resolve(relative)
    except PathEscapeError:
        return None
