"""
bot/src/bot.py
Entry point for the Prefix Hub Discord bot.
"""
from __future__ import annotations

import asyncio
import sys

from shared.config import get_settings
from shared.logging_config import configure_logging


async def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, service_name="prefix-hub-bot")

    # Import after logging is configured so early log calls are captured
    from bot.src.core.client import PrefixHubBot

    bot = PrefixHubBot()
    async with bot:
        await bot.start(settings.discord_token.get_secret_value())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
