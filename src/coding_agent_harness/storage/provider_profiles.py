import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from coding_agent_harness.providers.models import ProviderKind, ProviderProfile, normalize_model
from coding_agent_harness.providers.binding import ProviderBindingCoordinator
from coding_agent_harness.storage.database import Database


class ProviderProfileNotFoundError(LookupError):
    pass


class ProviderProfileConflictError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProviderProfileRepository:
    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], UUID] = uuid4,
        coordinator: ProviderBindingCoordinator | None = None,
    ) -> None:
        self._database = database
        self._clock = clock
        self._id_factory = id_factory
        self._coordinator = coordinator

    @staticmethod
    def normalize_model(model: str) -> str:
        return normalize_model(model)

    async def create(self, kind: ProviderKind, model: str) -> ProviderProfile:
        normalized = self.normalize_model(model)
        profile_id, now = self._id_factory(), self._require_utc(self._clock())
        profile = ProviderProfile(id=profile_id, kind=kind, model=normalized, version=1, created_at=now, updated_at=now)
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                await self._database.connection.execute(
                    "INSERT INTO provider_profiles (id, kind, model, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(profile.id), profile.kind.value, profile.model, profile.version, profile.created_at.isoformat(), profile.updated_at.isoformat()),
                )
                await self._database.connection.commit()
            except sqlite3.IntegrityError as error:
                await self._database.connection.rollback()
                if "provider_profiles.id" in str(error):
                    raise ProviderProfileConflictError("provider profile already exists") from None
                raise
            except BaseException:
                await self._database.connection.rollback()
                raise
        return profile

    async def get(self, profile_id: UUID) -> ProviderProfile | None:
        async with self._database.operation_lock:
            row = await (await self._database.connection.execute(
                "SELECT id, kind, model, version, created_at, updated_at FROM provider_profiles WHERE id = ?", (str(profile_id),)
            )).fetchone()
        return _profile_from_row(row) if row is not None else None

    async def list(self) -> tuple[ProviderProfile, ...]:
        async with self._database.operation_lock:
            cursor = await self._database.connection.execute(
                "SELECT id, kind, model, version, created_at, updated_at FROM provider_profiles ORDER BY created_at ASC, id ASC"
            )
            rows = await cursor.fetchall()
        return tuple(_profile_from_row(row) for row in rows)

    async def update_model(self, profile_id: UUID, model: str) -> ProviderProfile:
        if self._coordinator is not None:
            async with self._coordinator.hold(profile_id):
                return await self._update_model(profile_id, model)
        return await self._update_model(profile_id, model)

    async def _update_model(self, profile_id: UUID, model: str) -> ProviderProfile:
        normalized = self.normalize_model(model)
        async with self._database.operation_lock:
            try:
                await self._database.connection.execute("BEGIN IMMEDIATE")
                row = await (await self._database.connection.execute(
                    "SELECT id, kind, model, version, created_at, updated_at FROM provider_profiles WHERE id = ?", (str(profile_id),)
                )).fetchone()
                if row is None:
                    raise ProviderProfileNotFoundError("provider profile not found")
                current = _profile_from_row(row)
                if current.model == normalized:
                    await self._database.connection.commit()
                    return current
                updated = current.model_copy(update={"model": normalized, "version": current.version + 1, "updated_at": self._require_utc(self._clock())})
                await self._database.connection.execute(
                    "UPDATE provider_profiles SET model = ?, version = ?, updated_at = ? WHERE id = ?",
                    (updated.model, updated.version, updated.updated_at.isoformat(), str(profile_id)),
                )
                await self._database.connection.commit()
                return updated
            except ProviderProfileNotFoundError:
                await self._database.connection.rollback()
                raise
            except BaseException:
                await self._database.connection.rollback()
                raise

    @staticmethod
    def _require_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a UTC-aware datetime")
        return value.astimezone(UTC)


def _profile_from_row(row: sqlite3.Row | tuple[object, ...]) -> ProviderProfile:
    def timestamp(value: object) -> datetime:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("stored provider profile timestamp must be UTC-aware")
        return parsed.astimezone(UTC)

    return ProviderProfile(
        id=UUID(str(row[0])),
        kind=ProviderKind(str(row[1])),
        model=str(row[2]),
        version=int(str(row[3])),
        created_at=timestamp(row[4]),
        updated_at=timestamp(row[5]),
    )
