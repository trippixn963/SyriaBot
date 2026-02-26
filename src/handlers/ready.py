"""
SyriaBot - Ready Handler
========================

Handles bot startup events.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord.ext import commands, tasks

from datetime import datetime, timezone

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
        - Starts scheduled tasks (role snapshots, etc.)
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
        features.append(("Cmds Channel", "✅" if config.CMDS_CHANNEL_ID else "❌"))

        # API-dependent features
        features.append(("Weather", "✅" if config.OPENWEATHER_API_KEY else "❌"))
        features.append(("Translation", "✅" if config.DEEPL_API_KEY else "❌"))
        features.append(("Image Search", "✅" if config.GOOGLE_API_KEY else "❌"))
        features.append(("AI Chat", "✅" if config.OPENAI_API_KEY else "❌"))

        logger.tree("Feature Status", features, emoji="📋")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        # Set start time for uptime tracking
        self.bot.start_time = datetime.now(timezone.utc)

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

        # Start scheduled tasks
        try:
            if not self.snapshot_roles.is_running():
                self.snapshot_roles.start()
            if not self.track_voice_together.is_running():
                self.track_voice_together.start()
            if not self.daily_cleanup.is_running():
                self.daily_cleanup.start()
            logger.tree("Scheduled Tasks Started", [
                ("Role Snapshots", "Every 24h"),
                ("Voice Together", "Every 60s"),
                ("Daily Cleanup", "Every 24h"),
            ], emoji="⏰")
        except Exception as e:
            logger.error_tree("Scheduled Tasks Start Failed", e)

    @tasks.loop(hours=24)
    async def snapshot_roles(self) -> None:
        """Take a daily snapshot of role distribution."""
        try:
            guild = self.bot.get_guild(config.GUILD_ID)
            if not guild:
                return

            # Build role data (exclude @everyone)
            role_data = [
                {
                    "role_id": role.id,
                    "role_name": role.name,
                    "member_count": len(role.members)
                }
                for role in guild.roles
                if role.id != guild.id  # Exclude @everyone
            ]

            # Save to database
            db.snapshot_role_distribution(config.GUILD_ID, role_data)

            logger.tree("Daily Role Snapshot", [
                ("Guild", guild.name),
                ("Roles", str(len(role_data))),
            ], emoji="📸")
        except Exception as e:
            logger.error_tree("Role Snapshot Failed", e)

    @snapshot_roles.before_loop
    async def before_snapshot_roles(self) -> None:
        """Wait until bot is ready before starting the task."""
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def track_voice_together(self) -> None:
        """Track voice time together for users in the same channel."""
        try:
            guild = self.bot.get_guild(config.GUILD_ID)
            if not guild:
                return

            # Iterate through all voice channels
            for vc in guild.voice_channels:
                # Get non-bot members in this channel
                members = [m for m in vc.members if not m.bot]

                # Need at least 2 people to track "together" time
                if len(members) < 2:
                    continue

                # For each unique pair, add 1 minute
                for i, member_a in enumerate(members):
                    for member_b in members[i + 1:]:
                        # add_voice_together is bidirectional, so only call once per pair
                        db.add_voice_together(
                            member_a.id,
                            member_b.id,
                            guild.id,
                            1  # 1 minute
                        )

        except Exception as e:
            logger.error_tree("Voice Together Track Failed", e)

    @track_voice_together.before_loop
    async def before_track_voice_together(self) -> None:
        """Wait until bot is ready before starting the task."""
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def daily_cleanup(self) -> None:
        """Clean up old data from unbounded tables."""
        import asyncio

        try:
            # Run cleanup in thread pool to avoid blocking event loop
            results = await asyncio.to_thread(
                db.run_all_cleanups,
                config.GUILD_ID
            )

            total = sum(results.values())
            if total > 0:
                logger.tree("Daily Cleanup Complete", [
                    ("XP Snapshots", str(results.get("xp_snapshots", 0))),
                    ("Role Snapshots", str(results.get("role_snapshots", 0))),
                    ("Member Events", str(results.get("member_events", 0))),
                    ("Channel Daily", str(results.get("channel_daily_stats", 0))),
                    ("Total Deleted", str(total)),
                ], emoji="🧹")
        except Exception as e:
            logger.error_tree("Daily Cleanup Failed", e)

    @daily_cleanup.before_loop
    async def before_daily_cleanup(self) -> None:
        """Wait until bot is ready before starting the task."""
        await self.bot.wait_until_ready()
        # Delay first cleanup by 1 hour to not run immediately on startup
        import asyncio
        await asyncio.sleep(3600)

    def cog_unload(self) -> None:
        """Cancel tasks when cog is unloaded."""
        self.snapshot_roles.cancel()
        self.track_voice_together.cancel()
        self.daily_cleanup.cancel()


async def setup(bot: commands.Bot) -> None:
    """Register the ready handler cog with the bot."""
    await bot.add_cog(ReadyHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "ReadyHandler"),
    ], emoji="✅")
