"""Workspace 的 SQLite 持久化边界。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from coding_agent_harness.storage.database import Database
from coding_agent_harness.governance.path_identity import (
    UnsafePathNamespaceError,
    path_key,
    same_path,
)
from coding_agent_harness.workspace.models import ProjectProfile, Workspace


_COLUMNS = """
id, root, root_key, git_root, default_branch, profile_json, trust_fingerprint,
created_at, trust_state, trusted_at, trusted_fingerprint
"""


class WorkspaceStorageError(ValueError):
    """Workspace 记录无法安全读写。"""


@dataclass(frozen=True, slots=True)
class StoredWorkspace:
    workspace: Workspace
    created_at: datetime
    trusted_at: datetime | None
    trusted_fingerprint: str | None

    @property
    def is_trusted(self) -> bool:
        return self.trusted_at is not None and self.trusted_fingerprint == self.workspace.profile.trust_fingerprint


class WorkspaceRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, workspace: Workspace) -> StoredWorkspace:
        root, root_key = _normalized_path(workspace.root)
        git_root, git_root_key = _normalized_path(workspace.git_root)
        if root_key != git_root_key:
            raise WorkspaceStorageError("Workspace 根目录必须是 Git 根目录")
        created_at = datetime.now(UTC)
        profile_json = json.dumps(
            workspace.profile.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute(
                    f"""
                    INSERT INTO workspaces ({_COLUMNS})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'UNTRUSTED', NULL, NULL)
                    """,
                    (
                        str(workspace.id), root, root_key, git_root, workspace.default_branch,
                        profile_json, workspace.profile.trust_fingerprint, created_at.isoformat(),
                    ),
                )
                await self._database.connection.commit()
            except sqlite3.IntegrityError:
                await self._database.connection.rollback()
                raise WorkspaceStorageError("Workspace 根目录已存在") from None
            except BaseException:
                await self._database.connection.rollback()
                raise
        return StoredWorkspace(workspace.model_copy(update={"root": Path(root), "git_root": Path(git_root)}), created_at, None, None)

    async def get(self, workspace_id: UUID) -> StoredWorkspace | None:
        return await self._one("WHERE id = ?", (str(workspace_id),))

    async def list(self) -> list[StoredWorkspace]:
        async with self._database.operation_lock:
            cursor = await self._database.connection.execute(
                f"SELECT {_COLUMNS} FROM workspaces ORDER BY created_at, id"
            )
            rows = await cursor.fetchall()
        return [_from_row(row) for row in rows]

    async def trust(self, workspace_id: UUID, fingerprint: str) -> StoredWorkspace:
        stored = await self.get(workspace_id)
        if stored is None:
            raise WorkspaceStorageError("Workspace 不存在")
        if fingerprint != stored.workspace.profile.trust_fingerprint:
            raise WorkspaceStorageError("信任指纹已变化或不匹配")
        trusted_at = datetime.now(UTC)
        async with self._database.operation_lock:
            try:
                cursor = await self._database.connection.execute(
                    """
                    UPDATE workspaces
                    SET trust_state = 'TRUSTED', trusted_at = ?, trusted_fingerprint = ?
                    WHERE id = ? AND trust_fingerprint = ? AND trust_state = 'UNTRUSTED'
                    AND trusted_at IS NULL AND trusted_fingerprint IS NULL
                    """,
                    (trusted_at.isoformat(), fingerprint, str(workspace_id), fingerprint),
                )
                if cursor.rowcount != 1:
                    raise WorkspaceStorageError("Workspace 已信任或信任指纹已变化")
                await self._database.connection.commit()
            except WorkspaceStorageError:
                await self._database.connection.rollback()
                raise
            except BaseException:
                await self._database.connection.rollback()
                raise
        return StoredWorkspace(stored.workspace, stored.created_at, trusted_at, fingerprint)

    async def revoke_trust(self, workspace_id: UUID) -> None:
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute(
                    "UPDATE workspaces SET trust_state='UNTRUSTED', trusted_at=NULL, trusted_fingerprint=NULL WHERE id=?",
                    (str(workspace_id),),
                )
                await self._database.connection.commit()
            except BaseException:
                await self._database.connection.rollback()
                raise

    async def _one(self, suffix: str, parameters: tuple[str, ...]) -> StoredWorkspace | None:
        async with self._database.operation_lock:
            cursor = await self._database.connection.execute(
                f"SELECT {_COLUMNS} FROM workspaces {suffix}", parameters
            )
            row = await cursor.fetchone()
        return _from_row(row) if row is not None else None


def _normalized_path(value: Path) -> tuple[str, str]:
    try:
        resolved = value.resolve(strict=True)
        return str(resolved), "\x1f".join(path_key(resolved))
    except (OSError, RuntimeError, UnsafePathNamespaceError):
        raise WorkspaceStorageError("Workspace 路径无效") from None


def _from_row(row: sqlite3.Row | tuple[object, ...]) -> StoredWorkspace:
    try:
        if any(row[index] is None for index in range(1, 8)):
            raise WorkspaceStorageError("Workspace 旧记录不完整")
        profile = ProjectProfile.model_validate_json(str(row[5]), strict=True)
        root_value, root_key = _normalized_path(Path(str(row[1])))
        git_root_value, git_root_key = _normalized_path(Path(str(row[3])))
        root = Path(root_value)
        git_root = Path(git_root_value)
        persisted_root_key = str(row[2])
        if (
            root_key != persisted_root_key
            or git_root_key != persisted_root_key
            or not same_path(root, git_root)
        ):
            raise WorkspaceStorageError("Workspace 根路径身份无效")
        persisted_fingerprint = str(row[6]) if row[6] is not None else None
        if persisted_fingerprint != profile.trust_fingerprint:
            raise WorkspaceStorageError("Workspace 信任指纹记录无效")
        workspace = Workspace(
            id=UUID(str(row[0])), root=root, git_root=git_root,
            default_branch=str(row[4]), profile=profile,
        )
        created_at = datetime.fromisoformat(str(row[7]))
        state = str(row[8])
        trusted_at = datetime.fromisoformat(str(row[9])) if row[9] is not None else None
        trusted_fingerprint = str(row[10]) if row[10] is not None else None
        if state not in {"UNTRUSTED", "TRUSTED"}:
            raise WorkspaceStorageError("Workspace 信任状态无效")
        if state == "TRUSTED" and (trusted_at is None or trusted_fingerprint != profile.trust_fingerprint):
            raise WorkspaceStorageError("Workspace 信任记录无效")
        if state == "UNTRUSTED" and (trusted_at is not None or trusted_fingerprint is not None):
            raise WorkspaceStorageError("Workspace 信任记录无效")
        return StoredWorkspace(workspace, created_at, trusted_at, trusted_fingerprint)
    except WorkspaceStorageError:
        raise
    except (TypeError, ValueError, OSError, RuntimeError, json.JSONDecodeError):
        raise WorkspaceStorageError("Workspace 记录无效") from None
