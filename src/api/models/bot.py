"""
SyriaBot - Bot Status Models
============================

Response models for bot status, logs, and latency endpoints.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# System Info
# =============================================================================

class SystemInfo(BaseModel):
    """System resource information."""

    cpu_percent: float = Field(ge=0, le=100, description="CPU usage percentage")
    memory_used_mb: float = Field(ge=0, description="Memory used in MB")
    memory_total_mb: float = Field(ge=0, description="Total memory in MB")
    disk_used_gb: float = Field(ge=0, description="Disk used in GB")
    disk_total_gb: float = Field(ge=0, description="Total disk in GB")
    python_version: str = Field(description="Python version")
    discord_py_version: str = Field(description="discord.py version")


class HealthInfo(BaseModel):
    """Bot health information."""

    shard_id: int = Field(default=0, description="Current shard ID")
    shard_count: int = Field(default=1, ge=1, description="Total shard count")
    reconnect_count: int = Field(default=0, ge=0, description="Number of reconnections")
    rate_limit_hits: int = Field(default=0, ge=0, description="Rate limit hits")
    avg_latency_ms: float = Field(default=0, ge=0, description="Average latency")


# =============================================================================
# Bot Status
# =============================================================================

class BotStatusData(BaseModel):
    """Bot status data."""

    online: bool = Field(description="Whether bot is online")
    uptime_seconds: int = Field(ge=0, description="Uptime in seconds")
    started_at: Optional[str] = Field(None, description="Start time in ISO format")
    latency_ms: int = Field(ge=0, description="Discord latency in ms")
    guild_count: int = Field(ge=0, description="Number of guilds")
    user_count: int = Field(ge=0, description="Total users across guilds")
    version: str = Field(description="Bot version")
    system: SystemInfo
    health: Optional[HealthInfo] = None


class BotStatusResponse(BaseModel):
    """Bot status API response."""

    success: bool = True
    data: BotStatusData


# =============================================================================
# Bot Logs
# =============================================================================

class BotLog(BaseModel):
    """Single log entry."""

    id: int
    timestamp: str
    level: str
    message: str
    module: str
    formatted: Optional[str] = None


class BotLogsData(BaseModel):
    """Bot logs data."""

    logs: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int
    level: str


class BotLogsResponse(BaseModel):
    """Bot logs API response."""

    success: bool = True
    data: BotLogsData


# =============================================================================
# Latency
# =============================================================================

class LatencyData(BaseModel):
    """Latency data."""

    period: str
    points: List[Dict[str, Any]]
    count: int
    aggregated: bool = False


class LatencyResponse(BaseModel):
    """Latency API response."""

    success: bool = True
    data: LatencyData


class LatencyStatsResponse(BaseModel):
    """Latency stats API response."""

    success: bool = True
    data: Dict[str, Any]


class LatencyReportData(BaseModel):
    """Latency report data."""

    recorded: bool
    id: int
    discord_ms: int
    api_ms: int


class LatencyReportResponse(BaseModel):
    """Latency report API response."""

    success: bool = True
    data: LatencyReportData


class LatencyHistoryData(BaseModel):
    """Legacy latency history data."""

    history: List[Dict[str, Any]]
    count: int


class LatencyHistoryResponse(BaseModel):
    """Legacy latency history API response."""

    success: bool = True
    data: LatencyHistoryData


__all__ = [
    "SystemInfo",
    "HealthInfo",
    "BotStatusData",
    "BotStatusResponse",
    "BotLog",
    "BotLogsData",
    "BotLogsResponse",
    "LatencyData",
    "LatencyResponse",
    "LatencyStatsResponse",
    "LatencyReportData",
    "LatencyReportResponse",
    "LatencyHistoryData",
    "LatencyHistoryResponse",
]
