"""
SyriaBot - Extended Stats Router
=================================

StatBot-like analytics endpoints with caching.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import csv
import io
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse

from src.core.logger import logger
from src.core.config import config
from src.api.errors import APIError, ErrorCode
from src.services.database import db
from src.api.dependencies import get_bot
from src.api.services.cache import get_cache_service
from src.api.utils import get_client_ip


router = APIRouter(prefix="/api/syria/stats", tags=["Extended Stats"])

# Cache TTL (5 minutes for extended stats)
EXTENDED_STATS_CACHE_TTL = 300


@router.get("/all")
async def get_all_extended_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Days for daily history"),
) -> JSONResponse:
    """
    Get all extended stats in one request.

    Returns monthly, channels, hours, member growth, and daily history.
    More efficient than multiple separate calls.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        # Check cache
        cache_key = f"extended_stats_all_{days}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            elapsed_ms = round((time.time() - start_time) * 1000)
            logger.tree("Extended Stats All (Cached)", [
                ("Client IP", client_ip),
                ("Response Time", f"{elapsed_ms}ms"),
            ], emoji="⚡")
            return JSONResponse(
                content=cached_data,
                headers={"X-Cache": "HIT"}
            )

        # Fetch all data
        monthly_stats = db.get_monthly_stats(config.GUILD_ID)
        channel_stats = db.get_channel_stats(config.GUILD_ID, limit=20)
        hourly_stats = db.get_server_peak_hours(config.GUILD_ID)
        member_growth = db.get_member_growth_daily(config.GUILD_ID, days=days)
        daily_history = db.get_daily_stats(config.GUILD_ID, days=days)

        # Fill in missing hours
        hours_map = {h["hour"]: h for h in hourly_stats}
        complete_hours = []
        for hour in range(24):
            if hour in hours_map:
                complete_hours.append(hours_map[hour])
            else:
                complete_hours.append({
                    "guild_id": config.GUILD_ID,
                    "hour": hour,
                    "message_count": 0,
                    "voice_joins": 0,
                })

        response_data = {
            "monthly_stats": monthly_stats,
            "channels": channel_stats,
            "hourly_stats": complete_hours,
            "member_growth": member_growth,
            "daily_history": daily_history,
        }

        # Cache response
        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Extended Stats All", [
            ("Client IP", client_ip),
            ("Days", str(days)),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📊")

        return JSONResponse(
            content=response_data,
            headers={"X-Cache": "MISS"}
        )
    except Exception as e:
        logger.error_tree("Extended Stats All Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/history")
async def get_stats_history(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    days: int = Query(30, ge=1, le=365, description="Number of days if no date range"),
) -> JSONResponse:
    """
    Get daily stats history.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        # Check cache
        cache_key = f"stats_history_{start_date}_{end_date}_{days}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        if start_date and end_date:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
            daily_stats = db.get_daily_stats_range(config.GUILD_ID, start_date, end_date)
        else:
            daily_stats = db.get_daily_stats(config.GUILD_ID, days=days)

        response_data = {
            "daily_stats": daily_stats,
            "count": len(daily_stats),
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Stats History API", [
            ("Client IP", client_ip),
            ("Days", str(len(daily_stats))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📊")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except ValueError as e:
        raise APIError(ErrorCode.BAD_REQUEST, detail=f"Invalid date format: {e}")
    except Exception as e:
        logger.error_tree("Stats History API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/monthly")
async def get_monthly_stats(request: Request) -> JSONResponse:
    """
    Get monthly aggregated stats.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = "stats_monthly"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        monthly_stats = db.get_monthly_stats(config.GUILD_ID)

        response_data = {
            "monthly_stats": monthly_stats,
            "count": len(monthly_stats),
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Monthly Stats API", [
            ("Client IP", client_ip),
            ("Months", str(len(monthly_stats))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📅")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Monthly Stats API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/channels")
async def get_channel_stats(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Max channels to return"),
) -> JSONResponse:
    """
    Get channel activity statistics.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"stats_channels_{limit}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        channel_stats = db.get_channel_stats(config.GUILD_ID, limit=limit)

        response_data = {
            "channels": channel_stats,
            "count": len(channel_stats),
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Channel Stats API", [
            ("Client IP", client_ip),
            ("Channels", str(len(channel_stats))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📺")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Channel Stats API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/hours")
async def get_hourly_stats(request: Request) -> JSONResponse:
    """
    Get hourly activity patterns.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = "stats_hours"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        hourly_stats = db.get_server_peak_hours(config.GUILD_ID)

        # Fill in missing hours
        hours_map = {h["hour"]: h for h in hourly_stats}
        complete_hours = []
        for hour in range(24):
            if hour in hours_map:
                complete_hours.append(hours_map[hour])
            else:
                complete_hours.append({
                    "guild_id": config.GUILD_ID,
                    "hour": hour,
                    "message_count": 0,
                    "voice_joins": 0,
                })

        response_data = {"hourly_stats": complete_hours}
        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Hourly Stats API", [
            ("Client IP", client_ip),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="⏰")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Hourly Stats API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/members/growth")
