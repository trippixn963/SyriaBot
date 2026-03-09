"""
SyriaBot - Confess Command
==========================

Slash commands for anonymous confessions system.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import re
import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import logger
from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING


def strip_mentions_and_emojis(text: str) -> str:
    """
    Remove mentions and custom emojis from text.

    Args:
        text: The text to clean

    Returns:
        Cleaned text without mentions or custom emojis
    """
    # Remove user mentions <@123> or <@!123>
    text = re.sub(r'<@!?\d+>', '', text)
    # Remove role mentions <@&123>
    text = re.sub(r'<@&\d+>', '', text)
    # Remove channel mentions <#123>
    text = re.sub(r'<#\d+>', '', text)
    # Remove custom emojis <:name:123> or <a:name:123>
    text = re.sub(r'<a?:\w+:\d+>', '', text)
    # Clean up extra whitespace
    text = ' '.join(text.split())
    return text.strip()


class ConfessModal(discord.ui.Modal, title="Submit Confession"):
    """Modal for entering confession text."""

    confession_text = discord.ui.TextInput(
        label="Your Confession",
        placeholder="Write your anonymous confession here...",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=1500,
        required=True,
    )

    def __init__(self, service) -> None:
        super().__init__()
        self.service = service

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle confession submission."""
        content = self.confession_text.value.strip()

        logger.tree("Confession Modal Submitted", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Raw Length", f"{len(content)} chars"),
        ], emoji="📝")

        # Strip mentions and emojis
        original_length = len(content)
        content = strip_mentions_and_emojis(content)
        stripped_count = original_length - len(content)

        if stripped_count > 0:
            logger.tree("Confession Content Cleaned", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Before", f"{original_length} chars"),
                ("After", f"{len(content)} chars"),
                ("Removed", f"{stripped_count} chars"),
            ], emoji="🧹")

        # Validate after stripping
        if len(content) < 10:
            logger.tree("Confession Validation Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Length", f"{len(content)} chars"),
                ("Reason", "Too short after cleaning"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ Confession must be at least 10 characters (after removing mentions/emojis).",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Defer first — submit_confession() can take time (webhook, posting, thread creation)
        await interaction.response.defer(ephemeral=True)

        # Submit to service
        success = await self.service.submit_confession(content, interaction.user)

        if success:
            embed = discord.Embed(
                description="✅ Your confession has been posted anonymously!",
                color=COLOR_SUCCESS
            )

            logger.tree("Confession Modal Success", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Length", f"{len(content)} chars"),
            ], emoji="✅")
        else:
            embed = discord.Embed(
                description="❌ Failed to submit confession. Please try again later.",
                color=COLOR_ERROR
            )

            logger.tree("Confession Modal Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service returned False"),
            ], emoji="❌")

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle modal errors."""
        # Interaction expired — nothing we can do, just log it
        if isinstance(error, discord.NotFound):
            logger.tree("Confession Modal Expired", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ], emoji="⏳")
            return

        logger.error_tree("Confession Modal Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ])

        embed = discord.Embed(
            description="❌ An error occurred. Please try again.",
            color=COLOR_ERROR
        )

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except (discord.NotFound, discord.HTTPException):
            pass


class ReplyModal(discord.ui.Modal, title="Anonymous Reply"):
    """Modal for entering anonymous reply."""

    reply_text = discord.ui.TextInput(
        label="Your Reply",
        placeholder="Write your anonymous reply here...",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=1000,
        required=True,
    )

    def __init__(self, service, confession_number: int, thread: discord.Thread) -> None:
        super().__init__()
        self.service = service
        self.confession_number: int = confession_number
        self.thread: discord.Thread = thread

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle reply submission."""
        content = self.reply_text.value.strip()

        logger.tree("Reply Modal Submitted", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Confession", f"#{self.confession_number}"),
            ("Raw Length", f"{len(content)} chars"),
        ], emoji="💬")

        # Strip mentions and emojis
        original_length = len(content)
        content = strip_mentions_and_emojis(content)
        stripped_count = original_length - len(content)

        if stripped_count > 0:
            logger.tree("Reply Content Cleaned", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Before", f"{original_length} chars"),
                ("After", f"{len(content)} chars"),
            ], emoji="🧹")

        # Validate after stripping
        if len(content) < 5:
            logger.tree("Reply Validation Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Length", f"{len(content)} chars"),
                ("Reason", "Too short after cleaning"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ Reply must be at least 5 characters (after removing mentions/emojis).",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Defer first — post_anonymous_reply() can take time (webhook creation)
        await interaction.response.defer(ephemeral=True)

        # Post the anonymous reply
        success = await self.service.post_anonymous_reply(
            self.thread,
            content,
            interaction.user,
            self.confession_number
        )

        if success:
            embed = discord.Embed(
                description="✅ Your anonymous reply has been posted.",
                color=COLOR_SUCCESS
            )

            logger.tree("Reply Modal Success", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Confession", f"#{self.confession_number}"),
                ("Length", f"{len(content)} chars"),
            ], emoji="✅")
        else:
            embed = discord.Embed(
                description="❌ Failed to post reply. Please try again.",
                color=COLOR_ERROR
            )

            logger.tree("Reply Modal Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Confession", f"#{self.confession_number}"),
                ("Reason", "Service returned False"),
            ], emoji="❌")

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle modal errors."""
        if isinstance(error, discord.NotFound):
            logger.tree("Reply Modal Expired", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Confession", f"#{self.confession_number}"),
            ], emoji="⏳")
            return

        logger.error_tree("Reply Modal Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Confession", f"#{self.confession_number}"),
        ])

        embed = discord.Embed(
            description="❌ An error occurred. Please try again.",
            color=COLOR_ERROR
        )

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except (discord.NotFound, discord.HTTPException):
            pass


class ConfessCog(commands.Cog):
    """
    Confession slash commands.

    DESIGN:
        Provides /confess for anonymous confessions (1/day limit) and /reply
        for anonymous replies in confession threads. Strips mentions and custom
        emojis to prevent abuse. All confessions go through mod review before
        being posted publicly with auto-generated thread for discussion.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the confess cog.

        Args:
            bot: Main bot instance with confession_service attribute.
        """
        self.bot: commands.Bot = bot

    @app_commands.command(name="confess", description="Submit an anonymous confession")
    async def confess(self, interaction: discord.Interaction) -> None:
        """Open the confession submission modal."""
        logger.tree("Confess Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Channel", interaction.channel.name if hasattr(interaction.channel, 'name') else "Unknown"),
        ], emoji="📝")

        if not hasattr(self.bot, 'confession_service') or not self.bot.confession_service:
            logger.tree("Confess Command Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not available"),
            ], emoji="❌")
            embed = discord.Embed(
                description="❌ Confessions system is not available.",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        service = self.bot.confession_service

        # Check rate limit (1 confession per day, resets at midnight EST)
        can_submit, remaining = await service.check_rate_limit(interaction.user.id)
        if not can_submit:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            if hours > 0:
                time_str = f"{hours}h {minutes}m"
            else:
                time_str = f"{minutes}m"

            logger.tree("Confess Daily Limit Reached", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reset In", time_str),
            ], emoji="⏳")

            embed = discord.Embed(
                description=(
                    f"⏳ You've already submitted a confession today.\n\n"
                    f"The daily limit resets at **midnight Eastern Time**.\n"
                    f"You can submit again in **{time_str}**."
                ),
                color=COLOR_WARNING
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        logger.tree("Confess Modal Opening", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ], emoji="📋")

        modal = ConfessModal(service)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="reply", description="Reply anonymously to a confession")
    async def reply(self, interaction: discord.Interaction) -> None:
        """Open the anonymous reply modal - must be used in a confession thread."""
        logger.tree("Reply Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Channel", interaction.channel.name if hasattr(interaction.channel, 'name') else "Unknown"),
        ], emoji="💬")

        if not hasattr(self.bot, 'confession_service') or not self.bot.confession_service:
            logger.tree("Reply Command Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not available"),
            ], emoji="❌")
            embed = discord.Embed(
                description="❌ Confessions system is not available.",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        service = self.bot.confession_service

        # Check if in a confession thread
        if not isinstance(interaction.channel, discord.Thread):
            logger.tree("Reply Wrong Channel", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Channel Type", type(interaction.channel).__name__),
                ("Reason", "Not a thread"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ This command can only be used inside a confession thread.",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        thread = interaction.channel
        if not thread.name.startswith("Confession #"):
            logger.tree("Reply Wrong Thread", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Thread", thread.name),
                ("Reason", "Not a confession thread"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ This command can only be used inside a confession thread.",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Extract confession number
        try:
            confession_number = int(thread.name.replace("Confession #", ""))
        except ValueError:
            logger.tree("Reply Parse Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Thread", thread.name),
                ("Reason", "Could not parse confession number"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ Could not identify confession number.",
                color=COLOR_ERROR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        logger.tree("Reply Modal Opening", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Confession", f"#{confession_number}"),
        ], emoji="📋")

        modal = ReplyModal(service, confession_number, thread)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot) -> None:
    """Register the confess cog."""
    await bot.add_cog(ConfessCog(bot))
    logger.tree("Command Loaded", [
        ("Commands", "/confess, /reply"),
    ], emoji="✅")
