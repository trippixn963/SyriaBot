"""
SyriaBot - Convert View
=======================

Interactive view for image/video conversion with customization options.
Supports both images (with live preview) and videos (settings only).

Author: Unknown
"""

import asyncio
import io
import discord
from discord import ui
from typing import Optional
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont

from src.core.colors import (
    COLOR_ERROR, COLOR_WARNING, COLOR_GOLD,
    EMOJI_WHITE, EMOJI_BLACK, EMOJI_RED, EMOJI_BLUE,
    EMOJI_GREEN, EMOJI_YELLOW, EMOJI_PURPLE, EMOJI_PINK,
)
from src.core.constants import FONT_PATHS
from src.core.logger import log
from src.services.convert_service import convert_service
from src.utils.footer import set_footer
from src.utils.text import wrap_text


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
# Text Input Modal
# =============================================================================

class TextInputModal(ui.Modal, title="Edit Caption Text"):
    """Modal for editing caption text."""

    text_input = ui.TextInput(
        label="Caption Text",
        placeholder="Enter the text for the caption bar...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=200,
    )

    def __init__(self, current_text: str, view: "ConvertView"):
        super().__init__()
        self.view = view
        self.text_input.default = current_text

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle text input submission and update preview."""
        self.view.settings.text = self.text_input.value.strip()
        await self.view.update_preview(interaction)


class VideoTextInputModal(ui.Modal, title="Edit Caption Text"):
    """Modal for editing caption text (video version - no live preview)."""

    text_input = ui.TextInput(
        label="Caption Text",
        placeholder="Enter the text for the caption bar...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=200,
    )

    def __init__(self, current_text: str, view: "VideoConvertView"):
        super().__init__()
        self.view = view
        self.text_input.default = current_text

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Handle text input submission and update embed."""
        self.view.settings.text = self.text_input.value.strip()
        await self.view.update_embed(interaction)


# =============================================================================
# Color Select Menu
# =============================================================================

