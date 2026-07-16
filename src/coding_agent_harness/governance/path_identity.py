import os
from pathlib import Path


class UnsafePathNamespaceError(ValueError):
    """路径身份不能被安全确认。"""


_INVALID_WIN32_COMPONENT_CHARACTERS = frozenset('<>:"/\\|?*')
_DOS_DEVICE_NAMES = frozenset(
    {
        "aux",
        "clock$",
        "con",
        "conin$",
        "conout$",
        "nul",
        "prn",
        *(f"com{digit}" for digit in "123456789¹²³"),
        *(f"lpt{digit}" for digit in "123456789¹²³"),
    }
)


def _is_proven_win32_component(component: str) -> bool:
    if not component or component.endswith((".", " ")):
        return False
    if any(
        ord(character) < 32
        or character in _INVALID_WIN32_COMPONENT_CHARACTERS
        for character in component
    ):
        return False
    device_stem = component.partition(".")[0].rstrip(" .").casefold()
    return device_stem not in _DOS_DEVICE_NAMES


def _has_only_proven_win32_components(components: list[str]) -> bool:
    return all(
        _is_proven_win32_component(component)
        or (not component and index == len(components) - 1)
        for index, component in enumerate(components)
    )


def collapse_windows_extended_path(path: str) -> str:
    extended_unc_prefix = "\\\\?\\UNC\\"
    if path[: len(extended_unc_prefix)].casefold() == extended_unc_prefix.casefold():
        tail = path[len(extended_unc_prefix) :]
        parts = tail.split("\\")
        server_and_share_are_valid = (
            len(parts) >= 2
            and _is_proven_win32_component(parts[0])
            and _is_proven_win32_component(parts[1])
        )
        remaining_parts_are_valid = _has_only_proven_win32_components(parts[2:])
        if server_and_share_are_valid and remaining_parts_are_valid:
            return "\\\\" + tail
        raise UnsafePathNamespaceError("不支持的 Windows 设备命名空间")
    extended_prefix = "\\\\?\\"
    if path.startswith(extended_prefix):
        tail = path[len(extended_prefix) :]
        if (
            len(tail) >= 3
            and tail[0].isascii()
            and tail[0].isalpha()
            and tail[1] == ":"
            and tail[2] in {"\\", "/"}
            and _has_only_proven_win32_components(tail[3:].split("\\"))
        ):
            return tail
        raise UnsafePathNamespaceError("不支持的 Windows 设备命名空间")
    if (
        path.startswith("\\\\.\\")
        or path.startswith("\\??\\")
        or path.startswith("\\\\??\\")
    ):
        raise UnsafePathNamespaceError("不支持的 Windows 设备命名空间")
    return path


def path_key(path: Path) -> tuple[str, ...]:
    raw_path = str(path)
    if os.name == "nt":
        raw_path = collapse_windows_extended_path(raw_path)
    try:
        resolved = str(Path(raw_path).resolve(strict=False))
    except (OSError, RuntimeError):
        raise UnsafePathNamespaceError("无法确认路径身份") from None
    if os.name == "nt":
        resolved = collapse_windows_extended_path(resolved)
    normalized = os.path.normcase(os.path.normpath(resolved))
    return tuple(Path(normalized).parts)


def same_path(left: Path, right: Path) -> bool:
    if path_key(left) == path_key(right):
        return True
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return False
    except OSError:
        raise UnsafePathNamespaceError("无法确认路径身份") from None


def is_within(candidate: Path, root: Path) -> bool:
    candidate_parts = path_key(candidate)
    root_parts = path_key(root)
    if candidate_parts[: len(root_parts)] == root_parts:
        return True

    current = candidate
    while True:
        if same_path(current, root):
            return True
        if current.parent == current:
            return False
        current = current.parent


def paths_overlap(left: Path, right: Path) -> bool:
    return is_within(left, right) or is_within(right, left)
