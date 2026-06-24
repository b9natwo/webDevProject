"""
bot/src/services/feed_poller.py
Core RSS polling service for leaked.cx.
"""
from __future__ import annotations

import asyncio
import functools
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Optional

import feedparser

from bot.src.services.notifier import NotificationDispatcher, NotificationJob
from bot.src.services.scraper import LeakedCxScraper
from shared.config import get_settings
from shared.db.models import Guild, GuildArtist
from shared.db.repositories.artist_repo import GuildArtistRepository
from shared.db.repositories.feed_repo import (
    FeedEntryRepository,
    FeedRepository,
    GuildFeedEntryRepository,
)
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.session import get_db_session

if TYPE_CHECKING:
    from bot.src.core.client import PrefixHubBot

log = logging.getLogger(__name__)


class FeedPollerService:
    """
    Manages two background task loops.
    """

    def __init__(self, bot: "PrefixHubBot") -> None:
        self._bot = bot
        self._settings = get_settings()
        self._scraper: Optional[LeakedCxScraper] = None
        self._dispatcher: Optional[NotificationDispatcher] = None

        self._feed_task: Optional[asyncio.Task] = None
        self._deletion_task: Optional[asyncio.Task] = None

    async def start(self, scraper: LeakedCxScraper, dispatcher: NotificationDispatcher) -> None:
        """Attach services and launch background loops."""
        self._scraper = scraper
        self._dispatcher = dispatcher

        async with get_db_session() as session:
            feed_repo = FeedRepository(session)
            await feed_repo.seed_default_feeds()

        self._feed_task = asyncio.create_task(self._feed_loop(), name="feed-poller")
        self._deletion_task = asyncio.create_task(self._deletion_loop(), name="deletion-check")
        log.info("Feed poller started (interval=%ds)", self._settings.feed_poll_interval_seconds)

    async def stop(self) -> None:
        for task in (self._feed_task, self._deletion_task):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(self._feed_task, self._deletion_task, return_exceptions=True)
        log.info("Feed poller stopped")

    async def _feed_loop(self) -> None:
        while True:
            try:
                await self._poll_all_feeds()
            except Exception:
                log.exception("Unhandled error in feed loop")
            await asyncio.sleep(self._settings.feed_poll_interval_seconds)

    async def _poll_all_feeds(self) -> None:
        if not self._scraper or not self._scraper.is_authenticated:
            log.info("Not authenticated — attempting login before polling")
            if not await self._scraper.authenticate():
                log.warning("Authentication failed — skipping this poll cycle")
                return

        async with get_db_session() as session:
            feed_repo = FeedRepository(session)
            feeds = await feed_repo.get_active_feeds()

        for feed in feeds:
            try:
                await self._poll_feed(feed.id, feed.rss_url, feed.last_etag, feed.last_modified)
            except Exception:
                log.exception("Error polling feed %s", feed.rss_url)
                async with get_db_session() as session:
                    await FeedRepository(session).increment_failures(feed.id)
            await asyncio.sleep(2)

    async def _poll_feed(
        self,
        feed_id: int,
        rss_url: str,
        etag: Optional[str],
        last_modified: Optional[str],
    ) -> None:
        xml_text, new_etag, new_last_modified = await self._scraper.fetch_rss_text(
            rss_url, etag=etag, last_modified=last_modified
        )

        if xml_text is None:
            async with get_db_session() as session:
                await FeedRepository(session).update_poll_metadata(
                    feed_id,
                    last_polled_at=datetime.now(timezone.utc),
                    reset_failures=True,
                )
            return

        loop = asyncio.get_running_loop()
        feed_data = await loop.run_in_executor(
            None, functools.partial(feedparser.parse, xml_text)
        )

        now = datetime.now(timezone.utc)

        async with get_db_session() as session:
            await FeedRepository(session).update_poll_metadata(
                feed_id,
                last_polled_at=now,
                etag=new_etag,
                last_modified=new_last_modified,
                reset_failures=True,
            )

        entries = getattr(feed_data, "entries", [])
        if not entries:
            return

        new_entries = []
        async with get_db_session() as session:
            entry_repo = FeedEntryRepository(session)
            for entry in entries:
                url = getattr(entry, "link", None)
                if not url or await entry_repo.is_seen(url):
                    continue

                # In debug mode, process ALL entries regardless of age
                if not self._settings.debug_mode:
                    # Early filter: check if RSS entry has a timestamp and if it's too old
                    # This prevents unnecessary thread fetches for old entries
                    published_str = getattr(entry, "published", None)
                    if published_str:
                        try:
                            # Try to parse the published timestamp from RSS
                            published_time = parsedate_to_datetime(published_str)
                            age_minutes = (now - published_time).total_seconds() / 60
                            
                            # Skip entries older than recent window (optimization)
                            if age_minutes > self._settings.feed_recent_window_minutes:
                                log.debug(
                                    "Skipping RSS entry (%.1f min old): %s",
                                    age_minutes, url
                                )
                                continue
                        except Exception:
                            # If RSS timestamp parsing fails, process anyway
                            # (will be validated during thread fetch)
                            pass
                else:
                    log.debug("DEBUG MODE: Processing entry regardless of age: %s", url)

                new_entries.append(entry)

        if not new_entries:
            return

        log.info(
            "Feed %s: %d new/recent entries to process%s",
            rss_url,
            len(new_entries),
            " (DEBUG MODE: processing all)" if self._settings.debug_mode else ""
        )

        for entry in new_entries:
            try:
                await self._process_entry(feed_id, entry)
            except Exception:
                log.exception("Error processing entry %s", getattr(entry, "link", "unknown"))
            await asyncio.sleep(0.5)

    async def _process_entry(self, feed_id: int, entry) -> None:
        url: str = getattr(entry, "link", "")
        title: str = getattr(entry, "title", "No title")
        author: str = getattr(entry, "author", "Unknown")

        if not url:
            return

        if "re-up requests" in title.lower():
            async with get_db_session() as session:
                await FeedEntryRepository(session).create(
                    feed_id=feed_id,
                    entry_url=url,
                    title=title,
                    clean_title=title,
                    author=author,
                    thread_tags=[],
                    matched_artists=[],
                    download_links=[],
                    published_at=None,
                )
            return

        parsed = await self._scraper.parse_thread(url, title, author)
        if parsed is None:
            log.debug("Failed to parse thread or thread too old: %s", url)
            return

        log.info("Parsed thread: %s | tags: %s | artists: %s", 
                 parsed.clean_title[:60], parsed.content_tags, parsed.artist_labels)

        # Store the entry in database
        async with get_db_session() as session:
            db_entry = await FeedEntryRepository(session).create(
                feed_id=feed_id,
                entry_url=url,
                title=parsed.title,
                clean_title=parsed.clean_title,
                author=parsed.author,
                thread_tags=parsed.content_tags,
                matched_artists=[],
                download_links=parsed.download_links,
                published_at=parsed.published_at,
            )
            feed_entry_db_id = db_entry.id

        async with get_db_session() as session:
            guild_repo = GuildRepository(session)
            guilds = await guild_repo.get_all_active()

        log.debug("Processing entry for %d active guilds", len(guilds))

        enqueued_count = 0
        for guild in guilds:
            if not guild.leaks_channel_id:
                log.warning(
                    "Guild %s (%s) has no leaks_channel_id — run /setup in your Discord server to configure a channel",
                    guild.discord_id, guild.name
                )
                continue

            matched = await self._match_artists_for_guild(guild, parsed)

            # Home guild gets ALL threads. Other guilds only get matched artists.
            is_home_guild = guild.discord_id == self._settings.home_guild_id
            
            if not is_home_guild and not matched:
                log.debug(
                    "Guild %s (%s) is not home guild and has no matched artists",
                    guild.discord_id, guild.name
                )
                continue

            if not is_home_guild:
                log.debug(
                    "Guild %s (%s) matched %d artists: %s",
                    guild.discord_id, guild.name, len(matched),
                    [f"{ga.artist.name_display}" for ga in matched]
                )

            async with get_db_session() as session:
                g_repo = GuildRepository(session)
                settings = await g_repo.get_settings(guild.id)
                recognized_sites = (settings.recognized_sites or {}) if settings else {}

            job = NotificationJob(
                guild=guild,
                thread=parsed,
                feed_entry_db_id=feed_entry_db_id,
                matched_guild_artists=matched,
                recognized_sites=recognized_sites,
            )
            await self._dispatcher.enqueue(job)
            enqueued_count += 1

        if enqueued_count == 0:
            log.warning("No guilds eligible for notification: %s", url)
        else:
            log.info("Enqueued %d notifications for thread: %s", enqueued_count, parsed.clean_title[:60])

    async def _match_artists_for_guild(
        self, guild: Guild, thread: "ParsedThread"
    ) -> list[GuildArtist]:
        import re
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        from shared.db.models import GuildArtist as GA

        async with get_db_session() as session:
            result = await session.execute(
                select(GA)
                .where(GA.guild_id == guild.id, GA.is_active == True)
                .options(selectinload(GA.artist))
            )
            guild_artists: list[GuildArtist] = list(result.scalars().all())

        if not guild_artists:
            log.debug("Guild %s has no tracked artists", guild.discord_id)
            return []

        safe_text = " ".join(
            [thread.clean_title.lower()] + [a.lower() for a in thread.artist_labels]
        )
        
        log.debug(
            "Matching against text: %s",
            safe_text[:80]
        )

        matched: list[GuildArtist] = []
        for ga in guild_artists:
            name = ga.artist.name_normalized
            if re.search(r"\b" + re.escape(name) + r"\b", safe_text):
                log.debug("Matched artist: %s", ga.artist.name_display)
                matched.append(ga)
            else:
                log.debug("No match for artist: %s", ga.artist.name_display)

        return matched

    async def _deletion_loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.deletion_check_interval_seconds)
            try:
                await self._run_deletion_check()
            except Exception:
                log.exception("Unhandled error in deletion check loop")

    async def _run_deletion_check(self) -> None:
        async with get_db_session() as session:
            entries = await FeedEntryRepository(session).get_active_tracked_entries()

        if not entries:
            return

        log.info("Deletion check: inspecting %d tracked entries", len(entries))
        deleted_count = 0

        for entry in entries:
            exists = await self._scraper.check_thread_exists(entry.entry_url)
            if exists:
                continue

            log.info("Thread gone (404) — removing Discord messages: %s", entry.entry_url)

            async with get_db_session() as session:
                gfe_repo = GuildFeedEntryRepository(session)
                guild_deliveries = await gfe_repo.get_active_for_entry(entry.id)

            for gfe in guild_deliveries:
                channel = self._bot.get_channel(gfe.channel_id)
                if channel is None:
                    continue
                try:
                    import discord as _discord
                    if isinstance(channel, _discord.TextChannel):
                        msg = await channel.fetch_message(gfe.message_id)
                        await msg.delete()
                        log.info("Deleted message %s in guild %s", gfe.message_id, gfe.guild_id)
                except _discord.NotFound:
                    pass
                except Exception:
                    log.exception("Failed to delete message %s", gfe.message_id)

                async with get_db_session() as session:
                    await GuildFeedEntryRepository(session).mark_deleted(gfe.guild_id, entry.id)

                await asyncio.sleep(0.3)

            async with get_db_session() as session:
                await FeedEntryRepository(session).mark_deleted(entry.entry_url)

            deleted_count += 1

        if deleted_count:
            log.info("Deletion check complete — removed %d thread(s)", deleted_count)