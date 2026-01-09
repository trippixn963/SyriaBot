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
from typing import Optional

from src.core.logger import log
from src.core.config import config
from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING
from src.utils.footer import set_footer


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

    image_url = discord.ui.TextInput(
        label="Image URL (Optional)",
        placeholder="https://example.com/image.png",
        style=discord.TextStyle.short,
        required=False,
        max_length=500,
    )

    def __init__(self, service) -> None:
        super().__init__()
        self.service = service

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle confession submission."""
        content = self.confession_text.value.strip()
        image: Optional[str] = self.image_url.value.strip() if self.image_url.value else None

        log.tree("Confession Modal Submitted", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Raw Length", f"{len(content)} chars"),
            ("Image", "Yes" if image else "No"),
        ], emoji="📝")

        # Strip mentions and emojis
        original_length = len(content)
        content = strip_mentions_and_emojis(content)
        stripped_count = original_length - len(content)

        if stripped_count > 0:
            log.tree("Confession Content Cleaned", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Before", f"{original_length} chars"),
                ("After", f"{len(content)} chars"),
                ("Removed", f"{stripped_count} chars"),
            ], emoji="🧹")

        # Validate after stripping
        if len(content) < 10:
            log.tree("Confession Validation Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Length", f"{len(content)} chars"),
                ("Reason", "Too short after cleaning"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ Confession must be at least 10 characters (after removing mentions/emojis).",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Validate image URL if provided
        if image and not image.startswith(("http://", "https://")):
            log.tree("Confession Image Invalid", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("URL", image[:50]),
                ("Reason", "Invalid URL format"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ Invalid image URL. Must start with http:// or https://",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Submit to service
        success = await self.service.submit_confession(content, interaction.user, image)

        if success:
            embed = discord.Embed(
                description="✅ Your confession has been posted anonymously!",
                color=COLOR_SUCCESS
            )
            set_footer(embed)

            log.tree("Confession Modal Success", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Length", f"{len(content)} chars"),
                ("Image", "Yes" if image else "No"),
            ], emoji="✅")
        else:
            embed = discord.Embed(
                description="❌ Failed to submit confession. Please try again later.",
                color=COLOR_ERROR
            )
            set_footer(embed)

            log.tree("Confession Modal Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service returned False"),
            ], emoji="❌")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle modal errors."""
        log.error_tree("Confession Modal Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ])

        embed = discord.Embed(
            description="❌ An error occurred. Please try again.",
            color=COLOR_ERROR
        )
        set_footer(embed)

        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(embed=embed, ephemeral=True)


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

        log.tree("Reply Modal Submitted", [
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
            log.tree("Reply Content Cleaned", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Before", f"{original_length} chars"),
                ("After", f"{len(content)} chars"),
            ], emoji="🧹")

        # Validate after stripping
        if len(content) < 5:
            log.tree("Reply Validation Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Length", f"{len(content)} chars"),
                ("Reason", "Too short after cleaning"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ Reply must be at least 5 characters (after removing mentions/emojis).",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

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
            set_footer(embed)

            log.tree("Reply Modal Success", [
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
            set_footer(embed)

            log.tree("Reply Modal Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Confession", f"#{self.confession_number}"),
                ("Reason", "Service returned False"),
            ], emoji="❌")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handle modal errors."""
        log.error_tree("Reply Modal Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Confession", f"#{self.confession_number}"),
        ])

        embed = discord.Embed(
            description="❌ An error occurred. Please try again.",
            color=COLOR_ERROR
        )
        set_footer(embed)

        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(embed=embed, ephemeral=True)


class ConfessCog(commands.Cog):
    """Confession slash commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @app_commands.command(name="confess", description="Submit an anonymous confession")
    @app_commands.guild_only()
    async def confess(self, interaction: discord.Interaction) -> None:
        """Open the confession submission modal."""
        log.tree("Confess Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Channel", interaction.channel.name if hasattr(interaction.channel, 'name') else "Unknown"),
        ], emoji="📝")

        if not hasattr(self.bot, 'confession_service') or not self.bot.confession_service:
            log.tree("Confess Command Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not available"),
            ], emoji="❌")
            embed = discord.Embed(
                description="❌ Confessions system is not available.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        service = self.bot.confession_service

        # Check rate limit
        can_submit, remaining = await service.check_rate_limit(interaction.user.id)
        if not can_submit:
            minutes = remaining // 60
            seconds = remaining % 60
            time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

            log.tree("Confess Rate Limited", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Remaining", time_str),
            ], emoji="⏳")

            embed = discord.Embed(
                description=f"⏳ You can submit another confession in **{time_str}**",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        log.tree("Confess Modal Opening", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ], emoji="📋")

        modal = ConfessModal(service)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="reply", description="Reply anonymously to a confession")
    @app_commands.guild_only()
    async def reply(self, interaction: discord.Interaction) -> None:
        """Open the anonymous reply modal - must be used in a confession thread."""
        log.tree("Reply Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Channel", interaction.channel.name if hasattr(interaction.channel, 'name') else "Unknown"),
        ], emoji="💬")

        if not hasattr(self.bot, 'confession_service') or not self.bot.confession_service:
            log.tree("Reply Command Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not available"),
            ], emoji="❌")
            embed = discord.Embed(
                description="❌ Confessions system is not available.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        service = self.bot.confession_service

        # Check if in a confession thread
        if not isinstance(interaction.channel, discord.Thread):
            log.tree("Reply Wrong Channel", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Channel Type", type(interaction.channel).__name__),
                ("Reason", "Not a thread"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ This command can only be used inside a confession thread.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        thread = interaction.channel
        if not thread.name.startswith("Confession #"):
            log.tree("Reply Wrong Thread", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Thread", thread.name),
                ("Reason", "Not a confession thread"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ This command can only be used inside a confession thread.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Extract confession number
        try:
            confession_number = int(thread.name.replace("Confession #", ""))
        except ValueError:
            log.tree("Reply Parse Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Thread", thread.name),
                ("Reason", "Could not parse confession number"),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="❌ Could not identify confession number.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        log.tree("Reply Modal Opening", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Confession", f"#{confession_number}"),
        ], emoji="📋")

        modal = ReplyModal(service, confession_number, thread)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot) -> None:
    """Register the confess cog."""
    await bot.add_cog(ConfessCog(bot))
    log.tree("Command Loaded", [
        ("Commands", "/confess, /reply"),
    ], emoji="✅")
