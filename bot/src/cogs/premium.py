"""
bot/src/cogs/premium.py
Premium tier information and management commands.

/premium        — Show the user's current tier and limits
/premium info   — Explain the different tiers
/premium grant  — Bot-owner: manually grant premium to a user or guild
/invite         — Generate a bot invite link (Standard+ only)
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.src.services.premium_service import PremiumService
from bot.src.utils.rate_limit import is_bot_owner
from shared.db.models import PremiumTier
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.repositories.user_repo import UserRepository
from shared.db.session import get_db_session

log = logging.getLogger(__name__)

UPGRADE_URL = "https://prefixhub.xyz/premium"


class Premium(commands.Cog):
    """Premium tier commands."""

    def __init__(self, bot: commands.Bot, premium_service: PremiumService) -> None:
        self.bot = bot
        self.premium_service = premium_service

    # ── /premium ───────────────────────────────────────────────────────

    @app_commands.command(name="premium", description="View your premium status and server limits.")
    async def premium(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        user_tier = await self.premium_service.resolve_user_tier(interaction.user.id)
        guild_tier = (
            await self.premium_service.resolve_guild_tier(interaction.guild.id)
            if interaction.guild
            else PremiumTier.FREE
        )

        embed = discord.Embed(
            title="⭐ Prefix Hub Premium",
            color=discord.Color.gold() if user_tier != PremiumTier.FREE else discord.Color.blurple(),
        )
        embed.add_field(
            name="Your Account Tier",
            value=f"**{self.premium_service.tier_display_name(user_tier)}**",
            inline=True,
        )
        if interaction.guild:
            embed.add_field(
                name="This Server's Tier",
                value=f"**{self.premium_service.tier_display_name(guild_tier)}**",
                inline=True,
            )
            max_artists = self.premium_service.get_max_artists(guild_tier)
            artists_display = str(max_artists) if max_artists < 2**30 else "Unlimited"
            embed.add_field(
                name="Artist Tracking Limit",
                value=artists_display,
                inline=True,
            )

        if user_tier == PremiumTier.FREE:
            embed.add_field(
                name="Upgrade",
                value=(
                    f"Get **Standard** for $5/mo or **Pro** for $15/mo.\n"
                    f"[View plans]({UPGRADE_URL})"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /premium info ──────────────────────────────────────────────────

    @app_commands.command(name="premiuminfo", description="Compare Prefix Hub premium tiers.")
    async def premium_info(self, interaction: discord.Interaction) -> None:
        from shared.config import get_settings
        s = get_settings()

        embed = discord.Embed(
            title="⭐ Prefix Hub Premium Tiers",
            description=(
                "Upgrade to track more artists and unlock premium features.\n"
                f"[View plans & upgrade]({UPGRADE_URL})"
            ),
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="🆓 Free",
            value=(
                f"• Track up to **{s.free_max_artists} artists**\n"
                f"• **{s.free_max_guilds} server**\n"
                "• Standard notifications"
            ),
            inline=True,
        )
        embed.add_field(
            name="⭐ Standard — $5/mo",
            value=(
                f"• Track up to **{s.standard_max_artists} artists**\n"
                f"• Up to **{s.standard_max_guilds} servers**\n"
                "• Priority notifications\n"
                "• Bot invite access"
            ),
            inline=True,
        )
        embed.add_field(
            name="💎 Pro — $15/mo",
            value=(
                "• **Unlimited** artist tracking\n"
                "• **Unlimited** servers\n"
                "• Priority notifications\n"
                "• Bot invite access\n"
                "• Dashboard analytics"
            ),
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /grant (owner only) ────────────────────────────────────────────

    @app_commands.command(
        name="grant",
        description="[Owner] Manually grant premium to a user or server.",
    )
    @app_commands.describe(
        target_user="User to grant premium to (leave blank to target the current server)",
        tier="Premium tier to grant",
    )
    @is_bot_owner()
    async def grant(
        self,
        interaction: discord.Interaction,
        tier: PremiumTier,
        target_user: Optional[discord.User] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if target_user:
            result = await self.premium_service.grant_user_premium(target_user.id, tier)
            if result:
                await interaction.followup.send(
                    f"✅ Granted **{tier.value}** to user **{target_user}**.",
                    ephemeral=True,
                )
            else:
                # User doesn't exist in DB yet — create them first
                async with get_db_session() as session:
                    user_repo = UserRepository(session)
                    await user_repo.get_or_create(
                        discord_id=target_user.id,
                        username=str(target_user),
                    )
                await self.premium_service.grant_user_premium(target_user.id, tier)
                await interaction.followup.send(
                    f"✅ Created and granted **{tier.value}** to **{target_user}**.",
                    ephemeral=True,
                )
        elif interaction.guild:
            result = await self.premium_service.grant_guild_premium(interaction.guild.id, tier)
            if result:
                await interaction.followup.send(
                    f"✅ Granted **{tier.value}** to server **{interaction.guild.name}**.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send("⚠️ Server not registered.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Specify a user or run in a server.", ephemeral=True)

    # ── /invite ────────────────────────────────────────────────────────

    @app_commands.command(
        name="invite",
        description="Get a link to invite Prefix Hub to your server (Standard+ only).",
    )
    async def invite(self, interaction: discord.Interaction) -> None:
        user_tier = await self.premium_service.resolve_user_tier(interaction.user.id)

        if user_tier == PremiumTier.FREE:
            await interaction.response.send_message(
                f"⭐ The bot invite link is available to **Standard** and **Pro** subscribers.\n"
                f"[Upgrade here]({UPGRADE_URL})",
                ephemeral=True,
            )
            return

        from shared.config import get_settings
        settings = get_settings()
        invite_url = (
            f"{settings.bot_invite_base_url}"
            f"?client_id={settings.discord_client_id}"
            f"&scope=bot+applications.commands"
            f"&permissions=277025508352"
        )
        await interaction.response.send_message(
            f"✅ **Invite Prefix Hub to your server:**\n{invite_url}\n\n"
            "After inviting, run `/setup` in your server to configure channels.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    premium_service = getattr(bot, "premium_service", PremiumService())
    await bot.add_cog(Premium(bot, premium_service))
