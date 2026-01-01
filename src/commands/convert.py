"""
SyriaBot - Convert Command
==========================

Slash command for converting images/videos to GIFs with text bars.
Now with interactive editor for customization.
Supports both images and short videos (max 15 seconds).

Author: Unknown
"""

import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import log
from src.services.convert_service import convert_service
from src.services.database import db
from src.views.convert_view import start_convert_editor
from src.utils.footer import set_footer


# Consistent colors
COLOR_SUCCESS = 0x43b581  # Green
COLOR_ERROR = 0xf04747    # Red
COLOR_WARNING = 0xfaa61a  # Orange
COLOR_BOOST = 0xf47fff    # Nitro pink


# =============================================================================
# Rate Limit Helpers
# =============================================================================

def has_unlimited_convert(member: discord.Member) -> bool:
    """Check if member has unlimited convert access (mod or booster)."""
    # Check if booster
    if member.premium_since is not None:
        return True

    # Check if mod
    if config.MOD_ROLE_ID:
        mod_role = member.guild.get_role(config.MOD_ROLE_ID)
        if mod_role and mod_role in member.roles:
            return True

    return False


def create_boost_embed(member: discord.Member, reset_timestamp: int) -> discord.Embed:
    """Create an embed motivating users to boost for unlimited converts."""
    embed = discord.Embed(
        title="<a:boost:1322405893303328829> Want Unlimited Converts?",
        description=(
            f"You've used all **3 converts** for this week!\n\n"
            f"**Boost the server** to unlock:\n"
            f"<:check:1324165574191439953> **Unlimited** /convert usage\n"
            f"<:check:1324165574191439953> Support the community\n"
            f"<:check:1324165574191439953> Exclusive booster perks\n\n"
            f"Your limit resets <t:{reset_timestamp}:R> (<t:{reset_timestamp}:F>)"
        ),
        color=COLOR_BOOST
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1322405893303328829.gif")
    set_footer(embed)
    return embed


# =============================================================================
# URL Patterns (pre-compiled for performance)
# =============================================================================

IMAGE_URL_PATTERN = re.compile(
    r"https?://\S+\.(?:png|jpg|jpeg|gif|webp)(?:\?\S*)?",
    re.IGNORECASE
)

VIDEO_URL_PATTERN = re.compile(
    r"https?://\S+\.(?:mp4|mov|webm|avi|mkv)(?:\?\S*)?",
    re.IGNORECASE
)

MEDIA_URL_PATTERN = re.compile(
    r"https?://\S+\.(?:png|jpg|jpeg|gif|webp|mp4|mov|webm|avi|mkv)(?:\?\S*)?",
    re.IGNORECASE
)

# Supported media hosting sites (don't require file extension)
TENOR_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?tenor\.com/view/[\w-]+",
    re.IGNORECASE
)

GIPHY_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?giphy\.com/gifs/[\w-]+",
    re.IGNORECASE
)

IMGUR_URL_PATTERN = re.compile(
    r"https?://(?:www\.|i\.)?imgur\.com/(?:a/|gallery/)?[\w]+",
    re.IGNORECASE
)

REDDIT_URL_PATTERN = re.compile(
    r"https?://(?:www\.|i\.|preview\.)?redd\.it/[\w]+|https?://(?:www\.)?reddit\.com/media\?url=",
    re.IGNORECASE
)

DISCORD_CDN_PATTERN = re.compile(
    r"https?://(?:cdn|media)\.discord(?:app)?\.com/attachments/\d+/\d+/[\w.-]+",
    re.IGNORECASE
)

TWITTER_MEDIA_PATTERN = re.compile(
    r"https?://pbs\.twimg\.com/media/[\w-]+",
    re.IGNORECASE
)


# =============================================================================
# Convert Cog
# =============================================================================

