"""
SyriaBot - Image View
=====================

Interactive view for browsing image search results.
Downloads and attaches images for reliable display.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import io
import aiohttp
import discord
from discord import ui
from typing import Optional, Tuple

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_SYRIA_GOLD, EMOJI_SAVE, EMOJI_DELETE
from src.services.image.service import ImageResult
from src.utils.footer import set_footer
from src.utils.http import http_session


async def upload_to_storage(bot, file_bytes: bytes, filename: str) -> Optional[str]:
    """Upload file to asset storage channel for permanent URL."""
    if not config.ASSET_STORAGE_CHANNEL_ID:
        return None

    try:
        channel = bot.get_channel(config.ASSET_STORAGE_CHANNEL_ID)
        if not channel:
            return None

        file = discord.File(fp=io.BytesIO(file_bytes), filename=filename)
        msg = await channel.send(file=file)

        if msg.attachments:
            return msg.attachments[0].url

    except Exception as e:
        log.tree("Image Asset Storage Failed", [
            ("Error", str(e)[:50]),
        ], emoji="⚠️")

    return None


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
        bot=None,
    ):
        super().__init__(timeout=timeout)
        self.images = images
        self.query = query
        self.requester_id = requester_id
        self.bot = bot
        self.current_index = 0
        self.message: Optional[discord.Message] = None

        # Cache for current image (avoids re-downloading on save)
        self._cached_image: Optional[bytes] = None
        self._cached_index: int = -1

        # Update button states
        self._update_buttons()

        log.tree("Image View Created", [
            ("Query", query[:50]),
            ("Images", str(len(images))),
            ("Requester ID", str(requester_id)),
        ], emoji="🖼️")

    def _update_buttons(self):
        """Update button disabled states based on current index."""
        # Previous button
        self.prev_button.disabled = self.current_index == 0
        # Next button
        self.next_button.disabled = self.current_index >= len(self.images) - 1

    def _get_file_extension(self, url: str, content_type: str = None) -> str:
        """Determine file extension from URL or content type."""
        url_lower = url.lower()
        if ".gif" in url_lower:
            return "gif"
        elif ".png" in url_lower:
            return "png"
        elif ".webp" in url_lower:
            return "webp"
        elif ".jpg" in url_lower or ".jpeg" in url_lower:
            return "jpg"
        elif content_type:
            if "gif" in content_type:
                return "gif"
            elif "png" in content_type:
                return "png"
            elif "webp" in content_type:
                return "webp"
        return "jpg"  # Default to jpg

    async def fetch_current_image(self) -> Tuple[Optional[bytes], str]:
        """
        Download the current image and cache it.
        Returns (image_bytes, extension) or (None, "") on failure.
        """
        if not self.images:
            return None, ""

        # Return cached image if same index
        if self._cached_index == self.current_index and self._cached_image:
            ext = self._get_file_extension(self.images[self.current_index].url)
            log.tree("Image From Cache", [
                ("Size", f"{len(self._cached_image) // 1024}KB"),
                ("Index", str(self.current_index)),
            ], emoji="💾")
            return self._cached_image, ext

        image = self.images[self.current_index]

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with http_session.session.get(image.url, timeout=timeout) as response:
                if response.status != 200:
                    log.tree("Image Fetch Failed", [
                        ("URL", image.url[:60]),
                        ("Status", str(response.status)),
                    ], emoji="❌")
                    return None, ""

                content_type = response.headers.get("Content-Type", "")
                image_bytes = await response.read()
                ext = self._get_file_extension(image.url, content_type)

                # Cache the image
                self._cached_image = image_bytes
                self._cached_index = self.current_index

                log.tree("Image Fetched", [
                    ("Size", f"{len(image_bytes) // 1024}KB"),
                    ("Type", ext),
                    ("Cached", "Yes"),
                ], emoji="📥")

                return image_bytes, ext

        except Exception as e:
            log.tree("Image Fetch Error", [
                ("URL", image.url[:60]),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return None, ""

    def create_embed(self, use_attachment: bool = False, extension: str = "jpg") -> discord.Embed:
        """
        Create embed for current image.

        Args:
            use_attachment: If True, reference attachment instead of URL
            extension: File extension for attachment filename
        """
        if not self.images:
            embed = discord.Embed(
                title="No Images Found",
                description=f"No results for: **{self.query}**",
                color=COLOR_SYRIA_GOLD
            )
            set_footer(embed)
            return embed

        image = self.images[self.current_index]

        embed = discord.Embed(
            title=image.title[:256] if len(image.title) > 256 else image.title,
            url=image.source_url,
            color=COLOR_SYRIA_GREEN
        )

        # Use attachment reference or direct URL
        if use_attachment:
            embed.set_image(url=f"attachment://image.{extension}")
        else:
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

        # File type from extension or URL
        ext = extension.upper() if use_attachment else self._get_file_extension(image.url).upper()
        embed.add_field(name="Type", value=ext, inline=True)

        set_footer(embed)

        return embed

    async def create_embed_with_file(self) -> Tuple[discord.Embed, Optional[discord.File]]:
        """
        Create embed with downloaded image as attachment.
        Returns (embed, file) - file may be None if download fails.
        """
        image_bytes, ext = await self.fetch_current_image()

        if image_bytes:
            file = discord.File(
                fp=io.BytesIO(image_bytes),
                filename=f"image.{ext}"
            )
            embed = self.create_embed(use_attachment=True, extension=ext)
            log.tree("Embed Created With Attachment", [
                ("Position", f"{self.current_index + 1}/{len(self.images)}"),
                ("Size", f"{len(image_bytes) // 1024}KB"),
                ("Type", ext.upper()),
            ], emoji="📎")
            return embed, file
        else:
            # Fallback to URL-based embed if download fails
            embed = self.create_embed(use_attachment=False)
            log.tree("Embed Created With URL Fallback", [
                ("Position", f"{self.current_index + 1}/{len(self.images)}"),
                ("Reason", "Image fetch failed"),
            ], emoji="🔗")
            return embed, None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the requester to use buttons."""
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who searched can use these buttons.",
                ephemeral=True
            )
            log.tree("Image View Unauthorized", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Requester ID", str(self.requester_id)),
            ], emoji="⚠️")
            return False
        return True

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                log.tree("Image View Timeout", [
                    ("Query", self.query[:50]),
                    ("Position", f"{self.current_index + 1}/{len(self.images)}"),
                    ("Buttons", "Disabled"),
                ], emoji="⏳")
            except discord.NotFound:
                log.tree("Image View Timeout", [
                    ("Query", self.query[:50]),
                    ("Reason", "Message already deleted"),
                ], emoji="⏳")
            except discord.HTTPException as e:
                log.tree("Image View Timeout Failed", [
                    ("Query", self.query[:50]),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
        else:
            log.tree("Image View Timeout", [
                ("Query", self.query[:50]),
                ("Reason", "No message reference"),
            ], emoji="⏳")

    async def _update_message(self, interaction: discord.Interaction, nav_action: str):
        """Update the message with new image (downloaded and attached)."""
        await interaction.response.defer()

        self._update_buttons()
        embed, file = await self.create_embed_with_file()

        try:
            if file:
                # Edit with new attachment
                await interaction.message.edit(embed=embed, attachments=[file], view=self)
            else:
                # Fallback to URL-based (no attachment)
                await interaction.message.edit(embed=embed, view=self)

            log.tree("Image Navigation", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Action", nav_action),
                ("Position", f"{self.current_index + 1}/{len(self.images)}"),
                ("Attached", "Yes" if file else "No (fallback)"),
            ], emoji="🔄")
        except discord.HTTPException as e:
            log.tree("Image Navigation Failed", [
                ("User", f"{interaction.user.name}"),
                ("Action", nav_action),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    @ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Go to previous image."""
        log.tree("Image Nav Previous", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("From", str(self.current_index + 1)),
            ("To", str(max(1, self.current_index))),
        ], emoji="⬅️")
        if self.current_index > 0:
            self.current_index -= 1
        await self._update_message(interaction, "prev")

    @ui.button(label="", emoji=discord.PartialEmoji.from_str(EMOJI_SAVE), style=discord.ButtonStyle.secondary, custom_id="download")
    async def download_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Save image using cached data, send as public .gif, delete original."""
        await interaction.response.defer()

        log.tree("Image Save Started", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Query", self.query[:30]),
            ("Position", f"{self.current_index + 1}/{len(self.images)}"),
        ], emoji="📥")

        # Use cached image (already downloaded for display)
        image_bytes, _ = await self.fetch_current_image()

        if not image_bytes:
            await interaction.followup.send("Failed to download image.", ephemeral=True)
            log.tree("Image Save Failed", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Fetch failed"),
            ], emoji="❌")
            return

        try:
            filename = "discord.gg-syria.gif"

            # Upload to asset storage for permanent URL
            storage_url = None
            if self.bot:
                storage_url = await upload_to_storage(self.bot, image_bytes, filename)

            if storage_url:
                await interaction.followup.send(storage_url)
            else:
                # Fallback to direct upload
                file = discord.File(
                    fp=io.BytesIO(image_bytes),
                    filename=filename
                )
                await interaction.followup.send(file=file)

            # Delete original message
            if self.message:
                try:
                    await self.message.delete()
                except discord.NotFound:
                    log.tree("Image Original Delete", [
                        ("Reason", "Message already deleted"),
                    ], emoji="ℹ️")

            log.tree("Image Saved", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Size", f"{len(image_bytes) // 1024}KB"),
                ("Source", "Cache" if self._cached_index == self.current_index else "Fresh"),
                ("Original", "Deleted"),
            ], emoji="✅")

        except Exception as e:
            log.tree("Image Save Failed", [
                ("User", f"{interaction.user.name}"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            await interaction.followup.send("Failed to save image.", ephemeral=True)

    @ui.button(label="", emoji=discord.PartialEmoji.from_str(EMOJI_DELETE), style=discord.ButtonStyle.secondary, custom_id="delete")
    async def delete_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Delete the message."""
        await interaction.response.defer()
        try:
            await interaction.message.delete()
            log.tree("Image View Deleted", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Query", self.query[:30]),
                ("Position", f"{self.current_index + 1}/{len(self.images)}"),
            ], emoji="🗑️")
        except discord.NotFound:
            log.tree("Image Delete Skipped", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "Message already deleted"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            log.tree("Image Delete Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    @ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Go to next image."""
        log.tree("Image Nav Next", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("From", str(self.current_index + 1)),
            ("To", str(min(len(self.images), self.current_index + 2))),
        ], emoji="➡️")
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
        await self._update_message(interaction, "next")
