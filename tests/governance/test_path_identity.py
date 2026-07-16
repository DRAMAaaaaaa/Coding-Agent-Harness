import os
from pathlib import Path

import pytest

from coding_agent_harness.governance.path_identity import (
    UnsafePathNamespaceError,
    collapse_windows_extended_path,
    is_within,
    path_key,
    paths_overlap,
    same_path,
)


_UNPROVEN_EXTENDED_COMPONENTS = [
    "item.",
    "item ",
    "CON",
    "con.sqlite3",
    "item:stream",
    "item<name",
    "item>name",
    'item"name',
    "item|name",
    "item?name",
    "item*name",
    "item\x1fcontrol",
    "parent/child",
]


@pytest.mark.parametrize(
    ("extended", "ordinary"),
    [
        (r"\\?\C:\Workspace\file.py", r"C:\Workspace\file.py"),
        (r"\\?\z:/Workspace\file.py", r"z:/Workspace\file.py"),
        (
            r"\\?\UNC\Server\Share\Workspace\file.py",
            r"\\Server\Share\Workspace\file.py",
        ),
        ("\\\\?\\UNC\\Server\\Share\\", "\\\\Server\\Share\\"),
    ],
)
def test_collapse_windows_extended_path_accepts_only_proven_aliases(
    extended: str,
    ordinary: str,
) -> None:
    assert collapse_windows_extended_path(extended) == ordinary


@pytest.mark.parametrize(
    "path",
    [
        r"\\.\PhysicalDrive0",
        r"\\?\GLOBALROOT\Device\HarddiskVolume1\secret",
        r"\\?\Volume{01234567-89ab-cdef-0123-456789abcdef}\secret",
        r"\\?\C:relative",
        r"\\?\C:\safe\..\secret",
        r"\\?\UNC\server",
        r"\\?\UNC\server\share\..\secret",
        r"\??\C:\secret",
        "\\\\?\\",
    ],
)
def test_collapse_windows_extended_path_rejects_unproven_namespaces(
    path: str,
) -> None:
    with pytest.raises(
        UnsafePathNamespaceError,
        match="^不支持的 Windows 设备命名空间$",
    ):
        collapse_windows_extended_path(path)


@pytest.mark.parametrize("namespace", ["drive", "unc"])
@pytest.mark.parametrize("component", _UNPROVEN_EXTENDED_COMPONENTS)
def test_collapse_windows_extended_path_rejects_unproven_win32_components(
    namespace: str,
    component: str,
) -> None:
    if namespace == "drive":
        path = rf"\\?\C:\safe\{component}\state"
    else:
        path = rf"\\?\UNC\server\share\safe\{component}\state"

    with pytest.raises(
        UnsafePathNamespaceError,
        match="^不支持的 Windows 设备命名空间$",
    ):
        collapse_windows_extended_path(path)


@pytest.mark.parametrize(
    ("extended", "ordinary"),
    [
        (
            r"\\?\C:\工作区\.git\配置..版本\file.py",
            r"C:\工作区\.git\配置..版本\file.py",
        ),
        (
            r"\\?\UNC\服务器\共享\工作区\.git\配置..版本\file.py",
            r"\\服务器\共享\工作区\.git\配置..版本\file.py",
        ),
    ],
)
def test_collapse_windows_extended_path_preserves_unicode_and_intermediate_dots(
    extended: str,
    ordinary: str,
) -> None:
    assert collapse_windows_extended_path(extended) == ordinary


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 扩展路径字面语义")
def test_extended_trailing_dot_is_a_distinct_real_object(tmp_path: Path) -> None:
    ordinary = tmp_path / "item."
    extended = Path("\\\\?\\" + str(ordinary))
    extended.mkdir()
    try:
        assert extended.exists()
        assert not ordinary.exists()
        with pytest.raises(UnsafePathNamespaceError):
            path_key(extended)
    finally:
        extended.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 路径别名语义")
def test_path_relationships_fold_extended_drive_alias(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    child = root / "src" / "module.py"
    child.parent.mkdir(parents=True)
    child.write_text("value = 1\n", encoding="utf-8")
    extended_root = Path("\\\\?\\" + str(root.resolve()))
    extended_child = Path("\\\\?\\" + str(child.resolve()))

    assert path_key(extended_root) == path_key(root)
    assert same_path(extended_child, child)
    assert is_within(extended_child, root)
    assert paths_overlap(extended_root, root)


def test_same_path_uses_existing_object_identity(tmp_path: Path) -> None:
    original = tmp_path / "original.txt"
    alias = tmp_path / "alias.txt"
    original.write_text("same object\n", encoding="utf-8")
    try:
        os.link(original, alias)
    except OSError as error:
        pytest.skip(f"当前文件系统无法创建硬链接：{type(error).__name__}")

    assert same_path(original, alias)


def test_is_within_accepts_missing_tail_below_existing_directory_alias(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    alias = tmp_path / "alias"
    root.mkdir()
    try:
        alias.symlink_to(root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"当前系统无法创建目录符号链接：{type(error).__name__}")

    assert is_within(alias / "missing" / "file.py", root)


def test_path_identity_fails_closed_when_resolution_cannot_be_confirmed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_resolve(self: Path, strict: bool = False) -> Path:
        del self, strict
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "resolve", fail_resolve)

    with pytest.raises(UnsafePathNamespaceError, match="^无法确认路径身份$"):
        path_key(tmp_path / "blocked")
