import os
from pathlib import Path

from coding_agent_harness.governance.path_identity import (
    UnsafePathNamespaceError,
    collapse_windows_extended_path,
    is_within,
    path_key,
)


class PathGuardError(ValueError):
    """工作区根目录本身不可用。"""


class PathEscapeError(ValueError):
    """候选路径解析后位于工作区之外。"""


class PathGuard:
    def __init__(self, root: str | Path) -> None:
        try:
            raw_root = str(root)
            if os.name == "nt":
                raw_root = collapse_windows_extended_path(raw_root)
            root_path = Path(raw_root)
            path_key(root_path)
            resolved_root = root_path.resolve(strict=True)
        except (OSError, RuntimeError, UnsafePathNamespaceError):
            raise PathGuardError("工作区根目录无效") from None
        if not resolved_root.is_dir():
            raise PathGuardError("工作区根目录无效")
        self._root = resolved_root

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, candidate: str | Path) -> Path:
        raw_candidate = str(candidate)
        if os.name == "nt":
            try:
                raw_candidate = collapse_windows_extended_path(raw_candidate)
            except UnsafePathNamespaceError:
                raise PathEscapeError("路径超出工作区") from None
        path = Path(raw_candidate)
        if not path.is_absolute():
            path = self._root / path
        try:
            path_key(path)
            resolved = path.resolve(strict=False)
        except (OSError, RuntimeError, UnsafePathNamespaceError):
            raise PathEscapeError("路径超出工作区") from None
        try:
            contained = is_within(resolved, self._root)
        except UnsafePathNamespaceError:
            raise PathEscapeError("路径超出工作区") from None
        if not contained:
            raise PathEscapeError("路径超出工作区")
        return resolved
