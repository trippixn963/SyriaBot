"""
SyriaBot - Profile Sync Service
===============================

Syncs bot avatar with server icon.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import discord

from src.core.logger import logger


TIMEZONE = ZoneInfo("America/New_York")
SYNC_TIME = time(0, 0)  # Midnight


class ProfileSyncService:
    """Syncs bot avatar with server icon."""

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
        logger.tree("Profile Sync Initialized", [
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
            try:
                now = datetime.now(TIMEZONE)

                # Calculate next midnight
                tomorrow = now.date()
                if now.time() >= SYNC_TIME:
                    tomorrow = now.date() + timedelta(days=1)

                next_run = datetime.combine(tomorrow, SYNC_TIME, TIMEZONE)
                wait_seconds = (next_run - now).total_seconds()

                logger.tree("Profile Sync Scheduled", [
                    ("Next Run", next_run.strftime("%Y-%m-%d %H:%M EST")),
                    ("Wait Time", f"{wait_seconds / 3600:.1f} hours"),
                ], emoji="⏰")

                await asyncio.sleep(wait_seconds)

                try:
                    await self._sync_profile()
                except Exception as e:
                    logger.error_tree("Scheduled Profile Sync Failed", e)
                    # Continue loop - will retry next day

            except asyncio.CancelledError:
                raise  # Re-raise to allow clean shutdown
            except Exception as e:
                logger.error_tree("Profile Scheduler Error", e)
                await asyncio.sleep(3600)  # Wait 1 hour before retrying

    async def _sync_profile(self) -> None:
        """Sync bot avatar and banner with server."""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            logger.tree("Profile Sync Skipped", [
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
                    logger.tree("Avatar Update Rate Limited", [
                        ("Action", "Will retry next sync"),
                    ], emoji="⏳")
                else:
                    logger.tree("Avatar Sync Failed", [
                        ("Error", str(e)[:100]),
                    ], emoji="❌")
            except Exception as e:
                logger.tree("Avatar Sync Failed", [
                    ("Error", str(e)[:100]),
                ], emoji="❌")

        if changes:
            logger.tree("Bot Profile Synced", changes, emoji="🔄")
        else:
            logger.tree("Profile Sync", [
                ("Status", "No changes needed"),
            ], emoji="ℹ️")
