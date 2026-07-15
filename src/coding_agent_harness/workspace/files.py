"""从同一已验证文件句柄执行严格有界读取。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import stat
from typing import BinaryIO, ContextManager, Protocol


class BinaryFile(Protocol):
    def fileno(self) -> int: ...

    def read(self, size: int = -1) -> bytes: ...


class BinaryFileOpener(Protocol):
    def __call__(self, path: Path) -> ContextManager[BinaryFile]: ...


class BoundedFileError(OSError):
    """有界读取失败。"""


class BoundedFileTooLargeError(BoundedFileError):
    """文件内容超过读取上限。"""


class UnsafeBoundedFileError(BoundedFileError):
    """已打开句柄并非路径当前指向的普通文件。"""


class BoundedFileReadError(BoundedFileError):
    """文件无法打开、验证或读取。"""


class DefaultBinaryFileOpener:
    @contextmanager
    def __call__(self, path: Path) -> Iterator[BinaryIO]:
        with path.open("rb") as stream:
            yield stream


class BoundedFileReader:
    """验证句柄身份后只读取 ``limit + 1`` 字节。"""

    def __init__(self, opener: BinaryFileOpener | None = None) -> None:
        self._opener = opener or DefaultBinaryFileOpener()

    def read(self, path: Path, limit: int) -> bytes:
        if limit < 1:
            raise ValueError("文件读取上限必须为正数")
        try:
            with self._opener(path) as stream:
                opened_stat = os.fstat(stream.fileno())
                path_stat = path.stat(follow_symlinks=False)
                if not stat.S_ISREG(path_stat.st_mode) or not os.path.samestat(
                    opened_stat,
                    path_stat,
                ):
                    raise UnsafeBoundedFileError("文件句柄身份不匹配")
                content = stream.read(limit + 1)
        except UnsafeBoundedFileError:
            raise
        except OSError:
            raise BoundedFileReadError("文件不可读取") from None
        if len(content) > limit:
            raise BoundedFileTooLargeError("文件超过大小限制")
        return content
