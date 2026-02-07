"""
SyriaBot - Stats Models
=======================

Pydantic models for stats API responses.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TopUser(BaseModel):
    """Brief user info for top 3 display."""

    rank: int
    rank_change: Optional[int] = None
    user_id: str
    display_name: str
    username: Optional[str] = None
    avatar: Optional[str] = None
    level: int
    xp: int
    total_messages: int
    voice_minutes: int
    voice_formatted: str
    is_booster: bool = False
    last_active_at: Optional[int] = None
    last_seen: str = "Unknown"
    streak_days: int = 0


class DailyStats(BaseModel):
    """Daily activity snapshot."""

    date: str = Field(description="Date in YYYY-MM-DD format")
    unique_users: int = Field(ge=0, description="Unique active users")
    total_messages: int = Field(ge=0, description="Total messages sent")
    voice_peak_users: int = Field(ge=0, description="Peak concurrent voice users")
    new_members: int = Field(ge=0, description="New members joined")


class ChannelStats(BaseModel):
    """Channel message statistics."""

    channel_id: str
    channel_name: str
    total_messages: int


class ChannelsResponse(BaseModel):
    """Channels API response."""

    channels: list[ChannelStats]
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ServerStats(BaseModel):
    """Overall server XP statistics response."""

    # Guild info
    guild_name: str = "Syria"
    guild_icon: Optional[str] = None
    guild_banner: Optional[str] = None
    member_count: int = 0
    booster_count: int = 0

    # XP stats
    total_users: int = 0
    total_xp: int = 0
    total_messages: int = 0
    total_voice_minutes: int = 0
    total_voice_formatted: str = "0m"
    highest_level: int = 0

    # Top 3 users
    top_3: list[TopUser] = []

    # Daily stats
    daily_active_users: int = 0
    new_members_today: int = 0
    voice_peak_today: int = 0
    daily_stats_history: list[DailyStats] = []

    # Metadata
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


__all__ = ["TopUser", "DailyStats", "ChannelStats", "ChannelsResponse", "ServerStats"]
