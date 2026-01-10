"""
SyriaBot - Entry Point
======================

Main entry point for the bot.

Author: حَـــــنَّـــــا
"""

import asyncio
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from src.bot import SyriaBot
from src.core.config import config
from src.core.logger import log


async def main():
    """Main entry point."""
    if not config.TOKEN:
        log.tree("Startup Failed", [
            ("Reason", "SYRIA_BOT_TOKEN not set"),
        ], emoji="🚨")
        sys.exit(1)

    bot = SyriaBot()

    try:
        await bot.start(config.TOKEN)
    except KeyboardInterrupt:
        log.tree("Shutdown", [
            ("Reason", "Keyboard interrupt"),
        ], emoji="🛑")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
