"""
SyriaBot - Confession Views
===========================

Persistent views for confession threads.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import re
import discord
from discord import ui

from src.core.logger import logger
from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, EMOJI_COMMENT


def strip_mentions_and_emojis(text: str, max_length: int = 2000) -> str:
    """Remove mentions and custom emojis from text.

    Args:
        text: The input text to process
        max_length: Maximum input length to process (prevents ReDoS)

    Returns:
        Cleaned text with mentions and emojis removed
    """
    # Truncate extremely long inputs to prevent ReDoS attacks
    if len(text) > max_length:
        text = text[:max_length]

    text = re.sub(r'<@!?\d+>', '', text)
    text = re.sub(r'<@&\d+>', '', text)
    text = re.sub(r'<#\d+>', '', text)
    text = re.sub(r'<a?:\w+:\d+>', '', text)
    text = ' '.join(text.split())
    return text.strip()


class ReplyModal(ui.Modal, title="Anonymous Reply"):
    """Modal for entering anonymous reply."""

    reply_text = ui.TextInput(
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
        self.confession_number = confession_number
        self.thread = thread

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle reply submission."""
        from src.utils.footer import set_footer

        content = self.reply_text.value.strip()

        logger.tree("Reply Button Modal Submitted", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Confession", f"#{self.confession_number}"),
            ("Length", f"{len(content)} chars"),
        ], emoji="💬")

        # Strip mentions and emojis
        content = strip_mentions_and_emojis(content)

        if len(content) < 5:
            embed = discord.Embed(
                description="❌ Reply must be at least 5 characters.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

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
        else:
            embed = discord.Embed(
                description="❌ Failed to post reply. Please try again.",
                color=COLOR_ERROR
            )

        set_footer(embed)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ConfessionReplyView(ui.View):
    """Persistent view with Reply button for confession threads."""

    def __init__(self, confession_number: int):
        super().__init__(timeout=None)
        self.confession_number = confession_number

        # Add button with custom_id encoding confession number
        btn = ui.Button(
            label="Reply",
            emoji=discord.PartialEmoji.from_str(EMOJI_COMMENT),
            style=discord.ButtonStyle.secondary,
            custom_id=f"confession:reply:{confession_number}",
        )
        btn.callback = self.reply_callback
        self.add_item(btn)

    async def reply_callback(self, interaction: discord.Interaction) -> None:
        """Handle reply button click."""
        # Get service from bot
        if not hasattr(interaction.client, 'confession_service') or not interaction.client.confession_service:
            await interaction.response.send_message(
                "❌ Confessions system is not available.",
                ephemeral=True
            )
            return

        service = interaction.client.confession_service

        # Must be in a thread
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                "❌ This button only works in confession threads.",
                ephemeral=True
            )
            return

        logger.tree("Reply Button Clicked", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Confession", f"#{self.confession_number}"),
        ], emoji="🔘")

        modal = ReplyModal(service, self.confession_number, interaction.channel)
        await interaction.response.send_modal(modal)


async def handle_confession_reply_interaction(interaction: discord.Interaction) -> bool:
    """
    Handle confession reply button interactions.

    Returns True if the interaction was handled, False otherwise.
    Called from on_interaction listener.
    """
    # Only handle button interactions
    if interaction.type != discord.InteractionType.component:
        return False

    # Check if this is a confession reply button
    custom_id = interaction.data.get("custom_id", "")
    if not custom_id.startswith("confession:reply:"):
        return False

    # Parse confession number
    parts = custom_id.split(":")
    if len(parts) < 3:
        await interaction.response.defer()
        return True

    try:
        confession_number = int(parts[2])
    except ValueError:
        await interaction.response.defer()
        return True

    # Get service
    if not hasattr(interaction.client, 'confession_service') or not interaction.client.confession_service:
        await interaction.response.send_message(
            "❌ Confessions system is not available.",
            ephemeral=True
        )
        return True

    service = interaction.client.confession_service

    # Must be in a thread
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "❌ This button only works in confession threads.",
            ephemeral=True
        )
        return True

    logger.tree("Reply Button Clicked (Persistent)", [
        ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
        ("ID", str(interaction.user.id)),
        ("Confession", f"#{confession_number}"),
    ], emoji="🔘")

    modal = ReplyModal(service, confession_number, interaction.channel)
    await interaction.response.send_modal(modal)
    return True


def setup_confession_views(bot: discord.Client) -> None:
    """Register persistent confession interaction handler."""

    async def confession_interaction_listener(interaction: discord.Interaction) -> None:
        """Handle confession reply button interactions."""
        await handle_confession_reply_interaction(interaction)

    bot.add_listener(confession_interaction_listener, "on_interaction")

    logger.tree("Confession Persistent Views", [
        ("Status", "Registered (interaction listener)"),
    ], emoji="✅")
