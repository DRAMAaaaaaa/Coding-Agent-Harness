from __future__ import annotations

import stat
from pathlib import Path

from coding_agent_harness.governance.paths import PathEscapeError, PathGuard
from coding_agent_harness.workspace.files import (
    BoundedFileReadError,
    BoundedFileReader,
    BoundedFileTooLargeError,
    UnsafeBoundedFileError,
    is_symlink_or_reparse,
)
from coding_agent_harness.workspace.models import RepositoryMap

_MAX_FILES = 200
_MAX_FILE_BYTES = 256 * 1024
_MAX_MATCHES = 100
_MAX_OUTPUT_BYTES = 64 * 1024


def search(repository_map: RepositoryMap, query: str, guard: PathGuard) -> str:
    """仅在地图中的跟踪 UTF-8 文本文件内进行有界字面量检索。"""
    lines: list[str] = []
    output_size = 0
    matches = 0
    reader = BoundedFileReader()
    for relative in repository_map.tracked_files[:_MAX_FILES]:
        path = _unfollowed_tracked_path(guard, relative)
        if path is None:
            continue
        try:
            raw = reader.read(path, _MAX_FILE_BYTES)
        except (BoundedFileReadError, BoundedFileTooLargeError, UnsafeBoundedFileError):
            continue
        if b"\0" in raw:
            continue
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            if query not in line:
                continue
            entry = f"{relative}:{number}:{line}\n"
            encoded = entry.encode("utf-8")
            if matches >= _MAX_MATCHES or output_size + len(encoded) > _MAX_OUTPUT_BYTES:
                return "".join(lines)
            lines.append(entry)
            output_size += len(encoded)
            matches += 1
    return "".join(lines)


def _unfollowed_tracked_path(guard: PathGuard, relative: str) -> Path | None:
    raw = Path(relative)
    if (
        not raw.parts
        or raw.is_absolute()
        or any(part in {".", ".."} for part in raw.parts)
    ):
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
