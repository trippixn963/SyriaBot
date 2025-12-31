"""
SyriaBot - Main Bot
==================

Discord bot with TempVoice system.

Author: حَـــــنَّـــــا
"""

import discord
from discord.ext import commands
from typing import Optional

from src.core.config import config
from src.core.logger import log
from src.services.tempvoice import TempVoiceService
from src.services.sync_profile import ProfileSyncService


class SyriaBot(commands.Bot):
    """Main bot class for SyriaBot."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

        # Services
        self.tempvoice: Optional[TempVoiceService] = None
        self.profile_sync: Optional[ProfileSyncService] = None

    async def setup_hook(self) -> None:
        """Called when the bot is starting up."""
        # Load handlers
        await self.load_extension("src.handlers.ready")
        await self.load_extension("src.handlers.voice")
        await self.load_extension("src.handlers.members")
        await self.load_extension("src.handlers.message")

        # Load commands
        await self.load_extension("src.commands.convert")

    async def _init_services(self) -> None:
        """Initialize bot services."""
        # TempVoice
        self.tempvoice = TempVoiceService(self)
        await self.tempvoice.setup()

        # Profile Sync - use first guild or configured guild
        guild_id = config.GUILD_ID or (self.guilds[0].id if self.guilds else None)
        if guild_id:
            self.profile_sync = ProfileSyncService(self)
            await self.profile_sync.setup(guild_id)

    async def close(self) -> None:
        """Clean up when bot is shutting down."""
        log.info("Bot shutting down...")
        if self.tempvoice:
            await self.tempvoice.stop()
        if self.profile_sync:
            await self.profile_sync.stop()
        await super().close()
