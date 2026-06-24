"""
shared/db/repositories/feed_repo.py
Data access layer for Feed, FeedEntry, GuildFeedEntry, and NotificationLog.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Feed, FeedEntry, GuildFeedEntry, NotificationLog
from shared.db.repositories.base import BaseRepository


class FeedRepository(BaseRepository[Feed]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Feed)

    async def get_active_feeds(self) -> Sequence[Feed]:
        """Return all active feeds, ordered by ID (insertion order)."""
        result = await self._session.execute(
            select(Feed).where(Feed.is_active == True).order_by(Feed.id)  # noqa: E712
        )
        return result.scalars().all()

    async def get_by_rss_url(self, rss_url: str) -> Optional[Feed]:
        result = await self._session.execute(
            select(Feed).where(Feed.rss_url == rss_url)
        )
        return result.scalar_one_or_none()

    async def update_poll_metadata(
        self,
        feed_id: int,
        last_polled_at: datetime,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        reset_failures: bool = False,
    ) -> None:
        """Update conditional-request headers and timestamp after a successful poll."""
        values: dict = {"last_polled_at": last_polled_at}
        if etag is not None:
            values["last_etag"] = etag
        if last_modified is not None:
            values["last_modified"] = last_modified
        if reset_failures:
            values["consecutive_failures"] = 0
        await self._session.execute(
            update(Feed).where(Feed.id == feed_id).values(**values)
        )

    async def increment_failures(self, feed_id: int) -> None:
        """Increment the consecutive failure counter for a feed."""
        from sqlalchemy import func
        await self._session.execute(
            update(Feed)
            .where(Feed.id == feed_id)
            .values(consecutive_failures=Feed.consecutive_failures + 1)
        )

    async def seed_default_feeds(self) -> None:
        """
        Insert the three leaked.cx forum RSS feeds if they don't already exist.
        Called once during bot startup.
        """
        defaults = [
            {
                "name": "Hip-Hop Leaks",
                "rss_url": "https://leaked.cx/forums/hiphopleaks.rss",
                "forum_url": "https://leaked.cx/forums/hiphopleaks",
            },
            {
                "name": "Other Genre Leaks",
                "rss_url": "https://leaked.cx/forums/othergenreleaks.rss",
                "forum_url": "https://leaked.cx/forums/othergenreleaks",
            },
            {
                "name": "Other Media Leaks",
                "rss_url": "https://leaked.cx/forums/othermedialeaks.rss",
                "forum_url": "https://leaked.cx/forums/othermedialeaks",
            },
        ]
        for feed_data in defaults:
            existing = await self.get_by_rss_url(feed_data["rss_url"])
            if not existing:
                feed = Feed(**feed_data)
                self._session.add(feed)
        await self._session.flush()


class FeedEntryRepository(BaseRepository[FeedEntry]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FeedEntry)

    async def get_by_url(self, entry_url: str) -> Optional[FeedEntry]:
        """Primary deduplication lookup — check before processing any entry."""
        result = await self._session.execute(
            select(FeedEntry).where(FeedEntry.entry_url == entry_url)
        )
        return result.scalar_one_or_none()

    async def is_seen(self, entry_url: str) -> bool:
        """Fast existence check — avoids loading the full row."""
        from sqlalchemy import exists, literal
        result = await self._session.execute(
            select(literal(1)).where(
                select(FeedEntry.id).where(FeedEntry.entry_url == entry_url).exists()
            )
        )
        return result.scalar() is not None

    async def create(
        self,
        feed_id: int,
        entry_url: str,
        title: str,
        clean_title: str,
        author: Optional[str],
        thread_tags: list[str],
        matched_artists: list[str],
        download_links: list[str],
        published_at: Optional[datetime],
    ) -> FeedEntry:
        entry = FeedEntry(
            feed_id=feed_id,
            entry_url=entry_url,
            title=title,
            clean_title=clean_title,
            author=author,
            thread_tags=thread_tags,
            matched_artists=matched_artists,
            download_links=download_links,
            published_at=published_at,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def mark_deleted(self, entry_url: str) -> bool:
        """Mark an entry as deleted after confirming the thread returned 404."""
        result = await self._session.execute(
            select(FeedEntry).where(FeedEntry.entry_url == entry_url)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        entry.is_deleted = True
        entry.deleted_at = datetime.now(timezone.utc)
        await self._session.flush()
        return True

    async def get_active_tracked_entries(self) -> Sequence[FeedEntry]:
        """
        Return all non-deleted entries that have at least one GuildFeedEntry.
        Used by the deletion-check service.
        """
        from sqlalchemy.orm import selectinload
        result = await self._session.execute(
            select(FeedEntry)
            .where(FeedEntry.is_deleted == False)  # noqa: E712
            .options(selectinload(FeedEntry.guild_entries))
        )
        entries = result.scalars().all()
        return [e for e in entries if e.guild_entries]

    async def get_recent(self, limit: int = 50) -> Sequence[FeedEntry]:
        """Fetch the most recent entries for the dashboard analytics view."""
        result = await self._session.execute(
            select(FeedEntry)
            .order_by(FeedEntry.first_seen_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


class GuildFeedEntryRepository(BaseRepository[GuildFeedEntry]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, GuildFeedEntry)

    async def get(self, guild_db_id: int, feed_entry_db_id: int) -> Optional[GuildFeedEntry]:
        result = await self._session.execute(
            select(GuildFeedEntry).where(
                GuildFeedEntry.guild_id == guild_db_id,
                GuildFeedEntry.feed_entry_id == feed_entry_db_id,
            )
        )
        return result.scalar_one_or_none()

    async def record(
        self,
        guild_db_id: int,
        feed_entry_db_id: int,
        channel_id: int,
        message_id: int,
    ) -> GuildFeedEntry:
        """Record that a notification was posted to a guild."""
        gfe = GuildFeedEntry(
            guild_id=guild_db_id,
            feed_entry_id=feed_entry_db_id,
            channel_id=channel_id,
            message_id=message_id,
        )
        self._session.add(gfe)
        await self._session.flush()
        return gfe

    async def mark_deleted(self, guild_db_id: int, feed_entry_db_id: int) -> bool:
        """Mark the Discord message as deleted for this guild."""
        gfe = await self.get(guild_db_id, feed_entry_db_id)
        if not gfe:
            return False
        gfe.is_deleted = True
        gfe.deleted_at = datetime.now(timezone.utc)
        await self._session.flush()
        return True

    async def get_active_for_entry(self, feed_entry_db_id: int) -> Sequence[GuildFeedEntry]:
        """Fetch all non-deleted guild delivery records for an entry."""
        result = await self._session.execute(
            select(GuildFeedEntry).where(
                GuildFeedEntry.feed_entry_id == feed_entry_db_id,
                GuildFeedEntry.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalars().all()


class NotificationLogRepository(BaseRepository[NotificationLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NotificationLog)

    async def record(
        self,
        user_db_id: Optional[int],
        feed_entry_db_id: int,
        guild_db_id: int,
        channel_id: int,
        message_id: int,
    ) -> NotificationLog:
        log = NotificationLog(
            user_id=user_db_id,
            feed_entry_id=feed_entry_db_id,
            guild_id=guild_db_id,
            channel_id=channel_id,
            message_id=message_id,
        )
        self._session.add(log)
        await self._session.flush()
        return log

    async def count_for_guild(self, guild_db_id: int, since: Optional[datetime] = None) -> int:
        from sqlalchemy import func, select as sa_select
        q = sa_select(func.count()).where(NotificationLog.guild_id == guild_db_id)
        if since:
            q = q.where(NotificationLog.delivered_at >= since)
        result = await self._session.execute(q)
        return result.scalar_one()
