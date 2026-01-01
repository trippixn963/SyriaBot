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
    """Fetch developer avatar URL from the configured guild."""
    if not config.OWNER_ID or not config.GUILD_ID:
        return None

    try:
        guild = bot.get_guild(config.GUILD_ID)
        if not guild:
            return None

        member = guild.get_member(config.OWNER_ID)
        if not member:
            member = await guild.fetch_member(config.OWNER_ID)

        if member:
            return member.display_avatar.url
    except Exception:
        pass

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


async def refresh_avatar() -> None:
    """
    Refresh the cached avatar URL.
    Called daily at midnight EST by the scheduler.
    """
    global _cached_avatar_url
    if not _bot_ref:
        log.warning("Footer avatar refresh skipped: bot reference not set")
        return

    old_url = _cached_avatar_url
    try:
        _cached_avatar_url = await _get_developer_avatar(_bot_ref)
        changed = old_url != _cached_avatar_url
        log.tree("Footer Avatar Refreshed", [
            ("Changed", "Yes" if changed else "No"),
        ], emoji="REFRESH")
    except Exception as e:
        log.error(f"Footer Avatar Refresh Failed: {e}")


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


def get_cached_avatar() -> Optional[str]:
    """Get the cached avatar URL."""
    return _cached_avatar_url


__all__ = [
    "FOOTER_TEXT",
    "init_footer",
    "refresh_avatar",
    "set_footer",
    "get_cached_avatar",
]
