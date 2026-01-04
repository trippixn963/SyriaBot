"""
SyriaBot - Image View
=====================

Interactive view for browsing image search results.

Author: حَـــــنَّـــــا
"""

import discord
import random
from discord import ui
from typing import Optional

from src.core.logger import log
from src.core.config import config
from src.services.image_service import ImageResult
from src.utils.footer import set_footer


# =============================================================================
# Image View
# =============================================================================

class ImageView(ui.View):
    """Interactive view for browsing images with navigation."""

    def __init__(
        self,
        images: list[ImageResult],
        query: str,
        requester_id: int,
        timeout: float = 300,  # 5 minutes
    ):
        super().__init__(timeout=timeout)
        self.images = images
        self.query = query
        self.requester_id = requester_id
        self.current_index = 0
        self.message: Optional[discord.Message] = None

        # Update button states
        self._update_buttons()

        log.tree("Image View Created", [
            ("Query", query[:50]),
            ("Images", str(len(images))),
            ("Requester", str(requester_id)),
        ], emoji="🖼️")

    def _update_buttons(self):
        """Update button disabled states based on current index."""
        # First button (<<)
        self.first_button.disabled = self.current_index == 0
        # Previous button (<)
        self.prev_button.disabled = self.current_index == 0
        # Next button (>)
        self.next_button.disabled = self.current_index >= len(self.images) - 1
        # Last button (>>)
        self.last_button.disabled = self.current_index >= len(self.images) - 1

    def create_embed(self) -> discord.Embed:
        """Create embed for current image."""
        if not self.images:
            embed = discord.Embed(
                title="No Images Found",
                description=f"No results for: **{self.query}**",
                color=0xFF0000
            )
            set_footer(embed)
            return embed

        image = self.images[self.current_index]

        embed = discord.Embed(
            title=image.title[:256] if len(image.title) > 256 else image.title,
            url=image.source_url,
            color=0x5865F2
        )
        embed.set_image(url=image.url)

        # Add image info fields
        embed.add_field(
            name="Position",
            value=f"{self.current_index + 1}/{len(self.images)}",
            inline=True
        )
        if image.width and image.height:
            embed.add_field(
                name="Resolution",
                value=f"{image.width}x{image.height}",
                inline=True
            )

        # Detect file type from URL
        url_lower = image.url.lower()
        if ".gif" in url_lower:
            file_type = "GIF"
        elif ".png" in url_lower:
            file_type = "PNG"
        elif ".webp" in url_lower:
            file_type = "WebP"
        elif ".jpg" in url_lower or ".jpeg" in url_lower:
            file_type = "JPEG"
        else:
            file_type = "Image"
        embed.add_field(name="Type", value=file_type, inline=True)

        set_footer(embed)

        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the requester to use buttons."""
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who searched can use these buttons.",
                ephemeral=True
            )
            log.tree("Image View Unauthorized", [
                ("User", str(interaction.user)),
                ("User ID", str(interaction.user.id)),
                ("Requester ID", str(self.requester_id)),
            ], emoji="⚠️")
            return False
        return True

    async def on_timeout(self):
        """Disable buttons on timeout."""
        log.tree("Image View Timeout", [
            ("Query", self.query[:50]),
            ("Position", f"{self.current_index + 1}/{len(self.images)}"),
        ], emoji="⏳")

        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def _update_message(self, interaction: discord.Interaction, nav_action: str):
        """Update the message with new image."""
        self._update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

        log.tree("Image Navigation", [
            ("User", str(interaction.user)),
            ("Action", nav_action),
            ("Position", f"{self.current_index + 1}/{len(self.images)}"),
            ("Query", self.query[:30]),
        ], emoji="🔄")

    @ui.button(label="", emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="first")
    async def first_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to first image."""
        self.current_index = 0
        await self._update_message(interaction, "first")

    @ui.button(label="", emoji="◀️", style=discord.ButtonStyle.primary, custom_id="prev")
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to previous image."""
        if self.current_index > 0:
            self.current_index -= 1
        await self._update_message(interaction, "prev")

    @ui.button(label="", emoji="🎲", style=discord.ButtonStyle.secondary, custom_id="random")
    async def random_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to a random image."""
        if len(self.images) > 1:
            # Pick a random index different from current
            choices = [i for i in range(len(self.images)) if i != self.current_index]
            self.current_index = random.choice(choices)
        await self._update_message(interaction, "random")

    @ui.button(label="", emoji="▶️", style=discord.ButtonStyle.primary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to next image."""
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
        await self._update_message(interaction, "next")

    @ui.button(label="", emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="last")
    async def last_button(self, interaction: discord.Interaction, button: ui.Button):
        """Go to last image."""
        self.current_index = len(self.images) - 1
        await self._update_message(interaction, "last")

    @ui.button(label="", emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="delete")
    async def delete_button(self, interaction: discord.Interaction, button: ui.Button):
        """Delete the message."""
        log.tree("Image View Deleted", [
            ("User", str(interaction.user)),
            ("User ID", str(interaction.user.id)),
            ("Query", self.query[:30]),
        ], emoji="🗑️")

        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except discord.HTTPException as e:
            log.tree("Image Delete Failed", [
                ("Error", str(e)[:50]),
            ], emoji="❌")
