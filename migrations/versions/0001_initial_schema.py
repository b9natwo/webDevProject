"""
migrations/versions/0001_initial_schema.py
Initial database schema — creates all tables.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    premium_tier_enum = postgresql.ENUM(
        "FREE",
        "STANDARD",
        "PRO",
        name="premiumtier",
        create_type=False,
    )

    subscription_status_enum = postgresql.ENUM(
        "ACTIVE",
        "PAST_DUE",
        "CANCELED",
        "TRIALING",
        name="subscriptionstatus",
        create_type=False,
    )

    premium_tier_enum.create(op.get_bind(), checkfirst=True)
    subscription_status_enum.create(op.get_bind(), checkfirst=True)

    # ── users ────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("discord_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("discriminator", sa.String(4), nullable=True),
        sa.Column("avatar_hash", sa.String(64), nullable=True),
        sa.Column("premium_tier", premium_tier_enum, nullable=False, server_default='FREE'),
        sa.Column("premium_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_bot_owner", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ban_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discord_id"),
    )
    op.create_index("ix_users_discord_id", "users", ["discord_id"])

    # ── guilds ───────────────────────────────────────────────────────
    op.create_table(
        "guilds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("discord_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("icon_hash", sa.String(64), nullable=True),
        sa.Column("owner_discord_id", sa.BigInteger(), nullable=False),
        sa.Column("premium_tier", premium_tier_enum, nullable=False, server_default='FREE'),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("leaks_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("audit_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("artists_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("polls_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discord_id"),
    )
    op.create_index("ix_guilds_discord_id", "guilds", ["discord_id"])

    # ── guild_settings ───────────────────────────────────────────────
    op.create_table(
        "guild_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("recognized_sites", postgresql.JSONB(), nullable=True),
        sa.Column("whitelisted_artists", postgresql.JSONB(), nullable=True),
        sa.Column("blacklisted_artists", postgresql.JSONB(), nullable=True),
        sa.Column("filter_min_age_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notification_format", sa.String(20), nullable=False, server_default="embed"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id"),
    )

    # ── artists ──────────────────────────────────────────────────────
    op.create_table(
        "artists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name_normalized", sa.String(200), nullable=False),
        sa.Column("name_display", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_normalized"),
    )
    op.create_index("ix_artists_name_normalized", "artists", ["name_normalized"])

    # ── guild_artists ────────────────────────────────────────────────
    op.create_table(
        "guild_artists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("artist_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("added_by_discord_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artist_id"], ["artists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "artist_id", name="uq_guild_artist"),
    )
    op.create_index("ix_guild_artists_guild_id", "guild_artists", ["guild_id"])
    op.create_index("ix_guild_artists_artist_id", "guild_artists", ["artist_id"])

    # ── user_artist_subscriptions ────────────────────────────────────
    op.create_table(
        "user_artist_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("guild_artist_id", sa.Integer(), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guild_artist_id"], ["guild_artists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "guild_artist_id", name="uq_user_guild_artist"),
    )
    op.create_index("ix_uas_user_id", "user_artist_subscriptions", ["user_id"])
    op.create_index("ix_uas_guild_artist_id", "user_artist_subscriptions", ["guild_artist_id"])

    # ── feeds ────────────────────────────────────────────────────────
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rss_url", sa.String(500), nullable=False),
        sa.Column("forum_url", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_etag", sa.String(256), nullable=True),
        sa.Column("last_modified", sa.String(100), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rss_url"),
    )

    # ── feed_entries ─────────────────────────────────────────────────
    op.create_table(
        "feed_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("entry_url", sa.String(500), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("clean_title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("thread_tags", postgresql.JSONB(), nullable=True),
        sa.Column("matched_artists", postgresql.JSONB(), nullable=True),
        sa.Column("download_links", postgresql.JSONB(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["feed_id"], ["feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_url"),
    )
    op.create_index("ix_feed_entries_entry_url", "feed_entries", ["entry_url"])
    op.create_index("ix_feed_entries_feed_id", "feed_entries", ["feed_id"])

    # ── guild_feed_entries ───────────────────────────────────────────
    op.create_table(
        "guild_feed_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("feed_entry_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feed_entry_id"], ["feed_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "feed_entry_id", name="uq_guild_feed_entry"),
    )
    op.create_index("ix_gfe_guild_id", "guild_feed_entries", ["guild_id"])
    op.create_index("ix_gfe_feed_entry_id", "guild_feed_entries", ["feed_entry_id"])

    # ── notification_logs ────────────────────────────────────────────
    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("feed_entry_id", sa.Integer(), nullable=False),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["feed_entry_id"], ["feed_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notif_user_id", "notification_logs", ["user_id"])
    op.create_index("ix_notif_entry_id", "notification_logs", ["feed_entry_id"])
    op.create_index("ix_notif_guild_id", "notification_logs", ["guild_id"])

    # ── subscriptions ────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tier", premium_tier_enum, nullable=False),
        sa.Column("status", subscription_status_enum, nullable=False),
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_subscription_id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])

    # ── api_keys ─────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_hash", sa.String(256), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])


def downgrade() -> None:
    premium_tier_enum = postgresql.ENUM(
        "FREE", "STANDARD", "PRO",
        name="premiumtier",
        create_type=False,
    )
    subscription_status_enum = postgresql.ENUM(
        "ACTIVE", "PAST_DUE", "CANCELED", "TRIALING",
        name="subscriptionstatus",
        create_type=False,
    )

    for table in [
        "api_keys", "subscriptions", "notification_logs",
        "guild_feed_entries", "feed_entries", "feeds",
        "user_artist_subscriptions", "guild_artists", "artists",
        "guild_settings", "guilds", "users",
    ]:
        op.drop_table(table)

    subscription_status_enum.drop(op.get_bind(), checkfirst=True)
    premium_tier_enum.drop(op.get_bind(), checkfirst=True)