"""
dashboard/src/routers/analytics.py — Analytics API endpoints
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from dashboard.src.auth.session import get_current_user
from shared.db.models import FeedEntry, Guild, GuildArtist, NotificationLog, User
from shared.db.session import get_db_session

router = APIRouter(tags=["analytics"])


@router.get("/overview")
async def analytics_overview(user: User = Depends(get_current_user)) -> dict:
    """Global platform overview for bot owners; per-user view otherwise."""
    since_7d = datetime.now(timezone.utc) - timedelta(days=7)
    since_30d = datetime.now(timezone.utc) - timedelta(days=30)

    async with get_db_session() as session:
        total_guilds = (await session.execute(
            select(func.count()).select_from(Guild).where(Guild.is_active == True)  # noqa
        )).scalar_one()

        total_entries = (await session.execute(
            select(func.count()).select_from(FeedEntry)
        )).scalar_one()

        total_entries_7d = (await session.execute(
            select(func.count()).select_from(FeedEntry)
            .where(FeedEntry.first_seen_at >= since_7d)
        )).scalar_one()

        total_notifs_30d = (await session.execute(
            select(func.count()).select_from(NotificationLog)
            .where(NotificationLog.delivered_at >= since_30d)
        )).scalar_one()

        total_tracked = (await session.execute(
            select(func.count()).select_from(GuildArtist).where(GuildArtist.is_active == True)  # noqa
        )).scalar_one()

    return {
        "total_guilds": total_guilds,
        "total_feed_entries": total_entries,
        "feed_entries_last_7d": total_entries_7d,
        "notifications_last_30d": total_notifs_30d,
        "total_tracked_artists": total_tracked,
    }


@router.get("/recent-entries")
async def recent_entries(
    limit: int = 20,
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Most recently seen feed entries."""
    limit = min(limit, 50)
    async with get_db_session() as session:
        result = await session.execute(
            select(FeedEntry)
            .order_by(FeedEntry.first_seen_at.desc())
            .limit(limit)
        )
        entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "title": e.clean_title,
            "url": e.entry_url,
            "matched_artists": e.matched_artists or [],
            "thread_tags": e.thread_tags or [],
            "first_seen_at": e.first_seen_at.isoformat(),
            "is_deleted": e.is_deleted,
        }
        for e in entries
    ]
