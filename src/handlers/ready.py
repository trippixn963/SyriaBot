"""
SyriaBot - Ready Handler
========================

Handles bot startup events.

Author: حَـــــنَّـــــا
"""

import discord
from discord.ext import commands

from src.core.logger import log
from src.utils.footer import init_footer


class ReadyHandler(commands.Cog):
    """Handles bot ready event."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready."""
        log.tree("Bot Ready", [
            ("User", str(self.bot.user)),
            ("ID", str(self.bot.user.id)),
            ("Guilds", str(len(self.bot.guilds))),
        ], emoji="🚀")

        # Initialize footer (cache developer avatar)
        await init_footer(self.bot)

        # Initialize services
        await self.bot._init_services()

        # Set presence
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="voice channels"
            )
        )


async def setup(bot):
    await bot.add_cog(ReadyHandler(bot))
