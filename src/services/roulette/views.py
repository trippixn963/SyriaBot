"""
SyriaBot - Roulette Views
=========================

Discord UI components for the roulette minigame.
Join button, player list display, and result views.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import discord
from discord import ui
from typing import Set, Optional, TYPE_CHECKING

from src.core.logger import logger
from src.core.colors import COLOR_GOLD, COLOR_GREEN
from src.core.emojis import EMOJI_TICKET
from src.utils.footer import set_footer

if TYPE_CHECKING:
    from .service import RouletteGame


class JoinRouletteButton(ui.Button):
    """Button to join an active roulette game."""

    def __init__(self, game: "RouletteGame") -> None:
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="Join Roulette!",
            emoji=EMOJI_TICKET,
            custom_id=f"roulette_join_{game.game_id}",
        )
        self.game = game

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle join button click."""
        user = interaction.user

        # Check if already joined
        if user.id in self.game.player_ids:
            await interaction.response.send_message(
                "You've already joined this roulette!",
                ephemeral=True
            )
            return

        # Check if game is still accepting players
        if self.game.is_spinning or self.game.is_finished:
            await interaction.response.send_message(
                "This roulette has already started!",
                ephemeral=True
            )
            return

        # Add player
        self.game.player_ids.add(user.id)
        self.game.players.append({
            "user_id": user.id,
            "display_name": user.display_name,
            "avatar_url": user.display_avatar.url,
        })

        logger.tree("Roulette Player Joined", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Game ID", self.game.game_id),
            ("Total Players", str(len(self.game.players))),
        ], emoji="🎰")

        # Acknowledge
        await interaction.response.send_message(
            f"You joined the roulette! **{len(self.game.players)}** player(s) so far.",
            ephemeral=True
        )

        # Update the embed with new player count
        await self.game.update_join_embed()


class RouletteJoinView(ui.View):
    """View for the roulette join phase."""

    def __init__(self, game: "RouletteGame") -> None:
        super().__init__(timeout=None)  # We handle timeout manually
        self.game = game
        self.add_item(JoinRouletteButton(game))

    async def on_timeout(self) -> None:
        """Disable buttons when view times out."""
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True


def create_join_embed(
    player_count: int,
    time_remaining: int,
    min_players: int = 3,
    xp_reward: int = 1000,
) -> discord.Embed:
    """Create the join phase embed."""
    embed = discord.Embed(
        title="🎰 ROULETTE GAME",
        description=(
            f"A roulette has started!\n\n"
            f"**Click the button below to join!**\n\n"
            f"Time remaining: **{time_remaining}s**\n"
            f"Players: **{player_count}** (need {min_players}+)"
        ),
        color=COLOR_GOLD,
    )

    # Status indicator
    if player_count >= min_players:
        embed.add_field(
            name="Status",
            value="Ready to spin! More players can still join.",
            inline=False,
        )
    else:
        needed = min_players - player_count
        embed.add_field(
            name="Status",
            value=f"Need **{needed}** more player(s) to start!",
            inline=False,
        )

    embed.add_field(
        name="Prize",
        value=f"Winner gets **{xp_reward:,} XP**",
        inline=True,
    )

    set_footer(embed)
    return embed


def create_spinning_embed() -> discord.Embed:
    """Create embed shown while wheel is spinning."""
    embed = discord.Embed(
        title="🎰 SPINNING THE WHEEL...",
        description="Good luck everyone!",
        color=COLOR_GOLD,
    )
    set_footer(embed)
    return embed


def create_winner_embed(
    winner: discord.Member,
    xp_awarded: int,
    player_count: int,
) -> discord.Embed:
    """Create the winner announcement embed."""
    embed = discord.Embed(
        title="🎉 WINNER!",
        description=f"**{winner.mention}** won the roulette!",
        color=COLOR_GREEN,
    )

    embed.add_field(
        name="Prize",
        value=f"+**{xp_awarded}** XP",
        inline=True,
    )

    embed.add_field(
        name="Players",
        value=str(player_count),
        inline=True,
    )

    embed.set_thumbnail(url=winner.display_avatar.url)
    set_footer(embed)
    return embed


def create_cancelled_embed(reason: str) -> discord.Embed:
    """Create embed for cancelled game."""
    embed = discord.Embed(
        title="🎰 Roulette Cancelled",
        description=reason,
        color=discord.Color.dark_grey(),
    )
    set_footer(embed)
    return embed
