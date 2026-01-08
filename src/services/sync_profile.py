"""
SyriaBot - Profile Sync Service
===============================

Syncs bot avatar and banner with server.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord

from src.core.logger import log


TIMEZONE = ZoneInfo("America/New_York")
SYNC_TIME = time(0, 0)  # Midnight


class ProfileSyncService:
    """Syncs bot profile with server icon/banner."""

    def __init__(self, bot):
        self.bot = bot
        self.guild_id: int = None
        self._task: asyncio.Task = None

    async def setup(self, guild_id: int) -> None:
        """Initialize the sync service."""
        self.guild_id = guild_id

        # Sync on startup
        await self._sync_profile()

        # Start scheduler
        self._task = asyncio.create_task(self._scheduler())
        log.tree("Profile Sync Initialized", [
            ("Guild ID", str(guild_id)),
            ("Schedule", "Daily at midnight EST"),
        ], emoji="✅")

    async def stop(self) -> None:
        """Stop the sync service."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _scheduler(self) -> None:
        """Run sync at midnight every day."""
        while True:
            now = datetime.now(TIMEZONE)

            # Calculate next midnight
            tomorrow = now.date()
            if now.time() >= SYNC_TIME:
                tomorrow = now.date() + timedelta(days=1)

            next_run = datetime.combine(tomorrow, SYNC_TIME, TIMEZONE)
            wait_seconds = (next_run - now).total_seconds()

            log.tree("Profile Sync Scheduled", [
                ("Next Run", next_run.strftime("%Y-%m-%d %H:%M EST")),
                ("Wait Time", f"{wait_seconds / 3600:.1f} hours"),
            ], emoji="⏰")

            await asyncio.sleep(wait_seconds)
            await self._sync_profile()

    async def _sync_profile(self) -> None:
        """Sync bot avatar and banner with server."""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            log.tree("Profile Sync Skipped", [
                ("Guild ID", str(self.guild_id)),
                ("Reason", "Guild not found or unavailable"),
            ], emoji="⚠️")
            return

        changes = []

        # Sync avatar with server icon
        if guild.icon:
            try:
                icon_bytes = await guild.icon.read()

                # Check if different (compare by updating anyway, Discord handles dedup)
                await self.bot.user.edit(avatar=icon_bytes)
                changes.append(("Avatar", "Synced from server icon"))
            except discord.HTTPException as e:
                if "rate" in str(e).lower():
                    log.tree("Avatar Update Rate Limited", [
                        ("Action", "Will retry next sync"),
                    ], emoji="⏳")
                else:
                    log.tree("Avatar Sync Failed", [
                        ("Error", str(e)[:100]),
                    ], emoji="❌")
            except Exception as e:
                log.tree("Avatar Sync Failed", [
                    ("Error", str(e)[:100]),
                ], emoji="❌")

        # Sync banner with server banner (requires Nitro)
        if guild.banner:
            try:
                banner_bytes = await guild.banner.read()
                await self.bot.user.edit(banner=banner_bytes)
                changes.append(("Banner", "Synced from server banner"))
            except discord.HTTPException as e:
                if "nitro" in str(e).lower() or "premium" in str(e).lower():
                    pass  # Bot doesn't have Nitro, skip silently
                elif "rate" in str(e).lower():
                    log.tree("Banner Update Rate Limited", [
                        ("Action", "Will retry next sync"),
                    ], emoji="⏳")
                else:
                    log.tree("Banner Sync Failed", [
                        ("Error", str(e)[:100]),
                    ], emoji="❌")
            except Exception as e:
                log.tree("Banner Sync Failed", [
                    ("Error", str(e)[:100]),
                ], emoji="❌")

        if changes:
            log.tree("Bot Profile Synced", changes, emoji="🔄")
        else:
            log.tree("Profile Sync", [
                ("Status", "No changes needed"),
            ], emoji="ℹ️")
