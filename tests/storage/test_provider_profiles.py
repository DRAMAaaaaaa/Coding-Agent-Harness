from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from coding_agent_harness.providers.models import ProviderKind
from coding_agent_harness.domain.actions import TaskState
from coding_agent_harness.domain.models import Task
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.provider_profiles import ProviderProfileRepository
from coding_agent_harness.storage.repositories import TaskRepository


async def test_create_normalizes_model_and_starts_version_one(tmp_path) -> None:
    repository = ProviderProfileRepository(
        await Database.open(tmp_path / "profiles.db"),
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    try:
        profile = await repository.create(ProviderKind.DEEPSEEK, "  deepseek-chat  ")
        assert profile.kind is ProviderKind.DEEPSEEK
        assert profile.model == "deepseek-chat"
        assert profile.version == 1
        assert profile.created_at == datetime(2026, 1, 1, tzinfo=UTC)
    finally:
        await repository._database.close()


async def test_update_with_normalized_same_model_does_not_bump_version(tmp_path) -> None:
    values = iter((datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)))
    database = await Database.open(tmp_path / "profiles.db")
    repository = ProviderProfileRepository(database, clock=lambda: next(values))
    try:
        profile = await repository.create(ProviderKind.QWEN, "qwen-plus")
        unchanged = await repository.update_model(profile.id, " qwen-plus ")
        assert unchanged == profile
    finally:
        await database.close()


async def test_list_orders_equal_timestamps_by_id(tmp_path) -> None:
    database = await Database.open(tmp_path / "profiles.db")
    ids = iter((UUID(int=2), UUID(int=1)))
    repository = ProviderProfileRepository(
        database, id_factory=lambda: next(ids), clock=lambda: datetime(2026, 1, 1, tzinfo=UTC)
    )
    try:
        await repository.create(ProviderKind.QWEN, "one")
        await repository.create(ProviderKind.QWEN, "two")
        assert [profile.id for profile in await repository.list()] == [UUID(int=1), UUID(int=2)]
    finally:
        await database.close()


def test_rejects_control_characters_and_overlong_utf8_model() -> None:
    with pytest.raises(ValueError):
        ProviderProfileRepository.normalize_model("good\x00bad")
    with pytest.raises(ValueError):
        ProviderProfileRepository.normalize_model("界" * 43)


async def test_task_authorization_is_normalized_to_utc_before_persistence(tmp_path) -> None:
    database = await Database.open(tmp_path / "authorization.db")
    profiles = ProviderProfileRepository(database)
    repository = TaskRepository(database)
    local_authorization = datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    try:
        profile = await profiles.create(ProviderKind.QWEN, "qwen-plus")
        workspace_id = uuid4()
        await database.connection.execute("INSERT INTO workspaces (id) VALUES (?)", (str(workspace_id),))
        await database.connection.commit()
        task = Task(
            id=uuid4(), workspace_id=workspace_id, requirement="x", state=TaskState.CREATED,
            step_budget=1, time_budget_seconds=1.0, created_at=datetime(2026, 1, 1, tzinfo=UTC),
            deadline_at=None, provider_profile_id=profile.id,
            provider_profile_version=profile.version,
            llm_api_authorized_at=local_authorization,
        )
        assert task.llm_api_authorized_at == datetime(2026, 1, 1, tzinfo=UTC)
        await repository.create(task)
        stored = await repository.get(task.id)
        assert stored is not None
        assert stored.llm_api_authorized_at == datetime(2026, 1, 1, tzinfo=UTC)
        row = await (await database.connection.execute(
            "SELECT llm_api_authorized_at FROM tasks WHERE id = ?", (str(task.id),)
        )).fetchone()
        assert row == ("2026-01-01T00:00:00+00:00",)
    finally:
        await database.close()
