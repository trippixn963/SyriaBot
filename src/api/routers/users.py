"""
SyriaBot - Users Router
=======================

User XP data endpoints.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse

from src.core.logger import logger
from src.api.errors import APIError, ErrorCode, error_response
from src.core.config import config
from src.core.constants import TIMEZONE_DAMASCUS
from src.services.database import db
from src.services.xp.utils import xp_progress
from src.api.dependencies import get_bot
from src.api.models.users import UserResponse, ChannelActivity
from src.api.services.discord import get_discord_service
from src.api.utils import format_voice_time, format_last_seen, get_client_ip


router = APIRouter(prefix="/api/syria", tags=["Users"])


@router.get("/user/{user_id}")
async def get_user(
    request: Request,
    user_id: int = Path(..., description="Discord user ID"),
    bot: Any = Depends(get_bot),
) -> JSONResponse:
    """
    Get XP data for a specific user.

    Path Parameters:
    - user_id: Discord user ID
    """
    client_ip = get_client_ip(request)

    try:
        # Get user data from database
        xp_data = db.get_user_xp(user_id, config.GUILD_ID)

        if not xp_data:
            raise APIError(ErrorCode.USER_NOT_FOUND)

        # Get rank
        rank = db.get_user_rank(user_id, config.GUILD_ID)

        # Get previous rank for rank change
        previous_ranks = db.get_previous_ranks(user_ids=[user_id])
        rank_change = None
        if user_id in previous_ranks:
            rank_change = previous_ranks[user_id] - rank

        # Get Discord info via service
        discord = get_discord_service(bot)
        user_data = await discord.fetch_user(user_id)

        # Calculate progress
        _, xp_into_level, xp_needed, progress = xp_progress(xp_data["xp"])

        # Calculate activity stats
        now = int(time.time())
        joined_at = user_data.joined_at
        days_in_server = max(1, (now - joined_at) // 86400) if joined_at else 1
        xp_per_day = round(xp_data["xp"] / days_in_server, 1) if days_in_server > 0 else 0
        messages_per_day = round(xp_data["total_messages"] / days_in_server, 1) if days_in_server > 0 else 0

        # Activity tracking
        last_active_at = xp_data.get("last_active_at", 0) or 0
        streak_days = xp_data.get("streak_days", 0) or 0

        # Extended stats
        commands_used = xp_data.get("commands_used", 0) or 0
        reactions_given = xp_data.get("reactions_given", 0) or 0
        images_shared = xp_data.get("images_shared", 0) or 0
        total_voice_sessions = xp_data.get("total_voice_sessions", 0) or 0
        longest_voice_session = xp_data.get("longest_voice_session", 0) or 0
        first_message_at = xp_data.get("first_message_at", 0) or 0
        mentions_received = xp_data.get("mentions_received", 0) or 0

        # Get peak activity hour
        peak_hour, peak_hour_count = db.get_peak_activity_hour(user_id, config.GUILD_ID)

        # Get invite count
        invites_count = db.get_invite_count(user_id, config.GUILD_ID)

        # Get top channel activity
        channel_activity = db.get_user_channel_activity(user_id, config.GUILD_ID, limit=10)
        channels = [
            ChannelActivity(
                channel_id=str(ch.get("channel_id")),
                channel_name=ch.get("channel_name", "Unknown"),
                message_count=ch.get("message_count", 0),
            )
            for ch in channel_activity
        ]

        logger.tree("User API Request", [
            ("Client IP", client_ip),
            ("ID", str(user_id)),
            ("Booster", "Yes" if user_data.is_booster else "No"),
            ("Channels", str(len(channels))),
        ], emoji="👤")

        response_data = UserResponse(
            user_id=str(user_id),
            display_name=user_data.display_name,
            username=user_data.username,
            avatar=user_data.avatar_url,
            rank=rank,
            rank_change=rank_change,
            level=xp_data["level"],
            xp=xp_data["xp"],
            xp_into_level=xp_into_level,
            xp_for_next=xp_needed,
            progress=round(progress * 100, 1),
            total_messages=xp_data["total_messages"],
            voice_minutes=xp_data["voice_minutes"],
            voice_formatted=format_voice_time(xp_data["voice_minutes"]),
            joined_at=joined_at,
            days_in_server=days_in_server,
            xp_per_day=xp_per_day,
            messages_per_day=messages_per_day,
            is_booster=user_data.is_booster,
            last_active_at=last_active_at if last_active_at > 0 else None,
            last_seen=format_last_seen(last_active_at),
            streak_days=streak_days,
            commands_used=commands_used,
            reactions_given=reactions_given,
            images_shared=images_shared,
            total_voice_sessions=total_voice_sessions,
            longest_voice_session=longest_voice_session,
            longest_voice_formatted=format_voice_time(longest_voice_session),
            first_message_at=first_message_at if first_message_at > 0 else None,
            peak_hour=peak_hour if peak_hour >= 0 else None,
            peak_hour_count=peak_hour_count,
            invites_count=invites_count,
            mentions_received=mentions_received,
            channels=channels,
            updated_at=datetime.now(TIMEZONE_DAMASCUS),
        )

        return JSONResponse(
            content=response_data.model_dump(mode="json"),
            headers={"Cache-Control": "public, max-age=30"},
        )

    except APIError:
        raise
    except ValueError:
        raise APIError(ErrorCode.USER_INVALID_ID)
    except Exception as e:
        logger.error_tree("User API Error", e, [
            ("Client IP", client_ip),
            ("ID", str(user_id)),
        ])
        raise APIError(ErrorCode.SERVER_ERROR)


__all__ = ["router"]
