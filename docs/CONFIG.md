# Configuration Reference

All configuration is via environment variables. Copy `.env.example` to `.env` and fill in values.
**Never commit `.env` to source control.**

---

## Required Variables

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Your Discord bot token. Get from the Discord Developer Portal → Bot tab. |
| `DISCORD_CLIENT_ID` | Your Discord application's client ID. |
| `DISCORD_CLIENT_SECRET` | Your Discord application's OAuth2 client secret. |
| `LEAKED_USERNAME` | Your leaked.cx account username. |
| `LEAKED_PASSWORD` | Your leaked.cx account password. |
| `DATABASE_URL` | asyncpg-compatible PostgreSQL DSN. Format: `postgresql+asyncpg://USER:PASS@HOST:PORT/DB` |
| `DASHBOARD_SECRET_KEY` | Random 32+ character secret for signing JWT sessions. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |

---

## Discord OAuth2

| Variable | Default | Description |
|---|---|---|
| `DISCORD_REDIRECT_URI` | `http://localhost:8000/auth/callback` | Must match exactly what's registered in Discord Developer Portal. |

---

## Database Tuning

| Variable | Default | Description |
|---|---|---|
| `DATABASE_POOL_SIZE` | `10` | SQLAlchemy connection pool size. Increase for high traffic. |
| `DATABASE_MAX_OVERFLOW` | `20` | Extra connections beyond pool_size. |

---

## Dashboard / API

| Variable | Default | Description |
|---|---|---|
| `DASHBOARD_HOST` | `0.0.0.0` | Bind address for uvicorn. |
| `DASHBOARD_PORT` | `8000` | Port to listen on. |
| `ALLOWED_ORIGINS` | `["http://localhost:8000"]` | CORS allowed origins. JSON array of strings. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |
| `JWT_EXPIRE_MINUTES` | `10080` | Session TTL in minutes (default: 7 days). |

---

## Feed Polling

| Variable | Default | Description |
|---|---|---|
| `FEED_POLL_INTERVAL_SECONDS` | `35` | How often each RSS feed is polled. Minimum: 10. |
| `FEED_RECENT_WINDOW_MINUTES` | `5` | Threads older than this many minutes are ignored. Increase if posts are being missed. |
| `DELETION_CHECK_INTERVAL_SECONDS` | `3600` | How often the deletion-check sweep runs. Default: hourly. |
| `NOTIFICATION_QUEUE_WORKERS` | `3` | Parallel Discord delivery workers. Increase for high notification volume. |
| `HTTP_REQUEST_TIMEOUT` | `10` | Timeout in seconds for all outbound HTTP requests. |

---

## Premium Tier Limits

| Variable | Default | Description |
|---|---|---|
| `FREE_MAX_ARTISTS` | `10` | Maximum tracked artists for Free tier guilds. |
| `FREE_MAX_GUILDS` | `1` | Maximum guilds a Free user can use the bot in. |
| `STANDARD_MAX_ARTISTS` | `50` | Maximum tracked artists for Standard tier. |
| `STANDARD_MAX_GUILDS` | `3` | Maximum guilds for Standard tier. |

Pro tier has no hard limits.

---

## Stripe (Optional)

Leave all Stripe variables blank to disable payment features. The bot will function fully without them.

| Variable | Description |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe secret API key (`sk_live_...` or `sk_test_...`) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret for validating events. |
| `STRIPE_STANDARD_PRICE_ID` | Stripe Price ID for the Standard monthly subscription. |
| `STRIPE_PRO_PRICE_ID` | Stripe Price ID for the Pro monthly subscription. |

---

## Environment

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Options: `development`, `production`, `testing`. In `production`: API docs are disabled, cookies are marked secure, log level defaults to WARNING. |
| `LOG_LEVEL` | `INFO` | Python logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `BOT_INVITE_BASE_URL` | `https://discord.com/api/oauth2/authorize` | Base URL for bot invite links. |
