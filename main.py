"""
SyriaBot - Entry Point
======================

Main entry point for the bot.

Author: حَـــــنَّـــــا
"""

import asyncio
import os
import signal
import sys

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from src.bot import SyriaBot
from src.core.config import config
from src.core.logger import log


async def main() -> None:
    """Main entry point."""
    if not config.TOKEN:
        log.tree("Startup Failed", [
            ("Reason", "SYRIA_TOKEN not set"),
        ], emoji="🚨")
        sys.exit(1)

    bot = SyriaBot()

    # Handle SIGTERM (systemctl stop/restart) gracefully
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_shutdown(bot, s)))

    try:
        await bot.start(config.TOKEN)
    except KeyboardInterrupt:
        pass
    finally:
        if not bot.is_closed():
            await bot.close()


async def _shutdown(bot: SyriaBot, sig: signal.Signals) -> None:
    """Handle shutdown signal from systemd."""
    log.tree("Shutdown Signal", [
        ("Signal", sig.name),
    ], emoji="🛑")
    await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
