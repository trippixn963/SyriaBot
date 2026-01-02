"""
SyriaBot - Voice Handler
========================

Handles voice state updates for TempVoice.

Author: حَـــــنَّـــــا
"""

import discord
from discord.ext import commands

from src.core.logger import log


class VoiceHandler(commands.Cog):
    """Handles voice state updates."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
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


async def setup(bot: commands.Bot) -> None:
    """Register the voice handler cog with the bot."""
    await bot.add_cog(VoiceHandler(bot))
    log.success("Loaded voice handler")
