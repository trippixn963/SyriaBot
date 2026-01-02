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

# Cached avatar URL (set once at startup)
_cached_avatar_url: Optional[str] = None

# Bot reference for refreshing avatar
_bot_ref: Optional[discord.Client] = None


async def _get_developer_avatar(bot: discord.Client) -> Optional[str]:
    """Fetch developer avatar URL from the configured or first guild."""
    if not config.OWNER_ID:
        log.tree("Avatar Fetch Skipped", [
            ("Reason", "OWNER_ID not configured"),
        ], emoji="⚠️")
        return None

    try:
        # Use configured guild or fallback to first guild
        guild = None
        if config.GUILD_ID:
            guild = bot.get_guild(config.GUILD_ID)
        if not guild and bot.guilds:
            guild = bot.guilds[0]

        if not guild:
            log.tree("Avatar Fetch Skipped", [
                ("Owner ID", str(config.OWNER_ID)),
                ("Reason", "No guild available"),
            ], emoji="⚠️")
            return None

        member = guild.get_member(config.OWNER_ID)
        if not member:
            try:
                member = await guild.fetch_member(config.OWNER_ID)
            except Exception:
                log.tree("Avatar Fetch Skipped", [
                    ("Owner ID", str(config.OWNER_ID)),
                    ("Guild", guild.name),
                    ("Reason", "Owner not found in guild"),
                ], emoji="⚠️")
                return None

        if member:
            return member.display_avatar.url

        log.tree("Avatar Fetch Skipped", [
            ("Owner ID", str(config.OWNER_ID)),
            ("Reason", "Member object is None"),
        ], emoji="⚠️")
        return None

    except Exception as e:
        log.tree("Avatar Fetch Failed", [
            ("Owner ID", str(config.OWNER_ID)),
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
            ("Owner ID", str(config.OWNER_ID) if config.OWNER_ID else "Not set"),
            ("Avatar Cached", "Yes" if _cached_avatar_url else "No"),
        ], emoji="✅" if _cached_avatar_url else "⚠️")
    except Exception as e:
        log.tree("Footer Init Failed", [
            ("Owner ID", str(config.OWNER_ID) if config.OWNER_ID else "Not set"),
            ("Error", str(e)[:50]),
        ], emoji="❌")
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
