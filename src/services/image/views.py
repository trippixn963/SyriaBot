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
from discord.ext import commands
from typing import Optional, Tuple

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_SYRIA_GOLD, EMOJI_SAVE, EMOJI_DELETE
from src.services.image.service import ImageResult
from src.utils.footer import set_footer
from src.utils.http import http_session


async def upload_to_storage(bot: commands.Bot, file_bytes: bytes, filename: str) -> Optional[str]:
    """Upload file to asset storage channel for permanent URL."""
    if not config.ASSET_STORAGE_CHANNEL_ID:
        log.tree("Image Asset Storage Skipped", [
            ("Reason", "SYRIA_ASSET_CH not configured"),
            ("Filename", filename),
        ], emoji="ℹ️")
        return None

    try:
        channel = bot.get_channel(config.ASSET_STORAGE_CHANNEL_ID)
        if not channel:
            log.tree("Image Asset Storage Channel Not Found", [
                ("Channel ID", str(config.ASSET_STORAGE_CHANNEL_ID)),
                ("Filename", filename),
            ], emoji="⚠️")
            return None

        file = discord.File(fp=io.BytesIO(file_bytes), filename=filename)
        msg = await channel.send(file=file)

        if msg.attachments:
            url = msg.attachments[0].url
            log.tree("Image Asset Stored", [
                ("Filename", filename),
                ("Size", f"{len(file_bytes) / 1024:.1f} KB"),
                ("Message ID", str(msg.id)),
                ("URL", url[:80] + "..." if len(url) > 80 else url),
            ], emoji="💾")
            return url
        else:
            log.tree("Image Asset Storage No Attachment", [
                ("Filename", filename),
                ("Message ID", str(msg.id)),
                ("Reason", "Message sent but no attachment returned"),
            ], emoji="⚠️")
            return None

    except Exception as e:
        log.error_tree("Image Asset Storage Failed", e, [
            ("Filename", filename),
            ("Size", f"{len(file_bytes) / 1024:.1f} KB"),
            ("Channel ID", str(config.ASSET_STORAGE_CHANNEL_ID)),
        ])
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
        bot: Optional[commands.Bot] = None,
    ) -> None:
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

    def _update_buttons(self) -> None:
        """Update button disabled states based on current index."""
        # Previous button
        self.prev_button.disabled = self.current_index == 0
        # Next button
        self.next_button.disabled = self.current_index >= len(self.images) - 1

    def _get_file_extension(self, url: str, content_type: Optional[str] = None) -> str:
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

    async def _try_fetch_url(self, url: str) -> Tuple[Optional[bytes], str]:
        """
        Try to fetch an image from a URL with browser-like headers.
        Returns (image_bytes, content_type) or (None, "") on failure.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with http_session.session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    log.tree("Image Fetch HTTP Error", [
                        ("URL", url[:60] + "..." if len(url) > 60 else url),
                        ("Status", str(response.status)),
                    ], emoji="⚠️")
                    return None, ""

                content_type = response.headers.get("Content-Type", "")

                # Verify it's actually an image
                if content_type and not content_type.startswith("image/"):
                    log.tree("Image Fetch Invalid Content-Type", [
                        ("URL", url[:60] + "..." if len(url) > 60 else url),
                        ("Content-Type", content_type),
                    ], emoji="⚠️")
                    return None, ""

                image_bytes = await response.read()

                # Check minimum size (avoid placeholder images)
                if len(image_bytes) < 1000:
                    log.tree("Image Fetch Too Small", [
                        ("URL", url[:60] + "..." if len(url) > 60 else url),
                        ("Size", f"{len(image_bytes)} bytes"),
                        ("Min Required", "1000 bytes"),
                    ], emoji="⚠️")
                    return None, ""

                return image_bytes, content_type

        except aiohttp.ClientError as e:
            log.tree("Image Fetch Client Error", [
                ("URL", url[:60] + "..." if len(url) > 60 else url),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
            return None, ""
        except TimeoutError:
            log.tree("Image Fetch Timeout", [
                ("URL", url[:60] + "..." if len(url) > 60 else url),
                ("Timeout", "10s"),
            ], emoji="⏳")
            return None, ""
        except Exception as e:
            log.error_tree("Image Fetch Unexpected Error", e, [
                ("URL", url[:60] + "..." if len(url) > 60 else url),
            ])
            return None, ""

    async def fetch_current_image(self) -> Tuple[Optional[bytes], str]:
        """
        Download the current image and cache it.
        Tries main URL first, then thumbnail as fallback.
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

        # Try main URL first
        image_bytes, content_type = await self._try_fetch_url(image.url)

        if image_bytes:
            ext = self._get_file_extension(image.url, content_type)
            self._cached_image = image_bytes
            self._cached_index = self.current_index

            log.tree("Image Fetched", [
                ("Size", f"{len(image_bytes) // 1024}KB"),
                ("Type", ext),
                ("Source", "Main URL"),
            ], emoji="📥")
            return image_bytes, ext

        # Fallback to Google's thumbnail (always works)
        if image.thumbnail_url:
            log.tree("Image Main URL Failed, Trying Thumbnail", [
                ("Main URL", image.url[:50]),
                ("Thumbnail", image.thumbnail_url[:50]),
            ], emoji="🔄")

            image_bytes, content_type = await self._try_fetch_url(image.thumbnail_url)

            if image_bytes:
                ext = self._get_file_extension(image.thumbnail_url, content_type)
                self._cached_image = image_bytes
                self._cached_index = self.current_index

                log.tree("Image Fetched From Thumbnail", [
                    ("Size", f"{len(image_bytes) // 1024}KB"),
                    ("Type", ext),
                    ("Source", "Google Thumbnail"),
                ], emoji="📥")
                return image_bytes, ext

        log.tree("Image Fetch Failed", [
            ("URL", image.url[:60]),
            ("Thumbnail", "Also failed" if image.thumbnail_url else "None"),
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
            # Prefer thumbnail URL for fallback (Google-hosted, always works)
            embed.set_image(url=image.thumbnail_url if image.thumbnail_url else image.url)

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
        Always downloads - if current image fails, tries next images until one works.
        Returns (embed, file) - file is None only if ALL images fail.
        """
        # Try current image first
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

        # Current image failed - try remaining images until one works
        original_index = self.current_index
        tried_indices = {self.current_index}

        while len(tried_indices) < len(self.images):
            # Move to next image
            self.current_index = (self.current_index + 1) % len(self.images)

            if self.current_index in tried_indices:
                continue

            tried_indices.add(self.current_index)

            log.tree("Image Failed, Trying Next", [
                ("Failed Index", str(original_index + 1)),
                ("Trying Index", str(self.current_index + 1)),
                ("Total Images", str(len(self.images))),
            ], emoji="🔄")

            # Clear cache to force fresh fetch
            self._cached_image = None
            self._cached_index = -1

            image_bytes, ext = await self.fetch_current_image()

            if image_bytes:
                file = discord.File(
                    fp=io.BytesIO(image_bytes),
                    filename=f"image.{ext}"
                )
                embed = self.create_embed(use_attachment=True, extension=ext)
                self._update_buttons()

                log.tree("Embed Created After Skip", [
                    ("Original Index", str(original_index + 1)),
                    ("Working Index", str(self.current_index + 1)),
                    ("Skipped", str(len(tried_indices) - 1)),
                    ("Size", f"{len(image_bytes) // 1024}KB"),
                ], emoji="📎")
                return embed, file

        # ALL images failed
        log.tree("All Images Failed", [
            ("Total Tried", str(len(tried_indices))),
            ("Query", self.query[:30]),
        ], emoji="❌")

        # Reset to original index and return error embed
        self.current_index = original_index
        embed = discord.Embed(
            title="Failed to Load Images",
            description=f"All {len(self.images)} images failed to load.\nTry a different search query.",
            color=COLOR_SYRIA_GOLD
        )
        set_footer(embed)
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
            if isinstance(item, ui.Button):
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

    async def _update_message(self, interaction: discord.Interaction, nav_action: str) -> None:
        """Update the message with new image (always downloaded and attached)."""
        await interaction.response.defer()

        self._update_buttons()
        embed, file = await self.create_embed_with_file()

        try:
            if file:
                await interaction.message.edit(embed=embed, attachments=[file], view=self)
                log.tree("Image Navigation", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Action", nav_action),
                    ("Position", f"{self.current_index + 1}/{len(self.images)}"),
                ], emoji="🔄")
            else:
                # All images failed - show error
                await interaction.message.edit(embed=embed, attachments=[], view=self)
                log.tree("Image Navigation All Failed", [
                    ("User", f"{interaction.user.name}"),
                    ("Action", nav_action),
                ], emoji="❌")
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