class ConvertCog(commands.Cog):
    """Cog for the /convert command."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="convert",
        description="Convert an image or video to GIF with customizable text bar"
    )
    @app_commands.describe(
        media="Image or video to convert (attachment)",
        url="Media URL to convert (if no attachment)",
    )
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    async def convert(
        self,
        interaction: discord.Interaction,
        media: Optional[discord.Attachment] = None,
        url: Optional[str] = None,
    ) -> None:
        """Convert an image or video with interactive editor."""
        await interaction.response.defer()

        # Check rate limit for non-boosters/non-mods
        is_unlimited = has_unlimited_convert(interaction.user)

        if not is_unlimited:
            uses_remaining, _ = db.get_convert_usage(interaction.user.id)

            if uses_remaining <= 0:
                reset_timestamp = db.get_next_reset_timestamp()
                embed = create_boost_embed(interaction.user, reset_timestamp)
                await interaction.followup.send(embed=embed, ephemeral=True)
                log.tree("Convert Rate Limited", [
                    ("User", str(interaction.user)),
                    ("Resets", f"<t:{reset_timestamp}:R>"),
                ], emoji="⏳")
                return

        # Validate input - need either attachment or URL
        if not media and not url:
            embed = discord.Embed(description="⚠️ Please provide an image/video attachment or URL", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get media data
        media_data: Optional[bytes] = None
        source_name = "unknown"
        is_video = False

        if media:
            # Check if it's an image or video
            content_type = media.content_type or ""
            is_image = content_type.startswith("image/")
            is_video = content_type.startswith("video/")

            if not is_image and not is_video:
                # Try to detect from filename
                if convert_service.is_image(media.filename):
                    is_image = True
                elif convert_service.is_video(media.filename):
                    is_video = True
                else:
                    embed = discord.Embed(description="⚠️ Attachment must be an image (PNG, JPG, GIF, WebP) or video (MP4, MOV, WebM)", color=COLOR_WARNING)
                    set_footer(embed)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

            # Check file size
            max_size = 25 * 1024 * 1024 if is_video else 8 * 1024 * 1024
            if media.size > max_size:
                embed = discord.Embed(description=f"⚠️ File too large. Maximum size is {25 if is_video else 8}MB", color=COLOR_WARNING)
                set_footer(embed)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                media_data = await media.read()
                source_name = media.filename
            except Exception as e:
                log.tree("Attachment Read Failed", [
                    ("User", str(interaction.user)),
                    ("File", media.filename),
                    ("Error", str(e)),
                ], emoji="❌")
                embed = discord.Embed(description="❌ Failed to read attachment. Please try again", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

        elif url:
            # Check if it's a supported hosting site
            is_tenor = TENOR_URL_PATTERN.match(url) is not None
            is_giphy = GIPHY_URL_PATTERN.match(url) is not None
            is_imgur = IMGUR_URL_PATTERN.match(url) is not None
            is_reddit = REDDIT_URL_PATTERN.match(url) is not None
            is_discord = DISCORD_CDN_PATTERN.match(url) is not None
            is_twitter = TWITTER_MEDIA_PATTERN.match(url) is not None
            is_direct_media = MEDIA_URL_PATTERN.match(url) is not None

            is_supported_host = is_tenor or is_giphy or is_imgur or is_reddit or is_discord or is_twitter

            # Validate URL format
            if not is_direct_media and not is_supported_host:
                embed = discord.Embed(
                    description="⚠️ Invalid URL\nSupported: direct media URLs (.png, .jpg, .gif, .mp4) or Tenor, Giphy, Imgur, Reddit, Discord, Twitter",
                    color=COLOR_WARNING
                )
                set_footer(embed)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Determine if it's a video URL (Tenor embeds as video)
            is_video = VIDEO_URL_PATTERN.match(url) is not None or is_tenor

            media_data = await convert_service.fetch_media(url)
            if not media_data:
                embed = discord.Embed(description="❌ Failed to fetch media from URL. Make sure it's valid and accessible", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Set friendly source name
            if is_tenor:
                source_name = "tenor.gif"
            elif is_giphy:
                source_name = "giphy.gif"
            elif is_imgur:
                source_name = "imgur.gif"
            else:
                source_name = url.split("/")[-1].split("?")[0]

        # Record usage for non-unlimited users
        if not is_unlimited:
            remaining = db.record_convert_usage(interaction.user.id)
            log.tree("Convert Command", [
                ("User", str(interaction.user)),
                ("Source", source_name[:50]),
                ("Type", "Video" if is_video else "Image"),
                ("Uses Left", str(remaining)),
            ], emoji="CONVERT")
        else:
            log.tree("Convert Command", [
                ("User", str(interaction.user)),
                ("Source", source_name[:50]),
                ("Type", "Video" if is_video else "Image"),
                ("Access", "Unlimited"),
            ], emoji="CONVERT")

        # Start interactive editor
        await start_convert_editor(
            interaction_or_message=interaction,
            image_data=media_data,
            source_name=source_name,
            is_video=is_video,
        )

    @convert.error
    async def convert_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """Handle errors for the convert command."""
        if isinstance(error, app_commands.CommandOnCooldown):
            embed = discord.Embed(description=f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s", color=COLOR_WARNING)
            set_footer(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            log.tree("Convert Command Error", [
                ("User", str(interaction.user)),
                ("Error", f"{type(error).__name__}: {str(error)}"),
            ], emoji="❌")
            if not interaction.response.is_done():
                embed = discord.Embed(description="❌ An error occurred while processing your request", color=COLOR_ERROR)
                set_footer(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)


# =============================================================================
# Setup
# =============================================================================

async def setup(bot: commands.Bot) -> None:
    """Load the Convert cog."""
    await bot.add_cog(ConvertCog(bot))
    log.success("Convert Cog loaded")
