"""
SyriaBot - Convert Service
==========================

Image/video processing service for the /convert command.
Adds white bars with text and converts to GIF.
Supports both images and short videos.

Author: Unknown
"""

import asyncio
import io
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal

from PIL import Image, ImageDraw, ImageFont

# Try to import Wand for better GIF processing
try:
    from wand.image import Image as WandImage
    from wand.drawing import Drawing
    from wand.color import Color
    WAND_AVAILABLE = True
except ImportError:
    WAND_AVAILABLE = False

from src.core.logger import log
from src.core.constants import (
    FONT_PATHS,
    MAX_IMAGE_SIZE,
    MAX_VIDEO_SIZE,
    MAX_DIMENSION,
    MAX_VIDEO_DURATION,
    GIF_FPS,
    GIF_MAX_WIDTH,
    BAR_HEIGHT_RATIO,
    MIN_BAR_HEIGHT,
    FONT_SIZE_RATIO,
    LINE_SPACING_RATIO,
    BAR_PADDING_RATIO,
    TEXT_PADDING_RATIO,
    DEFAULT_BAR_COLOR,
    DEFAULT_TEXT_COLOR,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from src.utils.http import http_session, DOWNLOAD_TIMEOUT
from src.utils.text import wrap_text

# Temp directory for processing
TEMP_DIR = Path(tempfile.gettempdir()) / "syria_convert"

# Aliases for backwards compatibility
BAR_COLOR = DEFAULT_BAR_COLOR
TEXT_COLOR = DEFAULT_TEXT_COLOR


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ConvertResult:
    """Result of a convert operation."""
    success: bool
    gif_bytes: Optional[bytes] = None
    error: Optional[str] = None


@dataclass
class VideoInfo:
    """Information about a video file."""
    duration: float
    width: int
    height: int
    fps: float


# =============================================================================
# Convert Service
# =============================================================================

class ConvertService:
    """Service for converting images to GIFs with text bars."""

    def __init__(self):
        # Ensure temp directory exists
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # Find available font
        self._font_path = self._find_font()

        # Font cache for faster repeated access (cache by size)
        self._font_cache: dict[int, ImageFont.FreeTypeFont] = {}

        if self._font_path:
            # Pre-cache common font sizes for faster first-use
            for size in [24, 32, 48, 56, 64, 72, 80, 96, 112, 128, 140]:
                self._font_cache[size] = ImageFont.truetype(self._font_path, size)

        log.tree("Convert Service Initialized", [
            ("Font", Path(self._font_path).name if self._font_path else "Default"),
            ("GIF Engine", "ImageMagick (Wand)" if WAND_AVAILABLE else "Pillow"),
        ], emoji="✅" if WAND_AVAILABLE else "⚠️")

    def _find_font(self) -> Optional[str]:
        """Find an available font on the system."""
        for font_path in FONT_PATHS:
            try:
                ImageFont.truetype(font_path, 20)
                return font_path
            except (OSError, IOError):
                continue
        log.tree("Font Not Found", [
            ("Searched", ", ".join([p.split("/")[-1] for p in FONT_PATHS])),
            ("Fallback", "Default bitmap font"),
        ], emoji="⚠️")
        return None

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get a font at the specified size (cached for performance)."""
        # Check cache first
        if size in self._font_cache:
            return self._font_cache[size]

        # Load and cache
        if self._font_path:
            try:
                font = ImageFont.truetype(self._font_path, size)
                self._font_cache[size] = font
                return font
            except (OSError, IOError):
                pass
        return ImageFont.load_default()

    def _get_font_uncached(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get a font at the specified size (for preview, no cache)."""
        if self._font_path:
            try:
                return ImageFont.truetype(self._font_path, size)
            except (OSError, IOError):
                pass
        return ImageFont.load_default()

    def _calculate_font_size(self, text: str, max_width: int, max_height: int) -> int:
        """Calculate optimal font size to fit text in given dimensions (single line)."""
        # Start with a large font and decrease until it fits
        for size in range(80, 12, -2):
            font = self._get_font(size)

            # Get text bounding box
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            if text_width <= max_width and text_height <= max_height:
                return size

        return 12  # Minimum size

    def _calculate_font_size_multiline(self, text: str, max_width: int, max_height: int) -> tuple[int, list[str]]:
        """Calculate optimal font size with text wrapping. Returns (font_size, wrapped_lines)."""
        # Start with a large font and decrease until it fits
        for size in range(60, 12, -2):
            font = self._get_font(size)

            # Wrap text at this font size
            lines = wrap_text(text, font, max_width)

            # Calculate total height needed
            line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
            line_spacing = int(line_height * 0.2)  # 20% spacing between lines
            total_height = (line_height * len(lines)) + (line_spacing * (len(lines) - 1))

            if total_height <= max_height:
                return size, lines

        # If nothing fits, use minimum size
        font = self._get_font(12)
        lines = wrap_text(text, font, max_width)
        return 12, lines

    def _calculate_dynamic_layout(self, text: str, img_width: int, img_height: int) -> tuple[ImageFont.FreeTypeFont, list[str], int, int]:
        """
        Calculate layout with DYNAMIC sizing based on image dimensions (NotSoBot style).

        Bar height = 20% of image height
        Font size = 70% of bar height

        Returns:
            (font, wrapped_lines, bar_height, text_padding)
        """
        # Calculate bar height based on image (20% of height, minimum 80px)
        bar_height = max(MIN_BAR_HEIGHT, int(img_height * BAR_HEIGHT_RATIO))

        # Calculate font size based on bar height (70% of bar)
        font_size = max(24, int(bar_height * FONT_SIZE_RATIO))
        font = self._get_font(font_size)

        # Calculate horizontal padding (5% of image width, minimum 20px)
        text_padding = max(20, int(img_width * TEXT_PADDING_RATIO))

        # Wrap text at this font size
        max_text_width = img_width - (text_padding * 2)
        lines = wrap_text(text, font, max_text_width)

        # If text wraps to multiple lines, we may need to expand bar height
        line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
        line_spacing = int(line_height * LINE_SPACING_RATIO)
        total_text_height = (line_height * len(lines)) + (line_spacing * (len(lines) - 1))

        # Calculate padding (10% of bar height)
        vertical_padding = max(10, int(bar_height * BAR_PADDING_RATIO))

        # Expand bar if text needs more space
        min_bar_for_text = total_text_height + (vertical_padding * 2)
        if min_bar_for_text > bar_height:
            bar_height = min_bar_for_text

        return font, lines, bar_height, text_padding

    async def fetch_image(self, url: str) -> Optional[bytes]:
        """Fetch image from URL."""
        try:
            async with http_session.get(url, timeout=DOWNLOAD_TIMEOUT) as resp:
                if resp.status != 200:
                    return None

                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_IMAGE_SIZE:
                    return None

                return await resp.read()
        except Exception as e:
            log.tree("Fetch Image Failed", [
                ("Error", str(e)),
            ], emoji="❌")
            return None

    async def convert(
        self,
        image_data: bytes,
        text: str,
        position: Literal["top", "bottom"] = "top"
    ) -> ConvertResult:
        """
        Convert an image to GIF with text bar.

        Args:
            image_data: Raw image bytes
            text: Text to add to the bar
            position: Position of text bar ("top" or "bottom")

        Returns:
            ConvertResult with GIF bytes or error
        """
        log.tree("Converting Image", [
            ("Text", text[:50] + "..." if len(text) > 50 else text),
            ("Position", position),
        ], emoji="CONVERT")

        try:
            # Process in thread to avoid blocking
            result = await asyncio.to_thread(
                self._process_image,
                image_data,
                text,
                position
            )
            return result
        except Exception as e:
            log.tree("Convert Error", [("Type", type(e).__name__), ("Error", str(e)[:50])], emoji="❌")
            return ConvertResult(
                success=False,
                error=f"Failed to convert image: {type(e).__name__}"
            )

    def _process_image(
        self,
        image_data: bytes,
        text: str,
        position: Literal["top", "bottom"],
        bar_color: tuple = BAR_COLOR,
        text_color: tuple = TEXT_COLOR,
    ) -> ConvertResult:
        """Process image synchronously (runs in thread)."""
        try:
            # Open image
            img = Image.open(io.BytesIO(image_data))

            # Check if it's an animated GIF
            is_animated = getattr(img, 'is_animated', False)
            if is_animated:
                return self._process_animated_gif(
                    img, text, position, bar_color, text_color
                )

            # Convert to RGB for consistent processing
            if img.mode == "RGBA":
                # Preserve transparency by compositing on bar color
                background = Image.new("RGB", img.size, bar_color)
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode == "P":
                # Palette mode - convert properly
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Resize if too large
            if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
                img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

            # Only add bar if text is provided
            if text and text.strip():
                # Calculate DYNAMIC layout based on image size (NotSoBot style)
                font, lines, bar_height, text_padding = self._calculate_dynamic_layout(
                    text, img.width, img.height
                )

                # Create new image with bar
                new_height = img.height + bar_height
                new_img = Image.new("RGB", (img.width, new_height), bar_color)

                # Paste original image in correct position
                if position == "top":
                    # Bar at top, image below
                    new_img.paste(img, (0, bar_height))
                else:  # bottom
                    # Image at top, bar below
                    new_img.paste(img, (0, 0))

                # Draw text on the bar
                draw = ImageDraw.Draw(new_img)

                # Calculate line height and spacing
                line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
                line_spacing = int(line_height * LINE_SPACING_RATIO)
                total_text_height = (line_height * len(lines)) + (line_spacing * (len(lines) - 1))

                # Calculate starting Y position (centered vertically in bar)
                if position == "top":
                    start_y = (bar_height - total_text_height) // 2
                else:  # bottom
                    start_y = img.height + (bar_height - total_text_height) // 2

                # Draw each line centered horizontally
                current_y = start_y
                for line in lines:
                    bbox = font.getbbox(line)
                    line_width = bbox[2] - bbox[0]
                    text_x = (img.width - line_width) // 2 - bbox[0]
                    text_y = current_y - bbox[1]
                    draw.text((text_x, text_y), line, font=font, fill=text_color)
                    current_y += line_height + line_spacing
            else:
                # No text - just convert to GIF without adding bar
                new_img = img

            # Save as PNG (full quality) - filename will be .gif for Discord starring
            output = io.BytesIO()
            if new_img.mode == "RGBA":
                # Keep RGBA for PNG
                pass
            elif new_img.mode != "RGB":
                new_img = new_img.convert("RGB")

            new_img.save(output, format="PNG", optimize=True)
            result_bytes = output.getvalue()

            log.tree("Convert Complete", [
                ("Size", f"{len(result_bytes) / 1024:.1f} KB"),
                ("Dimensions", f"{new_img.width}x{new_img.height}"),
                ("Format", "GIF"),
            ], emoji="OK")

            return ConvertResult(
                success=True,
                gif_bytes=result_bytes
            )

        except Exception as e:
            return ConvertResult(
                success=False,
                error=str(e)
            )

    def _process_animated_gif(
        self,
        img: Image.Image,
        text: str,
        position: Literal["top", "bottom"],
        bar_color: tuple = BAR_COLOR,
        text_color: tuple = TEXT_COLOR,
    ) -> ConvertResult:
        """Process animated GIF, preserving colors and quality using Wand/ImageMagick."""

        # Try Wand first (much better quality), fall back to Pillow
        if WAND_AVAILABLE:
            try:
                return self._process_animated_gif_wand(img, text, position, bar_color, text_color)
            except Exception as e:
                log.tree("Wand GIF Processing Failed", [
                    ("Error", str(e)),
                    ("Fallback", "Using Pillow"),
                ], emoji="⚠️")

        # Fallback to Pillow-based processing
        return self._process_animated_gif_pillow(img, text, position, bar_color, text_color)

    def _process_animated_gif_wand(
        self,
        img: Image.Image,
        text: str,
        position: Literal["top", "bottom"],
        bar_color: tuple = BAR_COLOR,
        text_color: tuple = TEXT_COLOR,
    ) -> ConvertResult:
        """Process animated GIF using Wand/ImageMagick (NotSoBot method)."""
        # Save PIL image to bytes for Wand to read
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='GIF', save_all=True)
        img_bytes.seek(0)

        has_text = text and text.strip()

        with WandImage(blob=img_bytes.getvalue()) as wand_img:
            orig_width = wand_img.width
            orig_height = wand_img.height
            frame_count = len(wand_img.sequence)

            # Calculate bar dimensions (NotSoBot style)
            bar_height = max(MIN_BAR_HEIGHT, int(orig_height * BAR_HEIGHT_RATIO)) if has_text else 0
            new_height = orig_height + bar_height

            # Calculate font size (70% of bar height)
            font_size = max(24, int(bar_height * FONT_SIZE_RATIO)) if has_text else 0

            # Create output image
            with WandImage() as output_img:
                for frame in wand_img.sequence:
                    # Clone the frame
                    with frame.clone() as f:
                        # Coalesce to handle frame disposal properly
                        f.coalesce()

                        if has_text:
                            # Create new canvas with bar
                            bar_color_hex = f'rgb({bar_color[0]},{bar_color[1]},{bar_color[2]})'

                            with WandImage(width=orig_width, height=new_height, background=Color(bar_color_hex)) as new_frame:
                                # Paste original frame in correct position
                                if position == "top":
                                    new_frame.composite(f, left=0, top=bar_height)
                                else:
                                    new_frame.composite(f, left=0, top=0)

                                # Draw text on bar
                                text_color_hex = f'rgb({text_color[0]},{text_color[1]},{text_color[2]})'

                                with Drawing() as draw:
                                    draw.font = self._font_path or 'DejaVu-Sans-Bold'
                                    draw.font_size = font_size
                                    draw.fill_color = Color(text_color_hex)
                                    draw.text_alignment = 'center'
                                    draw.gravity = 'north' if position == "top" else 'south'

                                    # Calculate vertical center of bar
                                    text_y = bar_height // 2 + font_size // 3

                                    draw.text(orig_width // 2, text_y, text)
                                    draw(new_frame)

                                # Copy frame delay
                                new_frame.delay = f.delay or 10
                                output_img.sequence.append(new_frame.clone())
                        else:
                            # No text, just clone the frame
                            f.delay = f.delay or 10
                            output_img.sequence.append(f.clone())

                # Optimize and save
                output_img.type = 'optimize'
                output_img.format = 'gif'
                result_bytes = output_img.make_blob()

        log.tree("Animated GIF Convert Complete (Wand)", [
            ("Frames", frame_count),
            ("Size", f"{len(result_bytes) / 1024:.1f} KB"),
            ("Dimensions", f"{orig_width}x{new_height}"),
            ("Has Text", "Yes" if has_text else "No"),
            ("Engine", "ImageMagick"),
        ], emoji="OK")

        return ConvertResult(success=True, gif_bytes=result_bytes)

    def _process_animated_gif_pillow(
        self,
        img: Image.Image,
        text: str,
        position: Literal["top", "bottom"],
        bar_color: tuple = BAR_COLOR,
        text_color: tuple = TEXT_COLOR,
    ) -> ConvertResult:
        """Fallback: Process animated GIF using Pillow."""
        try:
            frames = []
            durations = []

            orig_width, orig_height = img.size
            has_text = text and text.strip()

            font = None
            lines = []
            line_height = 0
            line_spacing = 0
            total_text_height = 0
            start_y = 0
            bar_height = 0

            if has_text:
                font, lines, bar_height, text_padding = self._calculate_dynamic_layout(
                    text, orig_width, orig_height
                )
                line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
                line_spacing = int(line_height * LINE_SPACING_RATIO)
                total_text_height = (line_height * len(lines)) + (line_spacing * (len(lines) - 1))

                if position == "top":
                    start_y = (bar_height - total_text_height) // 2
                else:
                    start_y = orig_height + (bar_height - total_text_height) // 2

            new_height = orig_height + bar_height if has_text else orig_height

            frame_count = 0
            try:
                while True:
                    duration = img.info.get('duration', 100)
                    durations.append(duration)
                    frame = img.convert("RGBA")

                    if has_text:
                        bar_color_rgba = bar_color + (255,)
                        new_frame = Image.new("RGBA", (orig_width, new_height), bar_color_rgba)

                        if position == "top":
                            new_frame.paste(frame, (0, bar_height))
                        else:
                            new_frame.paste(frame, (0, 0))

                        draw = ImageDraw.Draw(new_frame)
                        current_y = start_y
                        for line in lines:
                            bbox = font.getbbox(line)
                            line_width = bbox[2] - bbox[0]
                            text_x = (orig_width - line_width) // 2 - bbox[0]
                            text_y = current_y - bbox[1]
                            draw.text((text_x, text_y), line, font=font, fill=text_color)
                            current_y += line_height + line_spacing
                    else:
                        new_frame = frame

                    frames.append(new_frame)
                    frame_count += 1
                    img.seek(img.tell() + 1)

            except EOFError:
                pass

            if not frames:
                return ConvertResult(success=False, error="No frames found in GIF")

            palette_frames = []
            for frame in frames:
                p_frame = frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
                palette_frames.append(p_frame)

            output = io.BytesIO()
            palette_frames[0].save(
                output,
                format="GIF",
                save_all=True,
                append_images=palette_frames[1:],
                duration=durations,
                loop=0,
                disposal=2,
            )
            result_bytes = output.getvalue()

            log.tree("Animated GIF Convert Complete (Pillow)", [
                ("Frames", frame_count),
                ("Size", f"{len(result_bytes) / 1024:.1f} KB"),
                ("Dimensions", f"{orig_width}x{new_height}"),
                ("Has Text", "Yes" if has_text else "No"),
                ("Engine", "Pillow (fallback)"),
            ], emoji="OK")

            return ConvertResult(success=True, gif_bytes=result_bytes)

        except Exception as e:
            return ConvertResult(success=False, error=str(e))

    # =========================================================================
    # Video Processing Methods
    # =========================================================================

    def _get_video_info(self, video_path: str) -> Optional[VideoInfo]:
        """Get video information using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return None

            import json
            data = json.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                return None

            # Parse FPS (can be "30/1" or "29.97")
            fps_str = video_stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 30.0
            else:
                fps = float(fps_str)

            return VideoInfo(
                duration=float(data.get("format", {}).get("duration", 0)),
                width=int(video_stream.get("width", 0)),
                height=int(video_stream.get("height", 0)),
                fps=fps
            )
        except Exception as e:
            log.tree("Get Video Info Failed", [
                ("Error", str(e)),
            ], emoji="❌")
            return None

    # FFmpeg filter mappings for video effects
    VIDEO_EFFECT_FILTERS = {
        "none": "",
        "grayscale": "colorchannelmixer=.3:.4:.3:0:.3:.4:.3:0:.3:.4:.3",
        "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
        "blur": "gblur=sigma=3",
        "sharpen": "unsharp=5:5:1.0:5:5:0.5",
        "contrast": "eq=contrast=1.5",
        "brightness": "eq=brightness=0.1",
    }

    async def convert_video_to_gif(
        self,
        video_data: bytes,
        text: str = "",
        position: Literal["top", "bottom"] = "top",
        bar_color: tuple = BAR_COLOR,
        text_color: tuple = TEXT_COLOR,
        effect: str = "none",
    ) -> ConvertResult:
        """
        Convert a video to animated GIF with optional text bar.

        Args:
            video_data: Raw video bytes
            text: Text to add to the bar (optional)
            position: Position of text bar ("top" or "bottom")
            bar_color: RGB tuple for bar color
            text_color: RGB tuple for text color

        Returns:
            ConvertResult with GIF bytes or error
        """
        log.tree("Converting Video to GIF", [
            ("Text", text[:30] + "..." if len(text) > 30 else text if text else "(none)"),
            ("Position", position),
            ("Effect", effect),
        ], emoji="VIDEO")

        try:
            result = await asyncio.to_thread(
                self._process_video,
                video_data,
                text,
                position,
                bar_color,
                text_color,
                effect
            )
            return result
        except Exception as e:
            log.tree("Video Convert Error", [("Type", type(e).__name__), ("Error", str(e)[:50])], emoji="❌")
            return ConvertResult(
                success=False,
                error=f"Failed to convert video: {type(e).__name__}"
            )

    def _process_video(
        self,
        video_data: bytes,
        text: str,
        position: Literal["top", "bottom"],
        bar_color: tuple,
        text_color: tuple,
        effect: str = "none"
    ) -> ConvertResult:
        """Process video synchronously (runs in thread)."""
        # Create unique temp files
        temp_id = uuid.uuid4().hex[:8]
        input_path = TEMP_DIR / f"input_{temp_id}.mp4"
        output_path = TEMP_DIR / f"output_{temp_id}.gif"
        palette_path = TEMP_DIR / f"palette_{temp_id}.png"

        try:
            # Write video data to temp file
            input_path.write_bytes(video_data)

            # Get video info
            info = self._get_video_info(str(input_path))
            if not info:
                return ConvertResult(success=False, error="Could not read video file")

            # Check duration
            if info.duration > MAX_VIDEO_DURATION:
                return ConvertResult(
                    success=False,
                    error=f"Video too long ({info.duration:.1f}s). Max is {MAX_VIDEO_DURATION}s."
                )

            # Calculate output dimensions
            scale_width = min(info.width, GIF_MAX_WIDTH)
            # Make width divisible by 2 for ffmpeg
            scale_width = scale_width - (scale_width % 2)

            # Calculate scaled height (maintaining aspect ratio)
            scale_factor = scale_width / info.width
            scale_height = int(info.height * scale_factor)
            # Make height divisible by 2 for ffmpeg
            scale_height = scale_height - (scale_height % 2)

            # Build ffmpeg filter chain
            bar_color_hex = "#{:02x}{:02x}{:02x}".format(*bar_color)
            text_color_hex = "#{:02x}{:02x}{:02x}".format(*text_color)

            # Base scale filter
            filters = [f"scale={scale_width}:{scale_height}:flags=lanczos"]

            # Add effect filter if specified
            effect_filter = self.VIDEO_EFFECT_FILTERS.get(effect, "")
            if effect_filter:
                filters.append(effect_filter)

            # Add text bar if text is provided
            if text:
                # Find font path
                font_file = self._font_path or ""
                font_option = f":fontfile='{font_file}'" if font_file else ""

                # DYNAMIC font sizing (NotSoBot style) - same as images
                # Bar height = 20% of scaled video height, minimum 60px
                bar_height = max(60, int(scale_height * BAR_HEIGHT_RATIO))
                # Font size = 70% of bar height, minimum 20px
                font_size = max(20, int(bar_height * FONT_SIZE_RATIO))
                # Vertical padding = 10% of bar height, minimum 8px
                vertical_padding = max(8, int(bar_height * BAR_PADDING_RATIO))

                # Calculate max chars per line based on width and font size
                # Average char width is roughly 0.5 * font_size for most fonts
                max_chars = int((scale_width * 0.90) / (font_size * 0.5))
                max_chars = max(max_chars, 8)  # At least 8 chars per line

                # Wrap text into lines
                words = text.split()
                lines = []
                current_line = ""
                for word in words:
                    test_line = f"{current_line} {word}".strip() if current_line else word
                    if len(test_line) <= max_chars:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                if current_line:
                    lines.append(current_line)
                if not lines:
                    lines = [text]

                # Calculate bar height based on number of lines (expand to fit multiline)
                line_spacing = int(font_size * LINE_SPACING_RATIO)
                total_text_height = (font_size * len(lines)) + (line_spacing * (len(lines) - 1))
                min_bar_for_text = total_text_height + (vertical_padding * 2)
                if min_bar_for_text > bar_height:
                    bar_height = min_bar_for_text
                # Make bar height divisible by 2 for ffmpeg
                bar_height = bar_height + (bar_height % 2)

                # Calculate starting Y for text (centered in bar)
                start_y = (bar_height - total_text_height) // 2

                if position == "top":
                    # Add padding at top for bar
                    filters.append(f"pad=iw:ih+{bar_height}:0:{bar_height}:color={bar_color_hex}")
                    # Draw each line centered
                    for i, line in enumerate(lines):
                        escaped_line = line.replace("'", "'\\''").replace(":", "\\:")
                        y_pos = start_y + (i * (font_size + line_spacing))
                        filters.append(
                            f"drawtext=text='{escaped_line}'{font_option}"
                            f":fontsize={font_size}:fontcolor={text_color_hex}"
                            f":x=(w-text_w)/2:y={y_pos}"
                        )
                else:  # bottom
                    # Add padding at bottom for bar
                    filters.append(f"pad=iw:ih+{bar_height}:0:0:color={bar_color_hex}")
                    # Draw each line centered
                    for i, line in enumerate(lines):
                        escaped_line = line.replace("'", "'\\''").replace(":", "\\:")
                        y_pos = start_y + (i * (font_size + line_spacing))
                        filters.append(
                            f"drawtext=text='{escaped_line}'{font_option}"
                            f":fontsize={font_size}:fontcolor={text_color_hex}"
                            f":x=(w-text_w)/2:y=h-{bar_height}+{y_pos}"
                        )

            # Add fps filter
            filters.append(f"fps={GIF_FPS}")

            filter_chain = ",".join(filters)

            # Step 1: Generate palette for better colors
            palette_cmd = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-vf", f"{filter_chain},palettegen=stats_mode=diff",
                "-t", str(min(info.duration, MAX_VIDEO_DURATION)),
                str(palette_path)
            ]

            result = subprocess.run(palette_cmd, capture_output=True, timeout=120)
            if result.returncode != 0:
                log.tree("Palette Generation Failed", [
                    ("Error", result.stderr.decode()[:100]),
                ], emoji="⚠️")
                # Fall back to no palette
                palette_path.unlink(missing_ok=True)

            # Step 2: Create GIF
            if palette_path.exists():
                # Use palette for better quality
                gif_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(input_path),
                    "-i", str(palette_path),
                    "-lavfi", f"{filter_chain} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
                    "-t", str(min(info.duration, MAX_VIDEO_DURATION)),
                    str(output_path)
                ]
            else:
                # No palette fallback
                gif_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(input_path),
                    "-vf", filter_chain,
                    "-t", str(min(info.duration, MAX_VIDEO_DURATION)),
                    str(output_path)
                ]

            result = subprocess.run(gif_cmd, capture_output=True, timeout=180)
            if result.returncode != 0:
                error_msg = result.stderr.decode()[:200]
                log.tree("FFmpeg Error", [("Message", error_msg[:80] if error_msg else "Unknown")], emoji="❌")
                return ConvertResult(success=False, error=f"FFmpeg error: {error_msg}")

            # Read output GIF
            if not output_path.exists():
                return ConvertResult(success=False, error="GIF output not created")

            gif_bytes = output_path.read_bytes()

            log.tree("Video Convert Complete", [
                ("Size", f"{len(gif_bytes) / 1024:.1f} KB"),
                ("Duration", f"{info.duration:.1f}s"),
                ("FPS", GIF_FPS),
            ], emoji="OK")

            return ConvertResult(success=True, gif_bytes=gif_bytes)

        except subprocess.TimeoutExpired:
            return ConvertResult(success=False, error="Video processing timed out")
        except Exception as e:
            return ConvertResult(success=False, error=str(e))
        finally:
            # Cleanup temp files
            for path in [input_path, output_path, palette_path]:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass

    def extract_thumbnail(self, video_data: bytes) -> Optional[bytes]:
        """Extract a thumbnail frame from video data."""
        temp_id = uuid.uuid4().hex[:8]
        input_path = TEMP_DIR / f"thumb_input_{temp_id}.mp4"
        output_path = TEMP_DIR / f"thumb_output_{temp_id}.png"

        try:
            # Write video to temp file
            input_path.write_bytes(video_data)

            # Extract first frame as thumbnail
            cmd = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-vf", "scale=400:-2",  # Scale to 400px width
                "-frames:v", "1",
                "-q:v", "2",
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0:
                return None

            if output_path.exists():
                return output_path.read_bytes()
            return None

        except Exception as e:
            log.tree("Extract Thumbnail Failed", [
                ("Error", str(e)),
            ], emoji="❌")
            return None
        finally:
            # Cleanup
            for path in [input_path, output_path]:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass

    def extract_preview_strip(self, video_data: bytes, num_frames: int = 5) -> Optional[bytes]:
        """
        Extract multiple frames and stitch into horizontal preview strip.

        Args:
            video_data: Raw video bytes
            num_frames: Number of frames to extract (default 5)

        Returns:
            PNG bytes of the stitched preview strip, or None on failure
        """
        temp_id = uuid.uuid4().hex[:8]
        input_path = TEMP_DIR / f"preview_input_{temp_id}.mp4"
        frame_paths = [TEMP_DIR / f"preview_frame_{temp_id}_{i}.png" for i in range(num_frames)]

        try:
            # Write video to temp file
            input_path.write_bytes(video_data)

            # Get video duration
            info = self._get_video_info(str(input_path))
            if not info or info.duration <= 0:
                return None

            duration = min(info.duration, MAX_VIDEO_DURATION)

            # Calculate timestamps for each frame (0%, 25%, 50%, 75%, 100%)
            timestamps = [duration * i / (num_frames - 1) for i in range(num_frames)]

            # Extract frames at each timestamp
            frames = []
            for i, ts in enumerate(timestamps):
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(ts),
                    "-i", str(input_path),
                    "-vf", "scale=160:-2",  # Small thumbnails for strip
                    "-frames:v", "1",
                    "-q:v", "2",
                    str(frame_paths[i])
                ]

                result = subprocess.run(cmd, capture_output=True, timeout=15)
                if result.returncode == 0 and frame_paths[i].exists():
                    img = Image.open(frame_paths[i])
                    frames.append(img)

            if len(frames) < 2:
                return None

            # Stitch frames horizontally
            total_width = sum(f.width for f in frames) + (len(frames) - 1) * 4  # 4px gap
            max_height = max(f.height for f in frames)

            strip = Image.new("RGB", (total_width, max_height), (30, 30, 30))  # Dark background

            x_offset = 0
            for frame in frames:
                # Center vertically if heights differ
                y_offset = (max_height - frame.height) // 2
                strip.paste(frame, (x_offset, y_offset))
                x_offset += frame.width + 4  # 4px gap

            # Save as PNG
            output = io.BytesIO()
            strip.save(output, format="PNG", optimize=True)

            log.tree("Video Preview Strip Generated", [
                ("Frames", len(frames)),
                ("Duration", f"{duration:.1f}s"),
                ("Size", f"{total_width}x{max_height}"),
            ], emoji="PREVIEW")

            return output.getvalue()

        except Exception as e:
            log.tree("Extract Preview Strip Failed", [
                ("Error", str(e)),
            ], emoji="❌")
            return None
        finally:
            # Cleanup
            try:
                input_path.unlink(missing_ok=True)
            except Exception:
                pass
            for path in frame_paths:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass

    def get_video_duration(self, video_data: bytes) -> Optional[float]:
        """Get video duration in seconds from video data."""
        temp_id = uuid.uuid4().hex[:8]
        input_path = TEMP_DIR / f"duration_{temp_id}.mp4"

        try:
            input_path.write_bytes(video_data)
            info = self._get_video_info(str(input_path))
            return info.duration if info else None
        except Exception as e:
            log.tree("Get Video Duration Failed", [
                ("Error", str(e)),
            ], emoji="❌")
            return None
        finally:
            try:
                input_path.unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def is_video(filename: str) -> bool:
        """Check if filename is a video file."""
        ext = Path(filename).suffix.lower()
        return ext in VIDEO_EXTENSIONS

    @staticmethod
    def is_image(filename: str) -> bool:
        """Check if filename is an image file."""
        ext = Path(filename).suffix.lower()
        return ext in IMAGE_EXTENSIONS

    async def fetch_media(self, url: str) -> Optional[bytes]:
        """Fetch image or video from URL."""
        try:
            async with http_session.get(url, timeout=DOWNLOAD_TIMEOUT) as resp:
                if resp.status != 200:
                    return None

                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_VIDEO_SIZE:
                    return None

                return await resp.read()
        except Exception as e:
            log.tree("Fetch Media Failed", [
                ("URL", url[:50]),
                ("Error", str(e)),
            ], emoji="❌")
            return None


# Global instance
convert_service = ConvertService()
