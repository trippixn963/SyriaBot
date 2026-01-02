"""
SyriaBot - Quote View
=====================

Interactive button to save quote image for Discord saving.
Uses PNG format with .gif filename for right-click save support.

Author: حَـــــنَّـــــا
"""

import io
import discord
from discord import ui
from typing import Optional

from src.core.logger import log


# Custom emoji ID
SAVE_EMOJI = "<:save:1455776703468273825>"


class QuoteView(ui.View):
    """View with Save button for quote images."""

    def __init__(
        self,
        image_bytes: bytes,
        timeout: float = 300,
    ):
        super().__init__(timeout=timeout)
        self.image_bytes = image_bytes
        self.message: Optional[discord.Message] = None

    @ui.button(
        label="Save",
        emoji=discord.PartialEmoji.from_str(SAVE_EMOJI),
        style=discord.ButtonStyle.secondary,
        custom_id="quote_save",
    )
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        """Send PNG with .gif filename for easy Discord saving (full quality)."""
        guild_name = interaction.guild.name if interaction.guild else "DM"

        log.tree("Quote Save Pressed", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
            ("Guild", guild_name),
            ("Size", f"{len(self.image_bytes) // 1024}KB"),
        ], emoji="💾")

        await interaction.response.defer(ephemeral=True)

        try:
            # Send original PNG bytes with .gif filename
            # Discord allows right-click save on .gif files
            # PNG format preserves full quality (no 256 color limit like real GIF)
            file = discord.File(
                fp=io.BytesIO(self.image_bytes),
                filename="discord.gg-syria.gif"
            )
            await interaction.followup.send(file=file, ephemeral=True)

            log.tree("Quote Saved", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("User ID", str(interaction.user.id)),
                ("Format", "PNG (full quality)"),
                ("Size", f"{len(self.image_bytes) // 1024}KB"),
            ], emoji="✅")

        except Exception as e:
            log.tree("Quote Save Failed", [
                ("User", f"{interaction.user.name}"),
                ("User ID", str(interaction.user.id)),
                ("Error", str(e)[:100]),
            ], emoji="❌")
            await interaction.followup.send("Failed to save quote.", ephemeral=True)

    async def on_timeout(self):
        """Disable button on timeout."""
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                log.tree("Quote View Timeout", [
                    ("Message ID", str(self.message.id)),
                    ("Action", "Disabled save button"),
                ], emoji="⏳")
            except discord.NotFound:
                log.tree("Quote View Timeout", [
                    ("Reason", "Message deleted"),
                ], emoji="⏳")
            except Exception as e:
                log.tree("Quote View Timeout Error", [
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
