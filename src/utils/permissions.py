"""
SyriaBot - Permission Utilities
===============================

Centralized permission checks for cooldown exemptions and other privileges.

Author: John Hamwi
Server: discord.gg/syria
"""

from typing import Union, Optional, Callable
import discord
from discord import app_commands

from src.core.config import config


def is_cooldown_exempt(user: Union[int, discord.Member, discord.User]) -> bool:
    """
    Check if a user bypasses cooldowns.

    Exempt users:
    - Developer (OWNER_ID)
    - Moderators (MOD_ROLE_ID)
    - Server Boosters (BOOSTER_ROLE_ID)

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

    # Role-based bypasses (only works with Member objects)
    if isinstance(user, discord.Member):
        if config.MOD_ROLE_ID and user.get_role(config.MOD_ROLE_ID):
            return True
        if config.BOOSTER_ROLE_ID and user.get_role(config.BOOSTER_ROLE_ID):
            return True

    return False


def create_cooldown(
    rate: int,
    per: float,
    *,
    owner_only: bool = False,
) -> Callable[[discord.Interaction], Optional[app_commands.Cooldown]]:
    """
    Factory function to create dynamic cooldown functions for slash commands.

    Creates a cooldown that exempt users (owner, mods, boosters) bypass.
    Use with @app_commands.checks.dynamic_cooldown decorator.

    Args:
        rate: Number of uses allowed per cooldown period
        per: Cooldown duration in seconds
        owner_only: If True, only owner bypasses (not mods/boosters)

    Returns:
        A function suitable for dynamic_cooldown decorator

    Example:
        @app_commands.checks.dynamic_cooldown(create_cooldown(1, 60))
        async def my_command(interaction): ...
    """
    def cooldown_check(interaction: discord.Interaction) -> Optional[app_commands.Cooldown]:
        user = interaction.user

        if owner_only:
            # Only owner bypasses
            if config.OWNER_ID and user.id == config.OWNER_ID:
                return None
        else:
            # Standard exemption check (owner, mods, boosters)
            if is_cooldown_exempt(user):
                return None

        return app_commands.Cooldown(rate, per)

    return cooldown_check
