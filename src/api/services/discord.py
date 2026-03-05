"""
SyriaBot - Discord Service
==========================

Service for fetching Discord user data with caching.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from src.core.logger import logger
from src.core.config import config
from src.api.services.cache import get_cache_service


@dataclass
class UserData:
    """Discord user data."""

    avatar_url: Optional[str]
    display_name: str
    username: Optional[str]
    joined_at: Optional[int]
    is_booster: bool
    banner_url: Optional[str] = None


class DiscordService:
    """
    Service for fetching Discord user data with caching.

    Uses the avatar cache from CacheService to avoid redundant API calls.
    """

    def __init__(self, bot: Any) -> None:
        self._bot = bot
        self._cache = get_cache_service()

    async def fetch_user(self, user_id: int) -> UserData:
        """
        Fetch user data from Discord with caching.

        Returns cached data if available, otherwise fetches from Discord API.
        """
        # Check cache first
        cached = await self._cache.get_avatar(user_id)
        if cached:
            return UserData(*cached)

        # Not in cache, fetch from Discord
        if not self._bot or not self._bot.is_ready():
            return UserData(None, str(user_id), None, None, False)

        try:
            return await self._fetch_from_discord(user_id)
        except asyncio.TimeoutError:
            return UserData(None, str(user_id), None, None, False)
        except Exception as e:
            logger.tree("User Fetch Error", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
            return UserData(None, str(user_id), None, None, False)

    async def _fetch_from_discord(self, user_id: int) -> UserData:
        """Fetch user data directly from Discord API."""
        guild = self._bot.get_guild(config.GUILD_ID)

        # Try to get member from guild
        member = guild.get_member(user_id) if guild else None

        if not member and guild:
            try:
                member = await asyncio.wait_for(
                    guild.fetch_member(user_id),
                    timeout=2.0
                )
            except Exception:
                pass

        if member:
            display_name = member.global_name or member.display_name or member.name
            username = member.name

            # Prefer guild avatar, fall back to global
            if member.guild_avatar:
                avatar_url = member.guild_avatar.url
            elif member.avatar:
                avatar_url = member.avatar.url
            else:
                avatar_url = member.default_avatar.url

            # Banner requires a separate fetch_user call (not available on Member)
            banner_url = None
            if member.premium_since is not None:
                try:
                    fetched_user = await asyncio.wait_for(
                        self._bot.fetch_user(user_id),
                        timeout=2.0
                    )
                    if fetched_user and fetched_user.banner:
                        banner_url = fetched_user.banner.url
                except Exception:
                    pass

            joined_at = int(member.joined_at.timestamp()) if member.joined_at else None
            is_booster = member.premium_since is not None

            # Cache the result
            await self._cache.set_avatar(user_id, avatar_url, display_name, username, joined_at, is_booster, banner_url)
            return UserData(avatar_url, display_name, username, joined_at, is_booster, banner_url)

        # Fallback to user if not in guild (fetch_user includes banner)
        user = await asyncio.wait_for(
            self._bot.fetch_user(user_id),
            timeout=2.0
        )

        if user:
            display_name = user.global_name or user.display_name or user.name
            username = user.name
            avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
            banner_url = user.banner.url if user.banner else None

            # Cache with no guild-specific data
            await self._cache.set_avatar(user_id, avatar_url, display_name, username, None, False, banner_url)
            return UserData(avatar_url, display_name, username, None, False, banner_url)

        return UserData(None, str(user_id), None, None, False)

    async def fetch_users_batch(
        self,
        user_ids: list[int],
        max_concurrent: int = 10,
    ) -> dict[int, UserData]:
        """
        Fetch multiple users with limited concurrency.

        Returns a dict mapping user_id to UserData.
        """
        if not user_ids:
            return {}

        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_limit(uid: int) -> tuple[int, UserData]:
            async with semaphore:
                data = await self.fetch_user(uid)
                return uid, data

        results = await asyncio.gather(
            *[fetch_with_limit(uid) for uid in user_ids],
            return_exceptions=True
        )

        user_data = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            uid, data = result
            user_data[uid] = data

        return user_data


# =============================================================================
# Singleton
# =============================================================================

_discord_service: Optional[DiscordService] = None


def get_discord_service(bot: Any = None) -> DiscordService:
    """Get or create the Discord service singleton."""
    global _discord_service
    if _discord_service is None:
        if bot is None:
            raise RuntimeError("DiscordService not initialized. Call init_discord_service first.")
        _discord_service = DiscordService(bot)
    return _discord_service


def init_discord_service(bot: Any) -> DiscordService:
    """Initialize the Discord service with a bot instance."""
    global _discord_service
    _discord_service = DiscordService(bot)
    return _discord_service


__all__ = ["DiscordService", "UserData", "get_discord_service", "init_discord_service"]
