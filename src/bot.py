"""
SyriaBot - Main Bot
==================

Discord bot with TempVoice system.

Author: حَـــــنَّـــــا
"""

import asyncio
import discord
from discord.ext import commands
from typing import Optional

from src.core.config import config
from src.core.logger import log
from src.services.tempvoice import TempVoiceService
from src.services.sync_profile import ProfileSyncService
from src.services.xp import XPService
from src.services.xp import card as rank_card
from src.services.stats_api import SyriaAPI
from src.services.status_webhook import get_status_service
from src.services.afk import AFKService
from src.services.gallery import GalleryService
from src.services.presence import PresenceHandler
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
        self.status_webhook = None
        self.afk_service: Optional[AFKService] = None
        self.gallery_service: Optional[GalleryService] = None
        self.presence_handler: Optional[PresenceHandler] = None

    async def setup_hook(self) -> None:
        """Called when the bot is starting up."""
        log.tree("Setup Hook", [
            ("Status", "Starting"),
        ], emoji="🔧")

        # Load handlers
        handlers = [
            "src.handlers.ready",
            "src.handlers.voice",
            "src.handlers.members",
            "src.handlers.message",
        ]
        loaded_handlers = []
        for handler in handlers:
            try:
                await self.load_extension(handler)
                loaded_handlers.append(handler.split('.')[-1])
            except Exception as e:
                log.error_tree("Handler Load Failed", e, [
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
        ]
        loaded_commands = []
        for cmd in commands_list:
            try:
                await self.load_extension(cmd)
                loaded_commands.append(cmd.split('.')[-1])
            except Exception as e:
                log.error_tree("Command Load Failed", e, [
                    ("Command", cmd),
                ])

        log.tree("Setup Hook Complete", [
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
            log.tree("Command Usage Track Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("User ID", str(interaction.user.id)),
                ("Command", command.name if command else "Unknown"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError
    ) -> None:
        """Handle app command errors."""
        log.error_tree("App Command Error", error, [
            ("Command", interaction.command.name if interaction.command else "Unknown"),
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
        ])

    async def _init_services(self) -> None:
        """Initialize bot services."""
        log.tree("Services Init", [
            ("Status", "Starting"),
        ], emoji="🔧")

        initialized = []

        # TempVoice
        try:
            self.tempvoice = TempVoiceService(self)
            await self.tempvoice.setup()
            initialized.append("TempVoice")
        except Exception as e:
            log.error_tree("TempVoice Init Failed", e)

        # Profile Sync - use first guild or configured guild
        guild_id = config.GUILD_ID or (self.guilds[0].id if self.guilds else None)
        if guild_id:
            try:
                self.profile_sync = ProfileSyncService(self)
                await self.profile_sync.setup(guild_id)
                initialized.append("ProfileSync")
            except Exception as e:
                log.error_tree("Profile Sync Init Failed", e)

        # XP System
        try:
            self.xp_service = XPService(self)
            await self.xp_service.setup()
            initialized.append("XP")
        except Exception as e:
            log.error_tree("XP Service Init Failed", e)

        # Stats API
        try:
            self.stats_api = SyriaAPI()
            self.stats_api.set_bot(self)
            await self.stats_api.start()
            initialized.append("StatsAPI")
        except Exception as e:
            log.error_tree("Stats API Init Failed", e)

        # Status Webhook
        if config.STATUS_WEBHOOK_URL:
            try:
                self.status_webhook = get_status_service(config.STATUS_WEBHOOK_URL)
                self.status_webhook.set_bot(self)
                await self.status_webhook.send_startup_alert()
                await self.status_webhook.start_hourly_alerts()
                initialized.append("StatusWebhook")
            except Exception as e:
                log.error_tree("Status Webhook Init Failed", e)

        # AFK Service
        try:
            self.afk_service = AFKService(self)
            initialized.append("AFK")
        except Exception as e:
            log.error_tree("AFK Service Init Failed", e)

        # Gallery Service
        try:
            self.gallery_service = GalleryService(self)
            initialized.append("Gallery")
        except Exception as e:
            log.error_tree("Gallery Service Init Failed", e)

        # Presence Handler
        try:
            self.presence_handler = PresenceHandler(self)
            await self.presence_handler.start()
            initialized.append("Presence")
        except Exception as e:
            log.error_tree("Presence Handler Init Failed", e)

        log.tree("Services Init Complete", [
            ("Services", ", ".join(initialized)),
            ("Count", f"{len(initialized)}/8"),
        ], emoji="✅")

    async def close(self) -> None:
        """Clean up when bot is shutting down."""
        log.tree("Bot Shutdown", [
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
                log.error_tree("Status Webhook Stop Error", e)

        if self.stats_api:
            try:
                await self.stats_api.stop()
                stopped.append("StatsAPI")
            except Exception as e:
                log.error_tree("Stats API Stop Error", e)

        if self.tempvoice:
            try:
                await self.tempvoice.stop()
                stopped.append("TempVoice")
            except Exception as e:
                log.error_tree("TempVoice Stop Error", e)

        if self.profile_sync:
            try:
                await self.profile_sync.stop()
                stopped.append("ProfileSync")
            except Exception as e:
                log.error_tree("Profile Sync Stop Error", e)

        if self.xp_service:
            try:
                await self.xp_service.stop()
                stopped.append("XP")
            except Exception as e:
                log.error_tree("XP Service Stop Error", e)

        if self.gallery_service:
            try:
                self.gallery_service.stop()
                stopped.append("Gallery")
            except Exception as e:
                log.error_tree("Gallery Service Stop Error", e)

        if self.presence_handler:
            try:
                await self.presence_handler.stop()
                stopped.append("Presence")
            except Exception as e:
                log.error_tree("Presence Handler Stop Error", e)

        # Close HTTP session
        try:
            await http_session.close()
            stopped.append("HTTP")
        except Exception as e:
            log.error_tree("HTTP Session Close Error", e)

        # Clean up rank card browser
        try:
            await rank_card.cleanup()
            stopped.append("RankCard")
        except Exception as e:
            log.error_tree("Rank Card Cleanup Error", e)

        await super().close()
        log.tree("Bot Shutdown Complete", [
            ("Services Stopped", ", ".join(stopped)),
        ], emoji="✅")
