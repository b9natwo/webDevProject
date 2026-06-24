"""
bot/src/utils/rate_limit.py
Per-user and per-guild cooldown helpers for slash commands.
"""
from __future__ import annotations

import discord
from discord import app_commands


def user_cooldown(rate: int, per: float) -> app_commands.checks.Cooldown:
    """Shorthand for a per-user cooldown check."""
    return app_commands.checks.cooldown(rate, per, key=lambda i: i.user.id)


def guild_cooldown(rate: int, per: float) -> app_commands.checks.Cooldown:
    """Shorthand for a per-guild cooldown check."""
    return app_commands.checks.cooldown(rate, per, key=lambda i: i.guild_id)


def is_guild_admin():
    """
    Slash command check: user must have Manage Guild permission.
    Raises MissingPermissions if not satisfied.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            raise app_commands.NoPrivateMessage()
        if not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.manage_guild:
            return True
        raise app_commands.MissingPermissions(["manage_guild"])
    return app_commands.check(predicate)


def is_bot_owner():
    """
    Slash command check: user must be the bot application owner
    OR have is_bot_owner=True in the database (set via /owner grant).
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        app_info = await interaction.client.application_info()
        if interaction.user.id == app_info.owner.id:
            return True
        from shared.db.repositories.user_repo import UserRepository
        from shared.db.session import get_db_session
        async with get_db_session() as session:
            user = await UserRepository(session).get_by_discord_id(interaction.user.id)
            if user and user.is_bot_owner:
                return True
        raise app_commands.MissingPermissions(["bot_owner"])
    return app_commands.check(predicate)
