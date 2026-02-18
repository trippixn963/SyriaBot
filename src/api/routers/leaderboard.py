"""
SyriaBot - Leaderboard Router
=============================

XP leaderboard endpoints.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.core.logger import logger
from src.api.errors import APIError, ErrorCode
from src.core.constants import TIMEZONE_DAMASCUS
from src.services.database import db
from src.api.dependencies import get_bot, PaginationParams, get_pagination, get_period
from src.api.models.leaderboard import LeaderboardEntry, LeaderboardResponse
from src.api.services.cache import get_cache_service
from src.api.services.discord import get_discord_service
from src.api.utils import format_voice_time, format_last_seen, get_client_ip


router = APIRouter(prefix="/api/syria", tags=["Leaderboard"])


async def _enrich_leaderboard(
    bot: Any,
    leaderboard: list[dict],
    include_xp_gained: bool = False,
    previous_ranks: dict[int, int] = None,
) -> list[LeaderboardEntry]:
    """Add avatar URLs, names, booster status, and rank changes to entries."""
    if not leaderboard:
        return []

    discord = get_discord_service(bot)
    user_ids = [entry["user_id"] for entry in leaderboard]
    user_data_map = await discord.fetch_users_batch(user_ids)

    enriched = []
    for entry in leaderboard:
        user_id = entry["user_id"]
        user_data = user_data_map.get(user_id)

        if user_data:
            avatar_url = user_data.avatar_url
            display_name = user_data.display_name
            username = user_data.username
            is_booster = user_data.is_booster
        else:
            avatar_url, display_name, username, is_booster = None, str(user_id), None, False

        last_active_at = entry.get("last_active_at", 0) or 0
        streak_days = entry.get("streak_days", 0) or 0

        # Calculate rank change
        rank_change = None
        current_rank = entry["rank"]
        if previous_ranks and user_id in previous_ranks:
            rank_change = previous_ranks[user_id] - current_rank

        enriched.append(LeaderboardEntry(
            rank=current_rank,
            rank_change=rank_change,
            user_id=str(user_id),
            display_name=display_name,
            username=username,
            avatar=avatar_url,
            level=entry["level"],
            xp=entry["xp"],
            xp_gained=entry.get("xp_gained") if include_xp_gained else None,
            total_messages=entry["total_messages"],
            voice_minutes=entry["voice_minutes"],
            voice_formatted=format_voice_time(entry["voice_minutes"]),
            is_booster=is_booster,
            last_active_at=last_active_at if last_active_at > 0 else None,
            last_seen=format_last_seen(last_active_at),
            streak_days=streak_days,
        ))

    return enriched


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    request: Request,
    pagination: PaginationParams = Depends(get_pagination),
    period: str = Depends(get_period),
    bot: Any = Depends(get_bot),
) -> JSONResponse:
    """
    Get the XP leaderboard.

    Query Parameters:
    - limit: Number of entries (1-100, default 50)
    - offset: Starting position (default 0)
    - period: Time filter (all, month, week, today)
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        # Check cache
        cache_key = f"leaderboard:{pagination.limit}:{pagination.offset}:{period}"
        cached_data = await cache.get_response(cache_key, cache.leaderboard_cache_ttl)

        if cached_data:
            elapsed_ms = round((time.time() - start_time) * 1000)
            logger.tree("Leaderboard API (Cached)", [
                ("Client IP", client_ip),
                ("Period", period),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="⚡")
            return JSONResponse(
                content=cached_data,
                headers={
                    "Cache-Control": "public, max-age=30",
                    "X-Cache": "HIT",
                }
            )

        # Get leaderboard from database
        if period != "all":
            raw_leaderboard = db.get_period_leaderboard(
                limit=pagination.limit,
                offset=pagination.offset,
                period=period
            )
            total_users = db.get_total_period_users(period=period)
        else:
            raw_leaderboard = db.get_leaderboard(
                limit=pagination.limit,
                offset=pagination.offset,
                period="all"
            )
            total_users = db.get_total_ranked_users(period="all")

        # Get previous ranks for rank change calculation
        user_ids = [entry["user_id"] for entry in raw_leaderboard]
        previous_ranks = db.get_previous_ranks(user_ids=user_ids) if user_ids else {}

        # Enrich with Discord data
        leaderboard = await _enrich_leaderboard(
            bot,
            raw_leaderboard,
            include_xp_gained=(period != "all"),
            previous_ranks=previous_ranks
        )

        response_data = {
            "leaderboard": [entry.model_dump() for entry in leaderboard],
            "total": total_users,
            "limit": pagination.limit,
            "offset": pagination.offset,
            "period": period,
            "updated_at": datetime.now(TIMEZONE_DAMASCUS).isoformat(),
        }

        # Cache response
        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Leaderboard API Request", [
            ("Client IP", client_ip),
            ("Limit", str(pagination.limit)),
            ("Offset", str(pagination.offset)),
            ("Period", period),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📊")

        return JSONResponse(
            content=response_data,
            headers={
                "Cache-Control": "public, max-age=30",
                "X-Cache": "MISS",
            }
        )

    except Exception as e:
        logger.error_tree("Leaderboard API Error", e, [
            ("Client IP", client_ip),
            ("Limit", str(pagination.limit)),
            ("Offset", str(pagination.offset)),
            ("Period", period),
        ])
        raise APIError(ErrorCode.SERVER_ERROR)


__all__ = ["router"]
