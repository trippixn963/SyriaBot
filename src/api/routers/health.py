"""
SyriaBot - Health Router
========================

Health check and system status endpoints.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import math
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from src.core.logger import logger
from src.core.constants import TIMEZONE_EST
from src.api.dependencies import get_bot_optional
from src.api.models.base import HealthResponse, DiscordStatus


router = APIRouter(tags=["Health"])

# Track startup time
_start_time: float = 0


def set_start_time() -> None:
    """Set the API start time."""
    global _start_time
    _start_time = time.time()


@router.get("/health")
async def health_check(
    bot: Any = Depends(get_bot_optional),
) -> HealthResponse:
    """
    Health check endpoint with full status.

    Returns bot status, uptime, and Discord connection info.
    """
    now = datetime.now(TIMEZONE_EST)
    start = datetime.fromtimestamp(_start_time, tz=TIMEZONE_EST) if _start_time else now
    uptime_seconds = int(time.time() - _start_time) if _start_time else 0

    # Format uptime as human-readable
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    # Get bot status
    is_ready = bot.is_ready() if bot else False
    latency_ms = round(bot.latency * 1000) if is_ready and bot.latency and math.isfinite(bot.latency) else None

    discord_status = DiscordStatus(
        connected=is_ready,
        latency_ms=latency_ms,
        guilds=len(bot.guilds) if is_ready else 0,
    )

    return HealthResponse(
        status="healthy" if is_ready else "starting",
        bot="SyriaBot",
        run_id=getattr(logger, "run_id", None),
        uptime=uptime_str,
        uptime_seconds=uptime_seconds,
        started_at=start,
        timestamp=now,
        timezone="America/New_York (EST)",
        discord=discord_status,
    )


__all__ = ["router", "set_start_time"]
