"""
SyriaBot - Divider Utility
===========================

Sends gold diamond divider images between posts and
blocks reactions on them.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from pathlib import Path
from typing import Set

import discord

from src.core.config import config

DIVIDER_PATH = Path(__file__).resolve().parent.parent / "assets" / "dividers" / "divider.png"

# Track divider message IDs so we only block reactions on actual dividers
_divider_message_ids: Set[int] = set()

# Cap the set size to avoid unbounded growth
_MAX_TRACKED = 500


async def send_divider(channel: discord.abc.Messageable) -> None:
    """Send a divider image to a channel and track the message ID."""
    try:
        msg = await channel.send(file=discord.File(DIVIDER_PATH))
        _divider_message_ids.add(msg.id)
        # Evict oldest if over cap
        while len(_divider_message_ids) > _MAX_TRACKED:
            _divider_message_ids.pop()
    except discord.HTTPException:
        pass


def is_divider_message(message_id: int) -> bool:
    """Check if a message ID belongs to a divider."""
    return message_id in _divider_message_ids


def is_divider_channel(channel_id: int) -> bool:
    """Check if a channel should get automatic dividers."""
    return channel_id in config.DIVIDER_CHANNELS
