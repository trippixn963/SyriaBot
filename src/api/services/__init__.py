"""
SyriaBot - API Services
=======================

Background services and caching for the API.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .cache import CacheService, get_cache_service
from .background import BackgroundTaskService, get_background_service, init_background_service
from .discord import DiscordService, UserData, get_discord_service, init_discord_service

__all__ = [
    # Cache
    "CacheService",
    "get_cache_service",
    # Background
    "BackgroundTaskService",
    "get_background_service",
    "init_background_service",
    # Discord
    "DiscordService",
    "UserData",
    "get_discord_service",
    "init_discord_service",
]
