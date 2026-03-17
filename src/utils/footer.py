"""
Unified Embed Footer Utility
============================

Centralized footer for all embeds across all bots.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import os
import discord
from typing import Optional

from src.core.logger import logger


# =============================================================================
# Configuration
# =============================================================================

def _get_footer_text() -> str:
    """Get footer text from environment variable."""
    bot_name = os.getenv("BOT_NAME", "").upper()
    return os.getenv(f"{bot_name}_FOOTER_TEXT", os.getenv("FOOTER_TEXT", "trippixn.com"))


FOOTER_TEXT = _get_footer_text()


# =============================================================================
# Initialization
# =============================================================================

# =============================================================================
# Footer Setter
# =============================================================================

def set_footer(embed: discord.Embed, icon_url: Optional[str] = None) -> discord.Embed:
    """
    No-op function - footers disabled.

    Args:
        embed: The embed (returned unchanged).
        icon_url: Ignored.

    Returns:
        The embed unchanged.
    """
    return embed


# =============================================================================
# Module Export
# =============================================================================

__all__ = [
    "FOOTER_TEXT",
    "set_footer",
]
