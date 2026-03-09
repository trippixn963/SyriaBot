"""
SyriaBot - Roulette Views
=========================

Discord embeds for the automatic roulette minigame.
No join buttons — participants are selected from recent chat activity.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from typing import List, TYPE_CHECKING

from src.core.colors import COLOR_GOLD, COLOR_GREEN, COLOR_NEUTRAL

if TYPE_CHECKING:
    from .graphics import RoulettePlayer


def create_announcement_embed(
    players: List["RoulettePlayer"],
    xp_reward: int,
) -> discord.Embed:
    """Create the announcement embed showing participants and their odds."""
    embed = discord.Embed(
        title="🎰 ROULETTE",
        description="The most active chatters are on the wheel!",
        color=COLOR_GOLD,
    )

    # Build participant list with message counts and odds
    lines = []
    for i, p in enumerate(players, 1):
        pct = p.weight * 100
        lines.append(f"**{i}.** {p.display_name} — {p.message_count} msgs ({pct:.1f}%)")

    embed.add_field(
        name="Participants",
        value="\n".join(lines),
        inline=False,
    )

    embed.add_field(
        name="Prize",
        value=f"Winner gets **{xp_reward:,} XP**",
        inline=True,
    )

    embed.add_field(
        name="How It Works",
        value="More messages = bigger slice = higher chance!",
        inline=True,
    )

    return embed


def create_spinning_embed() -> discord.Embed:
    """Create embed shown while wheel is spinning."""
    embed = discord.Embed(
        title="🎰 SPINNING THE WHEEL...",
        description="Good luck everyone!",
        color=COLOR_GOLD,
    )
    return embed


def create_winner_embed(
    winner: discord.Member,
    xp_awarded: int,
    player_count: int,
    message_count: int = 0,
    win_probability: float = 0.0,
) -> discord.Embed:
    """Create the winner announcement embed."""
    embed = discord.Embed(
        title="🎉 WINNER!",
        description=f"**{winner.mention}** won the roulette!",
        color=COLOR_GREEN,
    )

    embed.add_field(
        name="Prize",
        value=f"+**{xp_awarded:,}** XP",
        inline=True,
    )

    embed.add_field(
        name="Players",
        value=str(player_count),
        inline=True,
    )

    if message_count > 0:
        embed.add_field(
            name="Messages",
            value=f"{message_count} msgs ({win_probability:.1f}% chance)",
            inline=True,
        )

    embed.set_thumbnail(url=winner.display_avatar.url)
    return embed


def create_cancelled_embed(reason: str) -> discord.Embed:
    """Create embed for cancelled game."""
    embed = discord.Embed(
        title="🎰 Roulette Cancelled",
        description=reason,
        color=COLOR_NEUTRAL,
    )
    return embed
