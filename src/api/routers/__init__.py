"""
SyriaBot - API Routers
======================

Route handlers for the API.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from .health import router as health_router
from .leaderboard import router as leaderboard_router
from .users import router as users_router
from .stats import router as stats_router
from .channels import router as channels_router
from .xp import router as xp_router
from .ws import router as ws_router
from .extended_stats import router as extended_stats_router
from .bot import router as bot_router

__all__ = [
    "health_router",
    "leaderboard_router",
    "users_router",
    "stats_router",
    "channels_router",
    "xp_router",
    "ws_router",
    "extended_stats_router",
    "bot_router",
]
