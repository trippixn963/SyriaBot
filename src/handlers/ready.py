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
from src.core.logger import logger
from src.utils.footer import init_footer
from src.services.database import db
from src.api.services.websocket import get_ws_manager


class ReadyHandler(commands.Cog):
    """
    Handler for bot startup and initialization.

    DESIGN:
        Orchestrates startup sequence on bot ready:
        - Logs feature status and startup banner
        - Syncs slash commands to guild
        - Initializes all services (XP, TempVoice, etc.)
        - Sets up WebSocket for real-time dashboard stats
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the ready handler.

        Args:
            bot: Main bot instance for accessing services and guilds.
        """
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

        logger.tree("Feature Status", features, emoji="📋")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        # Use startup_banner for bot ready
        logger.startup_banner(
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
            logger.error_tree("Footer Init Failed", e)

        # Sync slash commands to Syria guild only (not globally)
        try:
            guild_obj = discord.Object(id=config.GUILD_ID)
            self.bot.tree.copy_global_to(guild=guild_obj)
            synced = await self.bot.tree.sync(guild=guild_obj)

            logger.tree("Commands Synced", [
                ("Guild", str(config.GUILD_ID)),
                ("Commands", str(len(synced))),
            ], emoji="🔄")
        except Exception as e:
            logger.error_tree("Command Sync Failed", e)

        # Initialize services (includes PresenceHandler which manages rotating presence)
        try:
            await self.bot._init_services()
        except Exception as e:
            logger.error_tree("Service Init Failed", e)

        # Check DeepL usage at startup
        try:
            from src.services.translate import translate_service
            await translate_service.check_deepl_usage()
        except Exception as e:
            logger.tree("DeepL Usage Check Skipped", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Initialize WebSocket with all stats
        try:
            ws_manager = get_ws_manager()
            ws_manager.set_bot(self.bot)

            # Get guild stats
            guild = self.bot.get_guild(config.GUILD_ID)
            members = guild.member_count if guild else 0
            boosts = guild.premium_subscription_count if guild else 0
            online = sum(
                1 for m in guild.members
                if not m.bot and m.status.name != "offline"
            ) if guild else 0

            # Get message count from server counter
            total_messages = db.init_message_counter_from_sum(config.GUILD_ID)

            # Get XP stats (ranked users, total XP, voice minutes)
            xp_stats = db.get_xp_stats(config.GUILD_ID)
            ranked_users = xp_stats.get("total_users", 0)
            total_xp = xp_stats.get("total_xp", 0)
            voice_minutes = xp_stats.get("total_voice_minutes", 0)

            # Set all stats
            ws_manager.set_stats(
                members=members,
                online=online,
                boosts=boosts,
                messages=total_messages,
                ranked=ranked_users,
                xp=total_xp,
                voice_minutes=voice_minutes
            )

            # Start periodic online updates
            await ws_manager.start_online_updates()

            logger.tree("WebSocket Initialized", [
                ("Members", f"{members:,}"),
                ("Online", f"{online:,}"),
                ("Boosts", str(boosts)),
                ("Messages", f"{total_messages:,}"),
                ("Ranked", f"{ranked_users:,}"),
                ("Total XP", f"{total_xp:,}"),
                ("Voice Minutes", f"{voice_minutes:,}"),
            ], emoji="🔌")
        except Exception as e:
            logger.error_tree("WebSocket Init Failed", e)


async def setup(bot: commands.Bot) -> None:
    """Register the ready handler cog with the bot."""
    await bot.add_cog(ReadyHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "ReadyHandler"),
    ], emoji="✅")
