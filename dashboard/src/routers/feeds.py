"""
dashboard/src/routers/feeds.py  — Feed status API (read-only for non-owners)
"""
from fastapi import APIRouter, Depends
from dashboard.src.auth.session import get_current_user
from shared.db.models import User
from shared.db.repositories.feed_repo import FeedRepository
from shared.db.session import get_db_session

router = APIRouter(tags=["feeds"])


@router.get("/")
async def list_feeds(user: User = Depends(get_current_user)) -> list[dict]:
    async with get_db_session() as session:
        feeds = await FeedRepository(session).get_active_feeds()
    return [
        {
            "id": f.id,
            "name": f.name,
            "rss_url": f.rss_url,
            "is_active": f.is_active,
            "last_polled_at": f.last_polled_at.isoformat() if f.last_polled_at else None,
            "consecutive_failures": f.consecutive_failures,
        }
        for f in feeds
    ]
