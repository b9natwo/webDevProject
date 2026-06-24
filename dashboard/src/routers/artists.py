"""
dashboard/src/routers/artists.py
Per-guild artist management API endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from dashboard.src.auth.session import get_current_user
from shared.db.models import User
from shared.db.repositories.artist_repo import ArtistRepository, GuildArtistRepository
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.session import get_db_session

router = APIRouter(tags=["artists"])


class AddArtistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role_id: Optional[int] = None


@router.get("/{guild_discord_id}/artists")
async def list_guild_artists(
    guild_discord_id: int,
    user: User = Depends(get_current_user),
) -> list[dict]:
    async with get_db_session() as session:
        guild_repo = GuildRepository(session)
        guild = await guild_repo.get_by_discord_id(guild_discord_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")
        if guild.owner_discord_id != user.discord_id and not user.is_bot_owner:
            raise HTTPException(status_code=403, detail="Not your guild")

        ga_repo = GuildArtistRepository(session)
        guild_artists = await ga_repo.get_for_guild(guild.id)

    return [
        {
            "id": ga.id,
            "artist_name": ga.artist.name_display,
            "role_id": str(ga.role_id) if ga.role_id else None,
            "is_active": ga.is_active,
            "added_at": ga.added_at.isoformat(),
        }
        for ga in guild_artists
    ]


@router.post("/{guild_discord_id}/artists")
async def add_guild_artist(
    guild_discord_id: int,
    body: AddArtistRequest,
    user: User = Depends(get_current_user),
) -> dict:
    async with get_db_session() as session:
        guild_repo = GuildRepository(session)
        guild = await guild_repo.get_by_discord_id(guild_discord_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")
        if guild.owner_discord_id != user.discord_id and not user.is_bot_owner:
            raise HTTPException(status_code=403, detail="Not your guild")

        artist_repo = ArtistRepository(session)
        artist, _ = await artist_repo.get_or_create(body.name)

        ga_repo = GuildArtistRepository(session)
        existing = await ga_repo.get_for_guild_with_artist(guild.id, artist.id)
        if existing and existing.is_active:
            raise HTTPException(status_code=409, detail="Artist already tracked")

        ga = await ga_repo.add(
            guild_db_id=guild.id,
            artist_db_id=artist.id,
            role_id=body.role_id,
            added_by_discord_id=user.discord_id,
        )

    return {"id": ga.id, "artist_name": artist.name_display, "status": "added"}


@router.delete("/{guild_discord_id}/artists/{artist_name}")
async def remove_guild_artist(
    guild_discord_id: int,
    artist_name: str,
    user: User = Depends(get_current_user),
) -> dict:
    async with get_db_session() as session:
        guild_repo = GuildRepository(session)
        guild = await guild_repo.get_by_discord_id(guild_discord_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")
        if guild.owner_discord_id != user.discord_id and not user.is_bot_owner:
            raise HTTPException(status_code=403, detail="Not your guild")

        artist_repo = ArtistRepository(session)
        artist = await artist_repo.get_by_normalized_name(artist_name)
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not tracked")

        ga_repo = GuildArtistRepository(session)
        removed = await ga_repo.remove(guild.id, artist.id)

    if not removed:
        raise HTTPException(status_code=404, detail="Artist not tracked")
    return {"status": "removed"}
