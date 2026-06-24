"""
bot/src/cogs/analytics.py
Analytics and statistics slash commands.

/stats   — Server or bot-wide statistics
/recent  — Show the most recently detected leaks
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot.src.utils.rate_limit import is_bot_owner
from shared.db.repositories.artist_repo import GuildArtistRepository
from shared.db.repositories.feed_repo import FeedEntryRepository, NotificationLogRepository
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.session import get_db_session

log = logging.getLogger(__name__)


class Analytics(commands.Cog):
    """Statistics and analytics commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="stats", description="View activity statistics for this server or the bot globally.")
    @app_commands.describe(global_stats="Set to True to show bot-wide stats (bot owner only)")
    async def stats(
        self,
        interaction: discord.Interaction,
        global_stats: bool = False,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if global_stats:
            # Check owner permission
            app_info = await self.bot.application_info()
            if interaction.user.id != app_info.owner.id:
                await interaction.followup.send("⚠️ Bot-owner only.", ephemeral=True)
                return
            await self._send_global_stats(interaction)
        else:
            await self._send_guild_stats(interaction)

    async def _send_guild_stats(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.followup.send("⚠️ Run in a server or use `global_stats: True`.", ephemeral=True)
            return

        async with get_db_session() as session:
            guild_repo = GuildRepository(session)
            guild = await guild_repo.get_by_discord_id(interaction.guild.id)
            if not guild:
                await interaction.followup.send("⚠️ Server not registered.", ephemeral=True)
                return

            ga_repo = GuildArtistRepository(session)
            tracked = await ga_repo.count_for_guild(guild.id)

            notif_repo = NotificationLogRepository(session)
            since_7d = datetime.now(timezone.utc) - timedelta(days=7)
            since_30d = datetime.now(timezone.utc) - timedelta(days=30)
            notifications_7d = await notif_repo.count_for_guild(guild.id, since=since_7d)
            notifications_30d = await notif_repo.count_for_guild(guild.id, since=since_30d)

        embed = discord.Embed(
            title=f"📊 Stats — {interaction.guild.name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Tracked Artists", value=str(tracked), inline=True)
        embed.add_field(name="Notifications (7d)", value=str(notifications_7d), inline=True)
        embed.add_field(name="Notifications (30d)", value=str(notifications_30d), inline=True)
        embed.add_field(name="Premium Tier", value=guild.premium_tier.value.title(), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _send_global_stats(self, interaction: discord.Interaction) -> None:
        from sqlalchemy import func, select
        from shared.db.models import FeedEntry, Guild, GuildArtist, User

        async with get_db_session() as session:
            total_guilds = (await session.execute(
                select(func.count()).select_from(Guild).where(Guild.is_active == True)  # noqa: E712
            )).scalar_one()
            total_users = (await session.execute(
                select(func.count()).select_from(User)
            )).scalar_one()
            total_entries = (await session.execute(
                select(func.count()).select_from(FeedEntry)
            )).scalar_one()
            total_tracked = (await session.execute(
                select(func.count()).select_from(GuildArtist).where(GuildArtist.is_active == True)  # noqa: E712
            )).scalar_one()

        embed = discord.Embed(
            title="📊 Prefix Hub — Global Stats",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Active Servers", value=str(total_guilds), inline=True)
        embed.add_field(name="Registered Users", value=str(total_users), inline=True)
        embed.add_field(name="Feed Entries Seen", value=str(total_entries), inline=True)
        embed.add_field(name="Active Artist Trackings", value=str(total_tracked), inline=True)
        embed.add_field(name="Bot Latency", value=f"{self.bot.latency * 1000:.1f}ms", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="recent", description="Show the most recently detected leaks.")
    @app_commands.describe(limit="Number of entries to show (max 20)")
    async def recent(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 1, 20] = 10,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            repo = FeedEntryRepository(session)
            entries = await repo.get_recent(limit=limit)

        if not entries:
            await interaction.followup.send("No entries found yet.", ephemeral=True)
            return

        lines = []
        for e in entries:
            ts = discord.utils.format_dt(e.first_seen_at, "R") if e.first_seen_at else ""
            artists = ", ".join(e.matched_artists[:3]) if e.matched_artists else "*(no match)*"
            deleted = " ~~DELETED~~" if e.is_deleted else ""
            lines.append(f"[{e.clean_title[:50]}]({e.entry_url}) — {artists} {ts}{deleted}")

        from bot.src.utils.paginator import PaginatedView
        view = PaginatedView(items=lines, title="🎵 Recent Leaks")
        await view.send(interaction)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Analytics(bot))
