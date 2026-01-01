"""
TempVoice - Utility Functions
=============================

Centralized utilities for the TempVoice system.
All shared logic lives here to avoid duplication.

Author: حَـــــنَّـــــا
"""

import re
from typing import Set, Tuple, TYPE_CHECKING

import discord

from src.core.config import config
from src.services.database import db

if TYPE_CHECKING:
    pass


# =============================================================================
# Constants
# =============================================================================

# Limits for non-boosters
MAX_ALLOWED_USERS_FREE = 3

# Colors
COLOR_BOOST = 0xFF73FA  # Pink boost color


# =============================================================================
# Roman Numeral Functions
# =============================================================================

def to_roman(num: int) -> str:
    """Convert integer to Roman numeral."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    result = ""
    for i, v in enumerate(val):
        while num >= v:
            result += syms[i]
            num -= v
    return result


def from_roman(roman: str) -> int:
    """Convert Roman numeral to integer."""
    roman_values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    result = 0
    prev = 0
    for char in reversed(roman.upper()):
        curr = roman_values.get(char, 0)
        if curr < prev:
            result -= curr
        else:
            result += curr
        prev = curr
    return result


# =============================================================================
# Channel Number Functions
# =============================================================================

def get_used_numbers(channel_names: list[str]) -> Set[int]:
    """Extract used numbers from channel names like 'I・Username', 'II・Username'."""
    used = set()
    pattern = re.compile(r'^([IVXLCDM]+)[・·\-\s]')
    for name in channel_names:
        match = pattern.match(name)
        if match:
            roman = match.group(1)
            num = from_roman(roman)
            if num > 0:
                used.add(num)
    return used


def get_next_available_number(channel_names: list[str]) -> int:
    """Get the next available number that's not in use."""
    used = get_used_numbers(channel_names)
    num = 1
    while num in used:
        num += 1
    return num


# =============================================================================
# Booster Check
# =============================================================================

def is_booster(member: discord.Member) -> bool:
    """
    Check if member has booster privileges.

    Boosters include:
    - Actual server boosters (premium_since)
    - Members with booster role
    - Moderators
    - Developer/Owner
    """
    # Actual booster
    if member.premium_since is not None:
        return True

    # Booster role
    if config.BOOSTER_ROLE_ID:
        for role in member.roles:
            if role.id == config.BOOSTER_ROLE_ID:
                return True

    # Mod role (mods get booster perks)
    if config.MOD_ROLE_ID:
        for role in member.roles:
            if role.id == config.MOD_ROLE_ID:
                return True

    # Developer
    if config.OWNER_ID and member.id == config.OWNER_ID:
        return True

    return False


# =============================================================================
# Channel Name Generation
# =============================================================================

def generate_channel_name(member: discord.Member, guild: discord.Guild) -> Tuple[str, str]:
    """
    Generate a channel name for a member.

    Args:
        member: The channel owner
        guild: The guild

    Returns:
        Tuple of (channel_name, source)
        source is "saved (booster)" or "generated"
    """
    # Get user's saved settings
    settings = db.get_user_settings(member.id)
    saved_name = settings.get("default_name") if settings else None

    # Boosters can use custom names
    if saved_name and is_booster(member):
        return saved_name, "saved (booster)"

    # Generate default name with unique number
    existing_channels = db.get_all_temp_channels(guild.id)
    existing_names = [ch.get("name", "") for ch in existing_channels.values()]
    channel_num = get_next_available_number(existing_names)
    roman = to_roman(channel_num)

    # Truncate display name if too long (Discord limit is 100 chars)
    display_name = member.display_name[:80]
    channel_name = f"{roman}・{display_name}"

    return channel_name, "generated"


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Constants
    "MAX_ALLOWED_USERS_FREE",
    "COLOR_BOOST",
    # Roman numerals
    "to_roman",
    "from_roman",
    # Channel numbers
    "get_used_numbers",
    "get_next_available_number",
    # Booster check
    "is_booster",
    # Channel name
    "generate_channel_name",
]
