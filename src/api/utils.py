"""
SyriaBot - API Utilities
========================

Shared utility functions for the API.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from fastapi import Request


def format_voice_time(mins: int) -> str:
    """Format minutes into human-readable string (e.g., '5h 30m')."""
    if mins >= 60:
        hours = mins // 60
        remaining_mins = mins % 60
        return f"{hours}h {remaining_mins}m"
    return f"{mins}m"


def format_last_seen(last_active_at: int) -> str:
    """Format timestamp as human-readable 'time ago' string."""
    if not last_active_at or last_active_at <= 0:
        return "Unknown"

    now = int(time.time())
    seconds_ago = now - last_active_at

    if seconds_ago < 60:
        return "Just now"
    elif seconds_ago < 3600:
        return f"{seconds_ago // 60}m ago"
    elif seconds_ago < 86400:
        return f"{seconds_ago // 3600}h ago"
    else:
        return f"{seconds_ago // 86400}d ago"


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    if request.client:
        return request.client.host

    return "unknown"


__all__ = ["format_voice_time", "format_last_seen", "get_client_ip"]
