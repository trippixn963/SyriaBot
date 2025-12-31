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
        log.error("SYRIA_BOT_TOKEN not set in environment")
        sys.exit(1)

    bot = SyriaBot()

    try:
        await bot.start(config.TOKEN)
    except KeyboardInterrupt:
        log.info("Received keyboard interrupt")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
