"""
SyriaBot - Stats Router
=======================

Server statistics endpoints.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
import discord
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.core.logger import logger
from src.api.errors import APIError, ErrorCode
from src.core.config import config
from src.core.constants import TIMEZONE_DAMASCUS
from src.services.database import db
from src.api.dependencies import get_bot
from src.api.models.stats import ServerStats, TopUser, DailyStats
from src.api.services.cache import get_cache_service
from src.api.services.discord import get_discord_service
from src.api.utils import format_voice_time, format_last_seen, get_client_ip


router = APIRouter(prefix="/api/syria", tags=["Stats"])


async def _enrich_top_users(bot: Any, raw_leaderboard: list[dict]) -> list[TopUser]:
    """Enrich top users with Discord data."""
    if not raw_leaderboard:
        return []

    discord = get_discord_service(bot)
    user_ids = [entry["user_id"] for entry in raw_leaderboard]
    user_data_map = await discord.fetch_users_batch(user_ids)

    enriched = []
    for entry in raw_leaderboard:
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

        enriched.append(TopUser(
            rank=entry["rank"],
            rank_change=None,
            user_id=str(user_id),
            display_name=display_name,
            username=username,
            avatar=avatar_url,
            level=entry["level"],
            xp=entry["xp"],
            total_messages=entry["total_messages"],
            voice_minutes=entry["voice_minutes"],
            voice_formatted=format_voice_time(entry["voice_minutes"]),
            is_booster=is_booster,
            last_active_at=last_active_at if last_active_at > 0 else None,
            last_seen=format_last_seen(last_active_at),
            streak_days=streak_days,
        ))

    return enriched


@router.get("/stats")
async def get_stats(
    request: Request,
    bot: Any = Depends(get_bot),
) -> JSONResponse:
    """
    Get overall server XP statistics.

    Returns guild info, total stats, top 3 users, and daily activity history.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        # Check cache
        cache_key = "stats"
        cached_data = await cache.get_response(cache_key, cache.stats_cache_ttl)

        if cached_data:
            elapsed_ms = round((time.time() - start_time) * 1000)
            logger.tree("Stats API (Cached)", [
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

        # Get overall stats from database
        stats = db.get_xp_stats()

        # Get top 3 for quick display
        raw_top_3 = db.get_leaderboard(limit=3)
        top_3 = await _enrich_top_users(bot, raw_top_3)

        # Get guild info
        guild_icon = None
        guild_banner = None
        guild_name = "Syria"
        member_count = 0
        booster_count = 0
        online_count = 0

        if bot and bot.is_ready():
            guild = bot.get_guild(config.GUILD_ID)
            if guild:
                guild_name = guild.name
                member_count = guild.member_count or 0
                booster_count = guild.premium_subscription_count or 0
                online_count = sum(1 for m in guild.members if m.status != discord.Status.offline)
                if guild.icon:
                    guild_icon = guild.icon.url
                if guild.banner:
                    guild_banner = guild.banner.url

        # Get today's daily stats
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_stats = db.get_daily_stats(config.GUILD_ID, days=7)

        # Find today's stats
        today_stats = next(
            (d for d in daily_stats if d.get("date") == today_str),
            {"unique_users": 0, "new_members": 0, "voice_peak_users": 0}
        )

        # Format daily stats history
        daily_stats_history = [
            DailyStats(
                date=d.get("date", ""),
                unique_users=d.get("unique_users", 0),
                total_messages=d.get("total_messages", 0),
                voice_peak_users=d.get("voice_peak_users", 0),
                new_members=d.get("new_members", 0),
            )
            for d in daily_stats
        ]

        response = ServerStats(
            guild_name=guild_name,
            guild_icon=guild_icon,
            guild_banner=guild_banner,
            member_count=member_count,
            booster_count=booster_count,
            online_count=online_count,
            total_users=stats.get("total_users", 0),
            total_xp=stats.get("total_xp", 0),
            total_messages=stats.get("total_messages", 0),
            total_voice_minutes=stats.get("total_voice_minutes", 0),
            total_voice_formatted=format_voice_time(stats.get("total_voice_minutes", 0)),
            highest_level=stats.get("highest_level", 0),
            top_3=top_3,
            daily_active_users=today_stats.get("unique_users", 0),
            new_members_today=today_stats.get("new_members", 0),
            voice_peak_today=today_stats.get("voice_peak_users", 0),
            daily_stats_history=daily_stats_history,
            updated_at=datetime.now(TIMEZONE_DAMASCUS),
        )

        response_data = response.model_dump(mode="json")

        # Cache response
        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Stats API Request", [
            ("Client IP", client_ip),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📈")

        return JSONResponse(
            content=response_data,
            headers={
                "Cache-Control": "public, max-age=60",
                "X-Cache": "MISS",
            }
        )

    except Exception as e:
        logger.error_tree("Stats API Error", e, [
            ("Client IP", client_ip),
        ])
        raise APIError(ErrorCode.SERVER_ERROR)


__all__ = ["router"]
