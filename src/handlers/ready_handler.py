"""
SyriaBot - Ready Handler
========================

Handles bot startup events.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord.ext import commands

from src.core.config import config
from src.core.logger import log
from src.utils.footer import init_footer


class ReadyHandler(commands.Cog):
    """Handles bot ready event."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the ready handler with bot reference."""
        self.bot = bot

    def _log_feature_status(self) -> None:
        """Log enabled/disabled features based on configuration."""
        features = []

        # Core features
        features.append(("TempVoice", "✅" if config.VC_CREATOR_CHANNEL_ID else "❌"))
        features.append(("XP System", "✅" if config.XP_ROLE_REWARDS else "❌"))
        features.append(("Confessions", "✅" if config.CONFESSIONS_CHANNEL_ID else "❌"))
        features.append(("Gallery", "✅" if config.GALLERY_CHANNEL_ID else "❌"))
        features.append(("Bump Reminder", "✅" if config.BUMP_CHANNEL_ID else "❌"))
        features.append(("Fun Commands", "✅" if config.FUN_COMMANDS_CHANNEL_ID else "❌"))

        # API-dependent features
        features.append(("Weather", "✅" if config.OPENWEATHER_API_KEY else "❌"))
        features.append(("Translation", "✅" if config.DEEPL_API_KEY else "❌"))
        features.append(("Image Search", "✅" if config.GOOGLE_API_KEY else "❌"))
        features.append(("AI Chat", "✅" if config.OPENAI_API_KEY else "❌"))

        log.tree("Feature Status", features, emoji="📋")

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

        # Log feature status
        self._log_feature_status()

        # Initialize footer (cache developer avatar)
        # Note: init_footer() logs its own status with Avatar Cached: Yes/No
        try:
            await init_footer(self.bot)
        except Exception as e:
            log.error_tree("Footer Init Failed", e)

        # Sync slash commands to Syria guild only (not globally)
        try:
            # Clear global commands so they don't appear in other servers
            self.bot.tree.clear_commands(guild=None)
            await self.bot.tree.sync()
            log.tree("Global Commands Cleared", [], emoji="🧹")

            # Sync all commands only to the main Syria guild
            guild_synced = []
            if config.GUILD_ID:
                guild_obj = discord.Object(id=config.GUILD_ID)
                self.bot.tree.copy_global_to(guild=guild_obj)
                guild_synced = await self.bot.tree.sync(guild=guild_obj)

            log.tree("Commands Synced To Syria Only", [
                ("Guild ID", str(config.GUILD_ID)),
                ("Commands", str(len(guild_synced))),
                ("Names", ", ".join(sorted(c.name for c in guild_synced))),
            ], emoji="🔄")
        except Exception as e:
            log.error_tree("Command Sync Failed", e)

        # Initialize services (includes PresenceHandler which manages rotating presence)
        try:
            await self.bot._init_services()
        except Exception as e:
            log.error_tree("Service Init Failed", e)

        # Check DeepL usage at startup
        try:
            from src.services.translate import translate_service
            await translate_service.check_deepl_usage()
        except Exception as e:
            log.tree("DeepL Usage Check Skipped", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")


async def setup(bot: commands.Bot) -> None:
    """Register the ready handler cog with the bot."""
    await bot.add_cog(ReadyHandler(bot))
    log.tree("Handler Loaded", [
        ("Name", "ReadyHandler"),
    ], emoji="✅")
