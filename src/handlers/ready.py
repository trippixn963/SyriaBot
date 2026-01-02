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
        # Use startup_tree for bot ready
        log.startup_tree(
            bot_name=str(self.bot.user),
            bot_id=self.bot.user.id,
            guilds=len(self.bot.guilds),
            latency=self.bot.latency * 1000,
        )

        # Initialize footer (cache developer avatar)
        try:
            await init_footer(self.bot)
            log.success("Footer initialized")
        except Exception as e:
            log.error_tree("Footer Init Failed", e)

        # Sync slash commands
        try:
            synced = await self.bot.tree.sync()
            log.tree("Commands Synced", [
                ("Count", str(len(synced))),
                ("Commands", ", ".join(c.name for c in synced)),
            ], emoji="🔄")
        except Exception as e:
            log.error_tree("Command Sync Failed", e)

        # Initialize services
        try:
            await self.bot._init_services()
        except Exception as e:
            log.error_tree("Service Init Failed", e)

        # Set presence
        try:
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="voice channels"
                )
            )
            log.success("Presence set")
        except Exception as e:
            log.error_tree("Presence Set Failed", e)


async def setup(bot: commands.Bot) -> None:
    """Register the ready handler cog with the bot."""
    await bot.add_cog(ReadyHandler(bot))
    log.success("Loaded ready handler")
