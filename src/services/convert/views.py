"""
SyriaBot - Convert View
=======================

Interactive view for image/video conversion with customization options.
Supports both images (with live preview) and videos (settings only).

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import io
import discord
from discord import ui
from typing import Optional
from dataclasses import dataclass
from PIL import Image, ImageDraw

from src.core.colors import (
    COLOR_ERROR, COLOR_WARNING, COLOR_GOLD,
    EMOJI_WHITE, EMOJI_BLACK, EMOJI_RED, EMOJI_BLUE,
    EMOJI_GREEN, EMOJI_YELLOW, EMOJI_PURPLE, EMOJI_PINK,
    EMOJI_RENAME, EMOJI_SAVE, EMOJI_BLOCK,
)
from src.core.config import config
from src.core.logger import logger
from src.services.convert.service import convert_service
from src.utils.footer import set_footer
from src.utils.text import wrap_text, find_font, get_font


# =============================================================================
# Asset Storage Helper
# =============================================================================

async def upload_to_storage(bot, file_bytes: bytes, filename: str, context: str = "Convert") -> Optional[str]:
    """
    Upload file to asset storage channel for permanent URL.

    Args:
        bot: The bot instance
        file_bytes: Raw file bytes to upload
        filename: Filename for the upload
        context: Context for logging (e.g., "Convert", "Quote", "Image")

    Returns:
        Permanent CDN URL or None if storage not configured/failed
    """
    if not config.ASSET_STORAGE_CHANNEL_ID:
        logger.tree(f"{context} Asset Storage Skipped", [
            ("Reason", "SYRIA_ASSET_CH not configured"),
            ("Filename", filename),
        ], emoji="ℹ️")
        return None

    try:
        channel = bot.get_channel(config.ASSET_STORAGE_CHANNEL_ID)
        if not channel:
            logger.tree(f"{context} Asset Storage Channel Not Found", [
                ("Channel ID", str(config.ASSET_STORAGE_CHANNEL_ID)),
                ("Filename", filename),
            ], emoji="⚠️")
            return None

        # Upload to storage channel
        file = discord.File(fp=io.BytesIO(file_bytes), filename=filename)
        msg = await channel.send(file=file)

        if msg.attachments:
            url = msg.attachments[0].url
            logger.tree(f"{context} Asset Stored", [
                ("Filename", filename),
                ("Size", f"{len(file_bytes) / 1024:.1f} KB"),
                ("Message ID", str(msg.id)),
                ("URL", url[:80] + "..." if len(url) > 80 else url),
            ], emoji="💾")
            return url
        else:
            logger.tree(f"{context} Asset Storage No Attachment", [
                ("Filename", filename),
                ("Message ID", str(msg.id)),
                ("Reason", "Message sent but no attachment returned"),
            ], emoji="⚠️")
            return None

    except Exception as e:
        logger.error_tree(f"{context} Asset Storage Failed", e, [
            ("Filename", filename),
            ("Size", f"{len(file_bytes) / 1024:.1f} KB"),
            ("Channel ID", str(config.ASSET_STORAGE_CHANNEL_ID)),
        ])
        return None


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ConvertSettings:
    """Settings for image/video conversion."""
    text: str = ""
    bar_color: tuple[int, int, int] = (255, 255, 255)  # White
    text_color: tuple[int, int, int] = (0, 0, 0)  # Black

    # Color presets
    COLOR_PRESETS = {
        "white": ((255, 255, 255), (0, 0, 0)),      # White bar, black text
        "black": ((0, 0, 0), (255, 255, 255)),      # Black bar, white text
        "red": ((220, 53, 69), (255, 255, 255)),    # Red bar, white text
        "blue": ((0, 123, 255), (255, 255, 255)),   # Blue bar, white text
        "green": ((40, 167, 69), (255, 255, 255)),  # Green bar, white text
        "yellow": ((255, 193, 7), (0, 0, 0)),       # Yellow bar, black text
        "purple": ((111, 66, 193), (255, 255, 255)), # Purple bar, white text
        "pink": ((232, 62, 140), (255, 255, 255)),  # Pink bar, white text
    }

    def apply_preset(self, preset: str) -> None:
        """Apply a color preset."""
        if preset in self.COLOR_PRESETS:
            self.bar_color, self.text_color = self.COLOR_PRESETS[preset]

    def get_preset_name(self) -> str:
        """Get the name of current preset if matching."""
        for name, (bar, text) in self.COLOR_PRESETS.items():
            if self.bar_color == bar and self.text_color == text:
                return name.title()
        return "Custom"


# =============================================================================
# Text Input Modal (Unified)
# =============================================================================

class TextInputModal(ui.Modal, title="Edit Caption Text"):
    """Modal for editing caption text. Works with both image and video views."""

    text_input = ui.TextInput(
        label="Caption Text",
        placeholder="Enter the text for the caption bar...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=200,
    )

    def __init__(self, current_text: str, view, callback_method: str = "update_preview"):
        super().__init__()
        self.view = view
        self.callback_method = callback_method
        self.text_input.default = current_text

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle text input submission and call the appropriate update method."""
        self.view.settings.text = self.text_input.value.strip()
        callback = getattr(self.view, self.callback_method)
        await callback(interaction)


