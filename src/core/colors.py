"""
SyriaBot - Colors Module
========================

Color definitions for Discord embeds.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""


# =============================================================================
# Base Color Values (Hex)
# =============================================================================

# Primary brand colors (Syria Discord)
COLOR_GREEN = 0x1F5E2E      # Syria green
COLOR_GOLD = 0xE6B84A       # Syria gold (primary brand color)
COLOR_RED = 0xB43232        # Syria red

# Status colors
COLOR_SUCCESS = 0x43B581    # Green - successful actions
COLOR_ERROR = 0xF04747      # Red - errors and failures
COLOR_WARNING = 0xFAA61A    # Orange - warnings

# Neutral colors
COLOR_NEUTRAL = 0x95A5A6    # Gray - neutral/cancelled
COLOR_INFO = 0x3498DB       # Blue - informational

# Feature-specific colors
COLOR_BOOST = 0xFF73FA      # Pink - Nitro boosters
COLOR_FEMALE = 0xFF69B4     # Pink - female/feminine
COLOR_MALE = 0x4169E1       # Royal Blue - male/masculine


# =============================================================================
# SyriaBot-Specific Aliases
# =============================================================================

COLOR_SYRIA_GREEN = COLOR_GREEN
COLOR_SYRIA_GOLD = COLOR_GOLD


# =============================================================================
# Emoji Re-exports
# =============================================================================

# Import all emojis for backwards compatibility
from src.core.emojis import *  # noqa: F401, F403


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Hex colors
    "COLOR_GREEN",
    "COLOR_GOLD",
    "COLOR_RED",
    "COLOR_SUCCESS",
    "COLOR_ERROR",
    "COLOR_WARNING",
    "COLOR_NEUTRAL",
    "COLOR_INFO",
    "COLOR_BOOST",
    "COLOR_FEMALE",
    "COLOR_MALE",
    # SyriaBot aliases
    "COLOR_SYRIA_GREEN",
    "COLOR_SYRIA_GOLD",
]
