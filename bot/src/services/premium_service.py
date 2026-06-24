"""
bot/src/services/premium_service.py
Tier enforcement and feature gating for the three-tier community model.

  FREE       — Limited artists, home server access only, basic notifications
  SUPPORTER  — $3–5/mo: special role, early access, 25 artists, support the project
  PREMIUM    — $8–15/mo: invite bot to personal servers, unlimited artists,
               custom monitoring, advanced filters, priority feed checking
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from shared.config import get_settings
from shared.db.models import Guild, PremiumTier, User
from shared.db.repositories.artist_repo import GuildArtistRepository
from shared.db.repositories.guild_repo import GuildRepository
from shared.db.repositories.user_repo import UserRepository
from shared.db.session import get_db_session

log = logging.getLogger(__name__)

UPGRADE_URL = "https://prefixhub.xyz/upgrade"


class EntitlementError(Exception):
    """Raised when a user or guild exceeds their tier's limits."""
    pass


class PremiumService:
    """Single service for all tier/entitlement logic."""

    def __init__(self) -> None:
        self._settings = get_settings()

    # ── Tier limits ────────────────────────────────────────────────────

    def get_max_artists(self, tier: PremiumTier) -> int:
        if tier == PremiumTier.PREMIUM:
            return 2 ** 31  # Unlimited
        if tier == PremiumTier.SUPPORTER:
            return self._settings.supporter_max_artists
        return self._settings.free_max_artists

    def get_max_guilds(self, tier: PremiumTier) -> int:
        """
        FREE/SUPPORTER: home server only.
        PREMIUM: can invite bot to personal servers (unlimited).
        """
        if tier == PremiumTier.PREMIUM:
            return 2 ** 31
        return 1  # FREE and SUPPORTER: home server only

    def can_invite_bot(self, tier: PremiumTier) -> bool:
        """Only Premium members can invite the bot to personal servers."""
        return tier == PremiumTier.PREMIUM

    def has_priority_feeds(self, tier: PremiumTier) -> bool:
        """Premium members get faster RSS polling."""
        return tier == PremiumTier.PREMIUM

    def has_advanced_filters(self, tier: PremiumTier) -> bool:
        """Custom monitoring and advanced tag/keyword filters."""
        return tier == PremiumTier.PREMIUM

    def has_early_access(self, tier: PremiumTier) -> bool:
        """Supporters and Premium get early access to new features."""
        return tier in (PremiumTier.SUPPORTER, PremiumTier.PREMIUM)

    def tier_display_name(self, tier: PremiumTier) -> str:
        return {
            PremiumTier.FREE: "Free",
            PremiumTier.SUPPORTER: "Supporter",
            PremiumTier.PREMIUM: "Premium",
        }[tier]

    def tier_price(self, tier: PremiumTier) -> str:
        return {
            PremiumTier.FREE: "Free",
            PremiumTier.SUPPORTER: "$4/mo",
            PremiumTier.PREMIUM: "$12/mo",
        }[tier]

    # ── Entitlement checks ─────────────────────────────────────────────

    async def assert_can_add_artist(self, guild_db_id: int, guild_tier: PremiumTier) -> None:
        max_artists = self.get_max_artists(guild_tier)
        async with get_db_session() as session:
            repo = GuildArtistRepository(session)
            current = await repo.count_for_guild(guild_db_id)
        if current >= max_artists:
            tier_name = self.tier_display_name(guild_tier)
            if guild_tier == PremiumTier.FREE:
                hint = f"Upgrade to **Supporter** to track up to {self._settings.supporter_max_artists} artists."
            elif guild_tier == PremiumTier.SUPPORTER:
                hint = "Upgrade to **Premium** to track unlimited artists."
            else:
                hint = ""
            raise EntitlementError(
                f"This server has reached its limit of **{max_artists} tracked artists** "
                f"on the **{tier_name}** tier.\n{hint}\n{UPGRADE_URL}"
            )

    async def assert_can_invite_bot(self, user_tier: PremiumTier) -> None:
        """Raise EntitlementError if user is not Premium."""
        if not self.can_invite_bot(user_tier):
            raise EntitlementError(
                "Inviting the bot to your own server requires **Premium**.\n"
                f"Upgrade at {UPGRADE_URL}"
            )

    async def resolve_user_tier(self, discord_id: int) -> PremiumTier:
        async with get_db_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_discord_id(discord_id)
            if not user:
                return PremiumTier.FREE
            if user.premium_tier != PremiumTier.FREE:
                if user.premium_expires_at and user.premium_expires_at < datetime.now(timezone.utc):
                    await user_repo.set_premium_tier(discord_id, PremiumTier.FREE)
                    log.info("Downgraded user %s to FREE (subscription expired)", discord_id)
                    return PremiumTier.FREE
            return user.premium_tier

    async def resolve_guild_tier(self, discord_guild_id: int) -> PremiumTier:
        async with get_db_session() as session:
            guild_repo = GuildRepository(session)
            guild = await guild_repo.get_by_discord_id(discord_guild_id)
            if not guild:
                return PremiumTier.FREE
            return guild.premium_tier

    async def grant_guild_premium(self, discord_guild_id: int, tier: PremiumTier) -> Optional[Guild]:
        async with get_db_session() as session:
            repo = GuildRepository(session)
            guild = await repo.set_premium_tier(discord_guild_id, tier)
            if guild:
                log.info("Granted %s to guild %s", tier, discord_guild_id)
            return guild

    async def grant_user_premium(
        self,
        discord_user_id: int,
        tier: PremiumTier,
        expires_at: Optional[datetime] = None,
    ) -> Optional[User]:
        async with get_db_session() as session:
            repo = UserRepository(session)
            user = await repo.set_premium_tier(discord_user_id, tier, expires_at)
            if user:
                log.info("Granted %s to user %s (expires=%s)", tier, discord_user_id, expires_at)
            return user
