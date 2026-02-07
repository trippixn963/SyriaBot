"""
SyriaBot - Background Task Service
==================================

Background tasks for cache refresh and snapshots.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.core.logger import logger
from src.core.constants import TIMEZONE_EST
from src.core.config import config
from src.services.database import db
from src.api.services.cache import get_cache_service


class BackgroundTaskService:
    """
    Manages background tasks for the API.
    """

    def __init__(self, bot: Any):
        self._bot = bot
        self._cache = get_cache_service()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._midnight_task: Optional[asyncio.Task] = None
        self._snapshot_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start all background tasks."""
        if self._running:
            return

        self._running = True

        # Bootstrap snapshots if needed
        await self._bootstrap_snapshots()

        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._midnight_task = asyncio.create_task(self._midnight_booster_refresh())
        self._snapshot_task = asyncio.create_task(self._daily_xp_snapshot())

        logger.tree("Background Tasks Started", [
            ("Cleanup", "Every 2 min"),
            ("Booster Refresh", "Midnight EST"),
            ("XP Snapshots", "Midnight UTC"),
        ], emoji="⏰")

    async def stop(self) -> None:
        """Stop all background tasks."""
        self._running = False

        tasks = [self._cleanup_task, self._midnight_task, self._snapshot_task]
        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._cleanup_task = None
        self._midnight_task = None
        self._snapshot_task = None

        logger.tree("Background Tasks Stopped", [], emoji="⏹️")

    # =========================================================================
    # Periodic Cleanup
    # =========================================================================

    async def _periodic_cleanup(self) -> None:
        """Periodically cleanup caches."""
        while self._running:
            await asyncio.sleep(120)  # Every 2 minutes

            try:
                expired = await self._cache.cleanup_expired_responses()
                if expired > 0:
                    logger.debug("Cache Cleanup", [
                        ("Expired Entries", str(expired)),
                    ])
            except Exception as e:
                logger.error("Cache Cleanup Error", [
                    ("Error", str(e)[:50]),
                ])

    # =========================================================================
    # Midnight Booster Refresh
    # =========================================================================

    async def _midnight_booster_refresh(self) -> None:
        """Refresh booster status for all cached users at midnight EST."""
        while self._running:
            try:
                # Calculate seconds until next midnight EST
                now_est = datetime.now(TIMEZONE_EST)
                tomorrow = now_est.replace(hour=0, minute=0, second=0, microsecond=0)
                if now_est.hour >= 0:
                    tomorrow += timedelta(days=1)
                seconds_until_midnight = (tomorrow - now_est).total_seconds()

                logger.tree("Midnight Booster Refresh Scheduled", [
                    ("Next Run", tomorrow.strftime("%Y-%m-%d %H:%M:%S EST")),
                    ("Wait Time", f"{int(seconds_until_midnight // 3600)}h {int((seconds_until_midnight % 3600) // 60)}m"),
                ], emoji="⏰")

                await asyncio.sleep(seconds_until_midnight)

                if not self._running:
                    break

                # Run the refresh
                await self._refresh_all_booster_status()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Midnight Refresh Error", [
                    ("Error", str(e)[:50]),
                ])
                # Wait an hour before retrying on error
                await asyncio.sleep(3600)

    async def _refresh_all_booster_status(self) -> None:
        """Refresh booster status for all cached users."""
        if not self._bot or not self._bot.is_ready():
            logger.tree("Booster Refresh Skipped", [
                ("Reason", "Bot not ready"),
            ], emoji="⚠️")
            return

        guild = self._bot.get_guild(config.GUILD_ID)
        if not guild:
            logger.tree("Booster Refresh Skipped", [
                ("Reason", "Guild not found"),
            ], emoji="⚠️")
            return

        cached_user_ids = await self._cache.get_cached_user_ids()
        total_users = len(cached_user_ids)

        if total_users == 0:
            return

        logger.tree("Midnight Booster Refresh Started", [
            ("Users to Check", str(total_users)),
        ], emoji="🔄")

        updated = 0
        errors = 0

        for i, user_id in enumerate(cached_user_ids):
            try:
                member = guild.get_member(user_id)
                if not member:
                    try:
                        member = await guild.fetch_member(user_id)
                    except Exception:
                        # User left server
                        await self._cache.remove_avatar(user_id)
                        continue

                # Get current cached data
                cached = await self._cache.get_avatar(user_id)
                if cached:
                    cached_is_booster = cached[4]
                    current_is_booster = member.premium_since is not None

                    if current_is_booster != cached_is_booster:
                        # Update cache with new booster status
                        display_name = member.global_name or member.display_name or member.name
                        username = member.name
                        if member.guild_avatar:
                            avatar_url = member.guild_avatar.url
                        elif member.avatar:
                            avatar_url = member.avatar.url
                        else:
                            avatar_url = member.default_avatar.url
                        joined_at = int(member.joined_at.timestamp()) if member.joined_at else None

                        await self._cache.set_avatar(
                            user_id, avatar_url, display_name, username, joined_at, current_is_booster
                        )
                        updated += 1

                # Stagger checks to avoid blocking
                if (i + 1) % 50 == 0:
                    await asyncio.sleep(0.5)
                else:
                    await asyncio.sleep(0.01)

            except Exception:
                errors += 1

        # Clear response cache if any updates occurred
        if updated > 0:
            await self._cache.clear_responses()

        logger.tree("Midnight Booster Refresh Complete", [
            ("Checked", str(total_users)),
            ("Updated", str(updated)),
            ("Errors", str(errors)),
        ], emoji="✅")

    # =========================================================================
    # Daily XP Snapshots
    # =========================================================================

    async def _daily_xp_snapshot(self) -> None:
        """Create daily XP snapshots at midnight UTC."""
        while self._running:
            try:
                # Calculate seconds until next midnight UTC
                now_utc = datetime.now(timezone.utc)
                tomorrow_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
                if now_utc.hour >= 0:
                    tomorrow_utc += timedelta(days=1)
                seconds_until_midnight = (tomorrow_utc - now_utc).total_seconds()

                logger.tree("XP Snapshot Scheduled", [
                    ("Next Run", tomorrow_utc.strftime("%Y-%m-%d %H:%M:%S UTC")),
                    ("Wait Time", f"{int(seconds_until_midnight // 3600)}h {int((seconds_until_midnight % 3600) // 60)}m"),
                ], emoji="📸")

                await asyncio.sleep(seconds_until_midnight)

                if not self._running:
                    break

                # Create snapshot in thread to avoid blocking
                snapshot_count = await asyncio.to_thread(db.create_daily_snapshot)

                # Cleanup old snapshots (keep 35 days for monthly leaderboards)
                deleted = await asyncio.to_thread(db.cleanup_old_snapshots, 35)

                logger.tree("Daily XP Snapshot Complete", [
                    ("Users Snapshotted", str(snapshot_count)),
                    ("Old Snapshots Deleted", str(deleted)),
                ], emoji="✅")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("XP Snapshot Error", [
                    ("Error", str(e)[:50]),
                ])
                # Wait an hour before retrying
                await asyncio.sleep(3600)

    async def _bootstrap_snapshots(self) -> None:
        """Create initial XP snapshot if none exist."""
        try:
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

            with db._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) as count FROM xp_snapshots
                    WHERE guild_id = ? AND date = ?
                """, (config.GUILD_ID, yesterday))
                row = cur.fetchone()
                has_yesterday = row["count"] > 0 if row else False

            if not has_yesterday:
                logger.tree("XP Snapshot Bootstrap", [
                    ("Status", "Creating initial snapshot"),
                    ("Date", yesterday),
                ], emoji="🔧")

                with db._get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT OR IGNORE INTO xp_snapshots
                            (user_id, guild_id, date, xp_total, level, total_messages, voice_minutes)
                        SELECT
                            user_id, guild_id, ?, xp, level, total_messages, voice_minutes
                        FROM user_xp
                        WHERE guild_id = ? AND is_active = 1
                    """, (yesterday, config.GUILD_ID))
                    count = cur.rowcount

                logger.tree("XP Snapshot Bootstrap Complete", [
                    ("Users", str(count)),
                    ("Date", yesterday),
                ], emoji="✅")
            else:
                logger.tree("XP Snapshots Found", [
                    ("Status", "Period leaderboards ready"),
                ], emoji="📸")

        except Exception as e:
            logger.error("XP Snapshot Bootstrap Error", [
                ("Error", str(e)[:50]),
            ])


# =============================================================================
# Singleton
# =============================================================================

_background_service: Optional[BackgroundTaskService] = None


def get_background_service() -> Optional[BackgroundTaskService]:
    """Get the background service singleton."""
    return _background_service


def init_background_service(bot: Any) -> BackgroundTaskService:
    """Initialize the background service."""
    global _background_service
    _background_service = BackgroundTaskService(bot)
    return _background_service


__all__ = ["BackgroundTaskService", "get_background_service", "init_background_service"]
