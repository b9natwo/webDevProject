"""
bot/src/cogs/feeds.py
Feed management slash commands (bot-owner only).
Regular users don't manage feeds — leaked.cx is the fixed source.

/feeds list   — List all configured RSS feeds and their status
/feeds enable  — Re-enable a disabled feed
/feeds disable — Temporarily disable a feed
/feeds refresh — Trigger an immediate poll cycle
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.src.utils.rate_limit import is_bot_owner
from shared.db.repositories.feed_repo import FeedRepository
from shared.db.session import get_db_session

log = logging.getLogger(__name__)


class Feeds(commands.Cog):
    """Feed configuration commands (bot-owner only)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    feeds_group = app_commands.Group(
        name="feeds",
        description="Manage RSS feed configuration (bot owner only).",
    )

    @feeds_group.command(name="list", description="List all configured RSS feeds.")
    @is_bot_owner()
    async def feeds_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            repo = FeedRepository(session)
            feeds = await repo.get_all()

        if not feeds:
            await interaction.followup.send("No feeds configured.", ephemeral=True)
            return

        embed = discord.Embed(title="📡 RSS Feeds", color=discord.Color.blurple())
        for feed in feeds:
            status = "✅ Active" if feed.is_active else "❌ Disabled"
            failures = f" | ⚠️ {feed.consecutive_failures} failures" if feed.consecutive_failures else ""
            last_polled = (
                discord.utils.format_dt(feed.last_polled_at, "R") if feed.last_polled_at else "Never"
            )
            embed.add_field(
                name=f"[{feed.id}] {feed.name}",
                value=f"{status}{failures}\nLast polled: {last_polled}\n`{feed.rss_url}`",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @feeds_group.command(name="disable", description="Temporarily disable a feed.")
    @app_commands.describe(feed_id="Feed ID from /feeds list")
    @is_bot_owner()
    async def feeds_disable(self, interaction: discord.Interaction, feed_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            repo = FeedRepository(session)
            feed = await repo.get_by_id(feed_id)
            if not feed:
                await interaction.followup.send(f"⚠️ No feed with ID {feed_id}.", ephemeral=True)
                return
            feed.is_active = False
        await interaction.followup.send(f"✅ Feed **{feed.name}** disabled.", ephemeral=True)
        log.info("Feed %s disabled by %s", feed_id, interaction.user.id)

    @feeds_group.command(name="enable", description="Re-enable a disabled feed.")
    @app_commands.describe(feed_id="Feed ID from /feeds list")
    @is_bot_owner()
    async def feeds_enable(self, interaction: discord.Interaction, feed_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            repo = FeedRepository(session)
            feed = await repo.get_by_id(feed_id)
            if not feed:
                await interaction.followup.send(f"⚠️ No feed with ID {feed_id}.", ephemeral=True)
                return
            feed.is_active = True
            feed.consecutive_failures = 0
        await interaction.followup.send(f"✅ Feed **{feed.name}** enabled.", ephemeral=True)
        log.info("Feed %s enabled by %s", feed_id, interaction.user.id)

    @feeds_group.command(name="refresh", description="Trigger an immediate poll of all active feeds.")
    @is_bot_owner()
    async def feeds_refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        poller = getattr(self.bot, "feed_poller", None)
        if not poller:
            await interaction.followup.send("⚠️ Feed poller not initialised.", ephemeral=True)
            return

        await interaction.followup.send("🔄 Manual poll triggered — check logs for results.", ephemeral=True)
        # Run in background so the interaction doesn't time out
        import asyncio
        asyncio.create_task(poller._poll_all_feeds())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Feeds(bot))
