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
    shutdown_task = None

    def on_signal(sig: signal.Signals) -> None:
        nonlocal shutdown_task
        if shutdown_task is not None:
            return  # Already shutting down
        log.tree("Shutdown Signal", [
            ("Signal", sig.name),
        ], emoji="🛑")
        shutdown_task = asyncio.create_task(bot.close())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, on_signal, sig)

    try:
        await bot.start(config.TOKEN)
    except KeyboardInterrupt:
        pass
    finally:
        # If signal triggered close(), wait for it to finish
        if shutdown_task:
            try:
                await shutdown_task
            except Exception:
                pass
        elif not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
