from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess

import pytest


def run_git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=check,
        capture_output=True,
    )


@pytest.fixture
def git_repository_factory(tmp_path: Path) -> Callable[[str, Mapping[str, str]], Path]:
    def create(name: str, files: Mapping[str, str]) -> Path:
        root = tmp_path / name
        root.mkdir()
        run_git(root, "init", "-b", "main")
        run_git(root, "config", "user.name", "Harness Tests")
        run_git(root, "config", "user.email", "harness@example.invalid")
        run_git(root, "config", "core.autocrlf", "false")
        for relative_path, content in files.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        run_git(root, "add", ".")
        run_git(root, "commit", "-m", "initial commit")
        return root

    return create
