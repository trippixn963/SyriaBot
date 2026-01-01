"""
SyriaBot - Embed Footer Utility
================================

Centralized footer for all embeds.
Avatar is cached and refreshed daily at midnight EST.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from typing import Optional

from src.core.logger import log
from src.core.config import config


# Footer text
FOOTER_TEXT = "trippixn.com/Syria"

# Cached avatar URL (refreshed daily at midnight EST)
_cached_avatar_url: Optional[str] = None

# Bot reference for refreshing avatar
_bot_ref: Optional[discord.Client] = None


async def _get_developer_avatar(bot: discord.Client) -> Optional[str]:
    """Fetch developer avatar URL from the configured or first guild."""
    if not config.OWNER_ID:
        return None

    try:
        # Use configured guild or fallback to first guild
        guild = None
        if config.GUILD_ID:
            guild = bot.get_guild(config.GUILD_ID)
        if not guild and bot.guilds:
            guild = bot.guilds[0]

        if not guild:
            return None

        member = guild.get_member(config.OWNER_ID)
        if not member:
            member = await guild.fetch_member(config.OWNER_ID)

        if member:
            return member.display_avatar.url
    except Exception as e:
        log.tree("Avatar Fetch Failed", [
            ("Error", str(e)[:50]),
        ], emoji="⚠️")

    return None


async def init_footer(bot: discord.Client) -> None:
    """
    Initialize footer with cached avatar.
    Should be called once at bot startup after ready.
    """
    global _bot_ref, _cached_avatar_url
    _bot_ref = bot

    try:
        _cached_avatar_url = await _get_developer_avatar(bot)
        log.tree("Footer Initialized", [
            ("Text", FOOTER_TEXT),
            ("Avatar Cached", "Yes" if _cached_avatar_url else "No"),
            ("Refresh Schedule", "Daily at 00:00 EST"),
        ], emoji="OK")
    except Exception as e:
        log.error(f"Footer Init Failed: {e}")
        _cached_avatar_url = None


def set_footer(embed: discord.Embed, avatar_url: Optional[str] = None) -> discord.Embed:
    """
    Set the standard footer on an embed.

    Args:
        embed: The embed to add footer to
        avatar_url: Optional override avatar URL (uses cached if not provided)

    Returns:
        The embed with footer set
    """
    url = avatar_url if avatar_url is not None else _cached_avatar_url
    embed.set_footer(text=FOOTER_TEXT, icon_url=url)
    return embed


__all__ = [
    "FOOTER_TEXT",
    "init_footer",
    "set_footer",
]
