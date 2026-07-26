from __future__ import annotations

from coding_agent_harness.workspace.models import RepositoryMap

_MAX_FILES = 200
_MAX_FILE_BYTES = 256 * 1024
_MAX_MATCHES = 100
_MAX_OUTPUT_BYTES = 64 * 1024


def search(repository_map: RepositoryMap, query: str) -> str:
    """仅在地图中的跟踪 UTF-8 文本文件内进行有界字面量检索。"""
    lines: list[str] = []
    output_size = 0
    matches = 0
    for relative in repository_map.tracked_files[:_MAX_FILES]:
        path = repository_map.root / relative
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if len(raw) > _MAX_FILE_BYTES or b"\0" in raw:
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
