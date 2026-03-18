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

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from src.core.logger import logger
from src.api.errors import APIError, ErrorCode
from src.core.constants import TIMEZONE_EST
from src.services.database import db
from src.api.dependencies import get_bot, PaginationParams, get_pagination, get_period
from src.api.models.leaderboard import LeaderboardEntry
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
            banner_url = user_data.banner_url
            display_name = user_data.display_name
            username = user_data.username
            is_booster = user_data.is_booster
        else:
            avatar_url, banner_url, display_name, username, is_booster = None, None, str(user_id), None, False

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
            banner=banner_url,
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


@router.get("/leaderboard")
async def get_leaderboard(
    request: Request,
    pagination: PaginationParams = Depends(get_pagination),
    period: str = Depends(get_period),
    sort: str = Query("xp", description="Sort/rank by: xp, voice, messages"),
    bot: Any = Depends(get_bot),
) -> JSONResponse:
    """
    Get the XP leaderboard.

    Query Parameters:
    - limit: Number of entries (1-100, default 50)
    - offset: Starting position (default 0)
    - period: Time filter (all, month, week, today)
    - sort: Rank change context (xp, voice, messages)
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        # Validate sort parameter
        if sort not in ("xp", "voice", "messages"):
            sort = "xp"

        # Check cache
        cache_key = f"leaderboard:{pagination.limit}:{pagination.offset}:{period}:{sort}"
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
        previous_ranks = db.get_previous_ranks(user_ids=user_ids, sort_by=sort) if user_ids else {}

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
            "updated_at": datetime.now(TIMEZONE_EST).isoformat(),
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


@router.get("/search")
async def search_users(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100, description="Search query"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    bot: Any = Depends(get_bot),
) -> JSONResponse:
    """
    Search leaderboard users by name.

    Searches Discord display names and usernames against guild members
    who have XP data. Returns enriched leaderboard entries.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        query = q.strip().lower()

        # Check cache
        cache_key = f"search:{query}:{limit}"
        cached_data = await cache.get_response(cache_key, 30)
        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        from src.core.config import config
        guild = bot.get_guild(config.GUILD_ID)
        if not guild:
            return JSONResponse(content={"results": []})

        # Use Discord's server-side member search (fast, no local iteration)
        try:
            members = await guild.query_members(query=query, limit=limit)
        except Exception:
            members = []
        matched_ids = [m.id for m in members if not m.bot]

        if not matched_ids:
            response_data = {"results": []}
            await cache.set_response(cache_key, response_data)
            return JSONResponse(content=response_data)

        # Get XP data for matched users
        raw_entries = db.get_users_by_ids(matched_ids, config.GUILD_ID)
        if not raw_entries:
            response_data = {"results": []}
            await cache.set_response(cache_key, response_data)
            return JSONResponse(content=response_data)

        # Sort by XP descending and limit
        raw_entries.sort(key=lambda e: e.get("xp", 0), reverse=True)
        raw_entries = raw_entries[:limit]

        # Enrich with Discord data
        enriched = await _enrich_leaderboard(bot, raw_entries)

        response_data = {
            "results": [entry.model_dump() for entry in enriched],
        }
        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Search API Request", [
            ("Client IP", client_ip),
            ("Query", q[:30]),
            ("Results", str(len(enriched))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="🔍")

        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error_tree("Search API Error", e, [
            ("Client IP", client_ip),
            ("Query", q[:30]),
        ])
        raise APIError(ErrorCode.SERVER_ERROR)


__all__ = ["router"]
