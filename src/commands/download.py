"""
SyriaBot - Download Command
===========================

Slash command to download media from social media platforms.
Supported: Instagram, Twitter/X, TikTok, Reddit, Facebook, Snapchat, Twitch.
Free users: 5/week limit. Boosters: Unlimited.
Clean output: just the video + ping, no embeds.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from src.core.logger import logger
from src.core.config import config
from src.core.colors import COLOR_ERROR, COLOR_WARNING, EMOJI_SAVE
from src.core.constants import DELETE_DELAY_MEDIUM
from src.services.downloader import downloader
from src.services.database import db
from src.utils.footer import set_footer
from src.utils.permissions import create_cooldown


def _is_booster(member: discord.Member) -> bool:
    """Check if member is a server booster."""
    if not config.BOOSTER_ROLE_ID:
        return False
    return any(role.id == config.BOOSTER_ROLE_ID for role in member.roles)


async def _check_download_limit(user: discord.Member) -> tuple[bool, int, str]:
    """
    Check if user can download.

    Returns:
        (can_download, remaining, error_message)
    """
    # Boosters have unlimited downloads
    if _is_booster(user):
        return (True, -1, "")  # -1 = unlimited

    # Check weekly limit
    remaining, _ = db.get_download_usage(user.id, config.DOWNLOAD_WEEKLY_LIMIT)

    if remaining <= 0:
        next_reset = db.get_next_reset_timestamp()
        return (False, 0, f"You've used all {config.DOWNLOAD_WEEKLY_LIMIT} downloads this week.\nResets <t:{next_reset}:R>")

    return (True, remaining, "")


MAX_URL_LENGTH = 2048  # Reasonable limit for URLs


async def handle_download(
    interaction_or_message: discord.Interaction | discord.Message,
    url: str,
    is_reply: bool = False,
) -> None:
    """
    Handle download from both slash command and reply.
    Clean output: just files + ping, no status embeds.

    Args:
        interaction_or_message: Either an Interaction or Message
        url: The URL to download from
        is_reply: Whether this is from a reply (for cleanup)
    """
    is_interaction = isinstance(interaction_or_message, discord.Interaction)

    # Validate URL length to prevent abuse
    if len(url) > MAX_URL_LENGTH:
        error_msg = f"URL too long (max {MAX_URL_LENGTH} characters)"
        if is_interaction:
            await interaction_or_message.response.send_message(error_msg, ephemeral=True)
        else:
            await interaction_or_message.reply(error_msg, delete_after=10)
        return

    # Validate URL scheme (security: prevent file://, data://, etc.)
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ('http', 'https'):
            error_msg = "Invalid URL. Only http:// and https:// URLs are supported."
            if is_interaction:
                await interaction_or_message.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction_or_message.reply(error_msg, delete_after=10)
            logger.tree("Download URL Rejected", [
                ("Reason", "Invalid scheme"),
                ("Scheme", parsed.scheme or "empty"),
                ("URL", url[:50] + "..." if len(url) > 50 else url),
            ], emoji="🚫")
            return
    except Exception as e:
        error_msg = "Invalid URL format."
        if is_interaction:
            await interaction_or_message.response.send_message(error_msg, ephemeral=True)
        else:
            await interaction_or_message.reply(error_msg, delete_after=10)
        logger.tree("Download URL Parse Failed", [
            ("Error", str(e)[:100]),
            ("URL", url[:50] + "..." if len(url) > 50 else url),
        ], emoji="⚠️")
        return

    if is_interaction:
        user = interaction_or_message.user
        channel = interaction_or_message.channel
        guild = interaction_or_message.guild
    else:
        user = interaction_or_message.author
        channel = interaction_or_message.channel
        guild = interaction_or_message.guild

    # Check if user is a member (needed for booster check)
    if not isinstance(user, discord.Member):
        if guild:
            user = guild.get_member(user.id) or user

    # Check download limit (ephemeral error if limit reached)
    can_download, remaining, error_msg = await _check_download_limit(user)

    if not can_download:
        embed = discord.Embed(
            title="Download Limit Reached",
            description=error_msg,
            color=COLOR_WARNING
        )
        embed.add_field(
            name="Want Unlimited Downloads?",
            value="Boost the server to get unlimited downloads!",
            inline=False
        )
        set_footer(embed)

        if is_interaction:
            await interaction_or_message.followup.send(embed=embed, ephemeral=True)
        else:
            msg = await interaction_or_message.reply(embed=embed, mention_author=False)
            # Auto-delete limit message after medium delay
            await msg.delete(delay=DELETE_DELAY_MEDIUM)
            try:
                await interaction_or_message.delete()
            except discord.HTTPException as e:
                logger.tree("Delete Failed (Limit)", [
                    ("User", f"{user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        logger.tree("Download Limit Reached", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Remaining", "0"),
        ], emoji="⚠️")
        return

    # Detect platform
    platform = downloader.get_platform(url)

    if not platform:
        embed = discord.Embed(
            title="Unsupported URL",
            description="Supported platforms: Instagram, Twitter/X, TikTok, Reddit, Facebook, Snapchat, Twitch.",
            color=COLOR_ERROR
        )
        set_footer(embed)

        if is_interaction:
            await interaction_or_message.followup.send(embed=embed, ephemeral=True)
        else:
            msg = await interaction_or_message.reply(embed=embed, mention_author=False)
            await msg.delete(delay=DELETE_DELAY_MEDIUM)
            try:
                await interaction_or_message.delete()
            except discord.HTTPException as e:
                logger.tree("Delete Failed (Unsupported)", [
                    ("User", f"{user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        logger.tree("Download Unsupported URL", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("URL", url[:60]),
        ], emoji="⚠️")
        return

    logger.tree("Download Starting", [
        ("User", f"{user.name} ({user.display_name})"),
        ("ID", str(user.id)),
        ("Platform", platform.title()),
        ("URL", url[:60] + "..." if len(url) > 60 else url),
        ("Remaining", "Unlimited" if remaining == -1 else str(remaining)),
    ], emoji="📥")

    # Track the reply message for deletion AFTER successful download
    # (don't delete early - user needs the URL if download fails)
    reply_to_delete = interaction_or_message if is_reply and isinstance(interaction_or_message, discord.Message) else None

    # Send progress message
    progress_msg = None
    try:
        if is_interaction:
            progress_msg = await interaction_or_message.followup.send(
                f"{EMOJI_SAVE} Downloading from **{platform.title()}**...",
                wait=True
            )
        else:
            progress_msg = await channel.send(
                f"{EMOJI_SAVE} Downloading from **{platform.title()}**..."
            )
        logger.tree("Download Progress Sent", [
            ("User", f"{user.name}"),
            ("Platform", platform.title()),
        ], emoji="💬")
    except discord.HTTPException as e:
        logger.tree("Download Progress Send Failed", [
            ("User", f"{user.name}"),
            ("Error", str(e)[:50]),
        ], emoji="⚠️")

    # Download
    result = await downloader.download(url)

    # Update progress message
    if progress_msg and result.success and len(result.files) > 0:
        try:
            await progress_msg.edit(
                content=f"{EMOJI_SAVE} Processing **{len(result.files)}** file(s)..."
            )
            logger.tree("Download Progress Updated", [
                ("User", f"{user.name}"),
                ("Files", str(len(result.files))),
            ], emoji="💬")
        except discord.HTTPException as e:
            logger.tree("Download Progress Update Failed", [
                ("User", f"{user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    if not result.success:
        # Delete progress message
        if progress_msg:
            try:
                await progress_msg.delete()
                logger.tree("Download Progress Deleted", [
                    ("Reason", "Download failed"),
                ], emoji="🗑️")
            except discord.HTTPException as e:
                logger.tree("Progress Delete Failed", [
                    ("User", f"{user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        # Send ephemeral-like error (auto-delete for replies)
        embed = discord.Embed(
            title="Download Failed",
            description=result.error or "An unknown error occurred.",
            color=COLOR_ERROR
        )
        set_footer(embed)

        if is_interaction:
            await interaction_or_message.followup.send(embed=embed, ephemeral=True)
        else:
            msg = await channel.send(embed=embed)
            await msg.delete(delay=DELETE_DELAY_MEDIUM)

        logger.tree("Download Failed", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Platform", platform.title()),
            ("Error", result.error[:50] if result.error else "Unknown"),
        ], emoji="❌")
        return

    # Record usage (only for non-boosters)
    if remaining != -1:
        new_remaining = db.record_download_usage(user.id, config.DOWNLOAD_WEEKLY_LIMIT)
        logger.tree("Download Usage Recorded", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Remaining", str(new_remaining)),
        ], emoji="📊")
    else:
        new_remaining = -1

    # Record lifetime download stats
    db.record_download_stats(user.id, platform, file_count=len(result.files))

    # Upload files - just the video + ping, no embed
    try:
        files = []
        total_size = 0

        for file_path in result.files:
            total_size += file_path.stat().st_size
            discord_file = discord.File(file_path, filename=file_path.name)
            files.append(discord_file)

        # Delete progress message before sending files
        if progress_msg:
            try:
                await progress_msg.delete()
                logger.tree("Download Progress Deleted", [
                    ("Reason", "Sending files"),
                ], emoji="🗑️")
            except discord.HTTPException as e:
                logger.tree("Progress Delete Failed", [
                    ("User", f"{user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        # Send just files with ping - no embed
        await channel.send(content=f"<@{user.id}>", files=files)

        # Delete the original reply message NOW (after success)
        if reply_to_delete:
            try:
                await reply_to_delete.delete()
                logger.tree("Download Reply Deleted", [
                    ("User", f"{user.name}"),
                    ("Channel", str(channel.id)),
                ], emoji="🗑️")
            except discord.HTTPException as e:
                logger.tree("Download Reply Delete Failed", [
                    ("User", f"{user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        logger.tree("Download Complete", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Platform", platform.title()),
            ("Files", str(len(files))),
            ("Size", downloader.format_size(total_size)),
            ("Remaining", "Unlimited" if new_remaining == -1 else str(new_remaining)),
        ], emoji="✅")

    except discord.HTTPException as e:
        # Delete progress message on error too
        if progress_msg:
            try:
                await progress_msg.delete()
                logger.tree("Download Progress Deleted", [
                    ("Reason", "Upload failed"),
                ], emoji="🗑️")
            except discord.HTTPException as del_e:
                logger.tree("Progress Delete Failed", [
                    ("User", f"{user.name}"),
                    ("Error", str(del_e)[:50]),
                ], emoji="⚠️")

        embed = discord.Embed(
            title="Upload Failed",
            description="The file couldn't be uploaded to Discord. It may be too large.",
            color=COLOR_ERROR
        )
        set_footer(embed)

        if is_interaction:
            await interaction_or_message.followup.send(embed=embed, ephemeral=True)
        else:
            msg = await channel.send(embed=embed)
            await msg.delete(delay=DELETE_DELAY_MEDIUM)

        logger.tree("Download Upload Failed", [
            ("User", f"{user.name} ({user.display_name})"),
            ("ID", str(user.id)),
            ("Error", str(e)[:50]),
        ], emoji="❌")

    finally:
        # Cleanup temp files
        if result.files:
            download_dir = result.files[0].parent
            downloader.cleanup([download_dir])


class DownloadCog(commands.Cog):
    """
    Commands for downloading social media content.

    DESIGN:
        Downloads media from Instagram, Twitter/X, TikTok, Reddit, Facebook,
        Snapchat, and Twitch. Uses Cobalt API with yt-dlp fallback.
        Rate limited: 5 downloads/week for free users, unlimited for boosters.
        Clean output: sends just the video file + user ping, no embed clutter.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the download cog.

        Args:
            bot: Main bot instance for channel access.
        """
        self.bot = bot

    @app_commands.command(
        name="download",
        description="Download media from Instagram, Twitter, TikTok, Reddit & more"
    )
    @app_commands.describe(url="URL to download (Instagram, Twitter, TikTok, Reddit, Facebook, Snapchat, Twitch)")
    @app_commands.checks.dynamic_cooldown(create_cooldown(1, 300))
    async def download(self, interaction: discord.Interaction, url: str) -> None:
        """Download media from a social media URL."""
        await interaction.response.defer()
        await handle_download(interaction, url, is_reply=False)

    @download.error
    async def download_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """Handle download command errors."""
        if isinstance(error, app_commands.CommandOnCooldown):
            embed = discord.Embed(
                description=f"Please wait {error.retry_after:.1f}s before downloading again.",
                color=COLOR_WARNING
            )
            set_footer(embed)

            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.HTTPException as e:
                logger.tree("Cooldown Response Failed", [
                    ("User", f"{interaction.user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

            logger.tree("Download Command Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Retry After", f"{error.retry_after:.1f}s"),
            ], emoji="⏳")
            return

        logger.error_tree("Download Command Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ])

        try:
            embed = discord.Embed(
                description="An error occurred while downloading.",
                color=COLOR_ERROR
            )
            set_footer(embed)

            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            logger.tree("Error Response Failed", [
                ("User", f"{interaction.user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(DownloadCog(bot))
    logger.tree("Command Loaded", [
        ("Name", "download"),
        ("Weekly Limit", str(config.DOWNLOAD_WEEKLY_LIMIT)),
    ], emoji="✅")