# =============================================================================
# Color Select Menu (Unified)
# =============================================================================

# Shared color options - defined once
COLOR_OPTIONS = [
    discord.SelectOption(label="White", value="white", description="White bar, black text", emoji=EMOJI_WHITE),
    discord.SelectOption(label="Black", value="black", description="Black bar, white text", emoji=EMOJI_BLACK),
    discord.SelectOption(label="Red", value="red", description="Red bar, white text", emoji=EMOJI_RED),
    discord.SelectOption(label="Blue", value="blue", description="Blue bar, white text", emoji=EMOJI_BLUE),
    discord.SelectOption(label="Green", value="green", description="Green bar, white text", emoji=EMOJI_GREEN),
    discord.SelectOption(label="Yellow", value="yellow", description="Yellow bar, black text", emoji=EMOJI_YELLOW),
    discord.SelectOption(label="Purple", value="purple", description="Purple bar, white text", emoji=EMOJI_PURPLE),
    discord.SelectOption(label="Pink", value="pink", description="Pink bar, white text", emoji=EMOJI_PINK),
]


class ColorSelect(ui.Select):
    """Dropdown for selecting bar color preset. Works with both image and video views."""

    def __init__(self, view, callback_method: str = "update_preview", custom_id: str = "color_select"):
        self.convert_view = view
        self.callback_method = callback_method
        super().__init__(
            placeholder="Bar Color",
            options=COLOR_OPTIONS.copy(),
            custom_id=custom_id,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle color selection and call the appropriate update method."""
        self.convert_view.settings.apply_preset(self.values[0])
        callback = getattr(self.convert_view, self.callback_method)
        await callback(interaction)


# =============================================================================
# Shared Image Processing Helper
# =============================================================================

def add_text_bar_to_image(
    image_data: bytes,
    text: str,
    bar_color: tuple[int, int, int],
    text_color: tuple[int, int, int],
    min_bar_height: int = 80,
    min_font_size: int = 24,
    min_text_padding: int = 20,
    min_vertical_padding: int = 10,
    max_dimension: int = 2000,
    handle_rgba: bool = True,
) -> bytes:
    """
    Add a text bar to an image. Shared by ConvertView and VideoConvertView.

    Args:
        image_data: Raw image bytes
        text: Caption text to add
        bar_color: RGB tuple for bar background
        text_color: RGB tuple for text
        min_bar_height: Minimum bar height in pixels
        min_font_size: Minimum font size
        min_text_padding: Minimum horizontal padding
        min_vertical_padding: Minimum vertical padding
        max_dimension: Max image dimension (resize if larger)
        handle_rgba: Whether to handle RGBA -> RGB conversion with bar color background

    Returns:
        PNG bytes of processed image
    """
    BAR_HEIGHT_RATIO = 0.20
    FONT_SIZE_RATIO = 0.70
    LINE_SPACING_RATIO = 0.25
    BAR_PADDING_RATIO = 0.10
    TEXT_PADDING_RATIO = 0.05

    img = Image.open(io.BytesIO(image_data))

    # Convert to RGB
    if handle_rgba and img.mode == "RGBA":
        background = Image.new("RGB", img.size, bar_color)
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if too large
    if max_dimension and (img.width > max_dimension or img.height > max_dimension):
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    # If no text, just return as PNG
    if not text:
        output = io.BytesIO()
        img.save(output, format="PNG", optimize=True)
        return output.getvalue()

    # Calculate bar height
    bar_height = max(min_bar_height, int(img.height * BAR_HEIGHT_RATIO))

    # Calculate font size
    font_size = max(min_font_size, int(bar_height * FONT_SIZE_RATIO))
    font_path = find_font()
    font = get_font(font_path, font_size)

    # Calculate padding
    text_padding = max(min_text_padding, int(img.width * TEXT_PADDING_RATIO))

    # Wrap text
    max_text_width = img.width - (text_padding * 2)
    lines = wrap_text(text, font, max_text_width)

    # Calculate text height
    line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
    line_spacing = int(line_height * LINE_SPACING_RATIO)
    total_text_height = (line_height * len(lines)) + (line_spacing * (len(lines) - 1))

    # Expand bar if needed
    vertical_padding = max(min_vertical_padding, int(bar_height * BAR_PADDING_RATIO))
    min_bar_for_text = total_text_height + (vertical_padding * 2)
    if min_bar_for_text > bar_height:
        bar_height = min_bar_for_text

    # Create new image with bar
    new_height = img.height + bar_height
    new_img = Image.new("RGB", (img.width, new_height), bar_color)
    new_img.paste(img, (0, bar_height))

    # Draw text
    draw = ImageDraw.Draw(new_img)
    start_y = (bar_height - total_text_height) // 2
    current_y = start_y

    for line in lines:
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        text_x = (img.width - line_width) // 2 - bbox[0]
        text_y = current_y - bbox[1]
        draw.text((text_x, text_y), line, font=font, fill=text_color)
        current_y += line_height + line_spacing

    output = io.BytesIO()
    new_img.save(output, format="PNG", optimize=True)
    return output.getvalue()


# =============================================================================
# Convert View (Images)
# =============================================================================

class ConvertView(ui.View):
    """Interactive view for image conversion with live preview."""

    def __init__(
        self,
        image_data: bytes,
        source_name: str,
        requester_id: int,
        initial_text: str = "",
        timeout: float = 300,  # 5 minutes
        original_message: Optional[discord.Message] = None,
        bot=None,
    ):
        super().__init__(timeout=timeout)
        self.image_data = image_data
        self.source_name = source_name
        self.requester_id = requester_id
        self.original_message = original_message  # For deletion if own message
        self.bot = bot  # For asset storage
        self.settings = ConvertSettings(text=initial_text)
        self.message: Optional[discord.Message] = None
        self._preview_bytes: Optional[bytes] = None

        # Add color select dropdown
        self.add_item(ColorSelect(self))

    def _get_image_info(self) -> dict:
        """Get image information."""
        img = Image.open(io.BytesIO(self.image_data))
        is_animated = getattr(img, 'is_animated', False)
        n_frames = getattr(img, 'n_frames', 1) if is_animated else 1
        return {
            "width": img.width,
            "height": img.height,
            "format": img.format or "Unknown",
            "mode": img.mode,
            "size_kb": len(self.image_data) / 1024,
            "is_animated": is_animated,
            "n_frames": n_frames,
        }

    def _process_preview(self) -> bytes:
        """Process image with current settings and return PNG bytes."""
        return add_text_bar_to_image(
            image_data=self.image_data,
            text=self.settings.text,
            bar_color=self.settings.bar_color,
            text_color=self.settings.text_color,
            min_bar_height=80,
            min_font_size=24,
            min_text_padding=20,
            min_vertical_padding=10,
            max_dimension=2000,
            handle_rgba=True,
        )

    def create_embed(self, preview_url: str = None) -> discord.Embed:
        """Create embed showing current settings and preview."""
        info = self._get_image_info()

        # Different title for animated GIFs
        if info.get("is_animated"):
            title = "Animated GIF Editor"
            description = f"Editing animated GIF ({info['n_frames']} frames)"
        else:
            title = "Image Converter"
            description = "Customize your image with the buttons below"

        embed = discord.Embed(
            title=title,
            description=description,
            color=COLOR_GOLD
        )

        # Current settings
        embed.add_field(
            name="Caption",
            value=f'"{self.settings.text}"' if self.settings.text else "*No text*",
            inline=True
        )
        embed.add_field(
            name="Color",
            value=self.settings.get_preset_name(),
            inline=True
        )

        set_footer(embed)

        return embed

    async def update_preview(self, interaction: discord.Interaction) -> None:
        """Update the preview image and embed."""
        await interaction.response.defer()

        self._preview_bytes = await asyncio.to_thread(self._process_preview)

        # Create new embed
        embed = self.create_embed()

        # Create preview file
        file = discord.File(
            fp=io.BytesIO(self._preview_bytes),
            filename="preview.png"
        )
        embed.set_image(url="attachment://preview.png")

        await interaction.message.edit(embed=embed, attachments=[file], view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the requester to use buttons."""
        if interaction.user.id != self.requester_id:
            embed = discord.Embed(description="⚠️ Only the person who started this can use these buttons", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                logger.tree("Image Convert Timeout Edit Failed", [
                    ("Source", self.source_name[:30]),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
        logger.tree("Image Convert View Expired", [
            ("Source", self.source_name[:30]),
            ("Requester ID", str(self.requester_id)),
        ], emoji="⏳")

    # ==========================================================================
    # Buttons - Row 1
    # ==========================================================================

    @ui.button(label="Edit", emoji=EMOJI_RENAME, style=discord.ButtonStyle.secondary, row=1)
    async def edit_text_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Open modal to edit caption text."""
        modal = TextInputModal(self.settings.text, self)
        await interaction.response.send_modal(modal)

    @ui.button(label="Save", emoji=EMOJI_SAVE, style=discord.ButtonStyle.secondary, row=1)
    async def download_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Download the final result."""
        await interaction.response.defer()

        # Disable all buttons while processing (gray out)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        # Get image info for animated check
        info = self._get_image_info()
        is_animated = info.get("is_animated", False)

        # Use convert_service - always outputs GIF
        result = await asyncio.to_thread(
            convert_service._process_image,
            self.image_data,
            self.settings.text,
            "top",
            self.settings.bar_color,
            self.settings.text_color,
        )
        if not result.success:
            # Re-enable buttons so user can retry
            for item in self.children:
                item.disabled = False
            await interaction.message.edit(view=self)

            embed = discord.Embed(description=f"❌ Failed to process image: {result.error}", color=COLOR_ERROR)
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.tree("Convert Image Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            return

        final_bytes = result.gif_bytes
        filename = "discord.gg-syria.gif"

        # Upload to asset storage for permanent URL (prevents dead links when VC chats are deleted)
        storage_url = None
        if self.bot:
            storage_url = await upload_to_storage(self.bot, final_bytes, filename, "Image Convert")

        # Send result with user ping
        if storage_url:
            # Send the permanent URL so it survives channel deletion
            await interaction.followup.send(content=f"{interaction.user.mention}\n{storage_url}")
        else:
            # Fallback to direct upload if storage not configured
            file = discord.File(fp=io.BytesIO(final_bytes), filename=filename)
            await interaction.followup.send(content=interaction.user.mention, file=file)

        # Delete the editor embed
        try:
            await interaction.message.delete()
        except Exception as e:
            logger.tree("Editor Delete Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Delete original message ONLY if it's the user's own message
        if self.original_message and self.original_message.author.id == self.requester_id:
            try:
                await self.original_message.delete()
            except Exception as e:
                logger.tree("Original Message Delete Failed", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        logger.tree("Convert Download", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("File", filename),
            ("Size", f"{len(final_bytes) / 1024:.1f} KB"),
            ("Text", self.settings.text[:30] if self.settings.text else "(none)"),
            ("Color", self.settings.get_preset_name()),
            ("Animated", "Yes" if is_animated else "No"),
        ], emoji="✅")

        self.stop()

    @ui.button(label="Cancel", emoji=EMOJI_BLOCK, style=discord.ButtonStyle.secondary, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Cancel and delete the editor."""
        await interaction.response.defer()

        logger.tree("Convert Cancelled", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Source", self.source_name[:30]),
        ], emoji="X")

        try:
            await interaction.message.delete()
        except Exception as e:
            logger.tree("Cancel Delete Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
        self.stop()


# =============================================================================
# Video Convert View
# =============================================================================

class VideoConvertView(ui.View):
    """Interactive view for video-to-GIF conversion with thumbnail preview."""

    def __init__(
        self,
        video_data: bytes,
        source_name: str,
        requester_id: int,
        initial_text: str = "",
        thumbnail_bytes: Optional[bytes] = None,
        timeout: float = 300,  # 5 minutes
        original_message: Optional[discord.Message] = None,
        bot=None,
    ):
        super().__init__(timeout=timeout)
        self.video_data = video_data
        self.source_name = source_name
        self.requester_id = requester_id
        self.thumbnail_bytes = thumbnail_bytes
        self.original_message = original_message  # For deletion if own message
        self.bot = bot  # For asset storage
        self.settings = ConvertSettings(text=initial_text)
        self.message: Optional[discord.Message] = None
        self._processing = False

        # Add color select dropdown
        self.add_item(ColorSelect(self, "update_embed", "video_color_select"))

    def _generate_preview_with_text(self) -> Optional[bytes]:
        """Generate preview thumbnail with text bar overlay."""
        if not self.thumbnail_bytes:
            return None

        try:
            return add_text_bar_to_image(
                image_data=self.thumbnail_bytes,
                text=self.settings.text,
                bar_color=self.settings.bar_color,
                text_color=self.settings.text_color,
                min_bar_height=40,
                min_font_size=16,
                min_text_padding=10,
                min_vertical_padding=5,
                max_dimension=0,  # No resize for thumbnails
                handle_rgba=False,
            )
        except Exception as e:
            logger.tree("Video Preview Generation Failed", [
                ("Source", self.source_name[:30]),
                ("Error", str(e)[:50]),
                ("Fallback", "Using original thumbnail"),
            ], emoji="⚠️")
            return self.thumbnail_bytes

    def create_embed(self) -> discord.Embed:
        """Create embed showing current settings."""
        embed = discord.Embed(
            title="Video to GIF Converter",
            description="Configure your GIF settings below, then click Save",
            color=COLOR_GOLD
        )

        # Current settings
        embed.add_field(
            name="Caption",
            value=f'"{self.settings.text}"' if self.settings.text else "*No text*",
            inline=True
        )
        embed.add_field(
            name="Color",
            value=self.settings.get_preset_name(),
            inline=True
        )

        set_footer(embed)

        return embed

    async def update_embed(self, interaction: discord.Interaction) -> None:
        """Update the embed with current settings and regenerate preview."""
        await interaction.response.defer()

        embed = self.create_embed()

        # Regenerate preview with text overlay
        preview_bytes = await asyncio.to_thread(self._generate_preview_with_text)

        if preview_bytes:
            file = discord.File(fp=io.BytesIO(preview_bytes), filename="preview.png")
            embed.set_image(url="attachment://preview.png")
            await interaction.message.edit(embed=embed, attachments=[file], view=self)
        else:
            await interaction.message.edit(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the requester to use buttons."""
        if interaction.user.id != self.requester_id:
            embed = discord.Embed(description="⚠️ Only the person who started this can use these buttons", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        if self._processing:
            embed = discord.Embed(description="⏳ Already processing video, please wait...", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                logger.tree("Video Convert Timeout Edit Failed", [
                    ("Source", self.source_name[:30]),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
        logger.tree("Video Convert View Expired", [
            ("Source", self.source_name[:30]),
            ("Requester ID", str(self.requester_id)),
        ], emoji="⏳")

    # ==========================================================================
    # Buttons - Row 1
    # ==========================================================================

    @ui.button(label="Edit", emoji=EMOJI_RENAME, style=discord.ButtonStyle.secondary, row=1)
    async def edit_text_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Open modal to edit caption text."""
        modal = TextInputModal(self.settings.text, self, "update_embed")
        await interaction.response.send_modal(modal)

    @ui.button(label="Save", emoji=EMOJI_SAVE, style=discord.ButtonStyle.secondary, row=1)
    async def convert_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Convert the video to GIF."""
        self._processing = True

        await interaction.response.defer()

        # Disable all buttons and show processing status
        for item in self.children:
            item.disabled = True

        processing_embed = discord.Embed(
            title="⏳ Converting Video...",
            description="Please wait while your video is being converted to GIF.\nThis may take up to 30 seconds.",
            color=COLOR_GOLD
        )
        processing_embed.add_field(name="Text", value=f"`{self.settings.text or '(none)'}`", inline=True)
        processing_embed.add_field(name="Color", value=self.settings.get_preset_name(), inline=True)
        set_footer(processing_embed)
        await interaction.message.edit(embed=processing_embed, view=self)

        # Convert video
        result = await convert_service.convert_video_to_gif(
            video_data=self.video_data,
            text=self.settings.text,
            position="top",
            bar_color=self.settings.bar_color,
            text_color=self.settings.text_color,
        )

        if not result.success:
            # Re-enable buttons so user can retry
            self._processing = False
            for item in self.children:
                item.disabled = False

            embed = discord.Embed(
                title="Conversion Failed",
                description=f"{result.error or 'Unknown error occurred'}\n\n*You can try again with different settings.*",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.message.edit(embed=embed, view=self)

            logger.tree("Video Convert Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            return

        # Success - send the GIF
        filename = "discord.gg-syria.gif"

        # Upload to asset storage for permanent URL (prevents dead links when VC chats are deleted)
        storage_url = None
        if self.bot:
            storage_url = await upload_to_storage(self.bot, result.gif_bytes, filename, "Video Convert")

        # Send result with user ping
        if storage_url:
            # Send the permanent URL so it survives channel deletion
            await interaction.followup.send(content=f"{interaction.user.mention}\n{storage_url}")
        else:
            # Fallback to direct upload if storage not configured
            file = discord.File(fp=io.BytesIO(result.gif_bytes), filename=filename)
            await interaction.followup.send(content=interaction.user.mention, file=file)

        # Delete the editor embed
        try:
            await interaction.message.delete()
        except Exception as e:
            logger.tree("Video Editor Delete Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Delete original message ONLY if it's the user's own message
        if self.original_message and self.original_message.author.id == self.requester_id:
            try:
                await self.original_message.delete()
            except Exception as e:
                logger.tree("Video Original Delete Failed", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        logger.tree("Video Convert Complete", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("File", filename),
            ("Size", f"{len(result.gif_bytes) / 1024:.1f} KB"),
            ("Text", self.settings.text[:30] if self.settings.text else "(none)"),
            ("Color", self.settings.get_preset_name()),
        ], emoji="✅")

        self.stop()

    @ui.button(label="Cancel", emoji=EMOJI_BLOCK, style=discord.ButtonStyle.secondary, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Cancel and delete the editor."""
        await interaction.response.defer()

        logger.tree("Video Convert Cancelled", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Source", self.source_name[:30]),
        ], emoji="X")

        try:
            await interaction.message.delete()
        except Exception as e:
            logger.tree("Video Cancel Delete Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
        self.stop()


# =============================================================================
# Helper Function
# =============================================================================

async def start_convert_editor(
    interaction_or_message,
    image_data: bytes,
    source_name: str,
    initial_text: str = "",
    is_video: bool = False,
    original_message: Optional[discord.Message] = None,
    bot=None,
) -> None:
    """
    Start the interactive convert editor.

    Args:
        interaction_or_message: Discord interaction or message to respond to
        image_data: Raw image/video bytes
        source_name: Original filename
        initial_text: Initial caption text
        is_video: Whether the input is a video file
        original_message: Original message with the media (for deletion if own message)
        bot: Bot instance for asset storage
    """
    # Determine requester ID based on type
    if isinstance(interaction_or_message, discord.Interaction):
        requester_id = interaction_or_message.user.id
        is_interaction = True
        # Get bot from interaction if not provided
        if not bot:
            bot = interaction_or_message.client
    else:
        requester_id = interaction_or_message.author.id
        is_interaction = False
        # Get bot from message if not provided
        if not bot and hasattr(interaction_or_message, '_state'):
            bot = interaction_or_message._state._get_client()

    if is_video:
        # Get video duration and preview in a single batched operation
        # (writes video to disk once instead of 2-3 times)
        duration, preview_strip_bytes = await asyncio.to_thread(
            convert_service.get_video_preview_data, image_data
        )

        # Video: Use VideoConvertView with preview strip
        view = VideoConvertView(
            video_data=image_data,
            source_name=source_name,
            requester_id=requester_id,
            initial_text=initial_text,
            thumbnail_bytes=preview_strip_bytes,
            original_message=original_message,
            bot=bot,
        )

        embed = view.create_embed()

        # Send response with preview strip if available
        if preview_strip_bytes:
            file = discord.File(fp=io.BytesIO(preview_strip_bytes), filename="preview.png")
            embed.set_image(url="attachment://preview.png")
            if is_interaction:
                await interaction_or_message.followup.send(embed=embed, file=file, view=view)
            else:
                msg = await interaction_or_message.reply(embed=embed, file=file, view=view, mention_author=False)
                view.message = msg
        else:
            # Add note about missing preview
            embed.add_field(name="Preview", value="*Could not generate preview thumbnail*", inline=False)
            logger.tree("Video Preview Failed", [
                ("Source", source_name[:30]),
            ], emoji="⚠️")
            if is_interaction:
                await interaction_or_message.followup.send(embed=embed, view=view)
            else:
                msg = await interaction_or_message.reply(embed=embed, view=view, mention_author=False)
                view.message = msg

        user = interaction_or_message.user if is_interaction else interaction_or_message.author
        logger.tree("Video Convert Editor Started", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Source", source_name[:30]),
            ("Initial Text", initial_text[:30] if initial_text else "(none)"),
            ("Preview Strip", "Yes" if preview_strip_bytes else "No"),
        ], emoji="🎬")

    else:
        # Image: Use ConvertView with live preview
        view = ConvertView(
            image_data=image_data,
            source_name=source_name,
            requester_id=requester_id,
            initial_text=initial_text,
            original_message=original_message,
            bot=bot,
        )

        # Generate initial preview
        preview_bytes = await asyncio.to_thread(view._process_preview)
        view._preview_bytes = preview_bytes

        # Create embed and file
        embed = view.create_embed()
        file = discord.File(fp=io.BytesIO(preview_bytes), filename="preview.png")
        embed.set_image(url="attachment://preview.png")

        # Send response
        if is_interaction:
            await interaction_or_message.followup.send(embed=embed, file=file, view=view)
        else:
            msg = await interaction_or_message.reply(embed=embed, file=file, view=view, mention_author=False)
            view.message = msg

        user = interaction_or_message.user if is_interaction else interaction_or_message.author
        logger.tree("Convert Editor Started", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Source", source_name[:30]),
            ("Initial Text", initial_text[:30] if initial_text else "(none)"),
        ], emoji="🖼️")
