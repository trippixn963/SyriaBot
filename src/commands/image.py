"""
SyriaBot - Image Command
========================

Slash command to search for images using Google Custom Search.
Free users: 5/week limit. Boosters: Unlimited.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import logger
from src.core.colors import COLOR_ERROR, COLOR_WARNING
from src.services.image import image_service
from src.services.database import db
from src.services.image.views import ImageView
from src.utils.footer import set_footer
from src.utils.permissions import create_cooldown


# Minimum images we want after filtering - if below this, fetch more
MIN_IMAGES_AFTER_FILTER = 5


class ImageSize:
    """Image size choices for the command."""
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"


def _is_booster(member: discord.Member) -> bool:
    """Check if member is a server booster."""
    if not config.BOOSTER_ROLE_ID:
        return False
    return any(role.id == config.BOOSTER_ROLE_ID for role in member.roles)


async def _check_image_limit(user: discord.Member) -> tuple[bool, int, str]:
    """
    Check if user can search for images.

    Returns:
        (can_search, remaining, error_message)
    """
    # Boosters have unlimited searches
    if _is_booster(user):
        return (True, -1, "")  # -1 = unlimited

    # Check weekly limit
    remaining, _ = db.get_image_usage(user.id, config.IMAGE_WEEKLY_LIMIT)

    if remaining <= 0:
        next_reset = db.get_next_reset_timestamp()
        return (False, 0, f"You've used all {config.IMAGE_WEEKLY_LIMIT} image searches this week.\nResets <t:{next_reset}:R>")

    return (True, remaining, "")


# =============================================================================
# Image Cog
# =============================================================================

class ImageCog(commands.Cog):
    """
    Commands for searching images.

    DESIGN:
        Uses Google Custom Search API for image search with pagination.
        Rate limited: 5 searches/week for free users, unlimited for boosters.
        Images are proxied through bot to avoid embed failures.
        Interactive view with prev/next buttons for browsing results.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the image cog.

        Args:
            bot: Main bot instance for view message tracking.
        """
        self.bot = bot

    @app_commands.command(
        name="image",
        description="Search for images on Google"
    )
    @app_commands.describe(
        subject="What to search for",
        size="Image size preference (default: large)",
    )
    @app_commands.choices(size=[
        app_commands.Choice(name="Medium", value=ImageSize.MEDIUM),
        app_commands.Choice(name="Large (Recommended)", value=ImageSize.LARGE),
        app_commands.Choice(name="Extra Large", value=ImageSize.XLARGE),
    ])
    @app_commands.checks.dynamic_cooldown(create_cooldown(1, 60))
    async def image(
        self,
        interaction: discord.Interaction,
        subject: str,
        size: str = ImageSize.LARGE,
    ) -> None:
        """Search for images."""
        await interaction.response.defer()

        user = interaction.user
        if not isinstance(user, discord.Member) and interaction.guild:
            user = interaction.guild.get_member(user.id) or user

        logger.tree("Image Command", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Subject", subject[:50] + "..." if len(subject) > 50 else subject),
        ], emoji="🖼️")

        # Check if service is available
        if not image_service.is_available:
            embed = discord.Embed(
                title="Image Search Unavailable",
                description="Image search is not configured. Contact the bot owner.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.tree("Image Search Unavailable", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Reason", "Service not configured"),
            ], emoji="❌")
            return

        # Check weekly limit
        can_search, remaining, error_msg = await _check_image_limit(user)

        if not can_search:
            embed = discord.Embed(
                title="Image Search Limit Reached",
                description=error_msg,
                color=COLOR_WARNING
            )
            embed.add_field(
                name="Want Unlimited Searches?",
                value="Boost the server to get unlimited image searches!",
                inline=False
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.tree("Image Search Limit Reached", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Remaining", "0"),
            ], emoji="⚠️")
            return

        logger.tree("Image Search Starting", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Subject", subject[:50] + "..." if len(subject) > 50 else subject),
            ("Size", size),
            ("Remaining", "Unlimited" if remaining == -1 else str(remaining)),
        ], emoji="🔍")

        # Search for images (first batch)
        result = await image_service.search(subject, num_results=10, img_size=size)

        if not result.success:
            embed = discord.Embed(
                title="Search Failed",
                description=result.error or "An unknown error occurred.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.tree("Image Search Failed", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Subject", subject[:30]),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            return

        # If too few images after filtering, fetch more
        all_images = result.images
        if len(all_images) < MIN_IMAGES_AFTER_FILTER:
            logger.tree("Image Search Fetching More", [
                ("Current", str(len(all_images))),
                ("Min Required", str(MIN_IMAGES_AFTER_FILTER)),
                ("Action", "Fetching second batch"),
            ], emoji="🔄")

            # Fetch second batch starting at index 11
            result2 = await image_service.search(subject, num_results=10, img_size=size, start_index=11)
            if result2.success and result2.images:
                all_images.extend(result2.images)
                logger.tree("Image Search Extended", [
                    ("Total", str(len(all_images))),
                    ("Added", str(len(result2.images))),
                ], emoji="✅")

        if not all_images:
            embed = discord.Embed(
                title="No Results",
                description=f"No images found for: **{subject}**\nTry a different size or search term.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.tree("Image Search No Results", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Subject", subject[:30]),
                ("Size", size),
            ], emoji="⚠️")
            return

        # Record usage (only for non-boosters)
        if remaining != -1:
            new_remaining = db.record_image_usage(user.id, config.IMAGE_WEEKLY_LIMIT)
            logger.tree("Image Usage Recorded", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Remaining", str(new_remaining)),
            ], emoji="📊")
        else:
            new_remaining = -1

        # Create view and embed with attached image
        view = ImageView(
            images=all_images,
            query=subject,
            requester_id=user.id,
            bot=self.bot,
        )
        embed, file = await view.create_embed_with_file()

        if file:
            msg = await interaction.followup.send(embed=embed, file=file, view=view)
            view.message = msg

            logger.tree("Image Search Complete", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Subject", subject[:50] + "..." if len(subject) > 50 else subject),
                ("Size", size),
                ("Results", str(len(all_images))),
                ("Position", f"{view.current_index + 1}/{len(all_images)}"),
                ("Remaining", "Unlimited" if new_remaining == -1 else str(new_remaining)),
            ], emoji="✅")
        else:
            # All images failed to download
            await interaction.followup.send(embed=embed, ephemeral=True)

            logger.tree("Image Search All Failed", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Subject", subject[:50] + "..." if len(subject) > 50 else subject),
                ("Results Tried", str(len(all_images))),
            ], emoji="❌")

    @image.error
    async def image_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """Handle image command errors."""
        if isinstance(error, app_commands.CommandOnCooldown):
            embed = discord.Embed(
                description=f"Please wait {error.retry_after:.1f}s before searching again.",
                color=COLOR_WARNING
            )
            set_footer(embed)

            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.HTTPException as e:
                logger.tree("Image Cooldown Response Failed", [
                    ("User", f"{interaction.user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

            logger.tree("Image Command Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Retry After", f"{error.retry_after:.1f}s"),
            ], emoji="⏳")
            return

        logger.error_tree("Image Command Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ])

        try:
            embed = discord.Embed(
                description="An error occurred while searching.",
                color=COLOR_ERROR
            )
            set_footer(embed)

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            logger.tree("Image Error Response Failed", [
                ("User", f"{interaction.user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")


# =============================================================================
# Setup
# =============================================================================

async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(ImageCog(bot))
    logger.tree("Command Loaded", [
        ("Name", "image"),
        ("Weekly Limit", str(config.IMAGE_WEEKLY_LIMIT)),
    ], emoji="✅")
