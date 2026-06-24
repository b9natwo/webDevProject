"""
shared/db/repositories/guild_repo.py
Data access layer for Guild and GuildSettings models.
"""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.db.models import Guild, GuildSettings, PremiumTier
from shared.db.repositories.base import BaseRepository


class GuildRepository(BaseRepository[Guild]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Guild)

    async def get_by_discord_id(self, discord_id: int) -> Optional[Guild]:
        """Fetch a guild by its Discord snowflake ID, eagerly loading settings."""
        result = await self._session.execute(
            select(Guild)
            .where(Guild.discord_id == discord_id)
            .options(selectinload(Guild.settings))
        )
        return result.scalar_one_or_none()

    async def get_all_active(self) -> Sequence[Guild]:
        """Fetch all active guilds with their settings loaded."""
        result = await self._session.execute(
            select(Guild)
            .where(Guild.is_active == True)  # noqa: E712
            .options(selectinload(Guild.settings))
        )
        return result.scalars().all()

    async def get_or_create(
        self,
        discord_id: int,
        name: str,
        owner_discord_id: int,
        icon_hash: Optional[str] = None,
    ) -> tuple[Guild, bool]:
        """
        Fetch an existing guild record or create a new one.
        Returns (guild, created) where created=True means it was just inserted.
        Also creates default GuildSettings if the guild is new.
        """
        existing = await self.get_by_discord_id(discord_id)
        if existing:
            # Update mutable fields in case they changed on Discord
            existing.name = name
            existing.owner_discord_id = owner_discord_id
            if icon_hash is not None:
                existing.icon_hash = icon_hash
            existing.is_active = True
            await self._session.flush()
            return existing, False

        guild = Guild(
            discord_id=discord_id,
            name=name,
            owner_discord_id=owner_discord_id,
            icon_hash=icon_hash,
        )
        self._session.add(guild)
        await self._session.flush()

        # Create default settings row
        settings = GuildSettings(guild_id=guild.id)
        self._session.add(settings)
        await self._session.flush()

        return guild, True

    async def update_channels(
        self,
        discord_id: int,
        *,
        leaks_channel_id: Optional[int] = None,
        audit_channel_id: Optional[int] = None,
        artists_channel_id: Optional[int] = None,
        polls_channel_id: Optional[int] = None,
    ) -> Optional[Guild]:
        """Update one or more configured channel IDs for a guild."""
        guild = await self.get_by_discord_id(discord_id)
        if not guild:
            return None
        if leaks_channel_id is not None:
            guild.leaks_channel_id = leaks_channel_id
        if audit_channel_id is not None:
            guild.audit_channel_id = audit_channel_id
        if artists_channel_id is not None:
            guild.artists_channel_id = artists_channel_id
        if polls_channel_id is not None:
            guild.polls_channel_id = polls_channel_id
        await self._session.flush()
        return guild

    async def set_premium_tier(self, discord_id: int, tier: PremiumTier) -> Optional[Guild]:
        """Set the premium tier for a guild."""
        guild = await self.get_by_discord_id(discord_id)
        if not guild:
            return None
        guild.premium_tier = tier
        await self._session.flush()
        return guild

    async def deactivate(self, discord_id: int) -> None:
        """Mark a guild as inactive (bot was removed from it)."""
        guild = await self.get_by_discord_id(discord_id)
        if guild:
            guild.is_active = False
            await self._session.flush()

    async def get_settings(self, guild_db_id: int) -> Optional[GuildSettings]:
        """Fetch GuildSettings by the internal guild PK."""
        result = await self._session.execute(
            select(GuildSettings).where(GuildSettings.guild_id == guild_db_id)
        )
        return result.scalar_one_or_none()

    async def update_settings(
        self,
        guild_discord_id: int,
        *,
        recognized_sites: Optional[dict] = None,
        whitelisted_artists: Optional[list] = None,
        blacklisted_artists: Optional[list] = None,
        filter_min_age_minutes: Optional[int] = None,
        notification_format: Optional[str] = None,
    ) -> Optional[GuildSettings]:
        """Partial update of GuildSettings fields."""
        guild = await self.get_by_discord_id(guild_discord_id)
        if not guild:
            return None

        settings = await self.get_settings(guild.id)
        if not settings:
            settings = GuildSettings(guild_id=guild.id)
            self._session.add(settings)

        if recognized_sites is not None:
            settings.recognized_sites = recognized_sites
        if whitelisted_artists is not None:
            settings.whitelisted_artists = whitelisted_artists
        if blacklisted_artists is not None:
            settings.blacklisted_artists = blacklisted_artists
        if filter_min_age_minutes is not None:
            settings.filter_min_age_minutes = filter_min_age_minutes
        if notification_format is not None:
            settings.notification_format = notification_format

        await self._session.flush()
        return settings
