"""
SyriaBot - Bump Reminder Service
================================

Reminds staff to bump the server on Disboard every 2 hours.
Detects successful bumps from Disboard's "bump done" embed.

Author: حَـــــنَّـــــا
"""

import asyncio
import json
import discord
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import time

from src.core.logger import log
from src.utils.footer import set_footer


# =============================================================================
# Bump Reminder Service
# =============================================================================

class BumpService:
    """Service for reminding staff to bump the server on Disboard."""

    BUMP_INTERVAL = 2 * 60 * 60  # 2 hours in seconds
    DISBOARD_BOT_ID = 302050872383242240  # Disboard's bot ID
    DATA_FILE = Path(__file__).parent.parent.parent / "data" / "bump_data.json"

    def __init__(self):
        self.bot: Optional[discord.Client] = None
        self.bump_channel_id: Optional[int] = None
        self.ping_role_id: Optional[int] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_bump_time: Optional[float] = None
        self._last_reminder_time: Optional[float] = None
        self._load_data()

    def setup(self, bot: discord.Client, channel_id: int, role_id: int) -> None:
        """Setup the bump service with bot, channel, and role to ping."""
        self.bot = bot
        self.bump_channel_id = channel_id
        self.ping_role_id = role_id
        log.tree("Bump Reminder Setup", [
            ("Channel ID", str(channel_id)),
            ("Role ID", str(role_id)),
            ("Interval", "2 hours"),
        ], emoji="📢")

    def start(self) -> None:
        """Start the bump reminder scheduler."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._reminder_loop())
        log.tree("Bump Scheduler Started", [
            ("Status", "Running"),
            ("Interval", "2 hours"),
        ], emoji="✅")

    def stop(self) -> None:
        """Stop the bump reminder scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        log.tree("Bump Scheduler Stopped", [
            ("Status", "Stopped"),
        ], emoji="🛑")

    def _load_data(self) -> None:
        """Load bump data from file."""
        try:
            if self.DATA_FILE.exists():
                with open(self.DATA_FILE, "r") as f:
                    data = json.load(f)
                    self._last_bump_time = data.get("last_bump_time")
                    self._last_reminder_time = data.get("last_reminder_time")

                if self._last_bump_time:
                    elapsed_min = int((time.time() - self._last_bump_time) / 60)
                    log.tree("Bump Data Loaded", [
                        ("Last Bump", f"{elapsed_min} min ago"),
                        ("File", str(self.DATA_FILE)),
                    ], emoji="📊")
            else:
                log.tree("Bump Data", [
                    ("Status", "No previous data"),
                    ("File", str(self.DATA_FILE)),
                ], emoji="📊")
        except Exception as e:
            log.tree("Bump Data Load Failed", [
                ("File", str(self.DATA_FILE)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    def _save_data(self) -> None:
        """Save bump data to file."""
        try:
            self.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.DATA_FILE, "w") as f:
                json.dump({
                    "last_bump_time": self._last_bump_time,
                    "last_reminder_time": self._last_reminder_time,
                }, f, indent=2)
        except Exception as e:
            log.tree("Bump Data Save Failed", [
                ("File", str(self.DATA_FILE)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    def record_bump(self) -> None:
        """Record that a bump just happened."""
        self._last_bump_time = time.time()
        self._last_reminder_time = None  # Reset so we send a new reminder after cooldown
        self._save_data()

        log.tree("Bump Recorded", [
            ("Time", datetime.now(timezone.utc).strftime("%H:%M UTC")),
            ("Next Reminder", "in 2 hours"),
        ], emoji="✅")

    async def _reminder_loop(self) -> None:
        """Main loop that sends bump reminders."""
        # Wait for bot to fully initialize
        await asyncio.sleep(10)

        while self._running:
            try:
                # Check cooldown status
                if self._last_bump_time:
                    elapsed = time.time() - self._last_bump_time
                    remaining = self.BUMP_INTERVAL - elapsed

                    if remaining > 0:
                        # Still on cooldown, wait
                        remaining_min = int(remaining // 60)
                        log.tree("Bump Cooldown", [
                            ("Remaining", f"{remaining_min} min"),
                        ], emoji="⏳")
                        await asyncio.sleep(remaining + 5)
                        continue

                    # Cooldown expired - check if we already sent a reminder
                    if self._last_reminder_time and self._last_reminder_time > self._last_bump_time:
                        # Already sent a reminder, wait for next bump
                        log.tree("Bump Reminder", [
                            ("Status", "Already sent, waiting for bump"),
                        ], emoji="⏸️")
                        await asyncio.sleep(300)  # Check every 5 minutes
                        continue
                else:
                    # No recorded bump - just wait, don't spam
                    log.tree("Bump Service", [
                        ("Status", "No bump recorded, waiting"),
                    ], emoji="⏰")
                    await asyncio.sleep(self.BUMP_INTERVAL)
                    continue

                # Send reminder
                await self._send_reminder()
                self._last_reminder_time = time.time()
                self._save_data()

                log.tree("Bump Reminder", [
                    ("Status", "Sent, waiting for bump"),
                ], emoji="⏳")

                # Wait for next bump (check periodically)
                while self._running:
                    await asyncio.sleep(300)  # Check every 5 minutes
                    # If a new bump happened, break out to restart cooldown
                    if self._last_bump_time and self._last_bump_time > self._last_reminder_time:
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error_tree("Bump Reminder Failed", e, [
                    ("Status", "Will retry"),
                ])
                await asyncio.sleep(60)

    async def _send_reminder(self) -> None:
        """Send a bump reminder in the designated channel."""
        if not self.bot or not self.bump_channel_id:
            log.tree("Bump Reminder Skipped", [
                ("Reason", "Service not configured"),
                ("Bot", "Missing" if not self.bot else "OK"),
                ("Channel ID", str(self.bump_channel_id) if self.bump_channel_id else "Missing"),
            ], emoji="⚠️")
            return

        channel = self.bot.get_channel(self.bump_channel_id)
        if not channel:
            log.tree("Bump Channel Not Found", [
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
                color=0x24B7B7
            )
            embed.set_thumbnail(url="https://disboard.org/images/bot-command-image-bump.png")
            set_footer(embed)

            await channel.send(content=role_mention, embed=embed)

            log.tree("Bump Reminder Sent", [
                ("Channel", f"#{channel.name}"),
                ("Channel ID", str(channel.id)),
                ("Role ID", str(self.ping_role_id)),
                ("Time", datetime.now(timezone.utc).strftime("%H:%M UTC")),
            ], emoji="📢")

        except discord.Forbidden:
            log.tree("Bump Reminder Failed", [
                ("Reason", "No permission"),
                ("Channel", f"#{channel.name}"),
                ("Channel ID", str(self.bump_channel_id)),
            ], emoji="❌")
        except discord.HTTPException as e:
            log.tree("Bump Reminder Failed", [
                ("Channel", f"#{channel.name}"),
                ("Channel ID", str(self.bump_channel_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")


# Global instance
bump_service = BumpService()
