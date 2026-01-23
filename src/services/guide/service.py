"""
SyriaBot - Guide Service
========================

Handles hourly auto-update of the guide panel with live server stats.

Author: John Hamwi
Server: discord.gg/syria
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import tasks

from src.core.logger import logger
from src.core.config import config
from src.core.colors import COLOR_SYRIA_GREEN
from src.core.constants import TIMEZONE_EST
from src.utils.footer import set_footer
from src.services.database import db
from src.services.guide.views import GuideView

if TYPE_CHECKING:
    from discord.ext.commands import Bot


class GuideService:
    """
    Service for managing the guide panel auto-updates.

    Updates the guide panel embed every hour with live server stats.
    """

    def __init__(self, bot: Bot) -> None:
        """
        Initialize the guide service.

        Args:
            bot: The Discord bot instance.
        """
        self.bot: Bot = bot
        self._running: bool = False

        logger.tree("Guide Service Init", [
            ("Status", "Created"),
        ], emoji="📋")

    async def setup(self) -> None:
        """Start the hourly update task."""
        if self._running:
            logger.tree("Guide Service Setup", [
                ("Status", "Already running"),
            ], emoji="ℹ️")
            return

        self._update_task.start()
        self._running = True

        logger.tree("Guide Service Started", [
            ("Task", "Hourly update"),
            ("Timezone", "EST"),
        ], emoji="✅")

    def stop(self) -> None:
        """Stop the hourly update task."""
        if self._running:
            self._update_task.cancel()
            self._running = False
            logger.tree("Guide Service Stopped", [], emoji="🛑")

    @tasks.loop(minutes=1)
    async def _update_task(self) -> None:
        """
        Check every minute if it's the top of the hour EST.
        If so, update the guide panel.
        """
        now = datetime.now(TIMEZONE_EST)

        # Only run at the top of each hour (minute 0)
        if now.minute != 0:
            return

        logger.tree("Guide Update Task", [
            ("Time", now.strftime("%Y-%m-%d %H:%M EST")),
            ("Status", "Running"),
        ], emoji="🕐")

        await self._update_guide_panel()

    @_update_task.before_loop
    async def _before_update_task(self) -> None:
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()
        logger.tree("Guide Update Task Ready", [
            ("Status", "Waiting for top of hour"),
        ], emoji="⏰")

    async def _update_guide_panel(self) -> None:
        """
        Update the guide panel embed with current server stats.
        """
        guild_id = config.GUILD_ID
        if not guild_id:
            logger.tree("Guide Update Skipped", [
                ("Reason", "No GUILD_ID configured"),
            ], emoji="⚠️")
            return

        # Get stored panel info
        panel_info = db.get_guide_panel(guild_id)
        if not panel_info:
            logger.tree("Guide Update Skipped", [
                ("Guild", str(guild_id)),
                ("Reason", "No panel info stored"),
            ], emoji="ℹ️")
            return

        channel_id: int = panel_info["channel_id"]
        message_id: int = panel_info["message_id"]

        # Get the guild
        guild: Optional[discord.Guild] = self.bot.get_guild(guild_id)
        if not guild:
            logger.tree("Guide Update Failed", [
                ("Guild", str(guild_id)),
                ("Reason", "Guild not found"),
            ], emoji="❌")
            return

        # Get the channel
        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.tree("Guide Update Failed", [
                ("Guild", guild.name),
                ("Channel", str(channel_id)),
                ("Reason", "Channel not found or not a text channel"),
            ], emoji="❌")
            return

        try:
            # Fetch the message
            message: discord.Message = await channel.fetch_message(message_id)

            # Build updated embed
            embed = self._build_guide_embed(guild)

            # Edit the message with updated embed, keep the view
            await message.edit(embed=embed, view=GuideView())

            # Update timestamp in database
            db.update_guide_panel_timestamp(guild_id)

            logger.tree("Guide Panel Updated", [
                ("Guild", guild.name),
                ("Members", f"{guild.member_count:,}"),
                ("Boosters", str(guild.premium_subscription_count or 0)),
            ], emoji="✅")

        except discord.NotFound:
            logger.tree("Guide Update Failed", [
                ("Guild", guild.name),
                ("Message", str(message_id)),
                ("Reason", "Message not found - panel may have been deleted"),
            ], emoji="❌")
            # Optionally delete the stale record
            db.delete_guide_panel(guild_id)

        except discord.Forbidden:
            logger.tree("Guide Update Failed", [
                ("Guild", guild.name),
                ("Reason", "Missing permissions to edit message"),
            ], emoji="❌")

        except discord.HTTPException as e:
            logger.error_tree("Guide Update HTTP Error", e, [
                ("Guild", guild.name),
                ("Channel", str(channel_id)),
                ("Message", str(message_id)),
            ])

        except Exception as e:
            logger.error_tree("Guide Update Error", e, [
                ("Guild", guild.name),
            ])

    def _build_guide_embed(self, guild: discord.Guild) -> discord.Embed:
        """
        Build the guide panel embed with current server stats.

        Args:
            guild: The Discord guild.

        Returns:
            The embed with updated stats.
        """
        created_timestamp: int = int(guild.created_at.timestamp())

        embed = discord.Embed(
            title="Server Guide",
            description=(
                "Welcome to the server! Click the buttons below to learn more.\n\n"
                "**Rules** - `Server rules and guidelines`\n"
                "**Roles** - `Role system and how to get roles`\n"
                "**FAQ** - `Frequently asked questions`\n"
                "**Commands** - `Bot commands and features`"
            ),
            color=COLOR_SYRIA_GREEN,
        )

        # Add server info with live stats
        embed.add_field(
            name="Server Info",
            value=(
                f"**Created:** <t:{created_timestamp}:D> (<t:{created_timestamp}:R>)\n"
                f"**Members:** {guild.member_count:,}\n"
                f"**Boosters:** {guild.premium_subscription_count or 0}"
            ),
            inline=False,
        )

        # Add server banner if available
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        set_footer(embed)
        return embed

    async def force_update(self) -> bool:
        """
        Force an immediate update of the guide panel.

        Returns:
            True if update was successful, False otherwise.
        """
        logger.tree("Guide Force Update", [
            ("Status", "Triggered"),
        ], emoji="🔄")
        try:
            await self._update_guide_panel()
            return True
        except Exception as e:
            logger.error_tree("Guide Force Update Failed", e)
            return False


# Singleton instance
_guide_service: Optional[GuideService] = None


def get_guide_service(bot: Bot) -> GuideService:
    """
    Get or create the guide service singleton.

    Args:
        bot: The Discord bot instance.

    Returns:
        The guide service instance.
    """
    global _guide_service
    if _guide_service is None:
        _guide_service = GuideService(bot)
    return _guide_service
