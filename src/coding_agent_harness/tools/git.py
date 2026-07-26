from __future__ import annotations

from pathlib import Path

from coding_agent_harness.workspace.git import SafeGit


def status(git: SafeGit, root: Path) -> tuple[str, str]:
    result = git.run(root, ("status", "--porcelain=v1", "-z"))
    return ("OK" if result.returncode == 0 else "GIT_FAILED"), result.stdout.decode("utf-8", errors="replace")


def diff(git: SafeGit, root: Path) -> tuple[str, str]:
    result = git.run(root, ("diff", "--no-ext-diff", "--no-textconv", "--binary", "--"))
    return ("OK" if result.returncode == 0 else "GIT_FAILED"), result.stdout.decode("utf-8", errors="replace")
