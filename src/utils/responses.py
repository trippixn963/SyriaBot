"""
SyriaBot - Response Utilities
=============================

Safe response helpers for Discord interactions.
Handles already-responded interactions gracefully.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Optional

import discord

from src.core.logger import log


async def safe_send(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    ephemeral: bool = True,
    view: Optional[discord.ui.View] = None,
) -> bool:
    """
    Safely send a response to an interaction.

    Handles cases where the interaction has already been responded to
    or has expired. Uses followup if already responded.

    Args:
        interaction: The Discord interaction
        content: Text content to send
        embed: Embed to send
        ephemeral: Whether the message should be ephemeral
        view: Optional view to attach

    Returns:
        True if message was sent successfully, False otherwise
    """
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                content=content,
                embed=embed,
                ephemeral=ephemeral,
                view=view,
            )
        else:
            await interaction.followup.send(
                content=content,
                embed=embed,
                ephemeral=ephemeral,
                view=view,
            )
        return True
    except discord.HTTPException as e:
        log.tree("Response Failed", [
            ("User", f"{interaction.user.name}"),
            ("Error", str(e)[:50]),
        ], emoji="❌")
        return False


async def safe_defer(
    interaction: discord.Interaction,
    ephemeral: bool = False,
    thinking: bool = True,
) -> bool:
    """
    Safely defer an interaction response.

    Args:
        interaction: The Discord interaction
        ephemeral: Whether the deferred response should be ephemeral
        thinking: Whether to show "thinking..." indicator

    Returns:
        True if deferred successfully, False otherwise
    """
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        return True
    except discord.HTTPException as e:
        log.tree("Defer Failed", [
            ("User", f"{interaction.user.name}"),
            ("Error", str(e)[:50]),
        ], emoji="❌")
        return False


async def safe_edit(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
) -> bool:
    """
    Safely edit the original interaction response.

    Args:
        interaction: The Discord interaction
        content: New text content
        embed: New embed
        view: New view

    Returns:
        True if edited successfully, False otherwise
    """
    try:
        await interaction.edit_original_response(
            content=content,
            embed=embed,
            view=view,
        )
        return True
    except discord.HTTPException as e:
        log.tree("Edit Failed", [
            ("User", f"{interaction.user.name}"),
            ("Error", str(e)[:50]),
        ], emoji="❌")
        return False


def is_guild_member(interaction: discord.Interaction) -> bool:
    """
    Check if the interaction user is a guild member.

    Use this before accessing member-specific attributes like roles.

    Args:
        interaction: The Discord interaction

    Returns:
        True if user is a Member (in a guild), False if User (in DMs)
    """
    return isinstance(interaction.user, discord.Member)


def get_member(interaction: discord.Interaction) -> Optional[discord.Member]:
    """
    Get the interaction user as a Member, or None if in DMs.

    Args:
        interaction: The Discord interaction

    Returns:
        The user as a Member, or None if not in a guild
    """
    if isinstance(interaction.user, discord.Member):
        return interaction.user
    return None