class ColorSelect(ui.Select):
    """Dropdown for selecting bar color preset."""

    def __init__(self, view: "ConvertView"):
        self.convert_view = view
        options = [
            discord.SelectOption(label="White", value="white", description="White bar, black text", emoji=EMOJI_WHITE),
            discord.SelectOption(label="Black", value="black", description="Black bar, white text", emoji=EMOJI_BLACK),
            discord.SelectOption(label="Red", value="red", description="Red bar, white text", emoji=EMOJI_RED),
            discord.SelectOption(label="Blue", value="blue", description="Blue bar, white text", emoji=EMOJI_BLUE),
            discord.SelectOption(label="Green", value="green", description="Green bar, white text", emoji=EMOJI_GREEN),
            discord.SelectOption(label="Yellow", value="yellow", description="Yellow bar, black text", emoji=EMOJI_YELLOW),
            discord.SelectOption(label="Purple", value="purple", description="Purple bar, white text", emoji=EMOJI_PURPLE),
            discord.SelectOption(label="Pink", value="pink", description="Pink bar, white text", emoji=EMOJI_PINK),
        ]
        super().__init__(
            placeholder="Bar Color",
            options=options,
            custom_id="color_select",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle color selection and update image preview."""
        self.convert_view.settings.apply_preset(self.values[0])
        await self.convert_view.update_preview(interaction)


class VideoColorSelect(ui.Select):
    """Dropdown for selecting bar color preset (video version)."""

    def __init__(self, view: "VideoConvertView"):
        self.convert_view = view
        options = [
            discord.SelectOption(label="White", value="white", description="White bar, black text", emoji=EMOJI_WHITE),
            discord.SelectOption(label="Black", value="black", description="Black bar, white text", emoji=EMOJI_BLACK),
            discord.SelectOption(label="Red", value="red", description="Red bar, white text", emoji=EMOJI_RED),
            discord.SelectOption(label="Blue", value="blue", description="Blue bar, white text", emoji=EMOJI_BLUE),
            discord.SelectOption(label="Green", value="green", description="Green bar, white text", emoji=EMOJI_GREEN),
            discord.SelectOption(label="Yellow", value="yellow", description="Yellow bar, black text", emoji=EMOJI_YELLOW),
            discord.SelectOption(label="Purple", value="purple", description="Purple bar, white text", emoji=EMOJI_PURPLE),
            discord.SelectOption(label="Pink", value="pink", description="Pink bar, white text", emoji=EMOJI_PINK),
        ]
        super().__init__(
            placeholder="Bar Color",
            options=options,
            custom_id="video_color_select",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle color selection and update video embed."""
        self.convert_view.settings.apply_preset(self.values[0])
        await self.convert_view.update_embed(interaction)


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
    ):
        super().__init__(timeout=timeout)
        self.image_data = image_data
        self.source_name = source_name
        self.requester_id = requester_id
        self.original_message = original_message  # For deletion if own message
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
        # Constants - DYNAMIC sizing like NotSoBot
        BAR_HEIGHT_RATIO = 0.20  # Bar = 20% of image height
        MIN_BAR_HEIGHT = 80  # Minimum bar height
        FONT_SIZE_RATIO = 0.70  # Font = 70% of bar height
        LINE_SPACING_RATIO = 0.25
        BAR_PADDING_RATIO = 0.10
        TEXT_PADDING_RATIO = 0.05
        MAX_DIMENSION = 2000

        def find_font() -> Optional[str]:
            """Find first available system font from predefined paths."""
            for font_path in FONT_PATHS:
                try:
                    ImageFont.truetype(font_path, 20)
                    return font_path
                except (OSError, IOError):
                    continue
            return None

        def get_font(font_path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
            """Load font from path or fall back to default."""
            if font_path:
                try:
                    return ImageFont.truetype(font_path, size)
                except (OSError, IOError):
                    pass
            return ImageFont.load_default()

        # Open image
        img = Image.open(io.BytesIO(self.image_data))

        # Convert to RGB
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, self.settings.bar_color)
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode == "P":
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if too large
        if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

        # If no text, just convert without bar
        if not self.settings.text:
            output = io.BytesIO()
            img.save(output, format="PNG", optimize=True)
            return output.getvalue()

        # Calculate DYNAMIC bar height (20% of image, min 80px)
        bar_height = max(MIN_BAR_HEIGHT, int(img.height * BAR_HEIGHT_RATIO))

        # Calculate font size (70% of bar height)
        font_size = max(24, int(bar_height * FONT_SIZE_RATIO))
        font_path = find_font()
        font = get_font(font_path, font_size)

        # Calculate padding
        text_padding = max(20, int(img.width * TEXT_PADDING_RATIO))

        # Wrap text
        max_text_width = img.width - (text_padding * 2)
        lines = wrap_text(self.settings.text, font, max_text_width)

        # Calculate text height
        line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
        line_spacing = int(line_height * LINE_SPACING_RATIO)
        total_text_height = (line_height * len(lines)) + (line_spacing * (len(lines) - 1))

        # Expand bar if needed for multiline
        vertical_padding = max(10, int(bar_height * BAR_PADDING_RATIO))
        min_bar_for_text = total_text_height + (vertical_padding * 2)
        if min_bar_for_text > bar_height:
            bar_height = min_bar_for_text

        # Create new image with bar
        new_height = img.height + bar_height
        new_img = Image.new("RGB", (img.width, new_height), self.settings.bar_color)

        # Paste original image (bar always at top)
        new_img.paste(img, (0, bar_height))

        # Draw text
        draw = ImageDraw.Draw(new_img)

        # Calculate starting Y position (centered vertically in bar)
        start_y = (bar_height - total_text_height) // 2

        # Draw each line centered horizontally
        current_y = start_y
        for line in lines:
            bbox = font.getbbox(line)
            line_width = bbox[2] - bbox[0]
            text_x = (img.width - line_width) // 2 - bbox[0]
            text_y = current_y - bbox[1]
            draw.text((text_x, text_y), line, font=font, fill=self.settings.text_color)
            current_y += line_height + line_spacing

        # Save as PNG
        output = io.BytesIO()
        new_img.save(output, format="PNG", optimize=True)
        return output.getvalue()

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

    async def on_timeout(self):
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                log.tree("Image Convert Timeout Edit Failed", [
                    ("Source", self.source_name[:30]),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
        log.tree("Image Convert View Expired", [
            ("Source", self.source_name[:30]),
            ("Requester ID", str(self.requester_id)),
        ], emoji="⏳")

    # ==========================================================================
    # Buttons - Row 1
    # ==========================================================================

    @ui.button(label="Edit", emoji="<:rename:1455709387711578394>", style=discord.ButtonStyle.secondary, row=1)
    async def edit_text_button(self, interaction: discord.Interaction, button: ui.Button):
        """Open modal to edit caption text."""
        modal = TextInputModal(self.settings.text, self)
        await interaction.response.send_modal(modal)

    @ui.button(label="Save", emoji="<:save:1455776703468273825>", style=discord.ButtonStyle.secondary, row=1)
    async def download_button(self, interaction: discord.Interaction, button: ui.Button):
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
            log.tree("Convert Image Failed", [
                ("User", str(interaction.user)),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            return

        final_bytes = result.gif_bytes
        filename = "discord.gg-syria.gif"

        file = discord.File(fp=io.BytesIO(final_bytes), filename=filename)

        # Send result with user ping
        await interaction.followup.send(content=interaction.user.mention, file=file)

        # Delete the editor embed
        try:
            await interaction.message.delete()
        except Exception as e:
            log.tree("Editor Delete Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Delete original message ONLY if it's the user's own message
        if self.original_message and self.original_message.author.id == self.requester_id:
            try:
                await self.original_message.delete()
            except Exception as e:
                log.tree("Original Message Delete Failed", [
                    ("User", str(interaction.user)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        log.tree("Convert Download", [
            ("User", str(interaction.user)),
            ("File", filename),
            ("Size", f"{len(final_bytes) / 1024:.1f} KB"),
            ("Text", self.settings.text[:30] if self.settings.text else "(none)"),
            ("Color", self.settings.get_preset_name()),
            ("Animated", "Yes" if is_animated else "No"),
        ], emoji="OK")

        self.stop()

    @ui.button(label="Cancel", emoji="<:block:1455709662316986539>", style=discord.ButtonStyle.secondary, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Cancel and delete the editor."""
        await interaction.response.defer()

        log.tree("Convert Cancelled", [
            ("User", str(interaction.user)),
            ("Source", self.source_name[:30]),
        ], emoji="X")

        try:
            await interaction.message.delete()
        except Exception as e:
            log.tree("Cancel Delete Failed", [
                ("User", str(interaction.user)),
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
    ):
        super().__init__(timeout=timeout)
        self.video_data = video_data
        self.source_name = source_name
        self.requester_id = requester_id
        self.thumbnail_bytes = thumbnail_bytes
        self.original_message = original_message  # For deletion if own message
        self.settings = ConvertSettings(text=initial_text)
        self.message: Optional[discord.Message] = None
        self._processing = False

        # Add color select dropdown
        self.add_item(VideoColorSelect(self))

    def _generate_preview_with_text(self) -> Optional[bytes]:
        """Generate preview thumbnail with text bar overlay."""
        if not self.thumbnail_bytes:
            return None

        # Constants - DYNAMIC sizing like NotSoBot
        BAR_HEIGHT_RATIO = 0.20  # Bar = 20% of image height
        MIN_BAR_HEIGHT = 40  # Minimum for thumbnail
        FONT_SIZE_RATIO = 0.70  # Font = 70% of bar height
        LINE_SPACING_RATIO = 0.25
        BAR_PADDING_RATIO = 0.10
        TEXT_PADDING_RATIO = 0.05

        def find_font() -> Optional[str]:
            """Find first available system font from predefined paths."""
            for font_path in FONT_PATHS:
                try:
                    ImageFont.truetype(font_path, 20)
                    return font_path
                except (OSError, IOError):
                    continue
            return None

        def get_font(font_path: Optional[str], size: int) -> ImageFont.FreeTypeFont:
            """Load font from path or fall back to default."""
            if font_path:
                try:
                    return ImageFont.truetype(font_path, size)
                except (OSError, IOError):
                    pass
            return ImageFont.load_default()

        try:
            # Open thumbnail
            img = Image.open(io.BytesIO(self.thumbnail_bytes))

            # Convert to RGB
            if img.mode != "RGB":
                img = img.convert("RGB")

            # If no text, return original thumbnail
            if not self.settings.text:
                output = io.BytesIO()
                img.save(output, format="PNG", optimize=True)
                return output.getvalue()

            # Calculate DYNAMIC bar height (20% of image, min 40px for thumbnail)
            bar_height = max(MIN_BAR_HEIGHT, int(img.height * BAR_HEIGHT_RATIO))

            # Calculate font size (70% of bar height)
            font_size = max(16, int(bar_height * FONT_SIZE_RATIO))
            font_path = find_font()
            font = get_font(font_path, font_size)

            # Calculate padding
            text_padding = max(10, int(img.width * TEXT_PADDING_RATIO))

            # Wrap text
            max_text_width = img.width - (text_padding * 2)
            lines = wrap_text(self.settings.text, font, max_text_width)

            # Calculate text height
            line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
            line_spacing = int(line_height * LINE_SPACING_RATIO)
            total_text_height = (line_height * len(lines)) + (line_spacing * (len(lines) - 1))

            # Expand bar if needed for multiline
            vertical_padding = max(5, int(bar_height * BAR_PADDING_RATIO))
            min_bar_for_text = total_text_height + (vertical_padding * 2)
            if min_bar_for_text > bar_height:
                bar_height = min_bar_for_text

            # Create new image with bar
            new_height = img.height + bar_height
            new_img = Image.new("RGB", (img.width, new_height), self.settings.bar_color)

            # Paste original image (bar always at top)
            new_img.paste(img, (0, bar_height))

            # Draw text
            draw = ImageDraw.Draw(new_img)

            # Calculate starting Y position (centered vertically in bar)
            start_y = (bar_height - total_text_height) // 2

            # Draw each line centered horizontally
            current_y = start_y
            for line in lines:
                bbox = font.getbbox(line)
                line_width = bbox[2] - bbox[0]
                text_x = (img.width - line_width) // 2 - bbox[0]
                text_y = current_y - bbox[1]
                draw.text((text_x, text_y), line, font=font, fill=self.settings.text_color)
                current_y += line_height + line_spacing

            # Save as PNG
            output = io.BytesIO()
            new_img.save(output, format="PNG", optimize=True)
            return output.getvalue()

        except Exception:
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

    async def on_timeout(self):
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                log.tree("Video Convert Timeout Edit Failed", [
                    ("Source", self.source_name[:30]),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
        log.tree("Video Convert View Expired", [
            ("Source", self.source_name[:30]),
            ("Requester ID", str(self.requester_id)),
        ], emoji="⏳")

    # ==========================================================================
    # Buttons - Row 1
    # ==========================================================================

    @ui.button(label="Edit", emoji="<:rename:1455709387711578394>", style=discord.ButtonStyle.secondary, row=1)
    async def edit_text_button(self, interaction: discord.Interaction, button: ui.Button):
        """Open modal to edit caption text."""
        modal = VideoTextInputModal(self.settings.text, self)
        await interaction.response.send_modal(modal)

    @ui.button(label="Save", emoji="<:save:1455776703468273825>", style=discord.ButtonStyle.secondary, row=1)
    async def convert_button(self, interaction: discord.Interaction, button: ui.Button):
        """Convert the video to GIF."""
        self._processing = True

        await interaction.response.defer()

        # Disable all buttons while processing (gray out)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

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

            log.tree("Video Convert Failed", [
                ("User", str(interaction.user)),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            return

        # Success - send the GIF
        filename = "discord.gg-syria.gif"
        file = discord.File(fp=io.BytesIO(result.gif_bytes), filename=filename)

        # Send result with user ping
        await interaction.followup.send(content=interaction.user.mention, file=file)

        # Delete the editor embed
        try:
            await interaction.message.delete()
        except Exception as e:
            log.tree("Video Editor Delete Failed", [
                ("User", str(interaction.user)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Delete original message ONLY if it's the user's own message
        if self.original_message and self.original_message.author.id == self.requester_id:
            try:
                await self.original_message.delete()
            except Exception as e:
                log.tree("Video Original Delete Failed", [
                    ("User", str(interaction.user)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        log.tree("Video Convert Complete", [
            ("User", str(interaction.user)),
            ("File", filename),
            ("Size", f"{len(result.gif_bytes) / 1024:.1f} KB"),
            ("Text", self.settings.text[:30] if self.settings.text else "(none)"),
            ("Color", self.settings.get_preset_name()),
        ], emoji="OK")

        self.stop()

    @ui.button(label="Cancel", emoji="<:block:1455709662316986539>", style=discord.ButtonStyle.secondary, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Cancel and delete the editor."""
        await interaction.response.defer()

        log.tree("Video Convert Cancelled", [
            ("User", str(interaction.user)),
            ("Source", self.source_name[:30]),
        ], emoji="X")

        try:
            await interaction.message.delete()
        except Exception as e:
            log.tree("Video Cancel Delete Failed", [
                ("User", str(interaction.user)),
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
    """
    # Determine requester ID based on type
    if isinstance(interaction_or_message, discord.Interaction):
        requester_id = interaction_or_message.user.id
        is_interaction = True
    else:
        requester_id = interaction_or_message.author.id
        is_interaction = False

    if is_video:
        # Get video duration to determine preview type
        # Short clips (< 10s) like Tenor/Giphy GIFs get single thumbnail
        # Longer videos get 5-frame preview strip
        duration = await asyncio.to_thread(convert_service.get_video_duration, image_data)
        is_short_clip = duration is not None and duration < 10

        if is_short_clip:
            preview_strip_bytes = await asyncio.to_thread(convert_service.extract_thumbnail, image_data)
        else:
            preview_strip_bytes = await asyncio.to_thread(convert_service.extract_preview_strip, image_data, 5)
            # Fall back to single thumbnail if strip fails
            if not preview_strip_bytes:
                preview_strip_bytes = await asyncio.to_thread(convert_service.extract_thumbnail, image_data)

        # Video: Use VideoConvertView with preview strip
        view = VideoConvertView(
            video_data=image_data,
            source_name=source_name,
            requester_id=requester_id,
            initial_text=initial_text,
            thumbnail_bytes=preview_strip_bytes,
            original_message=original_message,
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
            log.tree("Video Preview Failed", [
                ("Source", source_name[:30]),
            ], emoji="⚠️")
            if is_interaction:
                await interaction_or_message.followup.send(embed=embed, view=view)
            else:
                msg = await interaction_or_message.reply(embed=embed, view=view, mention_author=False)
                view.message = msg

        log.tree("Video Convert Editor Started", [
            ("User", str(interaction_or_message.user if is_interaction else interaction_or_message.author)),
            ("Source", source_name[:30]),
            ("Initial Text", initial_text[:30] if initial_text else "(none)"),
            ("Preview Strip", "Yes" if preview_strip_bytes else "No"),
        ], emoji="VIDEO")

    else:
        # Image: Use ConvertView with live preview
        view = ConvertView(
            image_data=image_data,
            source_name=source_name,
            requester_id=requester_id,
            initial_text=initial_text,
            original_message=original_message,
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

        log.tree("Convert Editor Started", [
            ("User", str(interaction_or_message.user if is_interaction else interaction_or_message.author)),
            ("Source", source_name[:30]),
            ("Initial Text", initial_text[:30] if initial_text else "(none)"),
        ], emoji="IMAGE")
