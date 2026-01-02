"""
SyriaBot - Quote Service
========================

Generates stylized quote images matching the Make it a Quote style.
Green & gold Syria theme with Arabic font support.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import io
import re
import aiohttp
import numpy as np
from datetime import datetime
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pilmoji import Pilmoji

from src.core.logger import log
from src.core.constants import (
    TIMEZONE_EST,
    FONT_ITALIC_PATHS,
    QUOTE_IMAGE_WIDTH,
    QUOTE_IMAGE_HEIGHT,
    QUOTE_THEME_COLOR,
    QUOTE_ACCENT_GOLD,
    QUOTE_BG_COLOR,
    QUOTE_TEXT_COLOR,
    QUOTE_SUBTEXT_COLOR,
    QUOTE_AVATAR_SECTION_WIDTH_RATIO,
    QUOTE_MAX_BANNER_CACHE_SIZE,
)
from src.utils.text import wrap_text

# Aliases for backwards compatibility
EASTERN_TZ = TIMEZONE_EST
MAX_BANNER_CACHE_SIZE = QUOTE_MAX_BANNER_CACHE_SIZE
IMAGE_WIDTH = QUOTE_IMAGE_WIDTH
IMAGE_HEIGHT = QUOTE_IMAGE_HEIGHT
THEME_COLOR = QUOTE_THEME_COLOR
ACCENT_GOLD = QUOTE_ACCENT_GOLD
BG_COLOR = QUOTE_BG_COLOR
TEXT_COLOR = QUOTE_TEXT_COLOR
SUBTEXT_COLOR = QUOTE_SUBTEXT_COLOR
AVATAR_SECTION_WIDTH = int(IMAGE_WIDTH * QUOTE_AVATAR_SECTION_WIDTH_RATIO)

# Font paths - Premium fonts with Arabic support (quote-specific)
FONT_PATHS = [
    "/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class QuoteResult:
    """Result from quote generation."""
    success: bool
    image_bytes: Optional[bytes] = None
    error: Optional[str] = None


# =============================================================================
# Quote Service
# =============================================================================

class QuoteService:
    """Generates quote images in Make it a Quote style."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._font_path: Optional[str] = None
        self._font_italic_path: Optional[str] = None
        self._banner_cache: Dict[int, Tuple[Image.Image, str]] = {}
        self._find_fonts()

    def _find_fonts(self) -> None:
        """Find available fonts on the system."""
        for path in FONT_PATHS:
            try:
                ImageFont.truetype(path, 20)
                self._font_path = path
                break
            except (OSError, IOError):
                continue

        for path in FONT_ITALIC_PATHS:
            try:
                ImageFont.truetype(path, 20)
                self._font_italic_path = path
                break
            except (OSError, IOError):
                continue

        log.tree("Quote Service Initialized", [
            ("Style", "Make it a Quote"),
            ("Theme", "Syria Green & Gold"),
            ("Font", self._font_path.split("/")[-1] if self._font_path else "Default"),
        ], emoji="💬")

    def _get_font(self, size: int, italic: bool = False) -> ImageFont.FreeTypeFont:
        """Get a font at the specified size."""
        path = self._font_italic_path if italic and self._font_italic_path else self._font_path
        if path:
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                pass
        return ImageFont.load_default()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_image(self, url: str) -> Optional[Image.Image]:
        """Fetch an image from URL."""
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data))
        except Exception as e:
            log.tree("Image Fetch Failed", [
                ("Error", str(e)[:50]),
            ], emoji="❌")
        return None

    def _get_today_est(self) -> str:
        """Get today's date string in EST timezone."""
        return datetime.now(EASTERN_TZ).strftime("%Y-%m-%d")

    async def _get_banner(self, guild_id: int, banner_url: str) -> Optional[Image.Image]:
        """Get banner from cache or fetch fresh."""
        today = self._get_today_est()

        # Check cache
        if guild_id in self._banner_cache:
            cached_img, cache_date = self._banner_cache[guild_id]
            if cache_date == today:
                return cached_img.copy()

        # Evict oldest entries if cache is full (simple LRU)
        if len(self._banner_cache) >= MAX_BANNER_CACHE_SIZE:
            # Remove first (oldest) entry
            oldest_key = next(iter(self._banner_cache))
            del self._banner_cache[oldest_key]

        # Fetch fresh
        banner_img = await self._fetch_image(banner_url)
        if banner_img:
            # Process banner
            if banner_img.mode in ("P", "PA"):
                banner_img = banner_img.convert("RGBA")
            elif banner_img.mode != "RGBA":
                banner_img = banner_img.convert("RGBA")

            # Resize to cover
            banner_ratio = banner_img.width / banner_img.height
            target_ratio = IMAGE_WIDTH / IMAGE_HEIGHT

            if banner_ratio > target_ratio:
                new_height = IMAGE_HEIGHT
                new_width = int(new_height * banner_ratio)
            else:
                new_width = IMAGE_WIDTH
                new_height = int(new_width / banner_ratio)

            banner_img = banner_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Center crop
            left = (new_width - IMAGE_WIDTH) // 2
            top = (new_height - IMAGE_HEIGHT) // 2
            banner_img = banner_img.crop((left, top, left + IMAGE_WIDTH, top + IMAGE_HEIGHT))

            # Blur and darken
            banner_img = banner_img.filter(ImageFilter.GaussianBlur(8))

            # Cache it
            self._banner_cache[guild_id] = (banner_img, today)
            return banner_img.copy()

        return None

    def _create_image(
        self,
        avatar_img: Optional[Image.Image] = None,
        banner_img: Optional[Image.Image] = None
    ) -> Image.Image:
        """Create the quote image background with avatar overlay."""

        # Start with banner or black background
        if banner_img:
            img = banner_img.convert("RGBA")
            # Add dark overlay to make text readable
            dark_overlay = Image.new("RGBA", img.size, (0, 0, 0, 140))
            img = Image.alpha_composite(img, dark_overlay)
        else:
            img = Image.new("RGBA", (IMAGE_WIDTH, IMAGE_HEIGHT), (*BG_COLOR, 255))

        # Add vignette effect (darker edges) - optimized with NumPy
        x = np.linspace(-1, 1, IMAGE_WIDTH)
        y = np.linspace(-1, 1, IMAGE_HEIGHT)
        xx, yy = np.meshgrid(x, y)
        dist = np.sqrt(xx**2 * 0.6 + yy**2)
        alpha = np.clip(dist ** 1.8 * 180, 0, 255).astype(np.uint8)
        vignette = Image.fromarray(np.dstack([
            np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.uint8),
            np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.uint8),
            np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.uint8),
            alpha
        ]), 'RGBA')
        vignette = vignette.filter(ImageFilter.GaussianBlur(30))
        img = Image.alpha_composite(img, vignette)

        # Add avatar on left side with fade effect
        if avatar_img:
            # Convert avatar
            if avatar_img.mode == "P":
                avatar_img = avatar_img.convert("RGBA")
            elif avatar_img.mode != "RGBA":
                avatar_img = avatar_img.convert("RGBA")

            # Resize avatar to fill left section height
            avatar_height = IMAGE_HEIGHT
            avatar_width = int(avatar_img.width * (avatar_height / avatar_img.height))
            avatar = avatar_img.resize((avatar_width, avatar_height), Image.Resampling.LANCZOS)

            # Create left section - much wider for ultra-smooth fade
            section_width = AVATAR_SECTION_WIDTH + 400
            left_section = Image.new("RGBA", (section_width, IMAGE_HEIGHT), (0, 0, 0, 0))

            # Center avatar in section
            avatar_x = (AVATAR_SECTION_WIDTH - avatar_width) // 2
            if avatar_x < 0:
                # Crop if too wide
                crop_x = -avatar_x
                avatar = avatar.crop((crop_x, 0, crop_x + section_width, avatar_height))
                avatar_x = 0

            left_section.paste(avatar, (avatar_x, 0))

            # Add ghosted overlay
            ghost = Image.new("RGBA", left_section.size, (255, 255, 255, 40))
            left_section = Image.alpha_composite(left_section, ghost)

            # Add theme color tint
            tint = Image.new("RGBA", left_section.size, (*THEME_COLOR, 60))
            left_section = Image.alpha_composite(left_section, tint)

            # Create horizontal fade mask - optimized with NumPy, ultra-smooth
            x = np.linspace(0, 1, section_width)
            alpha_row = (255 * (1 - x ** 0.35)).astype(np.uint8)  # Even more gradual
            fade_array = np.tile(alpha_row, (IMAGE_HEIGHT, 1))
            fade_mask = Image.fromarray(fade_array, 'L')
            fade_mask = fade_mask.filter(ImageFilter.GaussianBlur(50))  # More blur

            # Apply fade mask
            r, g, b, a = left_section.split()
            left_section = Image.merge("RGBA", (r, g, b, fade_mask))

            # Composite onto main image - shift left to hide edge
            img.paste(left_section, (-30, 0), left_section)

        return img  # Keep as RGBA for text overlays

    def _draw_text_shadow(
        self,
        img: Image.Image,
        pos: tuple,
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: tuple,
        shadow_color: tuple = (0, 0, 0),
        shadow_offset: int = 2,
        shadow_blur: int = 3
    ) -> None:
        """Draw text with emoji support and a subtle shadow effect."""
        x, y = pos
        draw = ImageDraw.Draw(img)

        # Strip emojis for shadow (no emoji support needed for shadows)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"  # dingbats
            "\U000024C2-\U0001F251"  # misc
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # symbols extended
            "\U00002600-\U000026FF"  # misc symbols
            "]+",
            flags=re.UNICODE
        )
        text_no_emoji = emoji_pattern.sub("", text)

        # Draw shadow layers for soft effect (text only, no emoji)
        for i in range(shadow_blur, 0, -1):
            alpha = int(80 / i)
            draw.text(
                (x + shadow_offset, y + shadow_offset + i),
                text_no_emoji,
                font=font,
                fill=(*shadow_color, alpha)
            )

        # Draw main text with emoji support - scale emojis to match font
        with Pilmoji(img) as pilmoji:
            pilmoji.text(
                (x, y),
                text,
                font=font,
                fill=fill,
                emoji_scale_factor=1.0,
                emoji_position_offset=(0, 8)
            )

    def _calculate_font_size(self, text: str, max_width: int, max_height: int) -> tuple[int, list[str]]:
        """Calculate optimal font size for the quote text. Returns (font_size, lines)."""
        # Smaller max size for cleaner look
        for size in range(52, 20, -2):
            font = self._get_font(size)
            lines = wrap_text(text, font, max_width)

            if len(lines) > 6:
                continue

            line_height = int(size * 1.4)
            total_height = len(lines) * line_height

            if total_height <= max_height:
                return size, lines

        # At minimum size, truncate if still too many lines
        font = self._get_font(20)
        lines = wrap_text(text, font, max_width)
        if len(lines) > 6:
            lines = lines[:5] + [lines[5][:40] + "..."]
            log.tree("Quote Text Truncated", [
                ("Original Lines", str(len(wrap_text(text, font, max_width)))),
                ("Truncated To", "6 lines"),
            ], emoji="⚠️")
        return 20, lines

    async def generate_quote(
        self,
        message_content: str,
        author_name: str,
        avatar_url: str,
        username: Optional[str] = None,
        guild_id: Optional[int] = None,
        banner_url: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> QuoteResult:
        """Generate a quote image in Make it a Quote style."""
        try:
            if not message_content or not message_content.strip():
                return QuoteResult(success=False, error="No message content")

            text = message_content.strip()
            if len(text) > 500:
                text = text[:497] + "..."

            # Fetch images
            avatar_img = await self._fetch_image(avatar_url)

            banner_img = None
            if banner_url and guild_id:
                banner_img = await self._get_banner(guild_id, banner_url)

            # Create the image
            img = self._create_image(avatar_img, banner_img)
            draw = ImageDraw.Draw(img)

            # === TEXT SECTION (right side - moved more right) ===
            text_x = AVATAR_SECTION_WIDTH + 120  # More to the right
            text_max_width = IMAGE_WIDTH - text_x - 50
            text_max_height = IMAGE_HEIGHT - 180

            # Calculate font size and get wrapped lines
            font_size, lines = self._calculate_font_size(text, text_max_width, text_max_height)
            quote_font = self._get_font(font_size)

            line_height = int(font_size * 1.4)
            total_text_height = len(lines) * line_height

            # Center vertically
            text_y = (IMAGE_HEIGHT - total_text_height - 70) // 2

            # === GOLD DECORATIVE QUOTE MARK ===
            quote_mark_font = self._get_font(120)
            draw.text(
                (text_x - 15, text_y - 60),
                "\u201C",  # Left double quotation mark "
                font=quote_mark_font,
                fill=(*ACCENT_GOLD, 100)  # Semi-transparent gold
            )

            # Draw quote text with shadow and emoji support
            for line in lines:
                self._draw_text_shadow(img, (text_x, text_y), line, quote_font, TEXT_COLOR)
                text_y += line_height

            # === GOLD SEPARATOR LINE ===
            line_y = text_y + 15
            draw.line(
                [(text_x, line_y), (text_x + 80, line_y)],
                fill=(*ACCENT_GOLD, 150),
                width=2
            )

            # === AUTHOR SECTION ===
            author_y = line_y + 20

            # "- AuthorName" in italic with shadow
            author_font = self._get_font(28, italic=True)
            author_text = f"- {author_name}"
            self._draw_text_shadow(img, (text_x, author_y), author_text, author_font, TEXT_COLOR)

            # "@username" and timestamp smaller and gray
            if username:
                username_font = self._get_font(18)
                username_text = f"@{username}"
                if timestamp:
                    username_text += f"  •  {timestamp}"
                username_y = author_y + 38
                draw.text((text_x, username_y), username_text, font=username_font, fill=SUBTEXT_COLOR)

            # === BRANDING WATERMARK ===
            brand_font = self._get_font(14)
            brand_text = "discord.gg/syria"
            brand_bbox = brand_font.getbbox(brand_text)
            brand_width = brand_bbox[2] - brand_bbox[0]
            draw.text(
                (IMAGE_WIDTH - brand_width - 25, IMAGE_HEIGHT - 30),
                brand_text,
                font=brand_font,
                fill=(*ACCENT_GOLD, 150)  # Semi-transparent gold
            )

            # === SUBTLE FILM GRAIN - optimized with NumPy ===
            noise = np.random.randint(108, 148, (IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.uint8)
            alpha = np.random.randint(0, 12, (IMAGE_HEIGHT, IMAGE_WIDTH), dtype=np.uint8)
            # Sparse grain - only 30% coverage
            mask = np.random.random((IMAGE_HEIGHT, IMAGE_WIDTH)) < 0.3
            alpha = (alpha * mask).astype(np.uint8)
            grain = Image.fromarray(np.dstack([noise, noise, noise, alpha]), 'RGBA')
            img = Image.alpha_composite(img, grain)

            # Save (convert to RGB for final output)
            output = io.BytesIO()
            if img.mode == "RGBA":
                # Flatten onto black background
                rgb_img = Image.new("RGB", img.size, BG_COLOR)
                rgb_img.paste(img, (0, 0), img.split()[3])
                rgb_img.save(output, format="PNG")
            else:
                img.save(output, format="PNG")
            output.seek(0)

            log.tree("Quote Generated", [
                ("Author", author_name),
                ("Length", f"{len(text)} chars"),
                ("Font", f"{font_size}px"),
                ("Banner", "Yes" if banner_img else "No"),
            ], emoji="💬")

            return QuoteResult(success=True, image_bytes=output.getvalue())

        except Exception as e:
            log.tree("Quote Generation Failed", [
                ("Error", str(e)),
            ], emoji="❌")
            return QuoteResult(success=False, error=str(e))


# =============================================================================
# Singleton
# =============================================================================

quote_service = QuoteService()
