"""
dashboard/src/routers/auth.py
Discord OAuth2 login / logout endpoints.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from dashboard.src.auth.discord_oauth import DiscordOAuth
from dashboard.src.auth.session import (
    clear_session_cookie,
    create_session_token,
    get_current_user,
    set_session_cookie,
)
from shared.db.models import User
from shared.db.repositories.user_repo import UserRepository
from shared.db.session import get_db_session

router = APIRouter(tags=["auth"])
_oauth = DiscordOAuth()
_pending_states: dict[str, bool] = {}  # state -> used (in-memory CSRF store)


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect to Discord OAuth2 consent screen."""
    state = secrets.token_urlsafe(32)
    _pending_states[state] = True
    # Prune old states (keep last 100)
    if len(_pending_states) > 100:
        oldest = list(_pending_states.keys())[0]
        del _pending_states[oldest]
    return RedirectResponse(_oauth.get_authorize_url(state))


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
) -> Response:
    """Handle the OAuth2 callback from Discord."""
    if state not in _pending_states:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")
    del _pending_states[state]

    token_data = await _oauth.exchange_code(code)
    if not token_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token exchange failed")

    user_info = await _oauth.get_user_info(token_data["access_token"])
    if not user_info:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not fetch user info")

    discord_id = int(user_info["id"])
    username = user_info.get("username", "Unknown")
    avatar = user_info.get("avatar")

    async with get_db_session() as session:
        user_repo = UserRepository(session)
        user, _ = await user_repo.get_or_create(
            discord_id=discord_id,
            username=username,
            discriminator=user_info.get("discriminator"),
            avatar_hash=avatar,
        )
        if user.is_banned:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account banned")

    jwt_token = create_session_token(discord_id, username)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    set_session_cookie(response, jwt_token)
    return response


@router.get("/logout")
async def logout() -> Response:
    """Clear the session cookie and redirect to home."""
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    clear_session_cookie(response)
    return response


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict:
    """Return the current user's profile information."""
    return {
        "id": str(user.discord_id),
        "username": user.username,
        "avatar_hash": user.avatar_hash,
        "premium_tier": user.premium_tier.value,
        "is_bot_owner": user.is_bot_owner,
    }
