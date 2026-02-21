"""
SyriaBot - API Package
======================

FastAPI-based REST API for the XP Leaderboard Dashboard.

Author: حَـــــنَّـــــا
Server: discord.gg/syria

Features:
- XP leaderboard with pagination and period filters
- User profiles with detailed stats
- Server statistics and daily activity
- Per-channel message counts
- Protected XP modification endpoints (API key required)
- Response caching with TTL
- Rate limiting per IP

Usage with bot:
    from src.api import APIService

    # In your bot's setup
    api_service = APIService(bot)
    await api_service.start()

    # On shutdown
    await api_service.stop()

Standalone (for development):
    uvicorn src.api.app:app --reload --port 8088
"""

import asyncio
from typing import Any, Optional

import uvicorn

from src.core.logger import logger
from src.api.config import get_api_config, APIConfig
from src.api.app import create_app
from src.api.dependencies import set_bot
from src.api.services.cache import get_cache_service, CacheService
from src.api.services.background import (
    BackgroundTaskService,
    get_background_service,
    init_background_service,
)


# =============================================================================
# API Service
# =============================================================================

class APIService:
    """
    Manages the FastAPI server lifecycle within the Discord bot.

    This service runs the API server in a background task, allowing
    the bot and API to run concurrently.
    """

    def __init__(self, bot: Any) -> None:
        """
        Initialize the API service.

        Args:
            bot: The Discord bot instance
        """
        self._bot = bot
        self._config = get_api_config()
        self._app = create_app(bot)
        self._server: Optional[uvicorn.Server] = None
        self._task: Optional[asyncio.Task] = None
        self._background_service = init_background_service(bot)

    @property
    def is_running(self) -> bool:
        """Check if the API server is running."""
        return self._task is not None and not self._task.done()

    @property
    def cache(self) -> CacheService:
        """Get the cache service."""
        return get_cache_service()

    @property
    def background_service(self) -> BackgroundTaskService:
        """Get the background task service."""
        return self._background_service

    async def start(self) -> None:
        """Start the API server in a background task."""
        if self.is_running:
            logger.warning("API Already Running", [])
            return

        # Configure uvicorn
        config = uvicorn.Config(
            app=self._app,
            host=self._config.host,
            port=self._config.port,
            log_level="warning",  # Reduce uvicorn logging
            access_log=False,  # We have our own logging middleware
        )

        self._server = uvicorn.Server(config)

        # Run in background
        self._task = asyncio.create_task(self._run_server())

        # Start background services
        await self._background_service.start()

        logger.tree("Syria API Ready", [
            ("Host", self._config.host),
            ("Port", str(self._config.port)),
            ("Endpoints", "/api/syria/leaderboard, /api/syria/user/{id}, /api/syria/stats"),
            ("Rate Limit", "60 req/min"),
            ("Midnight Refresh", "Enabled"),
            ("Daily Snapshots", "Enabled (UTC midnight)"),
        ], emoji="🌐")

    async def _run_server(self) -> None:
        """Run the uvicorn server."""
        try:
            await self._server.serve()
        except asyncio.CancelledError:
            logger.debug("API Server Cancelled", [])
        except Exception as e:
            logger.error("API Server Error", [
                ("Error Type", type(e).__name__),
                ("Error", str(e)[:100]),
            ])

    async def stop(self) -> None:
        """Stop the API server gracefully."""
        if not self.is_running:
            return

        logger.tree("Syria API Stopping", [], emoji="🛑")

        # Stop background services
        await self._background_service.stop()

        # Signal server to stop
        if self._server:
            self._server.should_exit = True

        # Wait for task to complete
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        self._server = None
        self._task = None

        logger.tree("Syria API Stopped", [
            ("Status", "Shutdown complete"),
        ], emoji="✅")


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Main service
    "APIService",
    # Config
    "get_api_config",
    "APIConfig",
    # App factory
    "create_app",
    # Services
    "get_cache_service",
    "CacheService",
    "get_background_service",
    "BackgroundTaskService",
    # Dependencies
    "set_bot",
]
