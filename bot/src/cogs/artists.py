"""
bot/src/cogs/artists.py
Slash commands for artist tracking and subscription management.
"""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.src.services.premium_service import EntitlementError, PremiumService
from bot.src.utils.paginator import PaginatedView
from bot.src.utils.rate_limit import is_guild_admin, user_cooldown
from shared.db.models import PremiumTier
from shared.db.repositories.artist_repo import ArtistRepository, GuildArtistRepository, UserArtistSubscriptionRepository
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.repositories.user_repo import UserRepository
from shared.db.session import get_db_session

log = logging.getLogger(__name__)


class Artists(commands.Cog):
    """Artist tracking and subscription management."""

    def __init__(self, bot: commands.Bot, premium_service: PremiumService) -> None:
        self.bot = bot
        self.premium_service = premium_service

    # ── /track ─────────────────────────────────────────────────────────

    @app_commands.command(name="track", description="Add an artist to this server's tracking list.")
    @app_commands.describe(
        name="Artist name to track",
        role="Optional: existing role to ping when this artist drops. Leave blank to create a new one.",
    )
    @is_guild_admin()
    async def track(
        self,
        interaction: discord.Interaction,
        name: str,
        role: Optional[discord.Role] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("⚠️ This command can only be used in a server.", ephemeral=True)
            return

        name = name.strip()
        if not name:
            await interaction.followup.send("⚠️ Artist name cannot be empty.", ephemeral=True)
            return
        if len(name) > 100:
            await interaction.followup.send("⚠️ Artist name must be 100 characters or fewer.", ephemeral=True)
            return

        async with get_db_session() as session:
            guild_repo = GuildRepository(session)
            guild = await guild_repo.get_by_discord_id(interaction.guild.id)
            if not guild:
                await interaction.followup.send("⚠️ Server not registered. Try again in a moment.", ephemeral=True)
                return

            guild_tier = guild.premium_tier

        # Tier enforcement
        try:
            await self.premium_service.assert_can_add_artist(guild.id, guild_tier)
        except EntitlementError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        # Titleize the artist name for consistent storage
        titleized_name = name.title().strip()

        # Resolve or create the Discord role
        assigned_role: Optional[discord.Role] = role
        if assigned_role is None:
            try:
                import random
                # Generate a random color for the role
                random_color = discord.Color(random.randint(0, 0xFFFFFF))
                
                assigned_role = await interaction.guild.create_role(
                    name=titleized_name,
                    color=random_color,
                    mentionable=True,
                    reason=f"Prefix Hub: tracking artist '{titleized_name}'",
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "⚠️ I don't have permission to create roles. Please create a role manually and pass it with the `role` parameter.",
                    ephemeral=True,
                )
                return

        async with get_db_session() as session:
            artist_repo = ArtistRepository(session)
            ga_repo = GuildArtistRepository(session)

            artist, _ = await artist_repo.get_or_create(titleized_name)

            # Check for duplicate
            existing = await ga_repo.get_for_guild_with_artist(guild.id, artist.id)
            if existing and existing.is_active:
                await interaction.followup.send(
                    f"⚠️ **{artist.name_display}** is already being tracked in this server.",
                    ephemeral=True,
                )
                return

            await ga_repo.add(
                guild_db_id=guild.id,
                artist_db_id=artist.id,
                role_id=assigned_role.id,
                added_by_discord_id=interaction.user.id,
            )

        # Assign the role to the user who tracked the artist
        try:
            await interaction.user.add_roles(assigned_role, reason="Prefix Hub: artist tracking")
        except discord.Forbidden:
            log.warning("Could not assign role %s to user %s", assigned_role.id, interaction.user.id)

        log.info(
            "Guild %s added artist %s (role=%s)",
            interaction.guild.id, artist.name_display, assigned_role.id,
        )
        await interaction.followup.send(
            f"✅ Now tracking **{artist.name_display}** — role: {assigned_role.mention}",
            ephemeral=True,
        )

    # ── /untrack ───────────────────────────────────────────────────────

    @app_commands.command(name="untrack", description="Remove an artist from this server's tracking list.")
    @app_commands.describe(name="Artist name to stop tracking")
    @is_guild_admin()
    async def untrack(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("⚠️ Server-only command.", ephemeral=True)
            return

        async with get_db_session() as session:
            guild_repo = GuildRepository(session)
            guild = await guild_repo.get_by_discord_id(interaction.guild.id)
            if not guild:
                await interaction.followup.send("⚠️ Server not registered.", ephemeral=True)
                return

            artist_repo = ArtistRepository(session)
            artist = await artist_repo.get_by_normalized_name(name.strip())
            if not artist:
                await interaction.followup.send(f"⚠️ No artist named **{name}** is tracked here.", ephemeral=True)
                return

            ga_repo = GuildArtistRepository(session)
            removed = await ga_repo.remove(guild.id, artist.id)

        if removed:
            await interaction.followup.send(f"✅ Stopped tracking **{artist.name_display}**.", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ **{name}** isn't in the tracking list.", ephemeral=True)

    # ── /artists ───────────────────────────────────────────────────────

    @app_commands.command(name="artists", description="View all tracked artists in this server.")
    async def artists(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("⚠️ Server-only command.", ephemeral=True)
            return

        async with get_db_session() as session:
            guild_repo = GuildRepository(session)
            guild = await guild_repo.get_by_discord_id(interaction.guild.id)
            if not guild:
                await interaction.response.send_message("⚠️ Server not registered.", ephemeral=True)
                return

            ga_repo = GuildArtistRepository(session)
            guild_artists = await ga_repo.get_for_guild(guild.id)

        if not guild_artists:
            await interaction.response.send_message(
                "No artists are being tracked yet. A server admin can use `/track` to add some.",
                ephemeral=True,
            )
            return

        lines = []
        for ga in sorted(guild_artists, key=lambda x: x.artist.name_normalized):
            role_mention = f"<@&{ga.role_id}>" if ga.role_id else "*(no role)*"
            lines.append(f"**{ga.artist.name_display}** — {role_mention}")

        view = PaginatedView(
            items=lines,
            title=f"Tracked Artists — {interaction.guild.name}",
        )
        await view.send(interaction)

    # ── /subscribe ─────────────────────────────────────────────────────

    @app_commands.command(
        name="subscribe",
        description="Subscribe to an artist to receive pings when they drop.",
    )
    @app_commands.describe(name="Artist name")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def subscribe(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("⚠️ Server-only command.", ephemeral=True)
            return

        async with get_db_session() as session:
            guild_repo = GuildRepository(session)
            guild = await guild_repo.get_by_discord_id(interaction.guild.id)
            if not guild:
                await interaction.followup.send("⚠️ Server not registered.", ephemeral=True)
                return

            artist_repo = ArtistRepository(session)
            artist = await artist_repo.get_by_normalized_name(name.strip())
            if not artist:
                await interaction.followup.send(
                    f"⚠️ **{name}** isn't tracked in this server. Ask an admin to add it with `/track`.",
                    ephemeral=True,
                )
                return

            ga_repo = GuildArtistRepository(session)
            ga = await ga_repo.get_for_guild_with_artist(guild.id, artist.id)
            if not ga or not ga.is_active:
                await interaction.followup.send(
                    f"⚠️ **{artist.name_display}** isn't tracked in this server.",
                    ephemeral=True,
                )
                return

            # Ensure the user exists in our DB
            user_repo = UserRepository(session)
            db_user, _ = await user_repo.get_or_create(
                discord_id=interaction.user.id,
                username=str(interaction.user),
            )

            sub_repo = UserArtistSubscriptionRepository(session)
            existing_sub = await sub_repo.get(db_user.id, ga.id)
            if existing_sub:
                await interaction.followup.send(
                    f"You're already subscribed to **{artist.name_display}**.",
                    ephemeral=True,
                )
                return

            await sub_repo.subscribe(db_user.id, ga.id)

        # Assign the Discord role
        if ga.role_id:
            role = interaction.guild.get_role(ga.role_id)
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Prefix Hub: artist subscription")
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"✅ Subscribed to **{artist.name_display}** but couldn't assign the role (missing permissions).",
                        ephemeral=True,
                    )
                    return

        await interaction.followup.send(
            f"✅ Subscribed to **{artist.name_display}**! You'll be pinged when they drop.",
            ephemeral=True,
        )

    # ── /unsubscribe ───────────────────────────────────────────────────

    @app_commands.command(
        name="unsubscribe",
        description="Remove your subscription to an artist's notifications.",
    )
    @app_commands.describe(name="Artist name")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: i.user.id)
    async def unsubscribe(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("⚠️ Server-only command.", ephemeral=True)
            return

        async with get_db_session() as session:
            guild_repo = GuildRepository(session)
            guild = await guild_repo.get_by_discord_id(interaction.guild.id)
            if not guild:
                await interaction.followup.send("⚠️ Server not registered.", ephemeral=True)
                return

            artist_repo = ArtistRepository(session)
            artist = await artist_repo.get_by_normalized_name(name.strip())
            if not artist:
                await interaction.followup.send(f"⚠️ **{name}** isn't tracked here.", ephemeral=True)
                return

            ga_repo = GuildArtistRepository(session)
            ga = await ga_repo.get_for_guild_with_artist(guild.id, artist.id)
            if not ga:
                await interaction.followup.send(f"⚠️ **{name}** isn't tracked here.", ephemeral=True)
                return

            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_discord_id(interaction.user.id)
            if not db_user:
                await interaction.followup.send("⚠️ You don't have a subscription to remove.", ephemeral=True)
                return

            sub_repo = UserArtistSubscriptionRepository(session)
            removed = await sub_repo.unsubscribe(db_user.id, ga.id)

        if not removed:
            await interaction.followup.send(
                f"⚠️ You aren't subscribed to **{artist.name_display}**.",
                ephemeral=True,
            )
            return

        # Remove the role
        if ga.role_id and isinstance(interaction.user, discord.Member):
            role = interaction.guild.get_role(ga.role_id)
            if role:
                try:
                    await interaction.user.remove_roles(role, reason="Prefix Hub: artist unsubscribe")
                except discord.Forbidden:
                    pass

        await interaction.followup.send(
            f"✅ Unsubscribed from **{artist.name_display}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Called by discord.py when the cog is loaded."""
    premium_service = getattr(bot, "premium_service", PremiumService())
    await bot.add_cog(Artists(bot, premium_service))