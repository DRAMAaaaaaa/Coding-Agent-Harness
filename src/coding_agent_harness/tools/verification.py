from __future__ import annotations

import os
from pathlib import Path

from coding_agent_harness.workspace.detector import ProjectDetector, ProjectDetectionError
from coding_agent_harness.workspace.models import ProjectProfile
from coding_agent_harness.workspace.processes import ProcessRequest, ProcessRunner, SubprocessGitRunner


def run_verification(
    root: Path, profile: ProjectProfile, name: str, runner: ProcessRunner | None
) -> tuple[str, str]:
    """仅运行经重新检测确认的精确批准 argv。"""
    try:
        current = ProjectDetector().detect(root)
    except ProjectDetectionError:
        return "STALE_CONFIG", ""
    if current.trust_fingerprint != profile.trust_fingerprint:
        return "STALE_CONFIG", ""
    argv = getattr(profile.commands, name, None)
    if argv is None:
        return "UNAVAILABLE_VERIFICATION", ""
    allowed_env = {key: os.environ[key] for key in profile.env_allowlist if key in os.environ}
    result = (runner or SubprocessGitRunner()).run(
        ProcessRequest(argv=argv, cwd=root, env=allowed_env)
    )
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    return ("OK" if result.returncode == 0 else "VERIFICATION_FAILED"), output
