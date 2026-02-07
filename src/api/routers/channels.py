"""
SyriaBot - Channels Router
==========================

Per-channel message statistics endpoints.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.core.logger import logger
from src.core.config import config
from src.core.constants import TIMEZONE_DAMASCUS
from src.services.database import db
from src.api.models.stats import ChannelStats, ChannelsResponse
from src.api.services.cache import get_cache_service
from src.api.utils import get_client_ip


router = APIRouter(prefix="/api/syria", tags=["Channels"])


@router.get("/channels")
async def get_channels(request: Request) -> JSONResponse:
    """
    Get per-channel message statistics.

    Returns message counts for all tracked channels.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        # Check cache
        cache_key = "channels"
        cached_data = await cache.get_response(cache_key, cache.stats_cache_ttl)

        if cached_data:
            elapsed_ms = round((time.time() - start_time) * 1000)
            logger.tree("Channels API (Cached)", [
                ("Client IP", client_ip),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="⚡")
            return JSONResponse(
                content=cached_data,
                headers={
                    "Cache-Control": "public, max-age=60",
                    "X-Cache": "HIT",
                }
            )

        # Get channel stats from database
        channel_stats = db.get_channel_stats(config.GUILD_ID, limit=100)

        # Format response
        channels = [
            ChannelStats(
                channel_id=str(ch.get("channel_id")),
                channel_name=ch.get("channel_name", "Unknown"),
                total_messages=ch.get("total_messages", 0),
            )
            for ch in channel_stats
        ]

        response = ChannelsResponse(
            channels=channels,
            updated_at=datetime.now(TIMEZONE_DAMASCUS),
        )

        response_data = response.model_dump(mode="json")

        # Cache response
        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Channels API Request", [
            ("Client IP", client_ip),
            ("Channels", str(len(channels))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📺")

        return JSONResponse(
            content=response_data,
            headers={
                "Cache-Control": "public, max-age=60",
                "X-Cache": "MISS",
            }
        )

    except Exception as e:
        logger.error_tree("Channels API Error", e, [
            ("Client IP", client_ip),
        ])
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500,
        )


__all__ = ["router"]
