"""
SyriaBot - API Dependencies
===========================

FastAPI dependency injection utilities.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import hmac
from typing import Any, Optional

from fastapi import Depends, Header, Query

from src.api.config import get_api_config
from src.api.errors import APIError, ErrorCode


# =============================================================================
# Bot Reference
# =============================================================================

_bot_instance: Optional[Any] = None


def set_bot(bot: Any) -> None:
    """Set the bot instance for dependency injection."""
    global _bot_instance
    _bot_instance = bot


def get_bot() -> Any:
    """Get the bot instance."""
    if _bot_instance is None:
        raise APIError(ErrorCode.BOT_NOT_INITIALIZED)
    return _bot_instance


def get_bot_optional() -> Optional[Any]:
    """Get the bot instance if available, None otherwise."""
    return _bot_instance


# =============================================================================
# API Key Authentication
# =============================================================================

async def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """
    Require a valid API key for protected endpoints.

    Raises 401 if API key is missing or invalid.
    """
    config = get_api_config()

    if not config.api_key:
        raise APIError(
            ErrorCode.AUTH_MISSING_KEY,
            message="API key not configured on server",
        )

    if not x_api_key:
        raise APIError(ErrorCode.AUTH_MISSING_KEY)

    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(x_api_key, config.api_key):
        raise APIError(ErrorCode.AUTH_INVALID_KEY)

    return x_api_key


# =============================================================================
# Pagination Dependencies
# =============================================================================

class PaginationParams:
    """Standard pagination parameters."""

    def __init__(
        self,
        limit: int = 50,
        offset: int = 0,
    ):
        config = get_api_config()

        # Clamp values to valid ranges
        if limit < 1:
            limit = 1
        if limit > config.max_page_size:
            limit = config.max_page_size
        if offset < 0:
            offset = 0

        self.limit = limit
        self.offset = offset


def get_pagination(
    limit: int = Query(50, ge=1, le=100, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
) -> PaginationParams:
    """Get pagination parameters from query string."""
    return PaginationParams(limit=limit, offset=offset)


# =============================================================================
# Period Filter
# =============================================================================

def get_period(
    period: str = Query("all", description="Time period filter: all, month, week, today"),
) -> str:
    """Get and validate period filter."""
    valid_periods = ("all", "month", "week", "today")
    if period not in valid_periods:
        return "all"
    return period


__all__ = [
    "set_bot",
    "get_bot",
    "get_bot_optional",
    "require_api_key",
    "PaginationParams",
    "get_pagination",
    "get_period",
]
