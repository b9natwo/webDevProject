"""
shared/db/session.py
Async SQLAlchemy session factory and engine configuration.
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from shared.config import get_settings

_engine = None
_session_factory = None


def _normalize_database_url(url: str) -> str:
    """Ensure we always use the asyncpg driver for async SQLAlchemy."""
    if not url:
        raise ValueError("DATABASE_URL is not set")

    # Handle common prefixes
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Fix double replacement if it somehow happened
    if "postgresql+asyncpg+asyncpg://" in url:
        url = url.replace("postgresql+asyncpg+asyncpg://", "postgresql+asyncpg://", 1)

    return url


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = _normalize_database_url(str(settings.database_url))

        _engine = create_async_engine(
            db_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            echo=not settings.is_production,
            pool_pre_ping=True,
            # Good for Render / serverless environments
            pool_recycle=300,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a database session.
    Commits on clean exit, rolls back on exception.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_engine() -> None:
    """Dispose the engine during shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
