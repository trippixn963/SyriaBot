"""
SyriaBot - Quote View
=====================

Interactive button to save quote as GIF for Discord saving.

Author: حَـــــنَّـــــا
"""

import io
import discord
from discord import ui
from PIL import Image
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
        """Convert PNG to GIF and send ephemeral for easy Discord saving."""
        guild_name = interaction.guild.name if interaction.guild else "DM"

        log.tree("Quote Save Pressed", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
            ("Guild", guild_name),
            ("Size", f"{len(self.image_bytes) // 1024}KB"),
        ], emoji="💾")

        await interaction.response.defer(ephemeral=True)

        try:
            # Convert PNG bytes to GIF
            img = Image.open(io.BytesIO(self.image_bytes))
            original_size = img.size

            # Convert to RGB if necessary (GIF doesn't support RGBA well)
            if img.mode in ('RGBA', 'P'):
                # Create background for transparency
                background = Image.new('RGB', img.size, (54, 57, 63))  # Discord dark theme color
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Save as GIF
            gif_buffer = io.BytesIO()
            img.save(gif_buffer, format='GIF', quality=100)
            gif_size = gif_buffer.tell()
            gif_buffer.seek(0)

            # Send as ephemeral GIF (only user can see and save)
            file = discord.File(fp=gif_buffer, filename="discord.gg-syria.gif")
            await interaction.followup.send(file=file, ephemeral=True)

            log.tree("Quote Saved as GIF", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("User ID", str(interaction.user.id)),
                ("Dimensions", f"{original_size[0]}x{original_size[1]}"),
                ("GIF Size", f"{gif_size // 1024}KB"),
            ], emoji="✅")

        except Exception as e:
            log.tree("Quote Save Failed", [
                ("User", f"{interaction.user.name}"),
                ("User ID", str(interaction.user.id)),
                ("Error", str(e)[:100]),
            ], emoji="❌")
            await interaction.followup.send("Failed to save quote as GIF.", ephemeral=True)

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
