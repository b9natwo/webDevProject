"""
shared/db/models.py
Complete SQLAlchemy 2.x ORM models for Prefix Hub.
All tables use BigInteger for Discord IDs (they exceed 32-bit int range).

Tier model:
  FREE       - Limited artists, home server only, basic notifications
  SUPPORTER  - $3-5/mo: special role, early access, higher limits
  PREMIUM    - $8-15/mo: personal bot invites, custom monitoring, priority feeds
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class PremiumTier(str, enum.Enum):
    FREE = "free"
    SUPPORTER = "supporter"   # was STANDARD
    PREMIUM = "premium"       # was PRO


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    TRIALING = "trialing"


# ─────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    discriminator: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    avatar_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    premium_tier: Mapped[PremiumTier] = mapped_column(
        Enum(PremiumTier), nullable=False, default=PremiumTier.FREE
    )
    premium_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_bot_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user", cascade="all, delete-orphan")
    artist_subscriptions: Mapped[list[UserArtistSubscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list[ApiKey]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notification_logs: Mapped[list[NotificationLog]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User discord_id={self.discord_id} username={self.username!r}>"


# ─────────────────────────────────────────────
# Guilds
# ─────────────────────────────────────────────

class Guild(Base):
    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    premium_tier: Mapped[PremiumTier] = mapped_column(
        Enum(PremiumTier), nullable=False, default=PremiumTier.FREE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    leaks_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    audit_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    artists_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    polls_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    settings: Mapped[Optional[GuildSettings]] = relationship(
        back_populates="guild", uselist=False, cascade="all, delete-orphan"
    )
    guild_artists: Mapped[list[GuildArtist]] = relationship(
        back_populates="guild", cascade="all, delete-orphan"
    )
    guild_feed_entries: Mapped[list[GuildFeedEntry]] = relationship(
        back_populates="guild", cascade="all, delete-orphan"
    )
    notification_logs: Mapped[list[NotificationLog]] = relationship(back_populates="guild")

    def __repr__(self) -> str:
        return f"<Guild discord_id={self.discord_id} name={self.name!r}>"


class GuildSettings(Base):
    __tablename__ = "guild_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guilds.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    recognized_sites: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)
    whitelisted_artists: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    blacklisted_artists: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    filter_min_age_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notification_format: Mapped[str] = mapped_column(String(20), nullable=False, default="embed")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    guild: Mapped[Guild] = relationship(back_populates="settings")

    def __repr__(self) -> str:
        return f"<GuildSettings guild_id={self.guild_id}>"


# ─────────────────────────────────────────────
# Artists
# ─────────────────────────────────────────────

class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_normalized: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    name_display: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    guild_artists: Mapped[list[GuildArtist]] = relationship(back_populates="artist")

    def __repr__(self) -> str:
        return f"<Artist name={self.name_normalized!r}>"


class GuildArtist(Base):
    __tablename__ = "guild_artists"
    __table_args__ = (UniqueConstraint("guild_id", "artist_id", name="uq_guild_artist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    added_by_discord_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    guild: Mapped[Guild] = relationship(back_populates="guild_artists")
    artist: Mapped[Artist] = relationship(back_populates="guild_artists")
    user_subscriptions: Mapped[list[UserArtistSubscription]] = relationship(
        back_populates="guild_artist", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<GuildArtist guild_id={self.guild_id} artist_id={self.artist_id}>"


class UserArtistSubscription(Base):
    __tablename__ = "user_artist_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "guild_artist_id", name="uq_user_guild_artist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guild_artist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guild_artists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user: Mapped[User] = relationship(back_populates="artist_subscriptions")
    guild_artist: Mapped[GuildArtist] = relationship(back_populates="user_subscriptions")

    def __repr__(self) -> str:
        return f"<UserArtistSubscription user_id={self.user_id} guild_artist_id={self.guild_artist_id}>"


# ─────────────────────────────────────────────
# Feeds & Entries
# ─────────────────────────────────────────────

class Feed(Base):
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rss_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    forum_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_etag: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    last_modified: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    entries: Mapped[list[FeedEntry]] = relationship(back_populates="feed", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Feed name={self.name!r}>"


class FeedEntry(Base):
    __tablename__ = "feed_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    clean_title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    thread_tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    matched_artists: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    download_links: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    feed: Mapped[Feed] = relationship(back_populates="entries")
    guild_entries: Mapped[list[GuildFeedEntry]] = relationship(
        back_populates="feed_entry", cascade="all, delete-orphan"
    )
    notification_logs: Mapped[list[NotificationLog]] = relationship(back_populates="feed_entry")

    def __repr__(self) -> str:
        return f"<FeedEntry title={self.title!r}>"


class GuildFeedEntry(Base):
    __tablename__ = "guild_feed_entries"
    __table_args__ = (UniqueConstraint("guild_id", "feed_entry_id", name="uq_guild_feed_entry"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feed_entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("feed_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    guild: Mapped[Guild] = relationship(back_populates="guild_feed_entries")
    feed_entry: Mapped[FeedEntry] = relationship(back_populates="guild_entries")

    def __repr__(self) -> str:
        return f"<GuildFeedEntry guild_id={self.guild_id} message_id={self.message_id}>"


# ─────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feed_entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("feed_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guild_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[Optional[User]] = relationship(back_populates="notification_logs")
    feed_entry: Mapped[FeedEntry] = relationship(back_populates="notification_logs")
    guild: Mapped[Guild] = relationship(back_populates="notification_logs")

    def __repr__(self) -> str:
        return f"<NotificationLog user_id={self.user_id} message_id={self.message_id}>"


# ─────────────────────────────────────────────
# Premium / Subscriptions
# ─────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier: Mapped[PremiumTier] = mapped_column(Enum(PremiumTier), nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus), nullable=False)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True)
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    user: Mapped[User] = relationship(back_populates="subscriptions")

    def __repr__(self) -> str:
        return f"<Subscription user_id={self.user_id} tier={self.tier} status={self.status}>"


# ─────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_hash: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user: Mapped[User] = relationship(back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey name={self.name!r} user_id={self.user_id}>"