async def get_member_growth(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Number of days"),
    period: str = Query("daily", description="daily or monthly"),
) -> JSONResponse:
    """
    Get member growth statistics.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"stats_growth_{period}_{days}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        if period == "monthly":
            growth_stats = db.get_member_growth_monthly(config.GUILD_ID)
        else:
            growth_stats = db.get_member_growth_daily(config.GUILD_ID, days=days)

        response_data = {
            "growth": growth_stats,
            "period": period,
            "count": len(growth_stats),
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Member Growth API", [
            ("Client IP", client_ip),
            ("Period", period),
            ("Records", str(len(growth_stats))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📈")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Member Growth API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/voice-channels")
async def get_voice_channel_breakdown(
    request: Request,
    limit: int = Query(10, ge=1, le=50, description="Max channels to return"),
) -> JSONResponse:
    """
    Get voice channel usage breakdown.
    Shows which voice channels are most popular by total minutes.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"stats_voice_channels_{limit}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        voice_stats = db.get_voice_channel_breakdown(config.GUILD_ID, limit=limit)

        response_data = {
            "channels": voice_stats,
            "count": len(voice_stats),
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Voice Channels API", [
            ("Client IP", client_ip),
            ("Channels", str(len(voice_stats))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="🎤")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Voice Channels API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/reactions")
async def get_reaction_stats(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Max users to return"),
) -> JSONResponse:
    """
    Get reaction statistics.
    Shows top users by reactions given and received.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"stats_reactions_{limit}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        reaction_stats = db.get_reaction_stats(config.GUILD_ID, limit=limit)

        response_data = {
            "users": reaction_stats,
            "count": len(reaction_stats),
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Reaction Stats API", [
            ("Client IP", client_ip),
            ("Users", str(len(reaction_stats))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="💜")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Reaction Stats API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/engagement")
async def get_engagement_leaderboard(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Max users to return"),
) -> JSONResponse:
    """
    Get engagement score leaderboard.
    Engagement combines messages, voice, reactions, replies, threads, etc.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"stats_engagement_{limit}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        engagement_stats = db.get_engagement_leaderboard(config.GUILD_ID, limit=limit)

        response_data = {
            "leaderboard": engagement_stats,
            "count": len(engagement_stats),
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Engagement Stats API", [
            ("Client IP", client_ip),
            ("Users", str(len(engagement_stats))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="🏆")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Engagement Stats API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/roles")
async def get_role_distribution(
    request: Request,
    date: Optional[str] = Query(None, description="Date for snapshot (YYYY-MM-DD), defaults to latest"),
) -> JSONResponse:
    """
    Get role distribution snapshot.
    Shows member counts per role.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"stats_roles_{date or 'latest'}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        role_stats = db.get_role_distribution(config.GUILD_ID, date=date)

        response_data = {
            "roles": role_stats,
            "count": len(role_stats),
            "date": date or "latest",
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Role Distribution API", [
            ("Client IP", client_ip),
            ("Roles", str(len(role_stats))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="🎭")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Role Distribution API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/export")
async def export_stats(
    request: Request,
    type: str = Query("leaderboard", description="Data type: leaderboard, engagement, channels"),
    format: str = Query("csv", description="Export format: csv"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to export"),
) -> StreamingResponse:
    """
    Export statistics data as CSV.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()

    try:
        # Get data based on type
        if type == "leaderboard":
            data = db.get_leaderboard(config.GUILD_ID, limit=limit)
            headers = ["rank", "user_id", "xp", "level", "total_messages", "voice_minutes"]
        elif type == "engagement":
            data = db.get_engagement_leaderboard(config.GUILD_ID, limit=limit)
            headers = ["user_id", "engagement_score", "total_messages", "voice_minutes",
                      "reactions_given", "reactions_received", "replies_sent",
                      "threads_created", "links_shared", "commands_used", "streak_days"]
        elif type == "channels":
            data = db.get_channel_stats(config.GUILD_ID, limit=limit)
            headers = ["channel_id", "channel_name", "total_messages", "last_message_at"]
        elif type == "voice_channels":
            data = db.get_voice_channel_breakdown(config.GUILD_ID, limit=limit)
            headers = ["channel_id", "channel_name", "total_minutes", "peak_users", "session_count"]
        elif type == "reactions":
            data = db.get_reaction_stats(config.GUILD_ID, limit=limit)
            headers = ["user_id", "reactions_given", "reactions_received", "total_reactions"]
        else:
            raise APIError(ErrorCode.BAD_REQUEST, detail=f"Unknown export type: {type}")

        # Generate CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()

        for i, row in enumerate(data):
            if type == "leaderboard":
                row["rank"] = i + 1
            writer.writerow(row)

        output.seek(0)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Export Stats API", [
            ("Client IP", client_ip),
            ("Type", type),
            ("Records", str(len(data))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📤")

        filename = f"syria_{type}_{datetime.now().strftime('%Y%m%d')}.csv"
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except APIError:
        raise
    except Exception as e:
        logger.error_tree("Export Stats API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/health")
async def get_health_score(request: Request) -> JSONResponse:
    """
    Get server health score (0-100) based on activity metrics.

    Score is calculated from:
    - Message activity vs last week (40%)
    - Daily active users vs last week (30%)
    - Member growth (net positive = bonus, net negative = penalty) (20%)
    - Voice activity (10%)
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = "stats_health"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        data = db.get_health_score_data(config.GUILD_ID)

        # Calculate score components
        this_week = data["this_week"]
        last_week = data["last_week"]
        growth = data["growth"]

        # Message activity score (0-40)
        if last_week["messages"] > 0:
            msg_ratio = this_week["messages"] / last_week["messages"]
            msg_score = min(40, max(0, 20 + (msg_ratio - 1) * 20))
        else:
            msg_score = 20 if this_week["messages"] > 0 else 0

        # DAU score (0-30)
        if last_week["avg_dau"] > 0:
            dau_ratio = this_week["avg_dau"] / last_week["avg_dau"]
            dau_score = min(30, max(0, 15 + (dau_ratio - 1) * 15))
        else:
            dau_score = 15 if this_week["avg_dau"] > 0 else 0

        # Growth score (0-20)
        joins = growth["joins"] or 0
        leaves = growth["leaves"] or 0
        net = joins - leaves
        if joins > 0:
            growth_ratio = net / joins
            growth_score = min(20, max(0, 10 + growth_ratio * 10))
        else:
            growth_score = 10

        # Voice score (0-10)
        if last_week["voice_peak"] > 0:
            voice_ratio = this_week["voice_peak"] / last_week["voice_peak"]
            voice_score = min(10, max(0, 5 + (voice_ratio - 1) * 5))
        else:
            voice_score = 5 if this_week["voice_peak"] > 0 else 0

        total_score = round(msg_score + dau_score + growth_score + voice_score)

        # Determine health status
        if total_score >= 80:
            status = "excellent"
        elif total_score >= 60:
            status = "good"
        elif total_score >= 40:
            status = "fair"
        else:
            status = "needs_attention"

        response_data = {
            "score": total_score,
            "status": status,
            "breakdown": {
                "messages": round(msg_score),
                "daily_active": round(dau_score),
                "growth": round(growth_score),
                "voice": round(voice_score),
            },
            "comparison": {
                "this_week": this_week,
                "last_week": last_week,
                "growth": growth,
            }
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Health Score API", [
            ("Client IP", client_ip),
            ("Score", str(total_score)),
            ("Status", status),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="💚")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Health Score API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/channels/trends")
async def get_channel_trends(
    request: Request,
    days: int = Query(30, ge=1, le=90, description="Days of history"),
) -> JSONResponse:
    """
    Get daily message trends for top channels.
    Returns time series data for multi-line chart.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"stats_channel_trends_{days}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        daily_stats = db.get_channel_daily_stats(config.GUILD_ID, days=days)

        # Group by date for chart data
        dates = {}
        channels = {}
        for row in daily_stats:
            date = row["date"]
            channel_id = row["channel_id"]
            channel_name = row["channel_name"] or "Unknown"
            count = row["message_count"]

            if date not in dates:
                dates[date] = {}
            dates[date][channel_name] = count

            if channel_name not in channels:
                channels[channel_name] = 0
            channels[channel_name] += count

        # Get top 5 channels by total
        top_channels = sorted(channels.items(), key=lambda x: x[1], reverse=True)[:5]
        top_names = [c[0] for c in top_channels]

        # Build chart data
        chart_data = []
        for date in sorted(dates.keys()):
            point = {"date": date}
            for name in top_names:
                point[name] = dates[date].get(name, 0)
            chart_data.append(point)

        response_data = {
            "chart_data": chart_data,
            "channels": top_names,
            "totals": dict(top_channels),
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Channel Trends API", [
            ("Client IP", client_ip),
            ("Days", str(days)),
            ("Channels", str(len(top_names))),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📊")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Channel Trends API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/retention")
async def get_retention_stats(
    request: Request,
    days_ago: int = Query(7, ge=1, le=30, description="Days ago when cohort joined"),
) -> JSONResponse:
    """
    Get member retention statistics.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"stats_retention_{days_ago}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        retention = db.get_retention_stats(config.GUILD_ID, days=days_ago)

        await cache.set_response(cache_key, retention)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Retention Stats API", [
            ("Client IP", client_ip),
            ("Days Ago", str(days_ago)),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="🔄")

        return JSONResponse(content=retention, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Retention Stats API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/comparison")
async def get_period_comparison(
    request: Request,
) -> JSONResponse:
    """
    Get this week vs last week comparison data.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = "stats_comparison"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        data = db.get_health_score_data(config.GUILD_ID)

        this_week = data["this_week"]
        last_week = data["last_week"]
        growth = data["growth"]

        # Calculate percentage changes
        def calc_change(current, previous):
            if previous == 0:
                return 100 if current > 0 else 0
            return round(((current - previous) / previous) * 100, 1)

        response_data = {
            "this_week": this_week,
            "last_week": last_week,
            "growth": growth,
            "changes": {
                "messages": calc_change(this_week["messages"], last_week["messages"]),
                "avg_dau": calc_change(this_week["avg_dau"], last_week["avg_dau"]),
                "voice_peak": calc_change(this_week["voice_peak"], last_week["voice_peak"]),
            }
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("Period Comparison API", [
            ("Client IP", client_ip),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="📊")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("Period Comparison API Error", e, [("Client IP", client_ip)])
        raise APIError(ErrorCode.SERVER_ERROR)


@router.get("/user/{user_id}/interactions")
async def get_user_interactions(
    request: Request,
    user_id: int,
    limit: int = Query(5, ge=1, le=10, description="Max interactions per category"),
    bot=Depends(get_bot),
) -> JSONResponse:
    """
    Get user's top social interactions.
    Returns who they spend most voice time with, mention most, and reply to most.
    """
    client_ip = get_client_ip(request)
    start_time = time.time()
    cache = get_cache_service()

    try:
        cache_key = f"user_interactions_{user_id}_{limit}"
        cached_data = await cache.get_response(cache_key, EXTENDED_STATS_CACHE_TTL)

        if cached_data:
            return JSONResponse(content=cached_data, headers={"X-Cache": "HIT"})

        # Get raw interaction data from database
        interactions = db.get_top_interactions(user_id, config.GUILD_ID, limit)

        # Enrich with user info (avatars, usernames)
        async def enrich_user(uid: int) -> dict:
            """Get user info from cache or Discord."""
            try:
                user = bot.get_user(uid) or await bot.fetch_user(uid)
                return {
                    "user_id": str(uid),
                    "username": user.name,
                    "display_name": user.display_name,
                    "avatar": user.display_avatar.url if user.display_avatar else None,
                }
            except Exception:
                return {
                    "user_id": str(uid),
                    "username": "Unknown",
                    "display_name": "Unknown",
                    "avatar": None,
                }

        # Enrich voice partners
        enriched_voice = []
        for entry in interactions.get("voice_partners", []):
            user_info = await enrich_user(entry["user_id"])
            user_info["minutes"] = entry["minutes"]
            enriched_voice.append(user_info)

        # Enrich mentions
        enriched_mentions = []
        for entry in interactions.get("mentions", []):
            user_info = await enrich_user(entry["user_id"])
            user_info["count"] = entry["count"]
            enriched_mentions.append(user_info)

        # Enrich replies
        enriched_replies = []
        for entry in interactions.get("replies", []):
            user_info = await enrich_user(entry["user_id"])
            user_info["count"] = entry["count"]
            enriched_replies.append(user_info)

        response_data = {
            "user_id": str(user_id),
            "voice_partners": enriched_voice,
            "mentions": enriched_mentions,
            "replies": enriched_replies,
        }

        await cache.set_response(cache_key, response_data)

        elapsed_ms = round((time.time() - start_time) * 1000)
        logger.tree("User Interactions API", [
            ("Client IP", client_ip),
            ("User", str(user_id)),
            ("Response Time", f"{elapsed_ms}ms"),
        ], emoji="👥")

        return JSONResponse(content=response_data, headers={"X-Cache": "MISS"})
    except Exception as e:
        logger.error_tree("User Interactions API Error", e, [
            ("Client IP", client_ip),
            ("User", str(user_id)),
        ])
        raise APIError(ErrorCode.SERVER_ERROR)


__all__ = ["router"]
