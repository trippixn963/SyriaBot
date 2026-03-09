"""
SyriaBot - Quote View
=====================

Interactive button to save quote image for Discord saving.
Uses PNG format with .gif filename for right-click save support.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import io
import discord
from discord import ui
from typing import Optional

from src.core.logger import logger
from src.core.colors import EMOJI_SAVE
from src.utils.storage import upload_to_storage


class QuoteView(ui.View):
    """View with Save button for quote images."""

    def __init__(
        self,
        image_bytes: bytes,
        requester_id: int,
        timeout: float = 300,
        bot=None,
    ):
        super().__init__(timeout=timeout)
        self.image_bytes = image_bytes
        self.requester_id = requester_id
        self.bot = bot
        self.message: Optional[discord.Message] = None

    @ui.button(
        label="Save",
        emoji=discord.PartialEmoji.from_str(EMOJI_SAVE),
        style=discord.ButtonStyle.secondary,
        custom_id="quote_save",
    )
    async def save_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Send as public .gif and delete original to avoid spam."""
        logger.tree("Quote Save Button", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ], emoji="💾")

        # Only allow the requester to save
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who made this quote can save it.",
                ephemeral=True
            )
            logger.tree("Quote Save Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Owner ID", str(self.requester_id)),
                ("Reason", "Not quote owner"),
            ], emoji="🚫")
            return

        guild_name = interaction.guild.name if interaction.guild else "DM"

        logger.tree("Quote Save Pressed", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Guild", guild_name),
            ("Size", f"{len(self.image_bytes) // 1024}KB"),
        ], emoji="💾")

        await interaction.response.defer()

        try:
            filename = "discord.gg-syria.gif"

            # Upload to asset storage for permanent URL
            storage_url = None
            if self.bot:
                storage_url = await upload_to_storage(self.bot, self.image_bytes, filename, "Quote")

            if storage_url:
                await interaction.followup.send(storage_url)
            else:
                # Fallback to direct upload
                file = discord.File(
                    fp=io.BytesIO(self.image_bytes),
                    filename=filename
                )
                await interaction.followup.send(file=file)

            # Delete original message to avoid spam
            if self.message:
                try:
                    await self.message.delete()
                except discord.NotFound:
                    logger.tree("Quote Original Delete", [
                        ("Reason", "Message already deleted"),
                    ], emoji="ℹ️")

            logger.tree("Quote Saved", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Format", "PNG as .gif"),
                ("Size", f"{len(self.image_bytes) // 1024}KB"),
                ("Original", "Deleted"),
            ], emoji="✅")

        except Exception as e:
            logger.tree("Quote Save Failed", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)[:100]),
            ], emoji="❌")
            await interaction.followup.send("Failed to save quote.", ephemeral=True)

    async def on_timeout(self) -> None:
        """Disable button on timeout."""
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                logger.tree("Quote View Timeout", [
                    ("Message ID", str(self.message.id)),
                    ("Action", "Disabled save button"),
                ], emoji="⏳")
            except discord.NotFound:
                logger.tree("Quote View Timeout", [
                    ("Reason", "Message deleted"),
                ], emoji="⏳")
            except Exception as e:
                logger.tree("Quote View Timeout Error", [
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
