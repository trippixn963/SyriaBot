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

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the ready handler with bot reference."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        # Use startup_tree for bot ready
        log.startup_tree(
            bot_name=str(self.bot.user),
            bot_id=self.bot.user.id,
            guilds=len(self.bot.guilds),
            latency=self.bot.latency * 1000,
        )

        # Initialize footer (cache developer avatar)
        # Note: init_footer() logs its own status with Avatar Cached: Yes/No
        try:
            await init_footer(self.bot)
        except Exception as e:
            log.error_tree("Footer Init Failed", e)

        # Sync slash commands (global + guild-specific)
        try:
            from src.core.config import config

            # Sync global commands
            global_synced = await self.bot.tree.sync()

            # Sync guild-specific commands (rank, translate use @guilds decorator)
            guild_synced = []
            if config.GUILD_ID:
                guild_obj = discord.Object(id=config.GUILD_ID)
                guild_synced = await self.bot.tree.sync(guild=guild_obj)

            all_commands = set(c.name for c in global_synced) | set(c.name for c in guild_synced)
            log.tree("Commands Synced", [
                ("Global", str(len(global_synced))),
                ("Guild", str(len(guild_synced))),
                ("Commands", ", ".join(sorted(all_commands))),
            ], emoji="🔄")
        except Exception as e:
            log.error_tree("Command Sync Failed", e)

        # Initialize services (includes PresenceHandler which manages rotating presence)
        try:
            await self.bot._init_services()
        except Exception as e:
            log.error_tree("Service Init Failed", e)


async def setup(bot: commands.Bot) -> None:
    """Register the ready handler cog with the bot."""
    await bot.add_cog(ReadyHandler(bot))
    log.tree("Handler Loaded", [
        ("Name", "ReadyHandler"),
    ], emoji="✅")
