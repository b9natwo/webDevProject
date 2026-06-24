"""
dashboard/src/routers/health.py
Health check endpoint — used by Docker and load balancers.
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from shared.db.session import get_db_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Returns 200 OK with basic status. Checks database connectivity."""
    db_ok = False
    try:
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}
