"""
SyriaBot - Base API Models
==========================

Common response models and utilities.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field


# =============================================================================
# Generic Type Variables
# =============================================================================

T = TypeVar("T")


# =============================================================================
# Base Response Models
# =============================================================================

class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = False
    error_code: str
    message: str
    details: Optional[dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    total: int = Field(ge=0, description="Total number of items")
    limit: int = Field(ge=1, le=100, description="Items per page")
    offset: int = Field(ge=0, description="Starting position")
    period: str = Field(default="all", description="Time period filter")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    success: bool = True
    data: list[T]
    pagination: PaginationMeta
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# =============================================================================
# Health Models
# =============================================================================

class DiscordStatus(BaseModel):
    """Discord connection status."""

    connected: bool
    latency_ms: Optional[int] = None
    guilds: int = 0


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    bot: str = "SyriaBot"
    run_id: Optional[str] = None
    uptime: str
    uptime_seconds: int
    started_at: datetime
    timestamp: datetime
    timezone: str = "America/New_York (EST)"
    discord: Optional[DiscordStatus] = None


# =============================================================================
# WebSocket Models
# =============================================================================

class WSMessage(BaseModel):
    """WebSocket message format."""

    type: str = Field(description="Event type")
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WSEventType:
    """WebSocket event type constants."""

    # Connection events
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    HEARTBEAT = "heartbeat"
    PONG = "pong"

    # Stats events
    STATS_UPDATED = "stats.updated"
    STATS_LEADERBOARD = "stats.leaderboard"
    STATS_USER = "stats.user"

    # XP events
    XP_GRANTED = "xp.granted"
    XP_SET = "xp.set"
    XP_DRAINED = "xp.drained"
    XP_LEVEL_UP = "xp.level_up"

    # Error events
    ERROR = "error"


__all__ = [
    "APIResponse",
    "ErrorResponse",
    "PaginationMeta",
    "PaginatedResponse",
    "HealthResponse",
    "DiscordStatus",
    "WSMessage",
    "WSEventType",
]
