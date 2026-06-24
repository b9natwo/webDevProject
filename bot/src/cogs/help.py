"""
bot/src/cogs/help.py
/help command — contextual command reference.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    """Help and information commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Show all available Prefix Hub commands.")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="📖 Prefix Hub — Commands",
            description=(
                "Prefix Hub monitors **leaked.cx** for new music drops and notifies "
                "your server when tracked artists appear."
            ),
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="🎤 Artist Tracking",
            value=(
                "`/track <artist>` — Add an artist (admin)\n"
                "`/untrack <artist>` — Remove an artist (admin)\n"
                "`/artists` — List all tracked artists\n"
                "`/subscribe <artist>` — Get pings for an artist\n"
                "`/unsubscribe <artist>` — Stop getting pings"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Setup & Config",
            value=(
                "`/setup` — Configure channels (admin)\n"
                "`/config` — View current settings (admin)"
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Analytics",
            value=(
                "`/stats` — Server activity statistics\n"
                "`/recent` — Most recently detected leaks"
            ),
            inline=False,
        )
        embed.add_field(
            name="⭐ Premium",
            value=(
                "`/premium` — View your premium status\n"
                "`/premiuminfo` — Compare tier features\n"
                "`/invite` — Get a bot invite link (Standard+)"
            ),
            inline=False,
        )
        embed.set_footer(text="Prefix Hub • leaked.cx notifications")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
