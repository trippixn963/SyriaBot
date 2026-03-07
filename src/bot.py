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
from src.core.constants import HEALTH_CHECK_INTERVAL, HEALTH_MAX_FAILURES


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
from src.api import APIService
from src.services.backup import BackupScheduler
from src.services.afk import AFKService
from src.services.gallery import GalleryService
from src.services.presence import PresenceService
from src.services.bump import bump_service
from src.services.confessions import ConfessionService
from src.services.currency import CurrencyService
from src.services.actions import action_service
from src.services.actions.panel import ActionsPanelService
from src.services.family_panel import FamilyPanelService
from src.services.quote import quote_service
from src.services.birthday import get_birthday_service, BirthdayService
from src.services.faq import setup_persistent_views
from src.services.confessions.views import setup_confession_views
from src.services.social_monitor import SocialMonitorService
from src.services.roulette import RouletteService, get_roulette_service
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
        self.stats_api: Optional[APIService] = None
        self.afk_service: Optional[AFKService] = None
        self.gallery_service: Optional[GalleryService] = None
        self.presence_handler: Optional[PresenceService] = None
        self.confession_service: Optional[ConfessionService] = None
        self.currency_service: Optional[CurrencyService] = None
        self.birthday_service: Optional[BirthdayService] = None
        self.social_monitor: Optional[SocialMonitorService] = None
        self.backup_scheduler: Optional[BackupScheduler] = None
        self.actions_panel: Optional[ActionsPanelService] = None
        self.family_panel: Optional[FamilyPanelService] = None
        self.roulette_service: Optional[RouletteService] = None
        self._health_task: Optional[asyncio.Task] = None
        self._health_failures: int = 0
        self._closing: bool = False
        self._services_initialized: bool = False

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
            "src.commands.rules",
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
        """Initialize bot services. Only runs once (guards against on_ready reconnects)."""
        if self._services_initialized:
            logger.tree("Services Init Skipped", [
                ("Reason", "Already initialized (reconnect)"),
            ], emoji="ℹ️")
            return

        self._services_initialized = True

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

        # Stats API (FastAPI, includes /health)
        try:
            self.stats_api = APIService(self)
            await self.stats_api.start()
            initialized.append("StatsAPI")
        except Exception as e:
            logger.error_tree("Stats API Init Failed", e)

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
            self.presence_handler = PresenceService(self)
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

        # Daily Stats (midnight EST summary)
        try:
            from src.services.daily_stats import DailyStatsService
            self.daily_stats_service = DailyStatsService(self)
            await self.daily_stats_service.setup()
            initialized.append("DailyStats")
        except Exception as e:
            logger.error_tree("Daily Stats Init Failed", e)

        # Actions Panel (persistent actions list in fun channel)
        try:
            self.actions_panel = ActionsPanelService(self)
            await self.actions_panel.setup()
            initialized.append("ActionsPanel")
        except Exception as e:
            logger.error_tree("Actions Panel Init Failed", e)

        # Family Panel (persistent family commands panel in cmds channel)
        try:
            self.family_panel = FamilyPanelService(self)
            await self.family_panel.setup()
            initialized.append("FamilyPanel")
        except Exception as e:
            logger.error_tree("Family Panel Init Failed", e)

        # Social Media Monitor
        if config.SOCIAL_MONITOR_CH:
            try:
                self.social_monitor = SocialMonitorService(self)
                await self.social_monitor.setup()
                initialized.append("SocialMonitor")
            except Exception as e:
                logger.error_tree("Social Monitor Init Failed", e)

        # Roulette Minigame
        try:
            self.roulette_service = get_roulette_service(self)
            await self.roulette_service.setup()
            initialized.append("Roulette")
        except Exception as e:
            logger.error_tree("Roulette Service Init Failed", e)

        # Start connection health monitor
        self._health_task = asyncio.create_task(self._health_check_loop())

        logger.tree("Services Init Complete", [
            ("Services", ", ".join(initialized)),
            ("Count", f"{len(initialized)}/18"),
        ], emoji="✅")

    async def _health_check_loop(self) -> None:
        """Monitor Discord connection health. Exit if connection is dead."""
        logger.tree("Health Monitor Started", [
            ("Interval", f"{HEALTH_CHECK_INTERVAL}s"),
            ("Max Failures", str(HEALTH_MAX_FAILURES)),
        ], emoji="💓")

        await asyncio.sleep(HEALTH_CHECK_INTERVAL)

        while not self.is_closed():
            try:
                ws_alive: bool = self.ws is not None and not self.ws.socket.closed
                latency_valid: bool = self.latency is not None and self.latency > 0

                if ws_alive and latency_valid:
                    self._health_failures = 0
                else:
                    self._health_failures += 1
                    logger.tree("Health Check Failed", [
                        ("Failures", f"{self._health_failures}/{HEALTH_MAX_FAILURES}"),
                        ("WS Alive", str(ws_alive)),
                        ("Latency", str(self.latency)),
                    ], emoji="⚠️")

                    if self._health_failures >= HEALTH_MAX_FAILURES:
                        logger.tree("Connection Dead - Restarting", [
                            ("Failures", str(self._health_failures)),
                            ("Action", "Closing bot for systemd restart"),
                        ], emoji="💀")
                        await self.close()
                        return

            except Exception as e:
                self._health_failures += 1
                logger.error_tree("Health Check Error", e, [
                    ("Failures", f"{self._health_failures}/{HEALTH_MAX_FAILURES}"),
                ])

            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def close(self) -> None:
        """Clean up when bot is shutting down."""
        if self._closing:
            return
        self._closing = True

        logger.tree("Bot Shutdown", [
            ("Status", "Starting cleanup"),
        ], emoji="🛑")

        # Cancel health check first to prevent restart loop
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Disconnect from Discord FIRST so no new events flow during cleanup
        try:
            await asyncio.wait_for(super().close(), timeout=5)
        except Exception:
            pass

        # Stop sync services (instant, no await)
        sync_stopped = []
        sync_services = [
            (self.gallery_service, "Gallery", lambda s: s.stop()),
            (self.confession_service, "Confessions", lambda s: s.stop()),
            (self.birthday_service, "Birthdays", lambda s: s.stop()),
            (self.social_monitor, "SocialMonitor", lambda s: s.stop()),
            (self.roulette_service, "Roulette", lambda s: s.stop()),
            (getattr(self, 'daily_stats_service', None), "DailyStats", lambda s: s.stop()),
            (self.afk_service, "AFK", lambda s: s.stop()),
        ]
        for svc, name, stop_fn in sync_services:
            if svc:
                try:
                    stop_fn(svc)
                    sync_stopped.append(name)
                except Exception as e:
                    logger.error_tree(f"{name} Stop Error", e)

        if bump_service._running:
            try:
                bump_service.stop()
                sync_stopped.append("BumpReminder")
            except Exception as e:
                logger.error_tree("Bump Reminder Stop Error", e)

        # Stop async services concurrently
        async def _stop(name: str, coro) -> str:
            try:
                await coro
                return name
            except Exception as e:
                logger.error_tree(f"{name} Stop Error", e)
                return ""

        async_tasks = []
        if self.backup_scheduler:
            async_tasks.append(_stop("Backup", self.backup_scheduler.stop()))
        if self.stats_api:
            async_tasks.append(_stop("StatsAPI", self.stats_api.stop()))
        if self.tempvoice:
            async_tasks.append(_stop("TempVoice", self.tempvoice.stop()))
        if self.profile_sync:
            async_tasks.append(_stop("ProfileSync", self.profile_sync.stop()))
        if self.xp_service:
            async_tasks.append(_stop("XP", self.xp_service.stop()))
        if self.presence_handler:
            async_tasks.append(_stop("Presence", self.presence_handler.stop()))
        if self.currency_service:
            async_tasks.append(_stop("Currency", self.currency_service.stop()))
        async_tasks.append(_stop("QuoteService", quote_service.close()))
        async_tasks.append(_stop("HTTP", http_session.close()))
        async_tasks.append(_stop("RankCard", rank_card.cleanup()))
        async_tasks.append(_stop("ActionService", action_service.close()))
        async_tasks.append(_stop("LoggerWebhook", logger.close_webhook_session()))

        async_stopped = []
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*async_tasks, return_exceptions=True),
                timeout=8,
            )
            async_stopped = [r for r in results if isinstance(r, str) and r]
        except asyncio.TimeoutError:
            logger.tree("Service Cleanup Timeout", [
                ("Action", "Skipping remaining services"),
            ], emoji="⚠️")

        all_stopped = sync_stopped + async_stopped
        logger.tree("Bot Shutdown Complete", [
            ("Services Stopped", ", ".join(all_stopped)),
        ], emoji="✅")
