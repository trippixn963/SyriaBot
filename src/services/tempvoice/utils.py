"""
SyriaBot - Utility Functions
============================

Centralized utilities for the TempVoice system.
All shared logic lives here to avoid duplication.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import re
from typing import Set, Tuple, TYPE_CHECKING

import discord

from src.core.config import config
from src.core.constants import TEMPVOICE_MAX_ALLOWED_USERS_FREE
from src.services.database import db

if TYPE_CHECKING:
    pass

# Alias for backwards compatibility
MAX_ALLOWED_USERS_FREE = TEMPVOICE_MAX_ALLOWED_USERS_FREE


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

# Pattern to match Roman numeral prefix: "III・Name" or "III Name" or "III-Name"
NUMERAL_PREFIX_PATTERN = re.compile(r'^([IVXLCDM]+)[・·\-\s]+(.+)$')


def extract_base_name(full_name: str) -> str:
    """
    Extract base name from a full channel name (removes numeral prefix).

    "III・Trippixn" -> "Trippixn"
    "Custom Name" -> "Custom Name" (no prefix found)
    """
    match = NUMERAL_PREFIX_PATTERN.match(full_name)
    if match:
        return match.group(2)
    return full_name


def build_full_name(position: int, base_name: str) -> str:
    """
    Build a full channel name from position and base name.

    (1, "Trippixn") -> "I・Trippixn"
    (4, "Custom Name") -> "IV・Custom Name"
    """
    roman = to_roman(position)
    # Truncate base name if too long (Discord limit is 100 chars, leave room for numeral)
    max_base_len = 95 - len(roman)
    truncated_base = base_name[:max_base_len]
    return f"{roman}・{truncated_base}"


def generate_base_name(member: discord.Member) -> Tuple[str, str]:
    """
    Generate a base name for a member (without numeral prefix).

    Args:
        member: The channel owner

    Returns:
        Tuple of (base_name, source)
        source is "saved (booster)" or "display_name"
    """
    # Get user's saved settings
    settings = db.get_user_settings(member.id)
    saved_name = settings.get("default_name") if settings else None

    # Boosters can use custom names
    if saved_name and is_booster(member):
        # Strip any existing numeral prefix from saved name
        return extract_base_name(saved_name), "saved (booster)"

    # Use display name
    return member.display_name[:80], "display_name"


def generate_channel_name(member: discord.Member, guild: discord.Guild) -> Tuple[str, str]:
    """
    Generate a channel name for a member.

    DEPRECATED: Use generate_base_name + build_full_name for new code.
    Kept for backwards compatibility.

    Args:
        member: The channel owner
        guild: The guild

    Returns:
        Tuple of (channel_name, source)
        source is "saved (booster)" or "generated"
    """
    # Get base name
    base_name, source = generate_base_name(member)

    # For backwards compat, still find next available number
    existing_channels = db.get_all_temp_channels(guild.id)
    existing_names = [ch.get("name", "") for ch in existing_channels]
    channel_num = get_next_available_number(existing_names)

    full_name = build_full_name(channel_num, base_name)
    return full_name, source if source == "saved (booster)" else "generated"


# =============================================================================
# Permission Helpers
# =============================================================================

def get_owner_overwrite() -> discord.PermissionOverwrite:
    """Get standard permission overwrite for channel owner."""
    return discord.PermissionOverwrite(
        connect=True,
        send_messages=True,
        read_message_history=True,
    )


async def set_owner_permissions(channel: discord.VoiceChannel, member: discord.Member) -> None:
    """Set owner permissions on a channel."""
    await channel.set_permissions(
        member,
        connect=True,
        send_messages=True,
        read_message_history=True,
    )


def get_trusted_overwrite() -> discord.PermissionOverwrite:
    """Get standard permission overwrite for trusted users."""
    return discord.PermissionOverwrite(
        connect=True,
        send_messages=True,
        read_message_history=True,
    )


def get_blocked_overwrite() -> discord.PermissionOverwrite:
    """Get standard permission overwrite for blocked users."""
    return discord.PermissionOverwrite(connect=False)


def get_locked_overwrite() -> discord.PermissionOverwrite:
    """Get permission overwrite for @everyone when channel is locked."""
    return discord.PermissionOverwrite(
        connect=False,
        send_messages=False,
        read_message_history=False,
    )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Constants
    "MAX_ALLOWED_USERS_FREE",
    "NUMERAL_PREFIX_PATTERN",
    # Roman numerals
    "to_roman",
    "from_roman",
    # Channel numbers
    "get_used_numbers",
    "get_next_available_number",
    # Booster check
    "is_booster",
    # Channel name
    "extract_base_name",
    "build_full_name",
    "generate_base_name",
    "generate_channel_name",
    # Permissions
    "get_owner_overwrite",
    "set_owner_permissions",
    "get_trusted_overwrite",
    "get_blocked_overwrite",
    "get_locked_overwrite",
]
