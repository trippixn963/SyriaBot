"""
SyriaBot - Voice Handler
========================

Handles voice state updates for TempVoice.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from src.core.config import config
from src.core.logger import logger
from src.services.database import db


class VoiceHandler(commands.Cog):
    """
    Handler for voice state updates.

    DESIGN:
        Forwards voice events to TempVoice service (channel creation/cleanup)
        and XP service (voice XP tracking). Also tracks server-level stats
        for hourly activity charts and peak concurrent users.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the voice handler.

        Args:
            bot: Main bot instance with tempvoice and xp_service attributes.
        """
        self.bot = bot
        # Track when users joined voice channels for session duration
        self.voice_join_times: dict[int, tuple[int, int]] = {}  # user_id -> (timestamp, channel_id)

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
                logger.error_tree("TempVoice Voice Update Error", e, [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Before Channel", str(before.channel.id) if before.channel else "None"),
                    ("After Channel", str(after.channel.id) if after.channel else "None"),
                ])

        # Forward to XP service for voice tracking
        if hasattr(self.bot, 'xp_service') and self.bot.xp_service:
            try:
                await self.bot.xp_service.on_voice_update(member, before, after)
            except Exception as e:
                logger.error_tree("XP Voice Update Error", e, [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                    ("Before Channel", str(before.channel.id) if before.channel else "None"),
                    ("After Channel", str(after.channel.id) if after.channel else "None"),
                ])

        # Track server-level voice stats (main server only)
        if member.guild.id == config.GUILD_ID:
            try:
                now = int(datetime.now().timestamp())
                est = ZoneInfo("America/New_York")

                # User joined a voice channel
                if after.channel and (not before.channel or before.channel.id != after.channel.id):
                    current_hour = datetime.now(est).hour
                    db.increment_server_hour_activity(member.guild.id, current_hour, "voice")

                    # Track join time for session duration
                    self.voice_join_times[member.id] = (now, after.channel.id)

                # User left a voice channel
                if before.channel and (not after.channel or before.channel.id != after.channel.id):
                    # Calculate session duration
                    if member.id in self.voice_join_times:
                        join_time, join_channel_id = self.voice_join_times.pop(member.id)
                        if join_channel_id == before.channel.id:
                            minutes = max(1, (now - join_time) // 60)

                            # Track voice channel stats
                            await asyncio.to_thread(
                                db.record_voice_channel_activity,
                                before.channel.id,
                                member.guild.id,
                                before.channel.name,
                                minutes,
                                len([m for m in before.channel.members if not m.bot])
                            )
                            # Note: Voice together tracking is handled by periodic task in ready.py

                # Track peak concurrent voice users
                if after.channel:
                    total_voice_users = sum(
                        1 for vc in member.guild.voice_channels
                        for m in vc.members if not m.bot
                    )
                    today = datetime.now(est).strftime("%Y-%m-%d")
                    db.update_voice_peak(member.guild.id, today, total_voice_users)
            except Exception as e:
                logger.error_tree("Voice Stats Track Failed", e, [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                ])


async def setup(bot: commands.Bot) -> None:
    """Register the voice handler cog with the bot."""
    await bot.add_cog(VoiceHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "VoiceHandler"),
    ], emoji="✅")
