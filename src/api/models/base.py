"""
SyriaBot - Base API Models
==========================

Common response models and utilities.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from datetime import datetime
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field


T = TypeVar("T")


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
    discord: Optional["DiscordStatus"] = None


class DiscordStatus(BaseModel):
    """Discord connection status."""

    connected: bool
    latency_ms: Optional[int] = None
    guilds: int = 0


# Update forward reference
HealthResponse.model_rebuild()


__all__ = [
    "APIResponse",
    "PaginationMeta",
    "PaginatedResponse",
    "HealthResponse",
    "DiscordStatus",
]
