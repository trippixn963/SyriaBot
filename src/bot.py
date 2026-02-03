"""
SyriaBot - Main Bot
===================

Discord bot with TempVoice system.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import os
import discord
from discord.ext import commands
from typing import Optional

from src.core.config import config, validate_config


# =============================================================================
# Guild Protection
# =============================================================================

def _get_authorized_guilds() -> set:
    """Get authorized guild IDs from environment."""
    guilds = set()
    syria_id = os.getenv("GUILD_ID")
    mods_id = os.getenv("MODS_GUILD_ID")
    if syria_id:
        guilds.add(int(syria_id))
    if mods_id:
        guilds.add(int(mods_id))
    return guilds

AUTHORIZED_GUILD_IDS = _get_authorized_guilds()

from src.core.logger import logger
from src.services.tempvoice import TempVoiceService
from src.services.sync_profile import ProfileSyncService
from src.services.xp import XPService
from src.services.xp import card as rank_card
from src.services.stats_api import SyriaAPI
from src.core.health import HealthCheckServer
from src.services.status_webhook import get_status_service
from src.services.backup import BackupScheduler
from src.services.afk import AFKService
from src.services.gallery import GalleryService
from src.services.presence import PresenceHandler
from src.services.bump_service import bump_service
from src.services.confessions import ConfessionService
from src.services.currency_service import CurrencyService
from src.services.action_service import action_service
from src.services.quote import quote_service
from src.services.birthday_service import get_birthday_service, BirthdayService
from src.services.city_game import get_city_game_service, CityGameService, setup_city_game_cog
from src.services.faq import setup_persistent_views
from src.services.confessions.views import setup_confession_views
from src.services.guide import setup_guide_views, get_guide_service, GuideService
from src.services.social_monitor import SocialMonitorService
from src.services.database import db
from src.utils.http import http_session


class SyriaBot(commands.Bot):
    """Main bot class for SyriaBot."""

    def __init__(self) -> None:
        """Initialize the bot with required intents and service placeholders."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        intents.presences = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

        # Services
        self.tempvoice: Optional[TempVoiceService] = None
        self.profile_sync: Optional[ProfileSyncService] = None
        self.xp_service: Optional[XPService] = None
        self.stats_api: Optional[SyriaAPI] = None
        self.health_server: Optional[HealthCheckServer] = None
        self.status_webhook = None
        self.afk_service: Optional[AFKService] = None
        self.gallery_service: Optional[GalleryService] = None
        self.presence_handler: Optional[PresenceHandler] = None
        self.confession_service: Optional[ConfessionService] = None
        self.currency_service: Optional[CurrencyService] = None
        self.birthday_service: Optional[BirthdayService] = None
        self.city_game_service: Optional[CityGameService] = None
        self.guide_service: Optional[GuideService] = None
        self.social_monitor: Optional[SocialMonitorService] = None
        self.backup_scheduler: Optional[BackupScheduler] = None

    async def setup_hook(self) -> None:
        """Called when the bot is starting up."""
        logger.tree("Setup Hook", [
            ("Status", "Starting"),
        ], emoji="🔧")

        # Load handlers
        handlers = [
            "src.handlers.ready",
            "src.handlers.voice",
            "src.handlers.member",
            "src.handlers.message",
            "src.handlers.giveaway_reaction",
            "src.handlers.presence",
        ]
        loaded_handlers = []
        for handler in handlers:
            try:
                await self.load_extension(handler)
                loaded_handlers.append(handler.split('.')[-1])
            except Exception as e:
                logger.error_tree("Handler Load Failed", e, [
                    ("Handler", handler),
                ])

        # Load commands
        commands_list = [
            "src.commands.convert",
            "src.commands.weather",
            "src.commands.get",
            "src.commands.rank",
            "src.commands.translate",
            "src.commands.download",
            "src.commands.afk",
            "src.commands.image",
            "src.commands.confess",
            "src.commands.birthday",
            "src.commands.faq",
            "src.commands.guide",
        ]
        loaded_commands = []
        for cmd in commands_list:
            try:
                await self.load_extension(cmd)
                loaded_commands.append(cmd.split('.')[-1])
            except Exception as e:
                logger.error_tree("Command Load Failed", e, [
                    ("Command", cmd),
                ])

        # Register persistent views
        setup_persistent_views(self)
        setup_confession_views(self)
        setup_guide_views(self)

        logger.tree("Setup Hook Complete", [
            ("Handlers", ", ".join(loaded_handlers)),
            ("Commands", ", ".join(loaded_commands)),
        ], emoji="✅")

        # Set up app command completion tracking
        self.tree.on_error = self._on_app_command_error

    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: discord.app_commands.Command
    ) -> None:
        """Track slash command usage."""
        if interaction.user.bot:
            return

        # Only track in main server
        if not interaction.guild or interaction.guild.id != config.GUILD_ID:
            return

        try:
            # Run DB operation in thread pool to avoid blocking event loop
            await asyncio.to_thread(
                db.increment_commands_used,
                interaction.user.id,
                interaction.guild.id
            )
        except Exception as e:
            logger.tree("Command Usage Track Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Command", command.name if command else "Unknown"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError
    ) -> None:
        """Handle app command errors."""
        logger.error_tree("App Command Error", error, [
            ("Command", interaction.command.name if interaction.command else "Unknown"),
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ])

    # =========================================================================
    # Guild Protection
    # =========================================================================

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Leave immediately if guild is not authorized."""
        # Safety: Don't leave if authorized set is empty (misconfigured env)
        if not AUTHORIZED_GUILD_IDS:
            return
        if guild.id not in AUTHORIZED_GUILD_IDS:
            logger.warning("Added To Unauthorized Guild - Leaving", [
                ("Guild", guild.name),
                ("ID", str(guild.id)),
            ])
            try:
                await guild.leave()
            except Exception as e:
                logger.error("Failed To Leave Unauthorized Guild", [
                    ("Guild", guild.name),
                    ("Error", str(e)),
                ])

    async def _leave_unauthorized_guilds(self) -> None:
        """Leave any guilds not in AUTHORIZED_GUILD_IDS."""
        # Safety: Don't leave any guilds if authorized set is empty (misconfigured env)
        if not AUTHORIZED_GUILD_IDS:
            logger.warning("Guild Protection Skipped", [
                ("Reason", "AUTHORIZED_GUILD_IDS is empty"),
                ("Action", "Check GUILD_ID and MODS_GUILD_ID in .env"),
            ])
            return
        unauthorized = [g for g in self.guilds if g.id not in AUTHORIZED_GUILD_IDS]
        if not unauthorized:
            return

        logger.tree("Leaving Unauthorized Guilds", [
            ("Count", str(len(unauthorized))),
        ], emoji="⚠️")

        for guild in unauthorized:
            try:
                logger.warning("Leaving Unauthorized Guild", [
                    ("Guild", guild.name),
                    ("ID", str(guild.id)),
                ])
                await guild.leave()
            except Exception as e:
                logger.error("Failed To Leave Guild", [
                    ("Guild", guild.name),
                    ("Error", str(e)),
                ])

    async def _init_services(self) -> None:
        """Initialize bot services."""
        logger.tree("Services Init", [
            ("Status", "Starting"),
        ], emoji="🔧")

        # Validate configuration first
        if not validate_config():
            logger.tree("CRITICAL: Config Invalid", [
                ("Impact", "Bot may not function correctly"),
                ("Action", "Check environment variables"),
            ], emoji="🚨")

        # Leave unauthorized guilds before initializing services
        await self._leave_unauthorized_guilds()

        # Check database health first - critical for most services
        if not db.is_healthy:
            logger.tree("CRITICAL: Database Unhealthy", [
                ("Reason", db.corruption_reason or "Unknown"),
                ("Impact", "Most services will not function"),
                ("Action", "Fix database and restart bot"),
            ], emoji="🚨")
            # Continue with limited functionality - some services may work without DB

        initialized = []

        # TempVoice
        try:
            self.tempvoice = TempVoiceService(self)
            await self.tempvoice.setup()
            initialized.append("TempVoice")
        except Exception as e:
            logger.error_tree("TempVoice Init Failed", e)

        # Profile Sync - use first guild or configured guild
        guild_id = config.GUILD_ID or (self.guilds[0].id if self.guilds else None)
        if guild_id:
            try:
                self.profile_sync = ProfileSyncService(self)
                await self.profile_sync.setup(guild_id)
                initialized.append("ProfileSync")
            except Exception as e:
                logger.error_tree("Profile Sync Init Failed", e)

        # XP System
        try:
            self.xp_service = XPService(self)
            await self.xp_service.setup()
            initialized.append("XP")
        except Exception as e:
            logger.error_tree("XP Service Init Failed", e)

        # Health Check Server (unified)
        try:
            self.health_server = HealthCheckServer(self)

            # Register database health callback
            async def db_health() -> dict:
                try:
                    connected = db.is_healthy
                    error = db.corruption_reason if not connected else None
                    return {"connected": connected, "error": error}
                except Exception as e:
                    return {"connected": False, "error": str(e)}

            self.health_server.register_db_health(db_health)

            # Register system health callback
            import psutil
            _psutil_process = psutil.Process()

            async def system_health() -> dict:
                cpu_percent = psutil.cpu_percent(interval=None)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                bot_memory_mb = _psutil_process.memory_info().rss / (1024 * 1024)
                return {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_percent": disk.percent,
                    "disk_total_gb": round(disk.total / (1024 ** 3), 1),
                    "disk_used_gb": round(disk.used / (1024 ** 3), 1),
                    "bot_memory_mb": round(bot_memory_mb, 1),
                    "threads": _psutil_process.num_threads(),
                    "open_files": len(_psutil_process.open_files()),
                }

            self.health_server.register_system(system_health)
            await self.health_server.start()
            initialized.append("HealthServer")
        except Exception as e:
            logger.error_tree("Health Server Init Failed", e)

        # Stats API
        try:
            self.stats_api = SyriaAPI(self)
            await self.stats_api.setup()
            initialized.append("StatsAPI")
        except Exception as e:
            logger.error_tree("Stats API Init Failed", e)

        # Status Webhook
        if config.STATUS_WEBHOOK_URL:
            try:
                self.status_webhook = get_status_service(config.STATUS_WEBHOOK_URL, bot_name="SyriaBot")
                self.status_webhook.set_bot(self)
                await self.status_webhook.send_startup_alert()
                await self.status_webhook.start_hourly_alerts()
                initialized.append("StatusWebhook")
            except Exception as e:
                logger.error_tree("Status Webhook Init Failed", e)

        # Backup Scheduler
        try:
            self.backup_scheduler = BackupScheduler()
            await self.backup_scheduler.start()
            initialized.append("Backup")
        except Exception as e:
            logger.error_tree("Backup Scheduler Init Failed", e)

        # AFK Service
        try:
            self.afk_service = AFKService(self)
            await self.afk_service.setup()
            initialized.append("AFK")
        except Exception as e:
            logger.error_tree("AFK Service Init Failed", e)

        # Gallery Service
        try:
            self.gallery_service = GalleryService(self)
            await self.gallery_service.setup()
            initialized.append("Gallery")
        except Exception as e:
            logger.error_tree("Gallery Service Init Failed", e)

        # Presence Handler
        try:
            self.presence_handler = PresenceHandler(self)
            await self.presence_handler.setup()
            initialized.append("Presence")
        except Exception as e:
            logger.error_tree("Presence Handler Init Failed", e)

        # Bump Reminder (Disboard)
        if config.BUMP_CHANNEL_ID and config.MOD_ROLE_ID:
            try:
                bump_service.setup(self, config.BUMP_CHANNEL_ID, config.MOD_ROLE_ID)
                bump_service.start()
                initialized.append("BumpReminder")
            except Exception as e:
                logger.error_tree("Bump Reminder Init Failed", e)

        # Confessions
        try:
            self.confession_service = ConfessionService(self)
            await self.confession_service.setup()
            initialized.append("Confessions")
        except Exception as e:
            logger.error_tree("Confessions Init Failed", e)

        # Currency (JawdatBot integration)
        try:
            self.currency_service = CurrencyService()
            await self.currency_service.setup()
            initialized.append("Currency")
        except Exception as e:
            logger.error_tree("Currency Service Init Failed", e)

        # Birthdays
        try:
            self.birthday_service = get_birthday_service(self)
            await self.birthday_service.setup()
            initialized.append("Birthdays")
        except Exception as e:
            logger.error_tree("Birthday Service Init Failed", e)

        # Guide (hourly auto-update)
        try:
            self.guide_service = get_guide_service(self)
            await self.guide_service.setup()
            initialized.append("Guide")
        except Exception as e:
            logger.error_tree("Guide Service Init Failed", e)

        # Social Media Monitor
        if config.SOCIAL_MONITOR_CH:
            try:
                self.social_monitor = SocialMonitorService(self)
                await self.social_monitor.setup()
                initialized.append("SocialMonitor")
            except Exception as e:
                logger.error_tree("Social Monitor Init Failed", e)

        # City Game (dead chat reviver) - DISABLED until images are added manually
        # try:
        #     self.city_game_service = get_city_game_service(self)
        #     await self.city_game_service.setup()
        #     await setup_city_game_cog(self)
        #     initialized.append("CityGame")
        # except Exception as e:
        #     logger.error_tree("City Game Service Init Failed", e)

        logger.tree("Services Init Complete", [
            ("Services", ", ".join(initialized)),
            ("Count", f"{len(initialized)}/16"),
        ], emoji="✅")

    async def close(self) -> None:
        """Clean up when bot is shutting down."""
        logger.tree("Bot Shutdown", [
            ("Status", "Starting cleanup"),
        ], emoji="🛑")

        stopped = []

        # Send shutdown alert first (while bot is still functional)
        if self.status_webhook:
            try:
                await self.status_webhook.send_shutdown_alert()
                self.status_webhook.stop_hourly_alerts()
                stopped.append("StatusWebhook")
            except Exception as e:
                logger.error_tree("Status Webhook Stop Error", e)

        if self.backup_scheduler:
            try:
                await self.backup_scheduler.stop()
                stopped.append("Backup")
            except Exception as e:
                logger.error_tree("Backup Scheduler Stop Error", e)

        if self.stats_api:
            try:
                await self.stats_api.stop()
                stopped.append("StatsAPI")
            except Exception as e:
                logger.error_tree("Stats API Stop Error", e)

        if self.tempvoice:
            try:
                await self.tempvoice.stop()
                stopped.append("TempVoice")
            except Exception as e:
                logger.error_tree("TempVoice Stop Error", e)

        if self.profile_sync:
            try:
                await self.profile_sync.stop()
                stopped.append("ProfileSync")
            except Exception as e:
                logger.error_tree("Profile Sync Stop Error", e)

        if self.xp_service:
            try:
                await self.xp_service.stop()
                stopped.append("XP")
            except Exception as e:
                logger.error_tree("XP Service Stop Error", e)

        if self.gallery_service:
            try:
                self.gallery_service.stop()
                stopped.append("Gallery")
            except Exception as e:
                logger.error_tree("Gallery Service Stop Error", e)

        if self.presence_handler:
            try:
                await self.presence_handler.stop()
                stopped.append("Presence")
            except Exception as e:
                logger.error_tree("Presence Handler Stop Error", e)

        # Bump Reminder
        if bump_service._running:
            try:
                bump_service.stop()
                stopped.append("BumpReminder")
            except Exception as e:
                logger.error_tree("Bump Reminder Stop Error", e)

        # Confessions
        if self.confession_service:
            try:
                self.confession_service.stop()
                stopped.append("Confessions")
            except Exception as e:
                logger.error_tree("Confessions Stop Error", e)

        # Currency
        if self.currency_service:
            try:
                await self.currency_service.stop()
                stopped.append("Currency")
            except Exception as e:
                logger.error_tree("Currency Service Stop Error", e)

        # Birthdays
        if self.birthday_service:
            try:
                self.birthday_service.stop()
                stopped.append("Birthdays")
            except Exception as e:
                logger.error_tree("Birthday Service Stop Error", e)

        # Guide
        if self.guide_service:
            try:
                self.guide_service.stop()
                stopped.append("Guide")
            except Exception as e:
                logger.error_tree("Guide Service Stop Error", e)

        # Social Media Monitor
        if self.social_monitor:
            try:
                self.social_monitor.stop()
                stopped.append("SocialMonitor")
            except Exception as e:
                logger.error_tree("Social Monitor Stop Error", e)

        # City Game
        if self.city_game_service:
            try:
                await self.city_game_service.close()
                stopped.append("CityGame")
            except Exception as e:
                logger.error_tree("City Game Service Stop Error", e)

        # Quote Service (close aiohttp session)
        try:
            await quote_service.close()
            stopped.append("QuoteService")
        except Exception as e:
            logger.error_tree("Quote Service Close Error", e)

        # Close HTTP session
        try:
            await http_session.close()
            stopped.append("HTTP")
        except Exception as e:
            logger.error_tree("HTTP Session Close Error", e)

        # Clean up rank card browser
        try:
            await rank_card.cleanup()
            stopped.append("RankCard")
        except Exception as e:
            logger.error_tree("Rank Card Cleanup Error", e)

        # Close action service session
        try:
            await action_service.close()
            stopped.append("ActionService")
        except Exception as e:
            logger.error_tree("Action Service Close Error", e)

        await super().close()
        logger.tree("Bot Shutdown Complete", [
            ("Services Stopped", ", ".join(stopped)),
        ], emoji="✅")
