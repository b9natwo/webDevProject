"""
dashboard/src/routers/guilds.py
Guild management API endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from dashboard.src.auth.session import get_current_user
from shared.db.models import User
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.session import get_db_session

import aiohttp

from shared.config import get_settings
settings = get_settings()

router = APIRouter(tags=["guilds"])


class ChannelUpdateRequest(BaseModel):
    leaks_channel_id: Optional[int] = None
    audit_channel_id: Optional[int] = None
    artists_channel_id: Optional[int] = None
    polls_channel_id: Optional[int] = None


@router.get("/")
async def list_guilds(user: User = Depends(get_current_user)) -> list[dict]:
    """List all guilds the bot is in (filtered to guilds the user manages)."""
    async with get_db_session() as session:
        repo = GuildRepository(session)
        guilds = await repo.get_all_active()

    return [
        {
            "id": str(g.discord_id),
            "name": g.name,
            "icon_hash": g.icon_hash,
            "premium_tier": g.premium_tier.value,
            "leaks_channel_id": str(g.leaks_channel_id) if g.leaks_channel_id else None,
            "is_configured": bool(g.leaks_channel_id),
        }
        for g in guilds
        if g.owner_discord_id == user.discord_id or user.is_bot_owner
    ]


@router.get("/{guild_discord_id}")
async def get_guild(
    guild_discord_id: int,
    user: User = Depends(get_current_user),
) -> dict:
    """Get detailed configuration for a guild the user owns."""
    async with get_db_session() as session:
        repo = GuildRepository(session)
        guild = await repo.get_by_discord_id(guild_discord_id)

    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    if guild.owner_discord_id != user.discord_id and not user.is_bot_owner:
        raise HTTPException(status_code=403, detail="Not your guild")

    return {
        "id": str(guild.discord_id),
        "name": guild.name,
        "premium_tier": guild.premium_tier.value,
        "leaks_channel_id": str(guild.leaks_channel_id) if guild.leaks_channel_id else None,
        "audit_channel_id": str(guild.audit_channel_id) if guild.audit_channel_id else None,
        "artists_channel_id": str(guild.artists_channel_id) if guild.artists_channel_id else None,
        "polls_channel_id": str(guild.polls_channel_id) if guild.polls_channel_id else None,
        "settings": {
            "notification_format": guild.settings.notification_format if guild.settings else "embed",
            "filter_min_age_minutes": guild.settings.filter_min_age_minutes if guild.settings else 0,
            "recognized_sites": guild.settings.recognized_sites if guild.settings else {},
        } if guild.settings else {},
    }

@router.get("/{guild_id}/roles")
async def get_guild_roles(
    guild_id: int,
    user: User = Depends(get_current_user),
) -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://discord.com/api/v10/guilds/{guild_id}/roles",
            headers={"Authorization": f"Bot {settings.discord_token.get_secret_value()}"}
        ) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail="Could not fetch roles from Discord")
            return await resp.json()

@router.patch("/{guild_discord_id}/channels")
async def update_guild_channels(
    guild_discord_id: int,
    body: ChannelUpdateRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """Update channel configuration for a guild."""
    async with get_db_session() as session:
        repo = GuildRepository(session)
        guild = await repo.get_by_discord_id(guild_discord_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")
        if guild.owner_discord_id != user.discord_id and not user.is_bot_owner:
            raise HTTPException(status_code=403, detail="Not your guild")

        await repo.update_channels(
            guild_discord_id,
            leaks_channel_id=body.leaks_channel_id,
            audit_channel_id=body.audit_channel_id,
            artists_channel_id=body.artists_channel_id,
            polls_channel_id=body.polls_channel_id,
        )
    return {"status": "updated"}
