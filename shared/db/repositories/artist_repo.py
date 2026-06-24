"""
shared/db/repositories/artist_repo.py
Data access layer for Artist, GuildArtist, and UserArtistSubscription models.
"""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.db.models import Artist, GuildArtist, UserArtistSubscription
from shared.db.repositories.base import BaseRepository


class ArtistRepository(BaseRepository[Artist]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Artist)

    async def get_by_normalized_name(self, name: str) -> Optional[Artist]:
        """Look up an artist by normalised (lowercase, stripped) name."""
        result = await self._session.execute(
            select(Artist).where(Artist.name_normalized == name.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str) -> tuple[Artist, bool]:
        """
        Fetch or create an Artist by name.
        Returns (artist, created).
        name_display is title-cased; name_normalized is lowercased.
        """
        normalised = name.lower().strip()
        existing = await self.get_by_normalized_name(normalised)
        if existing:
            return existing, False
        artist = Artist(
            name_normalized=normalised,
            name_display=name.title().strip(),
        )
        self._session.add(artist)
        await self._session.flush()
        return artist, True

    async def search(self, query: str, limit: int = 20) -> Sequence[Artist]:
        """Partial name search for the dashboard artist picker."""
        result = await self._session.execute(
            select(Artist)
            .where(Artist.name_normalized.ilike(f"%{query.lower().strip()}%"))
            .limit(limit)
        )
        return result.scalars().all()


class GuildArtistRepository(BaseRepository[GuildArtist]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GuildArtist)

    async def get_for_guild(self, guild_db_id: int) -> Sequence[GuildArtist]:
        """Fetch all active GuildArtist rows for a guild, with artist data loaded."""
        result = await self._session.execute(
            select(GuildArtist)
            .where(GuildArtist.guild_id == guild_db_id, GuildArtist.is_active == True)  # noqa: E712
            .options(selectinload(GuildArtist.artist))
        )
        return result.scalars().all()

    async def get_for_guild_with_artist(
        self, guild_db_id: int, artist_db_id: int
    ) -> Optional[GuildArtist]:
        """Fetch a specific GuildArtist link."""
        result = await self._session.execute(
            select(GuildArtist).where(
                GuildArtist.guild_id == guild_db_id,
                GuildArtist.artist_id == artist_db_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        guild_db_id: int,
        artist_db_id: int,
        role_id: Optional[int],
        added_by_discord_id: Optional[int],
    ) -> GuildArtist:
        """
        Create a new GuildArtist link (or reactivate a soft-deleted one).
        """
        existing = await self.get_for_guild_with_artist(guild_db_id, artist_db_id)
        if existing:
            existing.is_active = True
            existing.role_id = role_id
            existing.added_by_discord_id = added_by_discord_id
            await self._session.flush()
            return existing

        ga = GuildArtist(
            guild_id=guild_db_id,
            artist_id=artist_db_id,
            role_id=role_id,
            added_by_discord_id=added_by_discord_id,
        )
        self._session.add(ga)
        await self._session.flush()
        return ga

    async def remove(self, guild_db_id: int, artist_db_id: int) -> bool:
        """Soft-delete a GuildArtist link. Returns True if found."""
        ga = await self.get_for_guild_with_artist(guild_db_id, artist_db_id)
        if not ga:
            return False
        ga.is_active = False
        await self._session.flush()
        return True

    async def count_for_guild(self, guild_db_id: int) -> int:
        """Return the number of active tracked artists for a guild (for tier enforcement)."""
        from sqlalchemy import func, select as sa_select
        result = await self._session.execute(
            sa_select(func.count()).where(
                GuildArtist.guild_id == guild_db_id,
                GuildArtist.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def get_all_normalized_names_for_guild(self, guild_db_id: int) -> list[str]:
        """
        Return a list of normalised artist names tracked in a guild.
        Used by the feed poller for fast matching.
        """
        from sqlalchemy import select as sa_select
        result = await self._session.execute(
            sa_select(Artist.name_normalized)
            .join(GuildArtist, GuildArtist.artist_id == Artist.id)
            .where(
                GuildArtist.guild_id == guild_db_id,
                GuildArtist.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())


class UserArtistSubscriptionRepository(BaseRepository[UserArtistSubscription]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserArtistSubscription)

    async def get(self, user_db_id: int, guild_artist_id: int) -> Optional[UserArtistSubscription]:
        result = await self._session.execute(
            select(UserArtistSubscription).where(
                UserArtistSubscription.user_id == user_db_id,
                UserArtistSubscription.guild_artist_id == guild_artist_id,
            )
        )
        return result.scalar_one_or_none()

    async def subscribe(self, user_db_id: int, guild_artist_id: int) -> UserArtistSubscription:
        """Create a subscription if it doesn't exist."""
        existing = await self.get(user_db_id, guild_artist_id)
        if existing:
            return existing
        sub = UserArtistSubscription(user_id=user_db_id, guild_artist_id=guild_artist_id)
        self._session.add(sub)
        await self._session.flush()
        return sub

    async def unsubscribe(self, user_db_id: int, guild_artist_id: int) -> bool:
        """Delete a subscription. Returns True if it existed."""
        existing = await self.get(user_db_id, guild_artist_id)
        if not existing:
            return False
        await self._session.delete(existing)
        await self._session.flush()
        return True

    async def get_subscriber_count(self, guild_artist_id: int) -> int:
        from sqlalchemy import func, select as sa_select
        result = await self._session.execute(
            sa_select(func.count()).where(
                UserArtistSubscription.guild_artist_id == guild_artist_id
            )
        )
        return result.scalar_one()
