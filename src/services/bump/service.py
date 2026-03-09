"""
SyriaBot - Bump Reminder Service
================================

Reminds staff to bump the server on Disboard every 2 hours.
Detects successful bumps from Disboard's "bump done" embed.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import json
import discord
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import time

from src.core.logger import logger
from src.core.colors import COLOR_SUCCESS
from src.core.constants import DISBOARD_BOT_ID
from src.services.database import db
from src.utils.async_utils import create_safe_task


# =============================================================================
# Bump Reminder Service
# =============================================================================

class BumpService:
    """
    Service for reminding staff to bump the server on Disboard.

    DESIGN:
        Monitors for Disboard's "bump done" embed to track successful bumps.
        Sends reminder pings after 2-hour cooldown expires.
        Persists last bump time across bot restarts via SQLite.
    """

    BUMP_INTERVAL = 2 * 60 * 60  # 2 hours in seconds
    _JSON_FILE = Path(__file__).parent.parent.parent / "data" / "bump_data.json"

    def __init__(self) -> None:
        self.bot: discord.Client = None
        self.bump_channel_id: int = None
        self.ping_role_id: int = None
        self._task: asyncio.Task = None
        self._running = False
        self._last_bump_time: Optional[float] = None
        self._last_reminder_time: Optional[float] = None
        self._load_data()

    def setup(self, bot: discord.Client, channel_id: int, role_id: int) -> None:
        """Setup the bump service with bot, channel, and role to ping."""
        self.bot = bot
        self.bump_channel_id = channel_id
        self.ping_role_id = role_id
        logger.tree("Bump Reminder Setup", [
            ("Channel ID", str(channel_id)),
            ("Role ID", str(role_id)),
            ("Interval", "2 hours"),
        ], emoji="📢")

    def start(self) -> None:
        """Start the bump reminder scheduler."""
        if self._running:
            return

        self._running = True
        self._task = create_safe_task(self._reminder_loop(), "Bump Reminder Loop")
        logger.tree("Bump Scheduler Started", [
            ("Status", "Running"),
            ("Interval", "2 hours"),
        ], emoji="✅")

    def stop(self) -> None:
        """Stop the bump reminder scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.tree("Bump Scheduler Stopped", [
            ("Status", "Stopped"),
        ], emoji="🛑")

    def _load_data(self) -> None:
        """Load bump data from database, migrating from JSON if needed."""
        # Migrate from JSON if old file exists
        self._migrate_json()

        # Load from database
        bump_time, reminder_time = db.bump_get_state()
        self._last_bump_time = bump_time
        self._last_reminder_time = reminder_time

        if self._last_bump_time:
            elapsed_min = int((time.time() - self._last_bump_time) / 60)
            logger.tree("Bump Data Loaded", [
                ("Last Bump", f"{elapsed_min} min ago"),
            ], emoji="📊")

    def _migrate_json(self) -> None:
        """One-time migration from JSON file to SQLite."""
        if not self._JSON_FILE.exists():
            return

        try:
            with open(self._JSON_FILE, "r") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                self._JSON_FILE.rename(self._JSON_FILE.with_suffix(".json.migrated"))
                return

            bump_time = data.get("last_bump_time")
            reminder_time = data.get("last_reminder_time")

            if isinstance(bump_time, (int, float)) and bump_time > 0:
                bump_time = float(bump_time)
            else:
                bump_time = None

            if isinstance(reminder_time, (int, float)) and reminder_time > 0:
                reminder_time = float(reminder_time)
            else:
                reminder_time = None

            db.bump_save_state(bump_time, reminder_time)
            self._JSON_FILE.rename(self._JSON_FILE.with_suffix(".json.migrated"))

            logger.tree("Bump Data Migrated", [
                ("From", "JSON"),
                ("To", "SQLite"),
            ], emoji="🔄")

        except Exception as e:
            logger.error_tree("Bump JSON Migration Failed", e, [
                ("File", str(self._JSON_FILE)),
            ])

    def _save_data(self) -> None:
        """Save bump data to database."""
        db.bump_save_state(self._last_bump_time, self._last_reminder_time)

    def record_bump(self) -> None:
        """Record that a bump just happened."""
        self._last_bump_time = time.time()
        self._last_reminder_time = None  # Reset so we send a new reminder after cooldown
        self._save_data()

        logger.tree("Bump Recorded", [
            ("Time", datetime.now(timezone.utc).strftime("%H:%M UTC")),
            ("Next Reminder", "in 2 hours"),
        ], emoji="✅")

    async def _reminder_loop(self) -> None:
        """Main loop that sends bump reminders."""
        # Wait for bot to fully initialize
        await asyncio.sleep(10)

        # Reload data to ensure we have latest state
        self._load_data()
        logger.tree("Bump Service Ready", [
            ("Last Bump", f"{int((time.time() - self._last_bump_time) / 60)} min ago" if self._last_bump_time else "Never"),
            ("Reminder Pending", "Yes" if self._last_bump_time and not self._last_reminder_time else "No"),
        ], emoji="📢")

        while self._running:
            try:
                # Check cooldown status
                if self._last_bump_time:
                    elapsed = time.time() - self._last_bump_time
                    remaining = self.BUMP_INTERVAL - elapsed

                    if remaining > 0:
                        # Still on cooldown, wait
                        remaining_min = int(remaining // 60)
                        logger.tree("Bump Cooldown", [
                            ("Remaining", f"{remaining_min} min"),
                        ], emoji="⏳")
                        await asyncio.sleep(remaining + 5)
                        continue

                    # Cooldown expired - check if we already sent a reminder
                    if self._last_reminder_time and self._last_reminder_time > self._last_bump_time:
                        # Already sent a reminder, wait for next bump
                        logger.tree("Bump Reminder", [
                            ("Status", "Already sent, waiting for bump"),
                        ], emoji="⏸️")
                        await asyncio.sleep(300)  # Check every 5 minutes
                        continue
                else:
                    # No recorded bump - just wait, don't spam
                    logger.tree("Bump Service", [
                        ("Status", "No bump recorded, waiting"),
                    ], emoji="⏰")
                    await asyncio.sleep(self.BUMP_INTERVAL)
                    continue

                # Cooldown expired, send reminder
                logger.tree("Bump Cooldown Expired", [
                    ("Last Bump", f"{int((time.time() - self._last_bump_time) / 60)} min ago"),
                    ("Action", "Sending reminder"),
                ], emoji="⏰")

                await self._send_reminder()
                self._last_reminder_time = time.time()
                self._save_data()

                logger.tree("Bump Reminder", [
                    ("Status", "Sent, now waiting for bump"),
                ], emoji="✅")

                # Wait for next bump (check periodically)
                while self._running:
                    await asyncio.sleep(300)  # Check every 5 minutes
                    # Check if a new bump happened
                    # record_bump() sets _last_reminder_time to None to signal a new bump
                    if self._last_reminder_time is None:
                        logger.tree("New Bump Detected", [
                            ("Last Bump", f"{int((time.time() - self._last_bump_time) / 60)} min ago" if self._last_bump_time else "Unknown"),
                            ("Action", "Restarting 2-hour cooldown"),
                        ], emoji="🔄")
                        break

            except Exception as e:
                logger.error_tree("Bump Reminder Failed", e, [
                    ("Last Bump", str(self._last_bump_time)),
                    ("Last Reminder", str(self._last_reminder_time)),
                ])
                await asyncio.sleep(60)

    async def _send_reminder(self) -> None:
        """Send a bump reminder in the designated channel."""
        if not self.bot or not self.bump_channel_id:
            logger.tree("Bump Reminder Skipped", [
                ("Reason", "Service not configured"),
            ], emoji="⚠️")
            return

        channel = self.bot.get_channel(self.bump_channel_id)
        if not channel:
            logger.tree("Bump Reminder Skipped", [
                ("Reason", "Channel not found"),
                ("Channel ID", str(self.bump_channel_id)),
            ], emoji="⚠️")
            return

        try:
            role_mention = f"<@&{self.ping_role_id}>" if self.ping_role_id else ""

            embed = discord.Embed(
                title="Time to Bump!",
                description=(
                    "The server is ready to be bumped again!\n\n"
                    "**How to bump:**\n"
                    "Use </bump:947088344167366698> in this channel"
                ),
                color=COLOR_SUCCESS
            )
            embed.set_thumbnail(url="https://disboard.org/images/bot-command-image-bump.png")

            await channel.send(content=role_mention, embed=embed)

            logger.tree("Bump Reminder Sent", [
                ("Channel", f"#{channel.name}"),
                ("Time", datetime.now(timezone.utc).strftime("%H:%M UTC")),
            ], emoji="📢")

        except discord.Forbidden as e:
            logger.error_tree("Bump Reminder Failed", e, [
                ("Reason", "Missing permissions"),
                ("Channel", f"#{channel.name}"),
                ("Channel ID", str(channel.id)),
            ])
        except discord.HTTPException as e:
            logger.error_tree("Bump Reminder Failed", e, [
                ("Channel", f"#{channel.name}"),
                ("Channel ID", str(channel.id)),
            ])


# Global instance
bump_service = BumpService()
