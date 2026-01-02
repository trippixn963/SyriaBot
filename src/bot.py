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
from src.services.stats_api import SyriaAPI
from src.services.database import db
from src.utils.http import http_session


class SyriaBot(commands.Bot):
    """Main bot class for SyriaBot."""

    def __init__(self):
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

    async def setup_hook(self) -> None:
        """Called when the bot is starting up."""
        log.info("Running setup_hook...")

        # Load handlers
        handlers = [
            "src.handlers.ready",
            "src.handlers.voice",
            "src.handlers.members",
            "src.handlers.message",
        ]
        for handler in handlers:
            try:
                await self.load_extension(handler)
                log.success(f"Loaded handler: {handler.split('.')[-1]}")
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
        ]
        for cmd in commands_list:
            try:
                await self.load_extension(cmd)
                log.success(f"Loaded command: {cmd.split('.')[-1]}")
            except Exception as e:
                log.error_tree("Command Load Failed", e, [
                    ("Command", cmd),
                ])

        log.info("Setup hook complete")

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
        except Exception:
            pass  # Silent fail for tracking

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError
    ) -> None:
        """Handle app command errors."""
        log.error_tree("App Command Error", error, [
            ("Command", interaction.command.name if interaction.command else "Unknown"),
            ("User", str(interaction.user)),
        ])

    async def _init_services(self) -> None:
        """Initialize bot services."""
        log.info("Initializing services...")

        # TempVoice
        try:
            self.tempvoice = TempVoiceService(self)
            await self.tempvoice.setup()
            log.success("TempVoice service initialized")
        except Exception as e:
            log.error_tree("TempVoice Init Failed", e)

        # Profile Sync - use first guild or configured guild
        guild_id = config.GUILD_ID or (self.guilds[0].id if self.guilds else None)
        if guild_id:
            try:
                self.profile_sync = ProfileSyncService(self)
                await self.profile_sync.setup(guild_id)
                log.success("Profile sync service initialized")
            except Exception as e:
                log.error_tree("Profile Sync Init Failed", e)

        # XP System
        try:
            self.xp_service = XPService(self)
            await self.xp_service.setup()
            log.success("XP service initialized")
        except Exception as e:
            log.error_tree("XP Service Init Failed", e)

        # Stats API
        try:
            self.stats_api = SyriaAPI()
            self.stats_api.set_bot(self)
            await self.stats_api.start()
            log.success("Stats API initialized")
        except Exception as e:
            log.error_tree("Stats API Init Failed", e)

        log.info("All services initialized")

    async def close(self) -> None:
        """Clean up when bot is shutting down."""
        log.tree("Bot Shutdown", [
            ("Reason", "close() called"),
        ], emoji="🛑")

        if self.stats_api:
            try:
                await self.stats_api.stop()
                log.info("Stats API stopped")
            except Exception as e:
                log.error_tree("Stats API Stop Error", e)

        if self.tempvoice:
            try:
                await self.tempvoice.stop()
                log.info("TempVoice stopped")
            except Exception as e:
                log.error_tree("TempVoice Stop Error", e)

        if self.profile_sync:
            try:
                await self.profile_sync.stop()
                log.info("Profile sync stopped")
            except Exception as e:
                log.error_tree("Profile Sync Stop Error", e)

        if self.xp_service:
            try:
                await self.xp_service.stop()
                log.info("XP service stopped")
            except Exception as e:
                log.error_tree("XP Service Stop Error", e)

        # Close HTTP session
        try:
            await http_session.close()
        except Exception as e:
            log.error_tree("HTTP Session Close Error", e)

        await super().close()
        log.success("Bot shutdown complete")
