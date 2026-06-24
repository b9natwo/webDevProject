"""
bot/src/services/notifier.py
Async notification queue that decouples feed ingestion from Discord delivery.

The feed poller enqueues NotificationJob objects.
Worker coroutines drain the queue, build embeds, and send them to Discord.
This ensures a slow guild never blocks notifications to other guilds.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import discord
from discord.ui import Button, View

from bot.src.services.image_service import ImageService
from bot.src.services.scraper import ParsedThread
from shared.config import get_settings
from shared.db.models import Guild, GuildArtist
from shared.db.repositories.feed_repo import GuildFeedEntryRepository, NotificationLogRepository
from shared.db.session import get_db_session

if TYPE_CHECKING:
    from bot.src.core.client import PrefixHubBot

log = logging.getLogger(__name__)

DEFAULT_THUMBNAIL = (
    "https://media.discordapp.net/attachments/1367275986466635858/"
    "1457623614726865031/prefixhub.png"
)


@dataclass
class NotificationJob:
    """
    A fully-resolved notification ready for dispatch to Discord.
    One job is created per (guild, thread) pair that passes matching.
    """
    guild: Guild
    thread: ParsedThread
    feed_entry_db_id: int
    matched_guild_artists: list[GuildArtist] = field(default_factory=list)
    recognized_sites: dict[str, str] = field(default_factory=dict)


class SupportView(View):
    """Like and Dislike buttons that link directly to leaked.cx thread reactions."""

    def __init__(self, reaction_path: str) -> None:
        super().__init__(timeout=None)
        if reaction_path:
            self.add_item(Button(
                label="Like",
                style=discord.ButtonStyle.blurple,
                url=f"https://leaked.cx{reaction_path}/react?reaction_id=1",
                emoji="<:like:1469861411038560258>",
            ))
            self.add_item(Button(
                label="Dislike",
                style=discord.ButtonStyle.blurple,
                url=f"https://leaked.cx{reaction_path}/react?reaction_id=11",
                emoji="<:dislike:1469861384714977310>",
            ))


class NotificationDispatcher:
    """
    Manages a bounded async queue of NotificationJob objects and runs
    N worker coroutines that drain it.

    Workers respect Discord rate limits via asyncio.sleep after each send,
    and retry on transient failures with exponential backoff (up to 3 attempts).
    """

    _RETRY_DELAYS = (1, 4, 16)  # seconds between retries
    _POST_SEND_DELAY = 0.5       # politeness delay after each Discord API call

    def __init__(self, bot: "PrefixHubBot", image_service: ImageService) -> None:
        self._bot = bot
        self._image_service = image_service
        self._queue: asyncio.Queue[NotificationJob] = asyncio.Queue(maxsize=500)
        self._workers: list[asyncio.Task] = []
        self._settings = get_settings()

    async def start(self) -> None:
        """Spawn worker coroutines. Call once after bot is ready."""
        n = self._settings.notification_queue_workers
        for i in range(n):
            task = asyncio.create_task(self._worker(i), name=f"notifier-worker-{i}")
            self._workers.append(task)
        log.info("Notification dispatcher started with %d workers", n)

    async def stop(self) -> None:
        """Cancel all worker tasks during shutdown."""
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        log.info("Notification dispatcher stopped")

    async def enqueue(self, job: NotificationJob) -> None:
        """
        Add a job to the queue.
        If the queue is full, drop the job and log a warning.
        """
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            log.warning(
                "Notification queue full — dropping job for guild %s thread %s",
                job.guild.discord_id,
                job.thread.url,
            )

    async def _worker(self, worker_id: int) -> None:
        """
        Continuously drain the queue.
        Each iteration pops one job, attempts delivery, and marks done.
        """
        log.debug("Worker %d started", worker_id)
        while True:
            job = await self._queue.get()
            try:
                await self._dispatch(job)
            except Exception:
                log.exception("Worker %d unhandled error processing job", worker_id)
            finally:
                self._queue.task_done()

    async def _dispatch(self, job: NotificationJob) -> None:
        """
        Build the Discord embed and send it to the configured leaks channel.
        Retries up to 3 times on transient failures.
        """
        channel = self._bot.get_channel(job.guild.leaks_channel_id)
        if not isinstance(channel, discord.TextChannel):
            log.debug(
                "Leaks channel %s not found for guild %s",
                job.guild.leaks_channel_id,
                job.guild.discord_id,
            )
            return

        embed, view = await self._build_embed(job)
        role_mentions = [
            f"<@&{ga.role_id}>"
            for ga in job.matched_guild_artists
            if ga.role_id
        ]
        content = " ".join(role_mentions) if role_mentions else None

        message: Optional[discord.Message] = None
        for attempt, delay in enumerate(self._RETRY_DELAYS, start=1):
            try:
                message = await channel.send(content=content, embed=embed, view=view)
                break
            except discord.HTTPException as exc:
                if exc.status == 429:
                    retry_after = getattr(exc, "retry_after", delay)
                    log.warning("Rate limited — sleeping %.1fs", retry_after)
                    await asyncio.sleep(retry_after)
                elif attempt < len(self._RETRY_DELAYS):
                    log.warning(
                        "Send failed (attempt %d/%d) — %s",
                        attempt, len(self._RETRY_DELAYS), exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    log.error(
                        "Failed to deliver notification to guild %s after %d attempts: %s",
                        job.guild.discord_id, attempt, exc,
                    )
                    return

        if message is None:
            return

        log.info(
            "Posted → guild=%s title=%.60s mentions=%d links=%d",
            job.guild.name,
            embed.title,
            len(role_mentions),
            len(job.thread.download_links),
        )

        # Persist the delivery record
        async with get_db_session() as session:
            gfe_repo = GuildFeedEntryRepository(session)
            notif_repo = NotificationLogRepository(session)
            try:
                await gfe_repo.record(
                    guild_db_id=job.guild.id,
                    feed_entry_db_id=job.feed_entry_db_id,
                    channel_id=channel.id,
                    message_id=message.id,
                )
                await notif_repo.record(
                    user_db_id=None,
                    feed_entry_db_id=job.feed_entry_db_id,
                    guild_db_id=job.guild.id,
                    channel_id=channel.id,
                    message_id=message.id,
                )
            except Exception:
                log.exception("Failed to persist delivery record for message %s", message.id)

        await asyncio.sleep(self._POST_SEND_DELAY)

    async def _build_embed(self, job: NotificationJob) -> tuple[discord.Embed, View]:
        """
        Construct a rich Discord embed from a ParsedThread and guild context.
        """
        thread = job.thread

        # ── Description (formatted download links) ───────────────────
        if thread.download_links:
            lines: list[str] = []
            for url, filename in zip(thread.download_links, thread.download_filenames):
                emoji = next(
                    (e for site, e in job.recognized_sites.items() if site in url.lower()),
                    "",
                )
                if "discord.gg" in url or "discord.com/invite/" in url:
                    invite_code = url.split("discord.gg/")[-1].split("discord.com/invite/")[-1]
                    display = f"[Discord](https://discord.com/invite/{invite_code})"
                else:
                    display = f"[{filename}]({url})"
                lines.append(f"{emoji} {display}".strip() if emoji else display)
            description = "\n".join(lines)
        else:
            # Fall back to text excerpt from post body
            content_div = thread.raw_soup.find("div", class_="bbWrapper") if thread.raw_soup else None
            if content_div:
                raw_text = content_div.get_text(separator=" ", strip=True)
                excerpt = raw_text[:300].rsplit(" ", 1)[0].strip()
                description = (excerpt + "…") if excerpt else "No description provided."
            else:
                description = "No description provided."

        # ── Thumbnail via Last.fm ────────────────────────────────────
        # Priority: artist from thread labels → first matched artist → clean title left part
        artist_for_image: Optional[str] = None
        if thread.artist_labels:
            artist_for_image = thread.artist_labels[0]
        elif job.matched_guild_artists:
            artist_for_image = job.matched_guild_artists[0].artist.name_display
        elif " - " in thread.clean_title:
            artist_for_image = thread.clean_title.split(" - ")[0].strip()

        thumbnail_url = DEFAULT_THUMBNAIL
        if artist_for_image:
            try:
                thumbnail_url = await self._image_service.get_artist_image(artist_for_image)
            except Exception:
                pass

        # ── Embed title ──────────────────────────────────────────────
        tags_prefix = " ".join(sorted(thread.content_tags))
        title_parts = [p for p in [tags_prefix, thread.clean_title] if p.strip()]
        embed_title = " ".join(title_parts).strip() or thread.title

        # ── Build embed ──────────────────────────────────────────────
        embed = discord.Embed(
            title=embed_title[:256],
            url=thread.url,
            description=description[:4096],
            color=discord.Color.random(),
            timestamp=thread.published_at,
        )
        embed.set_thumbnail(url=thumbnail_url)
        embed.set_author(
            name=thread.author[:256] if thread.author else "Unknown",
            icon_url=thread.author_avatar_url,
        )
        embed.set_footer(text="leaked.cx")

        view = SupportView(thread.reaction_path)
        return embed, view
