"""
SyriaBot - Server Stats Module
==============================

Single source of truth for server statistics.
Used by both presence handler and dashboard API.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

import discord

from src.core.config import config
from src.core.logger import logger
from src.services.database import db

if TYPE_CHECKING:
    from discord import Client


# =============================================================================
# Stats Data Classes
# =============================================================================

@dataclass
class GuildStats:
    """Live guild statistics."""
    member_count: int = 0
    online_count: int = 0
    booster_count: int = 0
    guild_name: str = "Syria"


@dataclass
class XPStats:
    """XP system statistics."""
    total_users: int = 0
    total_xp: int = 0
    total_messages: int = 0
    total_voice_minutes: int = 0
    highest_level: int = 0

    @property
    def voice_hours(self) -> int:
        """Total voice time in hours."""
        return self.total_voice_minutes // 60


@dataclass
class DailyActivity:
    """Today's activity statistics."""
    active_users: int = 0
    new_members: int = 0
    voice_peak: int = 0
    messages_today: int = 0


@dataclass
class StreakStats:
    """Streak statistics."""
    active_streaks: int = 0
    longest_streak: int = 0
    users_with_streak: int = 0


@dataclass
class ServerStats:
    """Combined server statistics."""
    guild: GuildStats
    xp: XPStats
    daily: DailyActivity
    streaks: StreakStats
    updated_at: datetime


# =============================================================================
# Stats Functions
# =============================================================================

def get_guild_stats(bot: Optional["Client"] = None) -> GuildStats:
    """
    Get live guild statistics from Discord.

    Args:
        bot: Discord client instance.

    Returns:
        GuildStats with member counts.
    """
    stats = GuildStats()

    if not bot or not bot.is_ready():
        return stats

    try:
        guild = bot.get_guild(config.GUILD_ID)
        if guild:
            stats.guild_name = guild.name
            stats.member_count = guild.member_count or 0
            stats.booster_count = guild.premium_subscription_count or 0
            stats.online_count = sum(
                1 for m in guild.members
                if m.status != discord.Status.offline
            )
    except Exception as e:
        logger.debug("Guild Stats Error", [("Error", str(e)[:50])])

    return stats


def get_xp_stats() -> XPStats:
    """
    Get XP system statistics from database.

    Returns:
        XPStats with totals.
    """
    stats = XPStats()

    try:
        raw = db.get_xp_stats()
        stats.total_users = raw.get("total_users", 0)
        stats.total_xp = raw.get("total_xp", 0)
        stats.total_messages = raw.get("total_messages", 0)
        stats.total_voice_minutes = raw.get("total_voice_minutes", 0)
        stats.highest_level = raw.get("highest_level", 0)
    except Exception as e:
        logger.debug("XP Stats Error", [("Error", str(e)[:50])])

    return stats


def get_daily_activity() -> DailyActivity:
    """
    Get today's activity statistics.

    Returns:
        DailyActivity with today's metrics.
    """
    stats = DailyActivity()

    try:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_stats = db.get_daily_stats(config.GUILD_ID, days=1)

        if daily_stats:
            today = daily_stats[0] if daily_stats else {}
            stats.active_users = today.get("unique_users", 0)
            stats.new_members = today.get("new_members", 0)
            stats.voice_peak = today.get("voice_peak_users", 0)
            stats.messages_today = today.get("total_messages", 0)
    except Exception as e:
        logger.debug("Daily Stats Error", [("Error", str(e)[:50])])

    return stats


def get_streak_stats() -> StreakStats:
    """
    Get streak statistics.

    Returns:
        StreakStats with streak info.
    """
    stats = StreakStats()

    try:
        # Count users with active streaks (streak_days > 0)
        streak_data = db.fetchone("""
            SELECT
                COUNT(*) as users_with_streak,
                MAX(streak_days) as longest_streak,
                SUM(CASE WHEN streak_days > 0 THEN 1 ELSE 0 END) as active_streaks
            FROM user_xp
            WHERE guild_id = ? AND is_active = 1 AND streak_days > 0
        """, (config.GUILD_ID,))

        if streak_data:
            stats.users_with_streak = streak_data.get("users_with_streak", 0)
            stats.longest_streak = streak_data.get("longest_streak", 0) or 0
            stats.active_streaks = streak_data.get("active_streaks", 0)
    except Exception as e:
        logger.debug("Streak Stats Error", [("Error", str(e)[:50])])

    return stats


def get_server_stats(bot: Optional["Client"] = None) -> ServerStats:
    """
    Get all server statistics.

    Args:
        bot: Discord client instance.

    Returns:
        ServerStats with all metrics.
    """
    return ServerStats(
        guild=get_guild_stats(bot),
        xp=get_xp_stats(),
        daily=get_daily_activity(),
        streaks=get_streak_stats(),
        updated_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Formatting Helpers
# =============================================================================

def format_number(n: int) -> str:
    """
    Format a number with comma separators.

    Args:
        n: Number to format.

    Returns:
        Formatted string (e.g., "1,500", "2,300,000").
    """
    return f"{n:,}"


def format_voice_hours(minutes: int) -> str:
    """
    Format voice minutes as hours.

    Args:
        minutes: Total minutes.

    Returns:
        Formatted string (e.g., "1,500h").
    """
    hours = minutes // 60
    return f"{hours:,}h"


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "GuildStats",
    "XPStats",
    "DailyActivity",
    "StreakStats",
    "ServerStats",
    "get_guild_stats",
    "get_xp_stats",
    "get_daily_activity",
    "get_streak_stats",
    "get_server_stats",
    "format_number",
    "format_voice_hours",
]
