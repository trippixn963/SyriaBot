"""
SyriaBot - Rank Command
=======================

View XP and level information.
"""

import io
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.colors import COLOR_GOLD
from src.core.logger import log
from src.services.database import db
from src.utils.footer import set_footer
from src.services.xp.utils import (
    xp_progress,
    xp_for_level,
    progress_bar,
    format_xp,
    format_voice_time,
)
from src.services.xp.card import generate_rank_card


def rank_cooldown(interaction: discord.Interaction) -> Optional[app_commands.Cooldown]:
    """
    Dynamic cooldown - None for mods/owners, 5 min for everyone else.

    Args:
        interaction: The Discord interaction

    Returns:
        Cooldown object or None if user is exempt
    """
    # Owner bypass
    if interaction.user.id == config.OWNER_ID:
        return None

    # Mod bypass
    if isinstance(interaction.user, discord.Member):
        if config.MOD_ROLE_ID:
            mod_role = interaction.user.get_role(config.MOD_ROLE_ID)
            if mod_role:
                return None

    # Normal users: 1 use per 5 minutes
    return app_commands.Cooldown(1, 300.0)


class LeaderboardView(discord.ui.View):
    """View with leaderboard link button."""

    def __init__(self, user_id: int) -> None:
        """Initialize the leaderboard view with user link button."""
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Stats & Leaderboard",
            emoji=discord.PartialEmoji.from_str("<:leaderboard:1456582433033162927>"),
            url=f"https://trippixn.com/syria/leaderboard/{user_id}",
        ))


class RankCog(commands.Cog):
    """XP and ranking commands."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the rank cog."""
        self.bot = bot

    @app_commands.command(name="rank", description="View your XP and level")
    @app_commands.describe(user="User to check (defaults to yourself)")
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))
    @app_commands.checks.dynamic_cooldown(rank_cooldown)
    async def rank(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None
    ) -> None:
        """Display XP rank card for a user."""
        await interaction.response.defer()

        target = user or interaction.user
        member = interaction.guild.get_member(target.id) if interaction.guild else None

        if not member:
            embed = discord.Embed(
                description="❌ User not found in this server",
                color=0xf04747,
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get XP data
        xp_data = db.get_user_xp(member.id, interaction.guild.id)

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

        # Get rank
        rank = db.get_user_rank(member.id, interaction.guild.id)

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

            log.tree("Rank Command", [
                ("User", f"{interaction.user.name}"),
                ("Target", f"{member.name}"),
                ("Level", str(level)),
                ("XP", format_xp(current_xp)),
                ("Type", "Graphical"),
            ], emoji="📊")

        except Exception as e:
            # Fallback to embed if image generation fails
            log.tree("Rank Card Generation Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Error", str(e)),
            ], emoji="⚠️")

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
        set_footer(embed)

        view = LeaderboardView(member.id)
        await interaction.followup.send(embed=embed, view=view)

        log.tree("Rank Command", [
            ("User", f"{interaction.user.name}"),
            ("Target", f"{member.name}"),
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
            except discord.HTTPException:
                pass

            log.tree("Rank Cooldown", [
                ("User", interaction.user.name),
                ("Remaining", time_str),
            ], emoji="⏳")
            return

        log.tree("Rank Command Error", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
            ("Error", str(error)),
        ], emoji="❌")

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
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    await bot.add_cog(RankCog(bot))
    log.tree("Command Loaded", [("Name", "rank")], emoji="✅")
