# Changelog

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Changed
- Redesigned dashboard with professional landing page, sidebar navigation, and mobile support
- Renamed tiers: `standard` → `Supporter`, `pro` → `Premium` to better reflect the community model
- Supporter tier: $4/mo — 25 artists, Discord role, early access
- Premium tier: $12/mo — unlimited artists, personal bot invite, priority polls (15s), advanced filters
- Dashboard now shows artist usage progress bar with tier limits
- Feed health tab with live status indicators and failure counts
- Settings tab with notification toggles and Premium filter panel
- Upgrade tab with inline plan comparison and Stripe billing portal link
- Toast notifications for all user actions
- Animated stat counters on landing page

### Added
- CONTRIBUTING.md
- CODE_OF_CONDUCT.md
- CHANGELOG.md
- `PremiumService.can_invite_bot()` and `has_priority_feeds()` entitlement helpers
- `supporter_max_artists` and `supporter_max_guilds` settings
- `feed_poll_interval_premium_seconds` config for priority polling

### Fixed
- Guild list now filtered server-side to only return guilds owned by the requesting user
- Premium expiry downgrade now works correctly for Supporter tier

---

## [1.0.0] — Initial Release

- Discord bot with slash commands: `/track`, `/untrack`, `/list`, `/info`
- RSS feed polling from leaked.cx
- Discord OAuth2 dashboard
- Three-tier system: Free / Supporter / Premium
- Stripe subscription integration
- Alembic database migrations
- FastAPI dashboard backend
