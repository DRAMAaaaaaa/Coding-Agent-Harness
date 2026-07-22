import os
from pathlib import Path

import pytest

from coding_agent_harness.governance.paths import (
    PathEscapeError,
    PathGuard,
    PathGuardError,
)


_UNPROVEN_EXTENDED_COMPONENTS = [
    "item.",
    "item ",
    "CON",
    "con.txt",
    "item:stream",
    "item<name",
    "item\x1fcontrol",
    "parent/child",
]


def test_guard_rejects_missing_or_non_directory_root(tmp_path: Path) -> None:
    for invalid_root in (tmp_path / "missing", tmp_path / "file.txt"):
        if invalid_root.suffix:
            invalid_root.write_text("not a directory", encoding="utf-8")
        with pytest.raises(PathGuardError) as captured:
            PathGuard(invalid_root)
        assert str(captured.value) == "工作区根目录无效"


def test_resolve_accepts_root_relative_absolute_and_missing_tail(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    existing = root / "src"
    existing.mkdir(parents=True)
    guard = PathGuard(root)

    assert guard.resolve(".") == root.resolve()
    assert guard.resolve("src/module.py") == (existing / "module.py").resolve()
    assert guard.resolve(existing / "absolute.py") == (existing / "absolute.py").resolve()


@pytest.mark.parametrize("candidate", ["../secret", "../../workspace-secret"])
def test_resolve_rejects_traversal_without_leaking_candidate(
    tmp_path: Path,
    candidate: str,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(PathEscapeError) as captured:
        PathGuard(root).resolve(candidate)

    assert str(captured.value) == "路径超出工作区"
    assert candidate not in str(captured.value)
    assert not vars(captured.value)


def test_resolve_rejects_absolute_same_prefix_sibling(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    sibling = tmp_path / "workspace-secret"
    root.mkdir()
    sibling.mkdir()

    with pytest.raises(PathEscapeError, match="^路径超出工作区$"):
        PathGuard(root).resolve(sibling / "token.txt")


def test_resolve_rejects_existing_link_escape(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"当前系统无法创建目录符号链接：{type(error).__name__}")

    with pytest.raises(PathEscapeError, match="^路径超出工作区$"):
        PathGuard(root).resolve(link / "not-created-yet" / "secret.txt")


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 路径大小写语义")
def test_windows_root_comparison_is_case_insensitive(tmp_path: Path) -> None:
    root = tmp_path / "MixedCaseWorkspace"
    root.mkdir()
    differently_cased = Path(str(root).swapcase())

    assert PathGuard(root).resolve(differently_cased) == root.resolve()


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 扩展路径别名语义")
def test_resolve_collapses_extended_drive_alias(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    child = root / "src" / "module.py"
    child.parent.mkdir(parents=True)
    extended_child = Path("\\\\?\\" + str(child))

    assert PathGuard(root).resolve(extended_child) == child.resolve()


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 设备命名空间语义")
def test_resolve_rejects_unknown_device_namespace(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(PathEscapeError, match="^路径超出工作区$"):
        PathGuard(root).resolve(r"\\?\GLOBALROOT\Device\HarddiskVolume1\secret")


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows 扩展路径字面语义")
@pytest.mark.parametrize("component", _UNPROVEN_EXTENDED_COMPONENTS)
def test_resolve_rejects_unproven_extended_drive_component(
    tmp_path: Path,
    component: str,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    candidate = rf"\\?\{root}\safe\{component}\file.py"

    with pytest.raises(PathEscapeError, match="^路径超出工作区$"):
        PathGuard(root).resolve(candidate)


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows anchor 语义")
def test_guard_rejects_different_unc_anchor_without_identity_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    guard = PathGuard(root)
    calls: list[str] = []
    candidate = Path(r"\\untrusted.invalid\share\payload")
    relevant = {str(root), str(root.resolve()), str(candidate)}
    original_resolve = Path.resolve
    original_samefile = Path.samefile
    original_stat = Path.stat

    def record_resolve(self: Path, strict: bool = False) -> Path:
        if str(self) in relevant:
            calls.append(f"resolve:{self}")
            return self
        return original_resolve(self, strict=strict)

    def record_samefile(self: Path, other: object) -> bool:
        if str(self) in relevant or str(other) in relevant:
            calls.append(f"samefile:{self}:{other}")
            return False
        return original_samefile(self, other)

    def record_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if str(self) in relevant:
            calls.append(f"stat:{self}")
            raise AssertionError("不同 anchor 不得探测文件系统")
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "resolve", record_resolve)
    monkeypatch.setattr(Path, "samefile", record_samefile)
    monkeypatch.setattr(Path, "stat", record_stat)

    with pytest.raises(PathEscapeError, match="^路径超出工作区$"):
        guard.resolve(r"\\untrusted.invalid\share\payload")
    assert calls == []


@pytest.mark.skipif(os.name != "nt", reason="仅 Windows drive-relative 语义")
@pytest.mark.parametrize("candidate", [r"Z:payload", r"\payload"])
def test_guard_rejects_ambiguous_windows_path_without_identity_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidate: str,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    guard = PathGuard(root)
    calls: list[str] = []

    def reject_resolve(self: Path, strict: bool = False) -> Path:
        del strict
        calls.append(f"resolve:{self}")
        raise AssertionError("drive-relative 或 rooted-relative 路径不得探测文件系统")

    monkeypatch.setattr(Path, "resolve", reject_resolve)

    with pytest.raises(PathEscapeError, match="^路径超出工作区$"):
        guard.resolve(candidate)
    assert calls == []
