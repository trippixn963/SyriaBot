"""
SyriaBot - Presence Handler
===========================

Handles presence updates for activity tracking.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord.ext import commands

from src.core.logger import logger


class PresenceHandler(commands.Cog):
    """
    Handler for Discord presence updates.

    DESIGN:
        Forwards presence changes (online/idle/dnd/offline) to XP service
        for daily active user tracking. Helps measure engagement patterns.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the presence handler.

        Args:
            bot: Main bot instance with xp_service attribute.
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_presence_update(
        self,
        before: discord.Member,
        after: discord.Member
    ) -> None:
        """Called when a user's presence changes (online/idle/dnd/offline)."""
        # Skip bots
        if after.bot:
            return

        # Forward to XP service for activity tracking
        if hasattr(self.bot, 'xp_service') and self.bot.xp_service:
            try:
                await self.bot.xp_service.on_presence_update(before, after)
            except Exception as e:
                logger.error_tree("XP Presence Update Error", e, [
                    ("User", f"{after.name} ({after.display_name})"),
                    ("ID", str(after.id)),
                    ("Before Status", str(before.status)),
                    ("After Status", str(after.status)),
                ])


async def setup(bot: commands.Bot) -> None:
    """Register the presence handler cog with the bot."""
    await bot.add_cog(PresenceHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "PresenceHandler"),
    ], emoji="✅")
