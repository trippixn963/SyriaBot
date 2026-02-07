"""
SyriaBot - Cache Service
========================

Response and avatar caching for the API.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Optional, Tuple

from src.core.logger import logger
from src.core.constants import TIMEZONE_EST
from src.api.config import get_api_config


class CacheService:
    """
    Manages response and avatar caching with LRU eviction.
    """

    def __init__(self):
        config = get_api_config()

        # Response cache: {key: (data, timestamp)}
        self._response_cache: dict[str, Tuple[dict, float]] = {}
        self._response_cache_lock = asyncio.Lock()
        self._response_cache_max_size = config.cache_max_size

        # Avatar cache: {user_id: (avatar_url, display_name, username, joined_at, is_booster)}
        self._avatar_cache: OrderedDict[int, Tuple[Optional[str], str, Optional[str], Optional[int], bool]] = OrderedDict()
        self._avatar_cache_lock = asyncio.Lock()
        self._avatar_cache_date: Optional[str] = None
        self._avatar_cache_max_size = 500

        # TTLs
        self._stats_cache_ttl = config.stats_cache_ttl
        self._leaderboard_cache_ttl = config.leaderboard_cache_ttl

    # =========================================================================
    # Response Cache
    # =========================================================================

    async def get_response(self, key: str, ttl: Optional[int] = None) -> Optional[dict]:
        """Get cached response if not expired."""
        if key not in self._response_cache:
            return None

        data, cached_time = self._response_cache[key]
        cache_ttl = ttl or self._stats_cache_ttl

        if time.time() - cached_time < cache_ttl:
            return data

        return None

    async def set_response(self, key: str, data: dict) -> None:
        """Cache a response."""
        self._response_cache[key] = (data, time.time())

        # Evict oldest entries if cache exceeds limit
        while len(self._response_cache) > self._response_cache_max_size:
            oldest_key = min(self._response_cache, key=lambda k: self._response_cache[k][1])
            del self._response_cache[oldest_key]

    async def clear_responses(self) -> None:
        """Clear all cached responses."""
        self._response_cache.clear()

    async def cleanup_expired_responses(self) -> int:
        """Remove expired response cache entries. Returns count removed."""
        now = time.time()
        max_ttl = max(self._stats_cache_ttl, self._leaderboard_cache_ttl) * 2

        expired_keys = [
            k for k, (_, ts) in self._response_cache.items()
            if now - ts > max_ttl
        ]

        for k in expired_keys:
            del self._response_cache[k]

        return len(expired_keys)

    # =========================================================================
    # Avatar Cache
    # =========================================================================

    async def get_avatar(self, user_id: int) -> Optional[Tuple[Optional[str], str, Optional[str], Optional[int], bool]]:
        """Get cached avatar data for a user."""
        await self._check_avatar_cache_refresh()

        async with self._avatar_cache_lock:
            if user_id in self._avatar_cache:
                # Move to end for LRU
                self._avatar_cache.move_to_end(user_id)
                return self._avatar_cache[user_id]

        return None

    async def set_avatar(
        self,
        user_id: int,
        avatar_url: Optional[str],
        display_name: str,
        username: Optional[str],
        joined_at: Optional[int],
        is_booster: bool,
    ) -> None:
        """Cache avatar data for a user."""
        async with self._avatar_cache_lock:
            self._avatar_cache[user_id] = (avatar_url, display_name, username, joined_at, is_booster)

            # Enforce cache size limit
            while len(self._avatar_cache) > self._avatar_cache_max_size:
                self._avatar_cache.popitem(last=False)

    async def remove_avatar(self, user_id: int) -> None:
        """Remove a user from avatar cache."""
        async with self._avatar_cache_lock:
            if user_id in self._avatar_cache:
                del self._avatar_cache[user_id]

    async def get_cached_user_ids(self) -> list[int]:
        """Get list of all cached user IDs."""
        async with self._avatar_cache_lock:
            return list(self._avatar_cache.keys())

    async def _check_avatar_cache_refresh(self) -> None:
        """Clear avatar cache if it's a new day in EST."""
        today_est = datetime.now(TIMEZONE_EST).strftime("%Y-%m-%d")

        async with self._avatar_cache_lock:
            if self._avatar_cache_date != today_est:
                self._avatar_cache.clear()
                self._avatar_cache_date = today_est
                logger.tree("Avatar Cache Cleared", [
                    ("Reason", "New day (EST)"),
                    ("Date", today_est),
                ], emoji="🔄")

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def stats_cache_ttl(self) -> int:
        return self._stats_cache_ttl

    @property
    def leaderboard_cache_ttl(self) -> int:
        return self._leaderboard_cache_ttl


# =============================================================================
# Singleton
# =============================================================================

_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get or create the cache service singleton."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service


__all__ = ["CacheService", "get_cache_service"]
