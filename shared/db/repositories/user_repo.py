"""
shared/db/repositories/user_repo.py
Data access layer for User, Subscription, and ApiKey models.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.db.models import ApiKey, PremiumTier, Subscription, SubscriptionStatus, User
from shared.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_discord_id(self, discord_id: int) -> Optional[User]:
        result = await self._session.execute(
            select(User).where(User.discord_id == discord_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        discord_id: int,
        username: str,
        discriminator: Optional[str] = None,
        avatar_hash: Optional[str] = None,
    ) -> tuple[User, bool]:
        """
        Fetch or create a user by Discord ID.
        Updates mutable fields (username, avatar) if user already exists.
        Returns (user, created).
        """
        existing = await self.get_by_discord_id(discord_id)
        if existing:
            existing.username = username
            if discriminator is not None:
                existing.discriminator = discriminator
            if avatar_hash is not None:
                existing.avatar_hash = avatar_hash
            await self._session.flush()
            return existing, False

        user = User(
            discord_id=discord_id,
            username=username,
            discriminator=discriminator,
            avatar_hash=avatar_hash,
        )
        self._session.add(user)
        await self._session.flush()
        return user, True

    async def set_premium_tier(
        self,
        discord_id: int,
        tier: PremiumTier,
        expires_at: Optional[datetime] = None,
    ) -> Optional[User]:
        user = await self.get_by_discord_id(discord_id)
        if not user:
            return None
        user.premium_tier = tier
        user.premium_expires_at = expires_at
        await self._session.flush()
        return user

    async def set_banned(self, discord_id: int, banned: bool, reason: Optional[str] = None) -> Optional[User]:
        user = await self.get_by_discord_id(discord_id)
        if not user:
            return None
        user.is_banned = banned
        user.ban_reason = reason if banned else None
        await self._session.flush()
        return user


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Subscription)

    async def get_active_for_user(self, user_db_id: int) -> Optional[Subscription]:
        """Return the currently active subscription for a user, if any."""
        result = await self._session.execute(
            select(Subscription).where(
                Subscription.user_id == user_db_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_stripe_subscription_id(self, stripe_sub_id: str) -> Optional[Subscription]:
        result = await self._session.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        return result.scalar_one_or_none()

    async def upsert_from_stripe(
        self,
        user_db_id: int,
        tier: PremiumTier,
        status: SubscriptionStatus,
        stripe_customer_id: str,
        stripe_sub_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Subscription:
        """Create or update a subscription based on a Stripe webhook event."""
        existing = await self.get_by_stripe_subscription_id(stripe_sub_id)
        if existing:
            existing.tier = tier
            existing.status = status
            existing.current_period_start = period_start
            existing.current_period_end = period_end
            if status == SubscriptionStatus.CANCELED:
                existing.canceled_at = datetime.now(timezone.utc)
            await self._session.flush()
            return existing

        sub = Subscription(
            user_id=user_db_id,
            tier=tier,
            status=status,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_sub_id,
            current_period_start=period_start,
            current_period_end=period_end,
        )
        self._session.add(sub)
        await self._session.flush()
        return sub


class ApiKeyRepository(BaseRepository[ApiKey]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ApiKey)

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """SHA-256 hash of the raw key. Not bcrypt — API keys are long random strings."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def create_key(
        self,
        user_db_id: int,
        name: str,
        scopes: list[str],
    ) -> tuple[ApiKey, str]:
        """
        Generate and store a new API key.
        Returns (ApiKey, raw_key) — the raw key is shown only once and never stored.
        """
        raw_key = f"ph_{secrets.token_urlsafe(40)}"
        key_hash = self._hash_key(raw_key)
        api_key = ApiKey(
            user_id=user_db_id,
            key_hash=key_hash,
            name=name,
            scopes=scopes,
        )
        self._session.add(api_key)
        await self._session.flush()
        return api_key, raw_key

    async def get_by_raw_key(self, raw_key: str) -> Optional[ApiKey]:
        """Look up an API key by the raw value. Used during authentication."""
        key_hash = self._hash_key(raw_key)
        result = await self._session.execute(
            select(ApiKey)
            .where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)  # noqa: E712
            .options(selectinload(ApiKey.user))
        )
        api_key = result.scalar_one_or_none()
        if api_key:
            api_key.last_used_at = datetime.now(timezone.utc)
            await self._session.flush()
        return api_key

    async def list_for_user(self, user_db_id: int) -> Sequence[ApiKey]:
        result = await self._session.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user_db_id, ApiKey.is_active == True)  # noqa: E712
        )
        return result.scalars().all()

    async def revoke(self, key_id: int, user_db_id: int) -> bool:
        """Revoke an API key. Verifies ownership."""
        result = await self._session.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_db_id)
        )
        key = result.scalar_one_or_none()
        if not key:
            return False
        key.is_active = False
        await self._session.flush()
        return True
