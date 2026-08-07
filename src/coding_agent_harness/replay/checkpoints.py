"""只为受控文本改动生成可恢复检查点。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from coding_agent_harness.workspace.git import SafeGit

_MAX_PATCH_BYTES = 1024 * 1024


class CheckpointError(ValueError):
    """检查点不满足安全边界。"""


class Checkpoint(BaseModel):
    parent_task_id: UUID
    source_event_sequence: int
    base_commit: str
    patch_sha256: str
    patch_bytes: int
    file_name: str


def create_checkpoint(
    worktree: str | Path,
    state_root: str | Path,
    branch_id: UUID,
    parent_task_id: UUID,
    source_event_sequence: int,
) -> Checkpoint:
    """验证并原子保存唯一的 UTF-8 文本 diff。"""
    base_commit, patch = capture_patch(worktree, state_root, source_event_sequence)
    return write_checkpoint(state_root, branch_id, parent_task_id, source_event_sequence, base_commit, patch)


def capture_patch(
    worktree: str | Path,
    state_root: str | Path,
    source_event_sequence: int,
) -> tuple[str, bytes]:
    """只读捕获可恢复 patch；在唯一分支预留前不写入状态目录。"""
    if source_event_sequence <= 0:
        raise CheckpointError("检查点事件序号无效")
    root = Path(worktree).resolve(strict=True)
    git = SafeGit(state_root)
    status = git.run(root, ["status", "--porcelain=v1", "-z"])
    if status.returncode != 0 or _unsafe_status(status.stdout):
        raise CheckpointError("检查点只允许已跟踪且未重命名的改动")
    base = git.run(root, ["rev-parse", "HEAD"])
    diff = git.run(root, ["diff", "--no-ext-diff", "--no-color", "--binary", "HEAD", "--"])
    if base.returncode != 0 or diff.returncode != 0:
        raise CheckpointError("无法生成检查点")
    patch = diff.stdout
    if not patch or len(patch) > _MAX_PATCH_BYTES or b"\0" in patch or b"GIT binary patch" in patch:
        raise CheckpointError("检查点不是受限文本补丁")
    try:
        patch.decode("utf-8")
        base_commit = base.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        raise CheckpointError("检查点编码无效") from None
    if not base_commit:
        raise CheckpointError("检查点基准无效")
    return base_commit, patch


def write_checkpoint(
    state_root: str | Path,
    branch_id: UUID,
    parent_task_id: UUID,
    source_event_sequence: int,
    base_commit: str,
    patch: bytes,
) -> Checkpoint:
    """把已经过检查的 patch 以原子替换写进私有状态目录。"""
    state = Path(state_root).resolve(strict=False)
    if not patch or len(patch) > _MAX_PATCH_BYTES or b"\0" in patch:
        raise CheckpointError("检查点不是受限文本补丁")
    folder = state / "checkpoints"
    folder.mkdir(parents=True, exist_ok=True)
    file_name = f"{branch_id}.patch"
    final = folder / file_name
    temporary = folder / f".{branch_id}.patch.tmp"
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            offset = 0
            while offset < len(patch):
                written = os.write(descriptor, patch[offset:])
                if written <= 0:
                    raise OSError("checkpoint short write")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, final)
    except FileExistsError:
        raise CheckpointError("检查点已存在") from None
    except OSError:
        raise CheckpointError("检查点写入失败") from None
    return Checkpoint(parent_task_id=parent_task_id, source_event_sequence=source_event_sequence,
                      base_commit=base_commit, patch_sha256=hashlib.sha256(patch).hexdigest(),
                      patch_bytes=len(patch), file_name=file_name)


def _unsafe_status(raw: bytes) -> bool:
    if raw and not raw.endswith(b"\0"):
        return True
    for record in raw.split(b"\0")[:-1]:
        if len(record) < 3 or record[2:3] != b" ":
            return True
        code = record[:2]
        if code not in {b" M", b"M ", b" D", b"D "}:
            return True
    return False
