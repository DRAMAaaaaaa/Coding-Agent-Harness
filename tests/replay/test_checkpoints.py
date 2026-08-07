from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from coding_agent_harness.replay.checkpoints import CheckpointError, create_checkpoint


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def test_create_checkpoint_writes_only_bounded_utf8_tracked_patch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    source = root / "a.txt"
    source.write_text("before\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-m", "initial")
    source.write_text("after\n", encoding="utf-8")

    checkpoint = create_checkpoint(root, tmp_path / "state", uuid4(), uuid4(), 7)

    stored = tmp_path / "state" / "checkpoints" / checkpoint.file_name
    assert stored.read_bytes().decode("utf-8")
    assert checkpoint.patch_bytes == len(stored.read_bytes())


@pytest.mark.parametrize("change", ["untracked", "binary"])
def test_create_checkpoint_rejects_unsafe_changes(tmp_path: Path, change: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    (root / "a.txt").write_text("before\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-m", "initial")
    if change == "untracked":
        (root / "new.txt").write_text("new\n", encoding="utf-8")
    else:
        (root / "a.txt").write_bytes(b"\x00binary")

    with pytest.raises(CheckpointError):
        create_checkpoint(root, tmp_path / "state", uuid4(), uuid4(), 7)
