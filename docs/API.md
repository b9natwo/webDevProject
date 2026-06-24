# API Reference

The Prefix Hub dashboard exposes a REST API. In development, interactive docs are available at:
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

All API endpoints require authentication via the session cookie set by Discord OAuth2 login.

---

## Authentication

### `GET /auth/login`
Redirects to Discord's OAuth2 consent screen.

### `GET /auth/callback?code=...&state=...`
OAuth2 callback. Sets the `ph_session` HTTP-only cookie on success. Redirects to `/`.

### `GET /auth/logout`
Clears the session cookie. Redirects to `/`.

### `GET /auth/me`
Returns the authenticated user's profile.

**Response 200:**
```json
{
  "id": "123456789",
  "username": "yourname",
  "avatar_hash": "abc123",
  "premium_tier": "free",
  "is_bot_owner": false
}
```

---

## Health

### `GET /api/health`
Returns service health status. Safe to call without auth.

**Response 200:**
```json
{ "status": "ok", "database": true }
```

---

## Guilds

### `GET /api/guilds/`
List guilds the authenticated user manages (bot owners see all).

**Response 200:** Array of guild objects.

### `GET /api/guilds/{guild_discord_id}`
Get detailed config for a guild the user owns.

### `PATCH /api/guilds/{guild_discord_id}/channels`
Update channel configuration.

**Request body:**
```json
{
  "leaks_channel_id": 1234567890,
  "audit_channel_id": null,
  "artists_channel_id": null,
  "polls_channel_id": null
}
```

---

## Artists

### `GET /api/guilds/{guild_discord_id}/artists`
List all tracked artists for a guild.

**Response 200:**
```json
[
  {
    "id": 1,
    "artist_name": "Travis Scott",
    "role_id": "987654321",
    "is_active": true,
    "added_at": "2024-01-01T00:00:00Z"
  }
]
```

### `POST /api/guilds/{guild_discord_id}/artists`
Add an artist to a guild's tracking list.

**Request body:**
```json
{ "name": "Travis Scott", "role_id": 987654321 }
```

**Response 201:**
```json
{ "id": 1, "artist_name": "Travis Scott", "status": "added" }
```

**Error 409:** Artist already tracked.

### `DELETE /api/guilds/{guild_discord_id}/artists/{artist_name}`
Remove (soft-delete) a tracked artist.

---

## Feeds

### `GET /api/feeds/`
List all configured RSS feeds and their status.

---

## Premium

### `GET /api/premium/status`
Get the authenticated user's subscription status.

**Response 200:**
```json
{ "tier": "free", "expires_at": null }
```

### `POST /api/premium/checkout/{tier}`
Create a Stripe checkout session. Returns redirect URL.

**Path parameter:** `tier` — `standard` or `pro`

**Response 200:**
```json
{ "checkout_url": "https://checkout.stripe.com/..." }
```

**Error 503:** Stripe not configured.

---

## Analytics

### `GET /api/analytics/overview`
Platform-wide statistics.

**Response 200:**
```json
{
  "total_guilds": 42,
  "total_feed_entries": 12500,
  "feed_entries_last_7d": 350,
  "notifications_last_30d": 8200,
  "total_tracked_artists": 650
}
```

### `GET /api/analytics/recent-entries?limit=20`
Most recently detected leak entries.

**Query params:**
- `limit` — Number of results (1–50, default 20)

---

## Error Responses

All endpoints return errors in this format:
```json
{ "detail": "Human-readable error message" }
```

| Status | Meaning |
|---|---|
| 400 | Bad request / validation error |
| 401 | Not authenticated |
| 403 | Authenticated but not authorised (banned or wrong guild) |
| 404 | Resource not found |
| 409 | Conflict (e.g. duplicate artist) |
| 503 | Feature not configured (e.g. Stripe) |
| 500 | Internal server error |
