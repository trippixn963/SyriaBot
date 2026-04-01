"""
SyriaBot - Voice Handler
========================

Handles voice state updates for TempVoice.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import io
from datetime import datetime, time as dt_time

import discord
from discord.ext import commands, tasks

from src.core.config import config
from src.core.constants import TIMEZONE_EST
from src.core.logger import logger
from src.services.database import db
from src.api.services.event_logger import event_logger


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
    async def on_ready(self) -> None:
        """Sync public VC permissions on startup."""
        await self.sync_public_vc_permissions()

        # Start nightly maintenance
        if not self.public_vc_maintenance.is_running():
            self.public_vc_maintenance.start()

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        """Re-sync temp channel permissions after gateway reconnect."""
        if hasattr(self.bot, 'tempvoice') and self.bot.tempvoice:
            from src.services.tempvoice.permissions import sync_all_channels
            logger.tree("Gateway Resumed — Syncing TempVoice Permissions", [], emoji="🔄")
            await sync_all_channels(self.bot)

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

        # Public VC text access — grant on join, revoke on leave
        await self._handle_public_vc_text(member, before, after)

        # Track server-level voice stats (main server only)
        if member.guild.id == config.GUILD_ID:
            try:
                now = int(datetime.now(TIMEZONE_EST).timestamp())

                # Track server mute changes (by moderator)
                if before.mute != after.mute:
                    event_logger.log_voice_mute(member, muted=after.mute)

                # Track server deafen changes (by moderator)
                if before.deaf != after.deaf:
                    event_logger.log_voice_deafen(member, deafened=after.deaf)

                # Track streaming changes (screen share / Go Live)
                if before.self_stream != after.self_stream and after.channel:
                    if after.self_stream:
                        event_logger.log_voice_stream_start(member, after.channel)
                    else:
                        event_logger.log_voice_stream_end(member, before.channel or after.channel)

                # User joined a voice channel
                if after.channel and (not before.channel or before.channel.id != after.channel.id):
                    current_hour = datetime.now(TIMEZONE_EST).hour
                    db.increment_server_hour_activity(member.guild.id, current_hour, "voice")

                    # Track join time for session duration
                    self.voice_join_times[member.id] = (now, after.channel.id)

                    # Log voice join (to events system for dashboard)
                    if not before.channel:
                        member_count = len([m for m in after.channel.members if not m.bot])
                        event_logger.log_voice_join(member, after.channel, member_count)
                    else:
                        event_logger.log_voice_switch(member, before.channel, after.channel)

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

                            # Log voice leave (to events system for dashboard)
                            if not after.channel:
                                event_logger.log_voice_leave(member, before.channel, minutes)

                # Track peak concurrent voice users (only on joins, not leaves)
                if after.channel and (not before.channel or before.channel != after.channel):
                    total_voice_users = sum(
                        len([m for m in vc.members if not m.bot])
                        for vc in member.guild.voice_channels
                    )
                    today = datetime.now(TIMEZONE_EST).strftime("%Y-%m-%d")
                    await asyncio.to_thread(db.update_voice_peak, member.guild.id, today, total_voice_users)
            except Exception as e:
                logger.error_tree("Voice Stats Track Failed", e, [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("ID", str(member.id)),
                ])


    async def _handle_public_vc_text(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Grant/revoke text access for public voice channels."""
        public_vcs = config.PUBLIC_VC_CHANNELS
        if not public_vcs:
            return

        before_channel = before.channel if before and before.channel else None
        after_channel = after.channel if after and after.channel else None

        # Joined a public VC
        if after_channel and after_channel.id in public_vcs:
            if not before_channel or before_channel.id != after_channel.id:
                try:
                    await after_channel.set_permissions(member, overwrite=discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    ))
                except discord.HTTPException as e:
                    logger.debug("Public VC Text Grant Failed", [
                        ("User", f"{member.name}"),
                        ("Channel", after_channel.name),
                        ("Error", str(e)[:80]),
                    ])

        # Left a public VC
        if before_channel and before_channel.id in public_vcs:
            if not after_channel or after_channel.id != before_channel.id:
                try:
                    await before_channel.set_permissions(member, overwrite=None)
                except discord.HTTPException as e:
                    logger.debug("Public VC Text Revoke Failed", [
                        ("User", f"{member.name}"),
                        ("Channel", before_channel.name),
                        ("Error", str(e)[:80]),
                    ])

                # Delete all messages from this user in the VC text
                try:
                    deleted = 0
                    async for msg in before_channel.history(limit=100):
                        if msg.author.id == member.id:
                            try:
                                await msg.delete()
                                deleted += 1
                            except discord.HTTPException:
                                pass
                    if deleted > 0:
                        logger.tree("Public VC Messages Cleaned", [
                            ("User", f"{member.name} ({member.display_name})"),
                            ("ID", str(member.id)),
                            ("Channel", before_channel.name),
                            ("Deleted", str(deleted)),
                        ], emoji="🧹")
                except Exception as e:
                    logger.error_tree("Public VC Cleanup Failed", e, [
                        ("User", f"{member.name}"),
                        ("Channel", before_channel.name),
                    ])

    async def sync_public_vc_permissions(self) -> None:
        """Sync public VC permissions on startup.

        Sets @everyone to no text access and re-grants text
        to members currently in the VCs.
        """
        public_vcs = config.PUBLIC_VC_CHANNELS
        if not public_vcs:
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return

        synced = 0
        for vc_id in public_vcs:
            channel = guild.get_channel(vc_id)
            if not channel:
                continue

            # Ensure @everyone can't see text
            everyone = guild.default_role
            try:
                await channel.set_permissions(everyone, overwrite=discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    send_messages=False,
                    read_message_history=False,
                ))
            except discord.HTTPException:
                pass

            # Grant mod role full text access (even when not in VC)
            mod_role = guild.get_role(config.MOD_ROLE_ID) if config.MOD_ROLE_ID else None
            if mod_role:
                try:
                    await channel.set_permissions(mod_role, overwrite=discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    ))
                except discord.HTTPException:
                    pass

            # Clear all stale user overwrites (keep roles)
            for target, _ in list(channel.overwrites.items()):
                if isinstance(target, discord.Role):
                    continue
                if target.id == guild.me.id:
                    continue
                try:
                    await channel.set_permissions(target, overwrite=None)
                except discord.HTTPException:
                    pass

            # Re-grant text to members currently in the VC
            for member in channel.members:
                if member.bot:
                    continue
                try:
                    await channel.set_permissions(member, overwrite=discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    ))
                    synced += 1
                except discord.HTTPException:
                    pass

        if synced > 0:
            logger.tree("Public VC Permissions Synced", [
                ("Channels", str(len(public_vcs))),
                ("Members Re-granted", str(synced)),
            ], emoji="🔊")

    # =========================================================================
    # Nightly Public VC Maintenance (midnight EST)
    # =========================================================================

    @tasks.loop(time=dt_time(hour=0, minute=0, tzinfo=TIMEZONE_EST))
    async def public_vc_maintenance(self) -> None:
        """Nightly cleanup: purge all messages and resend music guide + divider."""
        public_vcs = config.PUBLIC_VC_CHANNELS
        if not public_vcs:
            return

        guild = self.bot.get_guild(config.GUILD_ID)
        if not guild:
            return

        from src.services.tempvoice.graphics import render_music_guide
        from src.utils.divider import send_divider

        music_bytes = await render_music_guide()

        for vc_id in public_vcs:
            channel = guild.get_channel(vc_id)
            if not channel:
                continue

            try:
                # Purge all messages
                deleted = 0
                async for msg in channel.history(limit=200):
                    try:
                        await msg.delete()
                        deleted += 1
                    except discord.HTTPException:
                        pass

                # Resend music guide + divider
                if music_bytes:
                    await channel.send(file=discord.File(io.BytesIO(music_bytes), "music_guide.png"))
                    await send_divider(channel)

                logger.tree("Public VC Maintenance", [
                    ("Channel", channel.name),
                    ("Messages Purged", str(deleted)),
                    ("Guide Resent", "Yes" if music_bytes else "No"),
                ], emoji="🧹")
            except Exception as e:
                logger.error_tree("Public VC Maintenance Failed", e, [
                    ("Channel", channel.name),
                ])

    @public_vc_maintenance.before_loop
    async def before_public_vc_maintenance(self) -> None:
        """Wait for bot to be ready."""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    """Register the voice handler cog with the bot."""
    await bot.add_cog(VoiceHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "VoiceHandler"),
    ], emoji="✅")
