"""
SyriaBot - Permission Utilities
===============================

Centralized permission checks for cooldown exemptions and other privileges.

Author: John Hamwi
Server: discord.gg/syria
"""

from typing import Union
import discord

from src.core.config import config


def is_cooldown_exempt(user: Union[int, discord.Member, discord.User]) -> bool:
    """
    Check if a user bypasses cooldowns.

    Exempt users:
    - Developer (OWNER_ID)
    - Moderators (MOD_ROLE_ID)

    Args:
        user: User ID, Member, or User object

    Returns:
        True if user bypasses cooldowns
    """
    # Extract user_id
    user_id = user if isinstance(user, int) else user.id

    # Developer bypass
    if config.OWNER_ID and user_id == config.OWNER_ID:
        return True

    # Mod bypass (only works with Member objects)
    if isinstance(user, discord.Member):
        if config.MOD_ROLE_ID and user.get_role(config.MOD_ROLE_ID):
            return True

    return False
