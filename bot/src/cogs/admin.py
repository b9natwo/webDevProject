"""
bot/src/cogs/admin.py
Server administration slash commands.

/setup   — Configure the bot's channels for this server (one-time or update)
/config  — View or update server settings (notification format, filters)
/ban     — Bot-owner command to ban a user from using the bot
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.src.utils.rate_limit import is_bot_owner, is_guild_admin
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.repositories.user_repo import UserRepository
from shared.db.session import get_db_session

log = logging.getLogger(__name__)


class Admin(commands.Cog):
    """Server setup and configuration commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /setup ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="setup",
        description="Configure Prefix Hub channels for this server.",
    )
    @app_commands.describe(
        leaks_channel="Channel where new leak notifications will be posted",
        audit_channel="Optional: channel for admin audit logs",
        artists_channel="Optional: channel for artist list display",
        polls_channel="Optional: channel for poll forwarding",
    )
    @is_guild_admin()
    async def setup(
        self,
        interaction: discord.Interaction,
        leaks_channel: discord.TextChannel,
        audit_channel: Optional[discord.TextChannel] = None,
        artists_channel: Optional[discord.TextChannel] = None,
        polls_channel: Optional[discord.TextChannel] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("⚠️ Server-only command.", ephemeral=True)
            return

        async with get_db_session() as session:
            repo = GuildRepository(session)
            # Ensure guild record exists
            await repo.get_or_create(
                discord_id=interaction.guild.id,
                name=interaction.guild.name,
                owner_discord_id=interaction.guild.owner_id or 0,
            )
            await repo.update_channels(
                interaction.guild.id,
                leaks_channel_id=leaks_channel.id,
                audit_channel_id=audit_channel.id if audit_channel else None,
                artists_channel_id=artists_channel.id if artists_channel else None,
                polls_channel_id=polls_channel.id if polls_channel else None,
            )

        # Verify the bot can actually send in the leaks channel
        perms = leaks_channel.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            await interaction.followup.send(
                f"⚠️ Setup saved, but I'm missing **Send Messages** or **Embed Links** permission in {leaks_channel.mention}. "
                f"Please fix this or notifications won't be delivered.",
                ephemeral=True,
            )
            return

        lines = [f"✅ **Prefix Hub configured!**\n"]
        lines.append(f"**Leaks channel:** {leaks_channel.mention}")
        if audit_channel:
            lines.append(f"**Audit channel:** {audit_channel.mention}")
        if artists_channel:
            lines.append(f"**Artists channel:** {artists_channel.mention}")
        if polls_channel:
            lines.append(f"**Polls channel:** {polls_channel.mention}")
        lines.append("\nUse `/track <artist>` to start tracking artists.")

        await interaction.followup.send("\n".join(lines), ephemeral=True)
        log.info("Guild %s completed setup (leaks=%s)", interaction.guild.id, leaks_channel.id)

    # ── /config ────────────────────────────────────────────────────────

    @app_commands.command(name="config", description="View or update this server's Prefix Hub settings.")
    @is_guild_admin()
    async def config(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("⚠️ Server-only command.", ephemeral=True)
            return

        async with get_db_session() as session:
            repo = GuildRepository(session)
            guild = await repo.get_by_discord_id(interaction.guild.id)

        if not guild:
            await interaction.followup.send(
                "⚠️ This server isn't registered yet. Run `/setup` first.",
                ephemeral=True,
            )
            return

        def channel_display(cid: Optional[int]) -> str:
            if not cid:
                return "*(not set)*"
            ch = interaction.guild.get_channel(cid)
            return ch.mention if ch else f"#{cid} *(deleted?)*"

        embed = discord.Embed(
            title=f"⚙️ Config — {interaction.guild.name}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Leaks Channel", value=channel_display(guild.leaks_channel_id), inline=True)
        embed.add_field(name="Audit Channel", value=channel_display(guild.audit_channel_id), inline=True)
        embed.add_field(name="Artists Channel", value=channel_display(guild.artists_channel_id), inline=True)
        embed.add_field(name="Polls Channel", value=channel_display(guild.polls_channel_id), inline=True)
        embed.add_field(name="Premium Tier", value=guild.premium_tier.value.title(), inline=True)
        embed.add_field(name="Active", value="Yes" if guild.is_active else "No", inline=True)

        if guild.settings:
            fmt = guild.settings.notification_format or "embed"
            embed.add_field(name="Notification Format", value=fmt.title(), inline=True)
            min_age = guild.settings.filter_min_age_minutes
            embed.add_field(name="Min Post Age (min)", value=str(min_age), inline=True)

        embed.set_footer(text="Use /setup to change channel assignments.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /ban (bot-owner only) ──────────────────────────────────────────

    @app_commands.command(name="ban", description="[Owner] Ban a user from using the bot.")
    @app_commands.describe(
        user="Discord user to ban",
        reason="Reason for the ban",
        unban="Set to True to remove an existing ban",
    )
    @is_bot_owner()
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: Optional[str] = None,
        unban: bool = False,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            repo = UserRepository(session)
            db_user = await repo.get_by_discord_id(user.id)
            if not db_user:
                await interaction.followup.send("⚠️ That user hasn't used the bot yet.", ephemeral=True)
                return
            await repo.set_banned(user.id, not unban, reason=reason if not unban else None)

        action = "unbanned" if unban else "banned"
        msg = f"✅ **{user}** has been {action}."
        if not unban and reason:
            msg += f"\nReason: {reason}"
        await interaction.followup.send(msg, ephemeral=True)
        log.info("User %s %s by %s (reason=%s)", user.id, action, interaction.user.id, reason)

    # ── Ban enforcement guard ──────────────────────────────────────────

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Globally check if the interacting user is banned.
        This runs before every slash command handled by this cog.
        The bot.on_app_command_error handler will catch any exceptions here.
        """
        from shared.db.repositories.user_repo import UserRepository
        from shared.db.session import get_db_session as _get_db

        async with _get_db() as session:
            user = await UserRepository(session).get_by_discord_id(interaction.user.id)
            if user and user.is_banned:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⛔ You have been banned from using Prefix Hub.",
                        ephemeral=True,
                    )
                return False
        return True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
