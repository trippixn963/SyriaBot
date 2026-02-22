"""
SyriaBot - Events Router
========================

API endpoints for Discord event logs.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from src.core.config import config
from src.api.dependencies import require_auth
from src.api.services.event_storage import get_event_storage, EventType


router = APIRouter(prefix="/api/syria/events", tags=["events"])


# =============================================================================
# Endpoints
# =============================================================================

@router.get("")
async def get_events(
    user_id: int = Depends(require_auth),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    actor_id: Optional[int] = Query(None),
    target_id: Optional[int] = Query(None),
    channel_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    hours: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """
    Get paginated Discord events with filtering.

    Filters:
    - event_type: Filter by specific event type (e.g., "member.ban")
    - category: Filter by category (e.g., "member", "voice", "message")
    - actor_id: Filter by who performed the action
    - target_id: Filter by who was affected
    - channel_id: Filter by channel
    - search: Full-text search in reasons/names
    - hours: Only events from last N hours
    """
    storage = get_event_storage()
    events, total = storage.get_events(
        guild_id=config.GUILD_ID,
        limit=limit,
        offset=offset,
        event_type=event_type,
        category=category,
        actor_id=actor_id,
        target_id=target_id,
        channel_id=channel_id,
        search=search,
        hours=hours,
    )

    return {
        "success": True,
        "data": {
            "events": [e.to_dict() for e in events],
            "total": total,
            "limit": limit,
            "offset": offset,
            "filters": {
                "event_type": event_type,
                "category": category,
                "actor_id": str(actor_id) if actor_id else None,
                "target_id": str(target_id) if target_id else None,
                "channel_id": str(channel_id) if channel_id else None,
                "search": search,
                "hours": hours,
            },
        },
    }


@router.get("/stats")
async def get_event_stats(
    user_id: int = Depends(require_auth),
) -> Dict[str, Any]:
    """Get event statistics (counts by type/category, top actors)."""
    storage = get_event_storage()
    stats = storage.get_stats(config.GUILD_ID)

    return {
        "success": True,
        "data": stats,
    }


@router.get("/types")
async def get_event_types(
    user_id: int = Depends(require_auth),
) -> Dict[str, Any]:
    """Get all event types with their categories."""
    types = [
        # Member events
        {"type": EventType.MEMBER_JOIN, "label": "Member Join", "category": "member"},
        {"type": EventType.MEMBER_LEAVE, "label": "Member Leave", "category": "member"},
        {"type": EventType.MEMBER_BAN, "label": "Ban", "category": "member"},
        {"type": EventType.MEMBER_UNBAN, "label": "Unban", "category": "member"},
        {"type": EventType.MEMBER_KICK, "label": "Kick", "category": "member"},
        {"type": EventType.MEMBER_BOOST, "label": "Boost", "category": "member"},
        {"type": EventType.MEMBER_UNBOOST, "label": "Unboost", "category": "member"},

        # Voice events
        {"type": EventType.VOICE_JOIN, "label": "Voice Join", "category": "voice"},
        {"type": EventType.VOICE_LEAVE, "label": "Voice Leave", "category": "voice"},
        {"type": EventType.VOICE_SWITCH, "label": "Voice Switch", "category": "voice"},

        # Channel events
        {"type": EventType.CHANNEL_CREATE, "label": "Channel Create", "category": "channel"},

        # Server events
        {"type": EventType.SERVER_BUMP, "label": "Server Bump", "category": "server"},

        # Thread events
        {"type": EventType.THREAD_CREATE, "label": "Thread Create", "category": "thread"},

        # XP events
        {"type": EventType.XP_LEVEL_UP, "label": "Level Up", "category": "xp"},
    ]

    return {
        "success": True,
        "data": {
            "types": types,
        },
    }


@router.get("/categories")
async def get_event_categories(
    user_id: int = Depends(require_auth),
) -> Dict[str, Any]:
    """Get event categories."""
    categories = [
        {"key": "member", "label": "Members", "color": "emerald"},
        {"key": "voice", "label": "Voice", "color": "purple"},
        {"key": "message", "label": "Messages", "color": "blue"},
        {"key": "channel", "label": "Channels", "color": "cyan"},
        {"key": "server", "label": "Server", "color": "amber"},
        {"key": "thread", "label": "Threads", "color": "pink"},
        {"key": "xp", "label": "XP", "color": "yellow"},
    ]

    return {
        "success": True,
        "data": {
            "categories": categories,
        },
    }


__all__ = ["router"]
