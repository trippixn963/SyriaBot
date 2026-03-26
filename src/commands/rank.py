"""
SyriaBot - Rank Command
=======================

View XP and level information.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import io

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.colors import COLOR_GOLD, COLOR_ERROR, EMOJI_LEADERBOARD
from src.core.logger import logger
from src.services.database import db
from src.utils.permissions import create_cooldown
from src.services.xp.utils import (
    xp_progress,
    xp_for_level,
    progress_bar,
    format_xp,
    format_voice_time,
)
from src.services.xp.card import generate_rank_card


class LeaderboardView(discord.ui.View):
    """View with leaderboard link button."""

    def __init__(self, user_id: int) -> None:
        """Initialize the leaderboard view with user link button."""
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Stats & Leaderboard",
            emoji=discord.PartialEmoji.from_str(EMOJI_LEADERBOARD),
            url=f"{config.LEADERBOARD_BASE_URL}/{user_id}",
        ))


class RankCog(commands.Cog):
    """
    XP and ranking commands.

    DESIGN:
        Generates graphical rank cards with PIL showing level, XP, rank,
        messages, and voice time. Falls back to embed if image generation
        fails. Includes dynamic cooldown (5 min for regular users, exempt
        for staff). Links to web leaderboard for detailed stats.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the rank cog.

        Args:
            bot: Main bot instance for guild access.
        """
        self.bot = bot

    @app_commands.command(name="rank", description="View your XP and level")
    @app_commands.describe(user="User to check (defaults to yourself)")
    @app_commands.checks.dynamic_cooldown(create_cooldown(1, 300))
    async def rank(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None
    ) -> None:
        """Display XP rank card for a user."""
        await interaction.response.defer()

        target = user or interaction.user
        member = interaction.guild.get_member(target.id) if interaction.guild else None

        if not member:
            embed = discord.Embed(
                description="❌ User not found in this server",
                color=COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.tree("Rank User Not Found", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Target ID", str(target.id)),
                ("Reason", "Not in server"),
            ], emoji="⚠️")
            return

        # Get XP data and rank in parallel
        xp_data, rank = await asyncio.gather(
            asyncio.to_thread(db.get_user_xp, member.id, interaction.guild.id),
            asyncio.to_thread(db.get_user_rank, member.id, interaction.guild.id),
        )

        if not xp_data:
            xp_data = {
                "xp": 0,
                "level": 0,
                "total_messages": 0,
                "voice_minutes": 0,
            }

        current_xp = xp_data["xp"]
        level = xp_data["level"]
        total_messages = xp_data["total_messages"]
        voice_minutes = xp_data["voice_minutes"]

        # Get progress info
        _, xp_into_level, xp_needed, progress = xp_progress(current_xp)

        # XP needed for next level (total)
        next_level_xp = xp_for_level(level + 1)

        # Get banner URL if server has one
        banner_url = None
        if interaction.guild and interaction.guild.banner:
            banner_url = str(interaction.guild.banner.url)

        try:
            # Get user status
            status = "offline"
            if member.status:
                status = str(member.status)

            # Generate graphical card
            card_bytes = await generate_rank_card(
                username=member.name,
                display_name=member.display_name,
                avatar_url=str(member.display_avatar.url),
                level=level,
                rank=rank,
                current_xp=xp_into_level,
                xp_for_next=xp_needed,
                xp_progress=progress,
                total_messages=total_messages,
                voice_minutes=voice_minutes,
                is_booster=member.premium_since is not None,
                guild_id=interaction.guild.id if interaction.guild else None,
                banner_url=banner_url,
                status=status,
            )

            file = discord.File(io.BytesIO(card_bytes), filename="rank.png")
            view = LeaderboardView(member.id)
            await interaction.followup.send(file=file, view=view)

            logger.tree("Rank Command", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Target", f"{member.name} ({member.display_name})"),
                ("Target ID", str(member.id)),
                ("Level", str(level)),
                ("XP", format_xp(current_xp)),
                ("Type", "Graphical"),
            ], emoji="📊")

        except Exception as e:
            # Fallback to embed if image generation fails
            logger.error_tree("Rank Card Generation Failed", e, [
                ("User", f"{member.name} ({member.display_name})"),
                ("ID", str(member.id)),
            ])

            await self._send_embed_rank(interaction, member, xp_data, rank)

    async def _send_embed_rank(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        xp_data: dict,
        rank: int
    ) -> None:
        """Send text-based embed rank card (fallback)."""
        current_xp = xp_data["xp"]
        level = xp_data["level"]
        total_messages = xp_data["total_messages"]
        voice_minutes = xp_data["voice_minutes"]

        _, xp_into_level, xp_needed, progress = xp_progress(current_xp)
        progress_percent = int(progress * 100)

        embed = discord.Embed(color=COLOR_GOLD)

        embed.set_author(
            name=f"{member.display_name}'s Rank",
            icon_url=member.display_avatar.url,
        )

        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="Rank", value=f"**#{rank}**", inline=True)
        embed.add_field(name="Total XP", value=f"**{format_xp(current_xp)}**", inline=True)

        bar = progress_bar(progress, 16)
        embed.add_field(
            name="Progress to Next Level",
            value=f"`{bar}` {progress_percent}%\n{format_xp(xp_into_level)} / {format_xp(xp_needed)} XP",
            inline=False,
        )

        voice_time = format_voice_time(voice_minutes)
        embed.add_field(name="Messages", value=f"**{total_messages:,}**", inline=True)
        embed.add_field(name="Voice Time", value=f"**{voice_time}**", inline=True)

        if member.premium_since is not None:
            embed.add_field(name="Boost", value="**2x XP**", inline=True)

        embed.set_thumbnail(url=member.display_avatar.url)

        view = LeaderboardView(member.id)
        await interaction.followup.send(embed=embed, view=view)

        logger.tree("Rank Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Target", f"{member.name} ({member.display_name})"),
            ("Target ID", str(member.id)),
            ("Level", str(level)),
            ("XP", format_xp(current_xp)),
            ("Type", "Embed (fallback)"),
        ], emoji="📊")

    @rank.error
    async def rank_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """Handle rank command errors."""
        # Handle cooldown error
        if isinstance(error, app_commands.CommandOnCooldown):
            minutes = int(error.retry_after // 60)
            seconds = int(error.retry_after % 60)
            if minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"

            try:
                await interaction.response.send_message(
                    f"⏳ Slow down! You can use `/rank` again in **{time_str}**",
                    ephemeral=True,
                )
            except discord.HTTPException as e:
                logger.error_tree("Rank Cooldown Response Failed", e, [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                ])

            logger.tree("Rank Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Remaining", time_str),
            ], emoji="⏳")
            return

        logger.error_tree("Rank Command Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ])

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while fetching rank data",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while fetching rank data",
                    ephemeral=True,
                )
        except discord.HTTPException as e:
            logger.error_tree("Rank Error Response Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(RankCog(bot))
    logger.tree("Command Loaded", [("Name", "rank")], emoji="✅")
