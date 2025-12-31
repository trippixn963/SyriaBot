"""
SyriaBot - Voice Handler
========================

Handles voice state updates for TempVoice.

Author: حَـــــنَّـــــا
"""

import discord
from discord.ext import commands


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
            await self.bot.tempvoice.on_voice_state_update(member, before, after)


async def setup(bot):
    await bot.add_cog(VoiceHandler(bot))
