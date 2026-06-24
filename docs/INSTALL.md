# Installation Guide

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | 3.12 | Required — f-string and type hint features used throughout |
| PostgreSQL | 15 | Can be run via Docker |
| Docker | 24 | Optional but strongly recommended |
| Docker Compose | v2 | Bundled with modern Docker Desktop |

---

## Step 1 — Discord Application Setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → name it "Prefix Hub"
3. Go to **Bot** → click **Add Bot**
4. Under **Privileged Gateway Intents**, enable **Server Members Intent** if needed (currently not required)
5. Copy the **Bot Token** — you'll need this for `DISCORD_TOKEN`
6. Go to **OAuth2 → General**:
   - Copy the **Client ID** → `DISCORD_CLIENT_ID`
   - Copy the **Client Secret** → `DISCORD_CLIENT_SECRET`
   - Add redirect URI: `http://localhost:8000/auth/callback` (dev) and/or `https://yourdomain.com/auth/callback` (prod)
7. Go to **OAuth2 → URL Generator** to generate an invite link:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Manage Roles`, `Read Message History`
   - Required permissions integer: `277025508352`

---

## Step 2 — Environment Configuration

```bash
cp .env.example .env
```

Open `.env` and fill in all required values. See [CONFIG.md](CONFIG.md) for full documentation of every variable.

**Minimum required values:**
```env
DISCORD_TOKEN=your_bot_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret
LEAKED_USERNAME=your_leaked_cx_username
LEAKED_PASSWORD=your_leaked_cx_password
DATABASE_URL=postgresql+asyncpg://prefixhub:changeme@localhost:5432/prefixhub
DASHBOARD_SECRET_KEY=<64-char random hex — see below>
```

Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 3A — Docker Install (Recommended)

```bash
# Build and start all services
docker compose up --build

# On first run, migrations run automatically via the `migrate` service.
# Subsequent runs: docker compose up
```

Services started:
- `db` — PostgreSQL on port 5432
- `migrate` — runs `alembic upgrade head` once then exits
- `bot` — Discord bot
- `dashboard` — Web dashboard on http://localhost:8000

To stop:
```bash
docker compose down        # Keep database
docker compose down -v     # Also remove database volume
```

To view logs:
```bash
docker compose logs -f bot
docker compose logs -f dashboard
```

---

## Step 3B — Manual Install (Without Docker)

### Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Start PostgreSQL

Install PostgreSQL 15+ and create the database:
```sql
CREATE USER prefixhub WITH PASSWORD 'changeme';
CREATE DATABASE prefixhub OWNER prefixhub;
```

### Run migrations

```bash
alembic upgrade head
```

### Start the bot

```bash
PYTHONPATH=. python -m bot.src.bot
```

### Start the dashboard

```bash
PYTHONPATH=. uvicorn dashboard.src.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Step 4 — First-time Discord Setup

1. Invite the bot to your server using the URL from Step 1
2. In Discord, run `/setup #your-leaks-channel`
3. Run `/track Travis Scott` to add your first artist
4. Run `/subscribe Travis Scott` to subscribe to notifications

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests use an in-memory SQLite database — no PostgreSQL required for testing.
