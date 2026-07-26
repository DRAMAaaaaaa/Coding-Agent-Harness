from hashlib import sha256
from pathlib import Path

import pytest

from coding_agent_harness.domain.actions import ToolAction
from coding_agent_harness.tools.models import ToolContext
from coding_agent_harness.tools.registry import ToolRegistry


def action(name: str, arguments: dict[str, object]) -> ToolAction:
    return ToolAction.model_validate({"kind": "tool", "tool": name, "arguments": arguments, "idempotency_key": name})


async def test_apply_patch_rejects_stale_digest_and_unknown_fields(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("one\n", encoding="utf-8")
    registry = ToolRegistry(ToolContext(workspace_root=tmp_path))
    stale = await registry.execute(action("apply_patch", {"path": "a.py", "expected_sha256": "0" * 64, "content": "two\n"}))
    invalid = await registry.execute(action("apply_patch", {"path": "a.py", "expected_sha256": sha256(target.read_bytes()).hexdigest(), "content": "two\n", "extra": True}))
    assert stale.code == "STALE_CONTENT"
    assert invalid.code == "INVALID_ARGUMENTS"
    assert target.read_text(encoding="utf-8") == "one\n"


async def test_apply_patch_creates_only_with_null_digest(tmp_path: Path) -> None:
    registry = ToolRegistry(ToolContext(workspace_root=tmp_path))
    result = await registry.execute(action("apply_patch", {"path": "new.py", "expected_sha256": None, "content": "new\n"}))
    assert result.ok
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "new\n"


@pytest.mark.parametrize("expected", [None, "old"])
async def test_apply_patch_fails_closed_for_harness_cas_when_pre_replace_digest_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expected: str | None,
) -> None:
    from coding_agent_harness.tools import files

    target = tmp_path / "race.py"
    if expected is not None:
        target.write_text(expected, encoding="utf-8")
        expected = sha256(target.read_bytes()).hexdigest()
    original_fsync = files.os.fsync

    def concurrent_change(descriptor: int) -> None:
        original_fsync(descriptor)
        target.write_text("concurrent\n", encoding="utf-8")

    monkeypatch.setattr(files.os, "fsync", concurrent_change)
    result = await ToolRegistry(ToolContext(workspace_root=tmp_path)).execute(
        action("apply_patch", {"path": "race.py", "expected_sha256": expected, "content": "agent\n"})
    )

    assert result.code == "STALE_CONTENT"
    assert target.read_text(encoding="utf-8") == "concurrent\n"


async def test_apply_patch_returns_busy_while_a_cooperating_harness_holds_the_lock(
    tmp_path: Path,
) -> None:
    from coding_agent_harness.tools import files

    target = tmp_path / "locked.py"
    target.write_text("old\n", encoding="utf-8")
    expected = sha256(target.read_bytes()).hexdigest()
    with files._cas_lock(target) as acquired:
        assert acquired
        result = await ToolRegistry(ToolContext(workspace_root=tmp_path)).execute(
            action("apply_patch", {"path": "locked.py", "expected_sha256": expected, "content": "agent\n"})
        )

    assert result.code == "CAS_BUSY"
    assert target.read_text(encoding="utf-8") == "old\n"
