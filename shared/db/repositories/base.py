"""
shared/db/repositories/base.py
Generic base repository providing common CRUD operations.
All concrete repositories inherit from this class.
"""
from __future__ import annotations

from typing import Any, Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Base class for all repository objects.
    Provides get_by_id, get_all, save, and delete operations.
    Business logic belongs in the service layer, not here.
    """

    def __init__(self, session: AsyncSession, model: Type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def get_by_id(self, record_id: int) -> Optional[ModelT]:
        """Fetch a single record by primary key. Returns None if not found."""
        return await self._session.get(self._model, record_id)

    async def get_all(self) -> Sequence[ModelT]:
        """Fetch all records for this model. Use sparingly on large tables."""
        result = await self._session.execute(select(self._model))
        return result.scalars().all()

    async def save(self, obj: ModelT) -> ModelT:
        """Persist a new or modified object. Does NOT commit — caller controls the transaction."""
        self._session.add(obj)
        await self._session.flush()  # Assigns PK without committing
        return obj

    async def delete(self, obj: ModelT) -> None:
        """Delete an object. Does NOT commit — caller controls the transaction."""
        await self._session.delete(obj)
        await self._session.flush()

    async def bulk_save(self, objects: list[ModelT]) -> list[ModelT]:
        """Persist a list of objects in a single flush."""
        for obj in objects:
            self._session.add(obj)
        await self._session.flush()
        return objects
