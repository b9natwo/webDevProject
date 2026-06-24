"""
dashboard/src/auth/discord_oauth.py
Discord OAuth2 flow: redirect → callback → token exchange → user info.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

import aiohttp

from shared.config import get_settings

log = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"
DISCORD_OAUTH_AUTHORIZE = "https://discord.com/api/oauth2/authorize"
DISCORD_OAUTH_TOKEN = f"{DISCORD_API}/oauth2/token"
DISCORD_OAUTH_REVOKE = f"{DISCORD_API}/oauth2/token/revoke"


class DiscordOAuth:
    """Handles the full Discord OAuth2 code-exchange flow."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def get_authorize_url(self, state: str) -> str:
        """Build the URL that redirects the user to Discord's consent screen."""
        params = {
            "client_id": self._settings.discord_client_id,
            "redirect_uri": str(self._settings.discord_redirect_uri),
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
            "prompt": "none",
        }
        return f"{DISCORD_OAUTH_AUTHORIZE}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> Optional[dict]:
        """Exchange the authorisation code for an access token."""
        data = {
            "client_id": self._settings.discord_client_id,
            "client_secret": self._settings.discord_client_secret.get_secret_value(),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": str(self._settings.discord_redirect_uri),
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DISCORD_OAUTH_TOKEN,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as resp:
                if resp.status != 200:
                    log.warning("Token exchange failed: HTTP %s", resp.status)
                    return None
                return await resp.json()

    async def get_user_info(self, access_token: str) -> Optional[dict]:
        """Fetch the authenticated user's Discord profile."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{DISCORD_API}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()

    async def get_user_guilds(self, access_token: str) -> list[dict]:
        """Fetch the guilds the authenticated user belongs to."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{DISCORD_API}/users/@me/guilds",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status != 200:
                    return []
                return await resp.json()
