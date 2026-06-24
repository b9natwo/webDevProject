# Prefix Hub

**Real-time music leak notifications from leaked.cx — delivered straight to your Discord server.**

Prefix Hub monitors leaked.cx RSS feeds and sends instant Discord notifications whenever a tracked artist appears in a new thread. It's a community project built by fans, for fans.

---

## Features

- **Artist Tracking** — Add artists by name; we normalize and match automatically
- **Rich Discord Embeds** — Title, tags, matched artists, direct links — no noise
- **Real-Time Polling** — Checks leaked.cx every 35 seconds (Priority: 15s for Premium)
- **Deletion Alerts** — Flags when a tracked thread disappears
- **Advanced Filters** — Keyword rules, tag filters, age thresholds (Premium)
- **Multi-Server** — Invite the bot to your own server (Premium)
- **Web Dashboard** — Manage everything from one clean interface

---

## Tiers

| Feature | Free | Supporter ($4/mo) | Premium ($12/mo) |
|---|---|---|---|
| Artist limit | 5 | 25 | Unlimited |
| Home server access | ✓ | ✓ | ✓ |
| Discord role | — | Supporter | Supporter |
| Early access | — | ✓ | ✓ |
| Personal bot invite | — | — | ✓ |
| Priority polling | — | — | ✓ (15s) |
| Advanced filters | — | — | ✓ |
| Multi-server | — | — | ✓ |

---

## Self-Hosting

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- A Discord application with a bot token and OAuth2 credentials
- A leaked.cx account (with permission to use the RSS feed)

### Setup

```bash
git clone https://github.com/prefixhub/prefix-hub
cd prefix-hub
pip install -e ".[dev]"
cp .env.example .env
# Fill in .env (see below)
alembic upgrade head
```

### Environment Variables

```env
# Discord
DISCORD_TOKEN=your_bot_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
DISCORD_REDIRECT_URI=http://localhost:8000/auth/callback

# leaked.cx
LEAKED_USERNAME=your_username
LEAKED_PASSWORD=your_password

# Home guild (main Prefix Hub server ID for Free/Supporter access)
HOME_GUILD_ID=123456789

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/prefixhub

# Dashboard
DASHBOARD_SECRET_KEY=your-random-32-char-secret-here

# Stripe (optional — enables paid tiers)
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_SUPPORTER_PRICE_ID=price_...
STRIPE_PREMIUM_PRICE_ID=price_...
```

### Running

```bash
# Bot
python -m bot.src.bot

# Dashboard (separate terminal)
uvicorn dashboard.src.main:app --host 0.0.0.0 --port 8000
```

---

## Project Structure

```
prefix-hub/
├── bot/
│   └── src/
│       ├── bot.py            # Discord client entry point
│       ├── cogs/             # Slash command groups
│       └── services/         # Feed poller, notifier, premium logic
├── dashboard/
│   └── src/
│       ├── main.py           # FastAPI app
│       ├── auth/             # Discord OAuth2 + JWT sessions
│       ├── routers/          # API endpoints
│       └── static/           # Frontend (single-file SPA)
├── shared/
│   ├── config.py             # Pydantic settings
│   └── db/                   # SQLAlchemy models + repositories
├── migrations/               # Alembic migrations
└── docs/                     # Documentation
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). We welcome all contributions — bug reports, feature ideas, code, and community feedback.

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

MIT © Prefix Hub Contributors
