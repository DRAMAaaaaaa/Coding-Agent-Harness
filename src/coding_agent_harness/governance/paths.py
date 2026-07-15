from pathlib import Path


class PathGuardError(ValueError):
    """工作区根目录本身不可用。"""


class PathEscapeError(ValueError):
    """候选路径解析后位于工作区之外。"""


class PathGuard:
    def __init__(self, root: str | Path) -> None:
        try:
            resolved_root = Path(root).resolve(strict=True)
        except (OSError, RuntimeError):
            raise PathGuardError("工作区根目录无效") from None
        if not resolved_root.is_dir():
            raise PathGuardError("工作区根目录无效")
        self._root = resolved_root

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, candidate: str | Path) -> Path:
        path = Path(candidate)
        if not path.is_absolute():
            path = self._root / path
        try:
            resolved = path.resolve(strict=False)
        except (OSError, RuntimeError):
            raise PathEscapeError("路径超出工作区") from None
        if not resolved.is_relative_to(self._root):
            raise PathEscapeError("路径超出工作区")
        return resolved
