"""
SyriaBot - Async Utilities
==========================

Utilities for handling async operations with proper error logging.
Eliminates silent failures in asyncio.gather and background tasks.

Usage:
    from src.utils.async_utils import gather_with_logging, create_safe_task

    # Instead of asyncio.gather with return_exceptions:
    await gather_with_logging(
        ("Send DM", send_dm()),
        ("Update DB", update_database()),
        context="XP Grant",
    )

    # Instead of asyncio.create_task:
    create_safe_task(self._cleanup_loop(), "Cleanup Loop")

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from typing import Tuple, Coroutine, Any, List, Optional

from src.core.logger import logger


async def gather_with_logging(
    *operations: Tuple[str, Coroutine[Any, Any, Any]],
    context: Optional[str] = None,
) -> List[Any]:
    """
    Run multiple async operations concurrently with error logging.

    Unlike asyncio.gather with return_exceptions=True, this function
    logs any exceptions that occur so failures aren't silent.
    """
    names = [name for name, _ in operations]
    coros = [coro for _, coro in operations]

    results = await asyncio.gather(*coros, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            error_details = [
                ("Operation", names[i]),
                ("Error Type", type(result).__name__),
                ("Error", str(result)[:100]),
            ]
            if context:
                error_details.insert(0, ("Context", context))

            logger.warning("Async Operation Failed", error_details)

    return results


def create_safe_task(
    coro: Coroutine[Any, Any, Any],
    name: str = "Background Task",
) -> asyncio.Task:
    """
    Create a background task with automatic error logging.

    Unlike raw asyncio.create_task(), this catches and logs any exceptions
    instead of letting them silently disappear.
    """
    async def wrapped():
        try:
            return await coro
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Background Task Failed", [
                ("Task", name),
                ("Error Type", type(e).__name__),
                ("Error", str(e)[:200]),
            ])

    return asyncio.create_task(wrapped())


async def run_with_timeout(
    coro: Coroutine[Any, Any, Any],
    timeout: float,
    name: str = "Operation",
) -> Optional[Any]:
    """
    Run a coroutine with a timeout, logging if it times out.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Operation Timed Out", [
            ("Operation", name),
            ("Timeout", f"{timeout}s"),
        ])
        return None


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "gather_with_logging",
    "create_safe_task",
    "run_with_timeout",
]
