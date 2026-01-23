"""
SyriaBot - Suggest Command
==========================

Submit suggestions for the server.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import logger
from src.core.colors import COLOR_SUCCESS, COLOR_ERROR
from src.services.suggestions.service import SUGGESTION_MIN_LENGTH, SUGGESTION_MAX_LENGTH


class SuggestionModal(discord.ui.Modal, title="Submit a Suggestion"):
    """Modal for submitting suggestions."""

    suggestion = discord.ui.TextInput(
        label="Your Suggestion",
        style=discord.TextStyle.paragraph,
        placeholder="Describe your suggestion in detail...",
        min_length=SUGGESTION_MIN_LENGTH,
        max_length=SUGGESTION_MAX_LENGTH,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle modal submission."""
        logger.tree("Suggestion Modal Submitted", [
            ("User", f"{interaction.user.name}"),
            ("ID", str(interaction.user.id)),
            ("Length", f"{len(self.suggestion.value)} chars"),
        ], emoji="📝")

        # Get suggestion service from bot
        bot = interaction.client
        if not hasattr(bot, "suggestion_service") or bot.suggestion_service is None:
            logger.tree("Suggestion Modal Failed", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not initialized"),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Suggestions are not enabled",
                ephemeral=True
            )
            return

        service = bot.suggestion_service

        # Submit suggestion
        success, message = await service.submit(
            content=self.suggestion.value,
            submitter=interaction.user
        )

        embed = discord.Embed(
            description=message,
            color=COLOR_SUCCESS if success else COLOR_ERROR
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

        if success:
            logger.tree("Suggestion Modal Success", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Response", message),
            ], emoji="✅")
        else:
            logger.tree("Suggestion Modal Failed", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Error", message),
            ], emoji="❌")


class SuggestCog(commands.Cog):
    """Suggestion commands."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the cog."""
        self.bot: commands.Bot = bot

        # Register context menus
        self.ctx_approve = app_commands.ContextMenu(
            name="✅ Approve Suggestion",
            callback=self.approve_suggestion,
        )
        self.ctx_reject = app_commands.ContextMenu(
            name="❌ Reject Suggestion",
            callback=self.reject_suggestion,
        )
        self.ctx_implement = app_commands.ContextMenu(
            name="🎉 Mark Implemented",
            callback=self.implement_suggestion,
        )
        self.ctx_pending = app_commands.ContextMenu(
            name="⏳ Mark Pending",
            callback=self.pending_suggestion,
        )
        self.bot.tree.add_command(self.ctx_approve)
        self.bot.tree.add_command(self.ctx_reject)
        self.bot.tree.add_command(self.ctx_implement)
        self.bot.tree.add_command(self.ctx_pending)

    async def cog_unload(self) -> None:
        """Remove context menus when cog unloads."""
        self.bot.tree.remove_command(self.ctx_approve.name, type=self.ctx_approve.type)
        self.bot.tree.remove_command(self.ctx_reject.name, type=self.ctx_reject.type)
        self.bot.tree.remove_command(self.ctx_implement.name, type=self.ctx_implement.type)
        self.bot.tree.remove_command(self.ctx_pending.name, type=self.ctx_pending.type)

    async def _update_suggestion(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
        status: str
    ) -> None:
        """Helper to update suggestion status."""
        # Check permissions
        if not interaction.user.guild_permissions.manage_messages:
            logger.tree("Suggestion Status Denied", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Missing manage_messages permission"),
            ], emoji="🚫")
            await interaction.response.send_message(
                "You need `Manage Messages` permission to do this.",
                ephemeral=True
            )
            return

        # Check if service is available
        if not hasattr(self.bot, "suggestion_service") or self.bot.suggestion_service is None:
            await interaction.response.send_message(
                "Suggestions service not available.",
                ephemeral=True
            )
            return

        service = self.bot.suggestion_service

        # Check if this is in the suggestions channel
        if message.channel.id != service._channel_id:
            logger.tree("Suggestion Status Wrong Channel", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("Channel", message.channel.name if hasattr(message.channel, "name") else str(message.channel.id)),
                ("Expected", str(service._channel_id)),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "This command only works on suggestions in the suggestions channel.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        success = await service.update_status(message, status, interaction.user)

        if success:
            status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌", "implemented": "🎉"}.get(status, "✅")
            await interaction.followup.send(
                f"{status_emoji} Suggestion marked as **{status}**!",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "Failed to update suggestion. Is this a valid suggestion message?",
                ephemeral=True
            )

    async def approve_suggestion(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Approve a suggestion (context menu)."""
        await self._update_suggestion(interaction, message, "approved")

    async def reject_suggestion(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Reject a suggestion (context menu)."""
        await self._update_suggestion(interaction, message, "rejected")

    async def implement_suggestion(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Mark a suggestion as implemented (context menu)."""
        await self._update_suggestion(interaction, message, "implemented")

    async def pending_suggestion(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Mark a suggestion as pending (context menu)."""
        await self._update_suggestion(interaction, message, "pending")

    @app_commands.command(
        name="suggest",
        description="Submit a suggestion for the server"
    )
    async def suggest(self, interaction: discord.Interaction) -> None:
        """Open suggestion modal."""
        logger.tree("Suggest Command", [
            ("User", f"{interaction.user.name}"),
            ("ID", str(interaction.user.id)),
        ], emoji="💡")

        # Check if service is enabled
        if not hasattr(self.bot, "suggestion_service") or self.bot.suggestion_service is None:
            logger.tree("Suggest Command Blocked", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service not initialized"),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Suggestions are not enabled",
                ephemeral=True
            )
            return

        service = self.bot.suggestion_service
        if not service.is_enabled():
            logger.tree("Suggest Command Blocked", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Service disabled"),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Suggestions are not enabled",
                ephemeral=True
            )
            return

        # Check if user can submit
        can_submit, reason = await service.can_submit(interaction.user.id)
        if not can_submit:
            logger.tree("Suggest Command Blocked", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Reason", reason),
            ], emoji="⏳")
            await interaction.response.send_message(reason, ephemeral=True)
            return

        # Show modal
        await interaction.response.send_modal(SuggestionModal())

        logger.tree("Suggest Modal Opened", [
            ("User", f"{interaction.user.name}"),
            ("ID", str(interaction.user.id)),
        ], emoji="📝")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(SuggestCog(bot))
    logger.tree("Command Loaded", [
        ("Name", "suggest"),
    ], emoji="✅")
