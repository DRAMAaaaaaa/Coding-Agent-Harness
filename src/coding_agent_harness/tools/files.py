from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
import stat
import tempfile
from typing import Iterator


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def _cas_lock(path: Path) -> Iterator[bool]:
    """协调同一 Workspace 中遵守协议的 Harness CAS 操作。"""
    lock_name = hashlib.sha256(os.fsencode(path.name)).hexdigest()
    lock = path.parent / f".harness-cas-{lock_name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        yield False
        return
    except OSError:
        yield False
        return
    try:
        os.close(descriptor)
        yield True
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def _matches(path: Path, expected_sha256: str | None) -> str:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return "OK" if expected_sha256 is None else "STALE_CONTENT"
    except OSError:
        return "FILE_ERROR"
    if not stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode):
        return "UNSAFE_PATH"
    if expected_sha256 is None or digest(path) != expected_sha256:
        return "STALE_CONTENT"
    return "OK"


def atomic_replace(path: Path, content: str, expected_sha256: str | None) -> str:
    """在 Harness 协作锁内执行文件级 CAS。

    create 以 link no-replace 原子落盘；replace 在锁内、最终 replace 前复验摘要。
    忽略锁的同 UID 外部进程若恰在复验与 replace 之间写入，不具备跨平台可用
    的 SHA-256 条件替换原语可供可靠阻断，属于已声明的外部竞争边界。
    """
    with _cas_lock(path) as acquired:
        if not acquired:
            return "CAS_BUSY"
        initial = _matches(path, expected_sha256)
        if initial != "OK":
            return initial
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".harness-", dir=path.parent)
            temporary_path = Path(temporary)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(content.encode("utf-8"))
                    handle.flush()
                    os.fsync(handle.fileno())
                checked = _matches(path, expected_sha256)
                if checked != "OK":
                    return checked
                if expected_sha256 is None:
                    try:
                        os.link(temporary_path, path)
                    except FileExistsError:
                        return "STALE_CONTENT"
                else:
                    os.replace(temporary_path, path)
            finally:
                temporary_path.unlink(missing_ok=True)
        except OSError:
            return "FILE_ERROR"
    return "OK"


def delete_regular_file(path: Path, expected_sha256: str) -> str:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return "NOT_FOUND"
    except OSError:
        return "FILE_ERROR"
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        return "UNSAFE_PATH"
    if digest(path) != expected_sha256:
        return "STALE_CONTENT"
    try:
        path.unlink()
    except OSError:
        return "FILE_ERROR"
    return "OK"
