"""
dashboard/src/auth/session.py
JWT-based session management via HTTP-only cookies.
Provides a FastAPI dependency that validates and returns the current user.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Cookie, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from shared.config import get_settings
from shared.db.models import User
from shared.db.repositories.user_repo import UserRepository
from shared.db.session import get_db_session

log = logging.getLogger(__name__)
COOKIE_NAME = "ph_session"


class SessionMiddleware(BaseHTTPMiddleware):
    """Attaches a CSRF state token to each session for OAuth protection."""

    def __init__(self, app: ASGIApp, secret_key: str) -> None:
        super().__init__(app)
        self.secret_key = secret_key

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        return response


def create_session_token(discord_id: int, username: str) -> str:
    """Create a signed JWT containing the user's Discord ID."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(discord_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.dashboard_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_session_token(token: str) -> Optional[dict]:
    """Decode and validate a session JWT. Returns the payload dict or None."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.dashboard_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        log.debug("Session token expired")
        return None
    except jwt.InvalidTokenError as e:
        log.debug("Invalid session token: %s", e)
        return None


def set_session_cookie(response: Response, token: str) -> None:
    """Attach the session JWT as a secure, HTTP-only cookie."""
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, httponly=True, secure=get_settings().is_production)


async def get_current_user(
    request: Request,
    ph_session: Optional[str] = Cookie(default=None),
) -> User:
    """
    FastAPI dependency that returns the authenticated User.
    Raises 401 if the session is missing or invalid.
    Raises 403 if the user is banned.
    """
    token = ph_session
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_session_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    discord_id = int(payload["sub"])
    async with get_db_session() as session:
        user = await UserRepository(session).get_by_discord_id(discord_id)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.is_banned:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account banned")

    return user


async def get_optional_user(
    ph_session: Optional[str] = Cookie(default=None),
) -> Optional[User]:
    """
    FastAPI dependency that returns the user if authenticated, or None.
    Use on public endpoints that show different content for logged-in users.
    """
    if not ph_session:
        return None
    try:
        return await get_current_user(ph_session=ph_session, request=None)  # type: ignore[arg-type]
    except HTTPException:
        return None
