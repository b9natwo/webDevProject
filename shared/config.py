"""
shared/config.py
Centralised, validated configuration for all Prefix Hub services.

Tier model:
  FREE       - Limited artists (home server only), basic notifications
  SUPPORTER  - $3-5/mo: special role, early access, higher artist limits
  PREMIUM    - $8-15/mo: personal bot, custom monitoring, priority feeds, multi-server
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Discord ────────────────────────────────────────────────────────
    discord_token: SecretStr = Field(..., description="Discord bot token")
    discord_client_id: str = Field(..., description="Discord application client ID")
    discord_client_secret: SecretStr = Field(..., description="Discord OAuth2 client secret")
    discord_redirect_uri: AnyHttpUrl = Field(
        "http://localhost:8000/auth/callback",
        description="OAuth2 redirect URI registered in Discord Developer Portal",
    )

    # ── Home Guild ─────────────────────────────────────────────────────
    home_guild_id: int = Field(
        ...,
        description="Main Prefix Hub community server ID — all threads delivered here regardless of tier"
    )

    # ── leaked.cx credentials ──────────────────────────────────────────
    leaked_username: str = Field(..., description="leaked.cx login username")
    leaked_password: SecretStr = Field(..., description="leaked.cx login password")

    # ── Database ───────────────────────────────────────────────────────
    database_url: PostgresDsn = Field(
        ..., description="asyncpg-compatible PostgreSQL DSN"
    )
    database_pool_size: int = Field(10, ge=1, le=50)
    database_max_overflow: int = Field(20, ge=0, le=100)

    # ── Dashboard / API ────────────────────────────────────────────────
    dashboard_secret_key: SecretStr = Field(
        ..., description="Random secret used to sign JWT session tokens (min 32 chars)"
    )
    dashboard_host: str = Field("0.0.0.0")
    dashboard_port: int = Field(8000, ge=1, le=65535)
    allowed_origins: List[str] = Field(
        ["http://localhost:8000"],
        description="CORS allowed origins for the dashboard",
    )
    jwt_algorithm: str = Field("HS256")
    jwt_expire_minutes: int = Field(60 * 24 * 7, description="JWT TTL in minutes (default 7 days)")

    # ── Feed polling ───────────────────────────────────────────────────
    feed_poll_interval_seconds: int = Field(35, ge=10, description="How often to poll each RSS feed")
    # Premium members get a faster poll interval
    feed_poll_interval_premium_seconds: int = Field(15, ge=5, description="Faster poll for Premium guilds")
    feed_recent_window_minutes: int = Field(5, ge=1)
    deletion_check_interval_seconds: int = Field(3600, ge=60)
    notification_queue_workers: int = Field(3, ge=1, le=20)
    http_request_timeout: int = Field(10, ge=5)

    # ── Tier limits ────────────────────────────────────────────────────
    # FREE: limited artists, home server only
    free_max_artists: int = Field(5, description="Free tier artist tracking limit")
    free_max_guilds: int = Field(1, description="Free: home server only")

    # SUPPORTER: more artists, still home server + supporter perks
    supporter_max_artists: int = Field(25, description="Supporter tier artist tracking limit")
    supporter_max_guilds: int = Field(1, description="Supporter: still home server only")

    # PREMIUM: invite bot anywhere, unlimited artists, multi-server
    premium_max_artists: int = Field(0, description="0 = unlimited for Premium")
    premium_max_guilds: int = Field(0, description="0 = unlimited for Premium")

    # ── Stripe ────────────────────────────────────────────────────────
    stripe_secret_key: SecretStr = Field("", description="Stripe secret API key")
    stripe_webhook_secret: SecretStr = Field("", description="Stripe webhook signing secret")
    stripe_supporter_price_id: str = Field("", description="Stripe Price ID for Supporter tier")
    stripe_premium_price_id: str = Field("", description="Stripe Price ID for Premium tier")

    stripe_supporter_price_id: str | None = None
    stripe_premium_price_id: str | None = None
    stripe_enabled: bool = False

    # ── Environment ────────────────────────────────────────────────────
    environment: str = Field("development", pattern="^(development|production|testing)$")
    log_level: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    debug_mode: bool = Field(False, description="If True, send ALL threads regardless of age (for testing)")
    bot_invite_base_url: AnyHttpUrl = Field(
        "https://discord.com/api/oauth2/authorize",
        description="Base URL for bot invite links",
    )

    @field_validator("dashboard_secret_key")
    @classmethod
    def _check_secret_length(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("dashboard_secret_key must be at least 32 characters")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.stripe_secret_key.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
