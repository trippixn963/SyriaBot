"""
SyriaBot - FastAPI Application
==============================

FastAPI application factory and configuration.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from src.core.logger import logger
from src.api.config import get_api_config
from src.api.errors import APIError, ErrorCode, error_response
from src.api.middleware.rate_limit import RateLimitMiddleware, get_rate_limiter
from src.api.middleware.logging import LoggingMiddleware
from src.api.dependencies import set_bot
from src.api.routers import (
    health_router,
    leaderboard_router,
    users_router,
    stats_router,
    channels_router,
    xp_router,
    ws_router,
    extended_stats_router,
    bot_router,
    events_router,
)
from src.api.routers.health import set_start_time
from src.api.services.log_storage import get_log_storage
from src.api.services.event_storage import get_event_storage
from src.api.services.websocket import get_ws_manager


# =============================================================================
# Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Handles startup and shutdown events.
    """
    # Startup
    set_start_time()
    get_log_storage()  # Initialize log capture early

    # Set up WebSocket callback for events
    def broadcast_event(event_data: dict):
        """Callback called when events are added."""
        import asyncio
        ws_manager = get_ws_manager()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(ws_manager.broadcast_discord_event(event_data))
        except Exception:
            pass

    event_storage = get_event_storage()
    event_storage.set_on_event(broadcast_event)

    logger.tree("API Starting", [
        ("Version", "2.0.0"),
        ("Framework", "FastAPI"),
    ], emoji="🚀")

    yield

    # Shutdown
    logger.tree("API Stopping", [], emoji="🛑")


# =============================================================================
# Application Factory
# =============================================================================

def create_app(bot: Optional[Any] = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        bot: Optional Discord bot instance for dependency injection

    Returns:
        Configured FastAPI application
    """
    config = get_api_config()

    # Create app
    app = FastAPI(
        title="SyriaBot API",
        description="XP Leaderboard Dashboard API for SyriaBot",
        version="2.0.0",
        docs_url="/api/syria/docs" if config.debug else None,
        redoc_url="/api/syria/redoc" if config.debug else None,
        openapi_url="/api/syria/openapi.json" if config.debug else None,
        lifespan=lifespan,
    )

    # Set bot reference
    if bot:
        set_bot(bot)

    # ==========================================================================
    # Middleware (order matters - last added = first executed)
    # ==========================================================================

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Rate limiting
    app.add_middleware(RateLimitMiddleware, rate_limiter=get_rate_limiter())

    # Request logging
    app.add_middleware(LoggingMiddleware)

    # ==========================================================================
    # Exception Handlers
    # ==========================================================================

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        """Handle APIError exceptions with structured response."""
        # Skip logging for auth failures (expected behavior - expired tokens, etc.)
        if exc.status_code != 401:
            logger.tree("API Error", [
                ("Path", str(request.url.path)[:50]),
                ("Code", exc.error_code.value),
                ("Status", str(exc.status_code)),
            ], emoji="⚠️")

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error_code": exc.error_code.value,
                "message": exc.error_message,
                "details": exc.error_details,
            },
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle uncaught exceptions."""
        logger.error("Unhandled API Error", [
            ("Path", str(request.url.path)[:50]),
            ("Error", str(exc)[:100]),
        ])

        return error_response(ErrorCode.SERVER_ERROR)

    # ==========================================================================
    # Routers
    # ==========================================================================

    # Health check at root level
    app.include_router(health_router)

    # API endpoints
    app.include_router(leaderboard_router)
    app.include_router(users_router)
    app.include_router(stats_router)
    app.include_router(channels_router)
    app.include_router(xp_router)
    app.include_router(ws_router)
    app.include_router(extended_stats_router)
    app.include_router(bot_router)
    app.include_router(events_router)

    return app


# =============================================================================
# Module-level app for uvicorn standalone
# =============================================================================

# This allows running with: uvicorn src.api.app:app
app = create_app()


__all__ = ["create_app", "app"]
