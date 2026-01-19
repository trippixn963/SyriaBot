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
from src.core.logger import log
from src.core.colors import COLOR_ERROR, COLOR_WARNING
from src.services.image import image_service
from src.services.database import db
from src.services.image.views import ImageView
from src.utils.footer import set_footer


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
    """Commands for searching images."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="image",
        description="Search for images on Google"
    )
    @app_commands.describe(
        query="What to search for",
    )
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def image(
        self,
        interaction: discord.Interaction,
        query: str,
    ) -> None:
        """Search for images."""
        await interaction.response.defer()

        user = interaction.user
        if not isinstance(user, discord.Member) and interaction.guild:
            user = interaction.guild.get_member(user.id) or user

        log.tree("Image Command", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Query", query[:50] + "..." if len(query) > 50 else query),
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

            log.tree("Image Search Unavailable", [
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

            log.tree("Image Search Limit Reached", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Remaining", "0"),
            ], emoji="⚠️")
            return

        log.tree("Image Search Starting", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Query", query[:50] + "..." if len(query) > 50 else query),
            ("Remaining", "Unlimited" if remaining == -1 else str(remaining)),
        ], emoji="🔍")

        # Search for images
        result = await image_service.search(query, num_results=10)

        if not result.success:
            embed = discord.Embed(
                title="Search Failed",
                description=result.error or "An unknown error occurred.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)

            log.tree("Image Search Failed", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Query", query[:30]),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            return

        if not result.images:
            embed = discord.Embed(
                title="No Results",
                description=f"No images found for: **{query}**",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)

            log.tree("Image Search No Results", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Query", query[:30]),
            ], emoji="⚠️")
            return

        # Record usage (only for non-boosters)
        if remaining != -1:
            new_remaining = db.record_image_usage(user.id, config.IMAGE_WEEKLY_LIMIT)
            log.tree("Image Usage Recorded", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Remaining", str(new_remaining)),
            ], emoji="📊")
        else:
            new_remaining = -1

        # Create view and embed with attached image
        view = ImageView(
            images=result.images,
            query=query,
            requester_id=user.id,
            bot=self.bot,
        )
        embed, file = await view.create_embed_with_file()

        if file:
            msg = await interaction.followup.send(embed=embed, file=file, view=view)
            view.message = msg

            log.tree("Image Search Complete", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Query", query[:50] + "..." if len(query) > 50 else query),
                ("Results", str(len(result.images))),
                ("Position", f"{view.current_index + 1}/{len(result.images)}"),
                ("Remaining", "Unlimited" if new_remaining == -1 else str(new_remaining)),
            ], emoji="✅")
        else:
            # All images failed to download
            await interaction.followup.send(embed=embed, ephemeral=True)

            log.tree("Image Search All Failed", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Query", query[:50] + "..." if len(query) > 50 else query),
                ("Results Tried", str(len(result.images))),
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
                log.tree("Image Cooldown Response Failed", [
                    ("User", f"{interaction.user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

            log.tree("Image Command Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Retry After", f"{error.retry_after:.1f}s"),
            ], emoji="⏳")
            return

        log.error_tree("Image Command Error", error, [
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
            log.tree("Image Error Response Failed", [
                ("User", f"{interaction.user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")


# =============================================================================
# Setup
# =============================================================================

async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(ImageCog(bot))
    log.tree("Command Loaded", [
        ("Name", "image"),
        ("Weekly Limit", str(config.IMAGE_WEEKLY_LIMIT)),
    ], emoji="✅")
