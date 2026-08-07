from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from coding_agent_harness.providers.models import ProviderKind
from coding_agent_harness.storage.database import Database
from coding_agent_harness.storage.provider_profiles import ProviderProfileRepository


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
