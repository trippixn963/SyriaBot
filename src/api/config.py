"""
SyriaBot - API Configuration
============================

Centralized configuration for the FastAPI service.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class APIConfig:
    """API configuration settings."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8088
    debug: bool = False

    # CORS
    cors_origins: tuple[str, ...] = (
        "https://trippixn.com",
        "https://www.trippixn.com",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    )

    # Rate Limiting
    rate_limit_requests: int = 60
    rate_limit_window: int = 60  # seconds
    rate_limit_burst: int = 10

    # API Key for protected endpoints
    api_key: str = ""

    # JWT for Bearer token auth (shared with AzabBot)
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"

    # Pagination
    default_page_size: int = 50
    max_page_size: int = 100

    # Cache TTLs (seconds)
    stats_cache_ttl: int = 60
    leaderboard_cache_ttl: int = 30
    cache_max_size: int = 200


def load_api_config() -> APIConfig:
    """Load API configuration from environment."""
    # Use same JWT secret as AzabBot for shared auth
    jwt_secret = (
        os.getenv("AZAB_JWT_SECRET") or
        os.getenv("JWT_SECRET_KEY") or
        ""
    )

    return APIConfig(
        host=os.getenv("SYRIA_API_HOST", "0.0.0.0"),
        port=int(os.getenv("SYRIA_API_PORT", "8088")),
        debug=os.getenv("SYRIA_API_DEBUG", "false").lower() == "true",
        api_key=os.getenv("SYRIA_XP_API_KEY", ""),
        jwt_secret=jwt_secret,
    )


# Singleton instance
_config: Optional[APIConfig] = None


def get_api_config() -> APIConfig:
    """Get the API configuration singleton."""
    global _config
    if _config is None:
        _config = load_api_config()
    return _config


__all__ = ["APIConfig", "get_api_config", "load_api_config"]
