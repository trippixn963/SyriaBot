"""
SyriaBot - Colors Module
========================

Re-exports shared colors plus SyriaBot-specific aliases and emojis.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

# Import all shared colors
from shared.core.colors import *  # noqa: F401, F403

# Import all emojis for backwards compatibility
from src.core.emojis import *  # noqa: F401, F403


# =============================================================================
# SyriaBot-Specific Aliases (for backwards compatibility)
# =============================================================================

# These are aliases to shared colors for existing code
COLOR_SYRIA_GREEN = COLOR_GREEN  # noqa: F405
COLOR_SYRIA_GOLD = COLOR_GOLD    # noqa: F405
