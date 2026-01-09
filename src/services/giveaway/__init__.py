"""
SyriaBot - Giveaway Package
===========================

Giveaway system with customizable prizes and requirements.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.services.giveaway.service import (
    GiveawayService,
    PRIZE_TYPES,
    DURATION_OPTIONS,
    WINNER_OPTIONS,
    BOOSTER_MULTIPLIER,
)
from src.services.giveaway.views import (
    GiveawaySetupView,
    GiveawayEntryView,
)

__all__ = [
    "GiveawayService",
    "PRIZE_TYPES",
    "DURATION_OPTIONS",
    "WINNER_OPTIONS",
    "BOOSTER_MULTIPLIER",
    "GiveawaySetupView",
    "GiveawayEntryView",
]
