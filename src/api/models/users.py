"""
SyriaBot - User Models
======================

Pydantic models for user API responses.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChannelActivity(BaseModel):
    """User's activity in a specific channel."""

    channel_id: str = Field(description="Discord channel ID as string")
    channel_name: str = Field(description="Channel name")
    message_count: int = Field(ge=0, description="Messages in this channel")


class UserXPData(BaseModel):
    """Core XP data for a user."""

    user_id: str = Field(description="Discord user ID as string")
    display_name: str = Field(description="User's display name")
    username: Optional[str] = Field(None, description="Discord username")
    avatar: Optional[str] = Field(None, description="Avatar URL")
    rank: int = Field(ge=1, description="Current rank position")
    rank_change: Optional[int] = Field(None, description="Rank change from previous day")
    level: int = Field(ge=0, description="Current level")
    xp: int = Field(ge=0, description="Total XP")
    xp_into_level: int = Field(ge=0, description="XP progress into current level")
    xp_for_next: int = Field(ge=0, description="XP needed for next level")
    progress: float = Field(ge=0, le=100, description="Level progress percentage")
    total_messages: int = Field(ge=0, description="Total messages sent")
    voice_minutes: int = Field(ge=0, description="Total voice minutes")
    voice_formatted: str = Field(description="Human-readable voice time")


class UserResponse(BaseModel):
    """Full user profile API response."""

    # Basic info
    user_id: str
    display_name: str
    username: Optional[str] = None
    avatar: Optional[str] = None

    # Rank & XP
    rank: int
    rank_change: Optional[int] = None
    level: int
    xp: int
    xp_into_level: int
    xp_for_next: int
    progress: float

    # Activity stats
    total_messages: int
    voice_minutes: int
    voice_formatted: str

    # Server info
    joined_at: Optional[int] = None
    days_in_server: int = 1
    xp_per_day: float = 0
    messages_per_day: float = 0
    is_booster: bool = False

    # Activity tracking
    last_active_at: Optional[int] = None
    last_seen: str = "Unknown"
    streak_days: int = 0

    # Extended stats
    commands_used: int = 0
    reactions_given: int = 0
    images_shared: int = 0
    total_voice_sessions: int = 0
    longest_voice_session: int = 0
    longest_voice_formatted: str = "0m"
    first_message_at: Optional[int] = None
    peak_hour: Optional[int] = None
    peak_hour_count: int = 0
    invites_count: int = 0
    mentions_received: int = 0

    # Channel breakdown
    channels: list[ChannelActivity] = []

    # Metadata
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


__all__ = ["ChannelActivity", "UserXPData", "UserResponse"]
