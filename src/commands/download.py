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

import discord
from discord import app_commands
from discord.ext import commands

from src.core.logger import log
from src.core.config import config
from src.core.colors import COLOR_ERROR, COLOR_WARNING
from src.services.downloader import downloader
from src.services.database import db
from src.utils.footer import set_footer


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
            # Auto-delete limit message after 10 seconds
            await msg.delete(delay=10)
            try:
                await interaction_or_message.delete()
            except discord.HTTPException:
                pass

        log.tree("Download Limit Reached", [
            ("User", f"{user.name} ({user.display_name})"),
            ("User ID", str(user.id)),
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
            await msg.delete(delay=10)
            try:
                await interaction_or_message.delete()
            except discord.HTTPException:
                pass

        log.tree("Download Unsupported URL", [
            ("User", f"{user.name}"),
            ("User ID", str(user.id)),
            ("URL", url[:60]),
        ], emoji="⚠️")
        return

    log.tree("Download Starting", [
        ("User", f"{user.name} ({user.display_name})"),
        ("User ID", str(user.id)),
        ("Platform", platform.title()),
        ("URL", url[:60] + "..." if len(url) > 60 else url),
        ("Remaining", "Unlimited" if remaining == -1 else str(remaining)),
    ], emoji="📥")

    # Delete the "download" reply message immediately (clean UI)
    if is_reply and isinstance(interaction_or_message, discord.Message):
        try:
            await interaction_or_message.delete()
            log.tree("Download Reply Deleted", [
                ("User", f"{user.name}"),
                ("Channel", str(channel.id)),
            ], emoji="🗑️")
        except discord.HTTPException as e:
            log.tree("Download Reply Delete Failed", [
                ("User", f"{user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    # Send progress message
    progress_msg = None
    try:
        if is_interaction:
            progress_msg = await interaction_or_message.followup.send(
                f"<:save:1455776703468273825> Downloading from **{platform.title()}**...",
                wait=True
            )
        else:
            progress_msg = await channel.send(
                f"<:save:1455776703468273825> Downloading from **{platform.title()}**..."
            )
        log.tree("Download Progress Sent", [
            ("User", f"{user.name}"),
            ("Platform", platform.title()),
        ], emoji="💬")
    except discord.HTTPException as e:
        log.tree("Download Progress Send Failed", [
            ("User", f"{user.name}"),
            ("Error", str(e)[:50]),
        ], emoji="⚠️")

    # Download
    result = await downloader.download(url)

    # Update progress message
    if progress_msg and result.success and len(result.files) > 0:
        try:
            await progress_msg.edit(
                content=f"<:save:1455776703468273825> Processing **{len(result.files)}** file(s)..."
            )
            log.tree("Download Progress Updated", [
                ("User", f"{user.name}"),
                ("Files", str(len(result.files))),
            ], emoji="💬")
        except discord.HTTPException as e:
            log.tree("Download Progress Update Failed", [
                ("User", f"{user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    if not result.success:
        # Delete progress message
        if progress_msg:
            try:
                await progress_msg.delete()
                log.tree("Download Progress Deleted", [
                    ("Reason", "Download failed"),
                ], emoji="🗑️")
            except discord.HTTPException:
                pass

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
            await msg.delete(delay=10)

        log.tree("Download Failed", [
            ("User", f"{user.name}"),
            ("User ID", str(user.id)),
            ("Platform", platform.title()),
            ("Error", result.error[:50] if result.error else "Unknown"),
        ], emoji="❌")
        return

    # Record usage (only for non-boosters)
    if remaining != -1:
        new_remaining = db.record_download_usage(user.id, config.DOWNLOAD_WEEKLY_LIMIT)
        log.tree("Download Usage Recorded", [
            ("User", f"{user.name}"),
            ("User ID", str(user.id)),
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
                log.tree("Download Progress Deleted", [
                    ("Reason", "Sending files"),
                ], emoji="🗑️")
            except discord.HTTPException:
                pass

        # Send just files with ping - no embed
        await channel.send(content=f"<@{user.id}>", files=files)

        log.tree("Download Complete", [
            ("User", f"{user.name} ({user.display_name})"),
            ("User ID", str(user.id)),
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
                log.tree("Download Progress Deleted", [
                    ("Reason", "Upload failed"),
                ], emoji="🗑️")
            except discord.HTTPException:
                pass

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
            await msg.delete(delay=10)

        log.tree("Download Upload Failed", [
            ("User", f"{user.name}"),
            ("User ID", str(user.id)),
            ("Error", str(e)[:50]),
        ], emoji="❌")

    finally:
        # Cleanup temp files
        if result.files:
            download_dir = result.files[0].parent
            downloader.cleanup([download_dir])


class DownloadCog(commands.Cog):
    """Commands for downloading social media content."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="download",
        description="Download media from Instagram, Twitter, TikTok, Reddit & more"
    )
    @app_commands.describe(url="URL to download (Instagram, Twitter, TikTok, Reddit, Facebook, Snapchat, Twitch)")
    @app_commands.checks.cooldown(1, 300, key=lambda i: i.user.id)
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
            except discord.HTTPException:
                pass

            log.tree("Download Command Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("User ID", str(interaction.user.id)),
                ("Retry After", f"{error.retry_after:.1f}s"),
            ], emoji="⏳")
            return

        log.error_tree("Download Command Error", error, [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
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
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(DownloadCog(bot))
    log.tree("Command Loaded", [
        ("Name", "download"),
        ("Weekly Limit", str(config.DOWNLOAD_WEEKLY_LIMIT)),
    ], emoji="✅")
