"""
SyriaBot - Voice Handler
========================

Handles voice state updates for TempVoice.

Author: حَـــــنَّـــــا
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from src.core.config import config
from src.core.logger import log
from src.services.database import db


class VoiceHandler(commands.Cog):
    """Handles voice state updates."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the voice handler with bot reference."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Called when a user's voice state changes."""
        # Skip bots
        if member.bot:
            return

        # Forward to TempVoice service
        if self.bot.tempvoice:
            try:
                await self.bot.tempvoice.on_voice_state_update(member, before, after)
            except Exception as e:
                log.tree("TempVoice Voice Update Error", [
                    ("User", f"{member.name} ({member.id})"),
                    ("Error", str(e)),
                ], emoji="❌")

        # Forward to XP service for voice tracking
        if hasattr(self.bot, 'xp_service') and self.bot.xp_service:
            try:
                await self.bot.xp_service.on_voice_update(member, before, after)
            except Exception as e:
                log.tree("XP Voice Update Error", [
                    ("User", f"{member.name} ({member.id})"),
                    ("Error", str(e)),
                ], emoji="❌")

        # Track server-level voice stats (main server only)
        if member.guild.id == config.GUILD_ID:
            try:
                # Track voice joins for hourly stats
                if after.channel and (not before.channel or before.channel.id != after.channel.id):
                    est = ZoneInfo("America/New_York")
                    current_hour = datetime.now(est).hour
                    db.increment_server_hour_activity(member.guild.id, current_hour, "voice")

                # Track peak concurrent voice users
                if after.channel:
                    total_voice_users = sum(
                        len([m for m in vc.members if not m.bot])
                        for vc in member.guild.voice_channels
                    )
                    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
                    db.update_voice_peak(member.guild.id, today, total_voice_users)
            except Exception as e:
                log.tree("Voice Stats Track Failed", [
                    ("User", f"{member.name} ({member.id})"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")


async def setup(bot: commands.Bot) -> None:
    """Register the voice handler cog with the bot."""
    await bot.add_cog(VoiceHandler(bot))
    log.tree("Handler Loaded", [
        ("Name", "VoiceHandler"),
    ], emoji="✅")
