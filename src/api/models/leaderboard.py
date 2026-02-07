"""
SyriaBot - Leaderboard Models
=============================

Pydantic models for leaderboard API responses.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry."""

    rank: int = Field(ge=1, description="Current rank position")
    rank_change: Optional[int] = Field(None, description="Rank change from previous day (+up, -down)")
    user_id: str = Field(description="Discord user ID as string")
    display_name: str = Field(description="User's display name")
    username: Optional[str] = Field(None, description="Discord username")
    avatar: Optional[str] = Field(None, description="Avatar URL")
    level: int = Field(ge=0, description="Current level")
    xp: int = Field(ge=0, description="Total XP")
    xp_gained: Optional[int] = Field(None, description="XP gained in period (only for period leaderboards)")
    total_messages: int = Field(ge=0, description="Total messages sent")
    voice_minutes: int = Field(ge=0, description="Total voice minutes")
    voice_formatted: str = Field(description="Human-readable voice time (e.g., '5h 30m')")
    is_booster: bool = Field(default=False, description="Whether user is a server booster")
    last_active_at: Optional[int] = Field(None, description="Unix timestamp of last activity")
    last_seen: str = Field(default="Unknown", description="Human-readable last seen (e.g., '2h ago')")
    streak_days: int = Field(default=0, description="Current activity streak in days")


class LeaderboardResponse(BaseModel):
    """Leaderboard API response."""

    leaderboard: list[LeaderboardEntry]
    total: int = Field(ge=0, description="Total ranked users")
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    period: str = Field(default="all", description="Time period: all, month, week, today")
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


__all__ = ["LeaderboardEntry", "LeaderboardResponse"]
