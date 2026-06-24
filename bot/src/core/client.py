"""
bot/src/core/client.py
PrefixHubBot — the main discord.py client subclass.
Owns startup, shutdown, cog loading, and shared service instances.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from bot.src.services.feed_poller import FeedPollerService
from bot.src.services.image_service import ImageService
from bot.src.services.notifier import NotificationDispatcher
from bot.src.services.premium_service import PremiumService
from bot.src.services.scraper import LeakedCxScraper
from shared.config import get_settings
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.session import close_engine, get_db_session

log = logging.getLogger(__name__)

_COGS = [
    "bot.src.cogs.artists",
    "bot.src.cogs.feeds",
    "bot.src.cogs.admin",
    "bot.src.cogs.premium",
    "bot.src.cogs.analytics",
    "bot.src.cogs.help",
]


class PrefixHubBot(commands.Bot):
    """
    Main bot class. Services are created here and injected into cogs
    so that cogs never instantiate their own HTTP clients or DB sessions.
    """

    def __init__(self) -> None:
        settings = get_settings()

        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = False  # We don't need member lists — reduces privileged intent usage

        super().__init__(
            command_prefix=commands.when_mentioned,  # Slash-only; prefix kept as fallback
            intents=intents,
            help_command=None,
        )

        self._settings = settings
        self._http_session: Optional[aiohttp.ClientSession] = None

        # Services — instantiated in setup_hook, available to all cogs
        self.scraper: Optional[LeakedCxScraper] = None
        self.image_service: Optional[ImageService] = None
        self.notifier: Optional[NotificationDispatcher] = None
        self.feed_poller: Optional[FeedPollerService] = None
        self.premium_service: PremiumService = PremiumService()

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def setup_hook(self) -> None:
        """
        Called by discord.py before connecting to the gateway.
        Set up services and load cogs here — NOT in on_ready.
        """
        # Create a single shared aiohttp session for all outbound HTTP.
        # unsafe=True is required so cookies set on the login POST (which may
        # have an IP/non-FQDN origin) are stored and re-sent on subsequent
        # requests to leaked.cx — without this the RSS fetches get 403.
        connector = aiohttp.TCPConnector(limit=20)
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        self._http_session = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=cookie_jar,
        )

        self.scraper = LeakedCxScraper(self._http_session)
        self.image_service = ImageService(self._http_session)
        self.notifier = NotificationDispatcher(self, self.image_service)
        self.feed_poller = FeedPollerService(self)

        # Load all cogs
        for cog_path in _COGS:
            try:
                await self.load_extension(cog_path)
                log.info("Loaded cog: %s", cog_path)
            except Exception:
                log.exception("Failed to load cog: %s", cog_path)

        # Sync slash commands to Discord
        synced = await self.tree.sync()
        log.info("Synced %d slash commands", len(synced))

    async def on_ready(self) -> None:
        """Called when the bot has connected and is fully operational."""
        log.info(
            "Bot ready — logged in as %s (ID: %s) | Guilds: %d",
            self.user,
            self.user.id,
            len(self.guilds),
        )

        # Start notification workers
        await self.notifier.start()

        # Authenticate with leaked.cx then start polling
        await self.feed_poller.start(self.scraper, self.notifier)

        # Update presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="leaked.cx for new drops",
            )
        )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Register a new guild in the database when the bot is invited."""
        async with get_db_session() as session:
            repo = GuildRepository(session)
            _, created = await repo.get_or_create(
                discord_id=guild.id,
                name=guild.name,
                owner_discord_id=guild.owner_id or 0,
                icon_hash=str(guild.icon) if guild.icon else None,
            )
        if created:
            log.info("Joined new guild: %s (ID: %s)", guild.name, guild.id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Mark a guild inactive when the bot is removed."""
        async with get_db_session() as session:
            repo = GuildRepository(session)
            await repo.deactivate(guild.id)
        log.info("Removed from guild: %s (ID: %s)", guild.name, guild.id)

    async def close(self) -> None:
        """Clean shutdown."""
        log.info("Shutting down...")
        
        # Close any background tasks properly
        if hasattr(self, 'feed_poller') and self.feed_poller:
            await self.feed_poller.stop()
        
        # Cancel any remaining tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Close session
        if hasattr(self, 'session') and self.session:
            await self.session.close()
        
        await super().close()

    # ── Error handling ─────────────────────────────────────────────────

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """
        Global slash command error handler.
        Surfaces friendly messages for known error types;
        logs unexpected exceptions at ERROR level.
        """
        from bot.src.services.premium_service import EntitlementError

        original = getattr(error, "original", error)

        if isinstance(original, EntitlementError):
            await self._send_error(interaction, str(original))
            return

        if isinstance(error, discord.app_commands.MissingPermissions):
            await self._send_error(
                interaction,
                f"You need the **{', '.join(error.missing_permissions)}** permission(s) to use this command.",
            )
            return

        if isinstance(error, discord.app_commands.CommandOnCooldown):
            await self._send_error(
                interaction,
                f"Slow down! Try again in **{error.retry_after:.1f}s**.",
            )
            return

        if isinstance(error, discord.app_commands.BotMissingPermissions):
            await self._send_error(
                interaction,
                f"I need the **{', '.join(error.missing_permissions)}** permission(s) to do that.",
            )
            return

        log.exception(
            "Unhandled slash command error in %s: %s",
            getattr(interaction.command, "name", "unknown"),
            original,
        )
        await self._send_error(
            interaction,
            "Something went wrong. The error has been logged.",
        )

    @staticmethod
    async def _send_error(interaction: discord.Interaction, message: str) -> None:
        """Send an ephemeral error message, handling already-responded interactions."""
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"⚠️ {message}", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ {message}", ephemeral=True)
        except discord.HTTPException:
            pass
