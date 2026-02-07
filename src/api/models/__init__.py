"""
SyriaBot - API Models
=====================

Pydantic models for API request/response schemas.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .base import APIResponse, PaginatedResponse, PaginationMeta
from .leaderboard import LeaderboardEntry, LeaderboardResponse
from .users import UserXPData, ChannelActivity, UserResponse
from .stats import ServerStats, DailyStats, TopUser

__all__ = [
    # Base
    "APIResponse",
    "PaginatedResponse",
    "PaginationMeta",
    # Leaderboard
    "LeaderboardEntry",
    "LeaderboardResponse",
    # Users
    "UserXPData",
    "ChannelActivity",
    "UserResponse",
    # Stats
    "ServerStats",
    "DailyStats",
    "TopUser",
]
