from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import os

from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.workspaces import (
    WorkspaceRepository,
    WorkspaceStorageError,
)
from coding_agent_harness.workspace.models import ProjectProfile, VerificationCommands, Workspace
from coding_agent_harness.governance.path_identity import UnsafePathNamespaceError, collapse_windows_extended_path


def _workspace(root: Path) -> Workspace:
    return Workspace(
        id=uuid4(),
        root=root,
        git_root=root,
        default_branch="main",
        profile=ProjectProfile(
            languages=("python",),
            commands=VerificationCommands(test=("python", "-m", "pytest")),
            requires_trust=True,
            trust_fingerprint="a" * 64,
        ),
    )


async def test_create_get_list_and_persist_trust(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    database_path = tmp_path / "state" / "harness.db"
    workspace = _workspace(root)

    database = await Database.open(database_path)
    try:
        repository = WorkspaceRepository(database)
        created = await repository.create(workspace)
        assert created.workspace.root == root.resolve()
        assert created.trusted_at is None
        assert await repository.list() == [created]
        trusted = await repository.trust(created.workspace.id, "a" * 64)
        assert trusted.trusted_at is not None
    finally:
        await database.close()

    reopened = await Database.open(database_path)
    try:
        stored = await WorkspaceRepository(reopened).get(workspace.id)
        assert stored is not None
        assert stored.trusted_at is not None
        assert stored.workspace.profile.commands.test == ("python", "-m", "pytest")
    finally:
        await reopened.close()


async def test_rejects_duplicate_root_and_invalid_legacy_row(tmp_path: Path) -> None:
    database = await Database.open(tmp_path / "harness.db")
    try:
        repository = WorkspaceRepository(database)
        workspace = _workspace(tmp_path / "repo")
        workspace.root.mkdir()
        await repository.create(workspace)
        with pytest.raises(WorkspaceStorageError, match="已存在"):
            await repository.create(_workspace(workspace.root))

        legacy_id = uuid4()
        await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(legacy_id),))
        await database.connection.commit()
        with pytest.raises(WorkspaceStorageError, match="不完整"):
            await repository.get(legacy_id)
    finally:
        await database.close()


async def test_create_rejects_sensitive_profile_before_sqlite_write(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    database = await Database.open(tmp_path / "harness.db")
    canary = "credential-" + uuid4().hex
    workspace = _workspace(root).model_copy(
        update={
            "profile": ProjectProfile(
                languages=("python",),
                commands=VerificationCommands(
                    test=("python", "-m", "pytest", f"token={canary}"),
                ),
                requires_trust=True,
                trust_fingerprint="a" * 64,
            )
        }
    )
    try:
        repository = WorkspaceRepository(database)

        with pytest.raises(
            WorkspaceStorageError,
            match="Workspace 配置包含敏感信息，拒绝持久化",
        ) as captured:
            await repository.create(workspace)

        row = await (
            await database.connection.execute(
                "SELECT COUNT(*), COALESCE(group_concat(profile_json), '') FROM workspaces"
            )
        ).fetchone()
        assert row == (0, "")
        assert canary not in str(captured.value)
    finally:
        await database.close()


async def test_get_rejects_sensitive_profile_tampering_with_fixed_error(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    database = await Database.open(tmp_path / "harness.db")
    workspace = _workspace(root)
    canary = "tamper-" + uuid4().hex
    try:
        repository = WorkspaceRepository(database)
        await repository.create(workspace)
        profile_json = (
            workspace.profile.model_copy(
                update={
                    "commands": VerificationCommands(
                        test=("python", "-m", "pytest", f"password={canary}"),
                    )
                }
            ).model_dump_json()
        )
        await database.connection.execute(
            "UPDATE workspaces SET profile_json = ? WHERE id = ?",
            (profile_json, str(workspace.id)),
        )
        await database.connection.commit()

        with pytest.raises(
            WorkspaceStorageError,
            match="Workspace 配置包含敏感信息，拒绝持久化",
        ) as captured:
            await repository.get(workspace.id)

        assert canary not in str(captured.value)
    finally:
        await database.close()


@pytest.mark.parametrize("column", ["root", "git_root", "trust_fingerprint"])
async def test_get_fails_closed_when_workspace_identity_is_tampered(
    tmp_path: Path,
    column: str,
) -> None:
    root = tmp_path / "repo"
    other = tmp_path / "other"
    root.mkdir()
    other.mkdir()
    database = await Database.open(tmp_path / "harness.db")
    try:
        repository = WorkspaceRepository(database)
        workspace = _workspace(root)
        await repository.create(workspace)
        tampered = "b" * 64 if column == "trust_fingerprint" else str(other)
        await database.connection.execute(
            f"UPDATE workspaces SET {column} = ? WHERE id = ?",
            (tampered, str(workspace.id)),
        )
        await database.connection.commit()

        with pytest.raises(WorkspaceStorageError):
            await repository.get(workspace.id)
    finally:
        await database.close()


def test_windows_extended_namespace_helper_rejects_unsafe_device_name() -> None:
    with pytest.raises(UnsafePathNamespaceError):
        collapse_windows_extended_path("\\\\?\\GLOBALROOT\\Device")


@pytest.mark.skipif(os.name != "nt", reason="Windows 路径身份契约")
async def test_windows_extended_alias_conflicts_in_real_sqlite(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    database = await Database.open(tmp_path / "state.db")
    try:
        repository = WorkspaceRepository(database)
        first = _workspace(root)
        await repository.create(first)
        alias = _workspace(Path("\\\\?\\" + str(root.resolve())))
        with pytest.raises(WorkspaceStorageError, match="已存在"):
            await repository.create(alias)
    finally:
        await database.close()
