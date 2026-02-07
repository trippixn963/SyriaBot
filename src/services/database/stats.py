"""
SyriaBot - Database Stats Mixin
===============================

Server-level statistics database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import List, Dict, Any

from src.core.logger import logger


class StatsMixin:
    """Mixin for server statistics database operations."""

    # =========================================================================
    # Daily Stats
    # =========================================================================

    def record_daily_activity(self, guild_id: int, user_id: int, date: str) -> None:
        """Record a user's activity for the day (for DAU tracking)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, unique_users, total_messages)
                VALUES (?, ?, 1, 1)
                ON CONFLICT(date) DO UPDATE SET
                    total_messages = total_messages + 1
            """, (date, guild_id))

    def increment_daily_unique_user(self, guild_id: int, date: str) -> None:
        """Increment unique user count for the day."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, unique_users, total_messages)
                VALUES (?, ?, 1, 0)
                ON CONFLICT(date) DO UPDATE SET
                    unique_users = unique_users + 1
            """, (date, guild_id))

    def increment_daily_messages(self, guild_id: int, date: str) -> None:
        """Increment total messages for the day."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, total_messages)
                VALUES (?, ?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    total_messages = total_messages + 1
            """, (date, guild_id))

    def update_voice_peak(self, guild_id: int, date: str, current_users: int) -> None:
        """Update voice peak if current is higher."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, voice_peak_users)
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    voice_peak_users = MAX(voice_peak_users, ?)
            """, (date, guild_id, current_users, current_users))

    def increment_new_members(self, guild_id: int, date: str) -> None:
        """Increment new members count for the day."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, new_members)
                VALUES (?, ?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    new_members = new_members + 1
            """, (date, guild_id))

    def get_daily_stats(self, guild_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily stats for the last N days."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM server_daily_stats
                WHERE guild_id = ?
                ORDER BY date DESC
                LIMIT ?
            """, (guild_id, days))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Channel Activity
    # =========================================================================

    def increment_channel_messages(self, channel_id: int, guild_id: int, channel_name: str) -> None:
        """Increment message count for a channel."""
        now = int(time.time())
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO channel_stats (channel_id, guild_id, channel_name, total_messages, last_message_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    total_messages = total_messages + 1,
                    last_message_at = ?,
                    channel_name = ?
            """, (channel_id, guild_id, channel_name, now, now, channel_name))

    def get_channel_stats(self, guild_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get channel activity stats sorted by message count."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM channel_stats
                WHERE guild_id = ?
                ORDER BY total_messages DESC
                LIMIT ?
            """, (guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    def get_inactive_channels(self, guild_id: int, days_inactive: int = 7) -> List[Dict[str, Any]]:
        """Get channels with no activity in the last N days."""
        cutoff = int(time.time()) - (days_inactive * 86400)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM channel_stats
                WHERE guild_id = ? AND last_message_at < ?
                ORDER BY last_message_at ASC
            """, (guild_id, cutoff))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # User Channel Activity (per-user-per-channel tracking)
    # =========================================================================

    def increment_user_channel_messages(
        self,
        user_id: int,
        channel_id: int,
        guild_id: int,
        channel_name: str
    ) -> None:
        """Increment message count for a user in a specific channel."""
        now = int(time.time())
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_channel_activity
                    (user_id, channel_id, guild_id, channel_name, message_count, last_message_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(user_id, channel_id) DO UPDATE SET
                    message_count = message_count + 1,
                    last_message_at = ?,
                    channel_name = ?
            """, (user_id, channel_id, guild_id, channel_name, now, now, channel_name))

    def get_user_channel_activity(
        self,
        user_id: int,
        guild_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top channels for a user sorted by message count."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT channel_id, channel_name, message_count, last_message_at
                FROM user_channel_activity
                WHERE user_id = ? AND guild_id = ?
                ORDER BY message_count DESC
                LIMIT ?
            """, (user_id, guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Server Hourly Activity
    # =========================================================================

    def increment_server_hour_activity(self, guild_id: int, hour: int, activity_type: str = "message") -> None:
        """Increment hourly activity counter."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            if activity_type == "message":
                cur.execute("""
                    INSERT INTO server_hourly_activity (guild_id, hour, message_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(guild_id, hour) DO UPDATE SET
                        message_count = message_count + 1
                """, (guild_id, hour))
            else:  # voice
                cur.execute("""
                    INSERT INTO server_hourly_activity (guild_id, hour, voice_joins)
                    VALUES (?, ?, 1)
                    ON CONFLICT(guild_id, hour) DO UPDATE SET
                        voice_joins = voice_joins + 1
                """, (guild_id, hour))

    def get_server_peak_hours(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get hourly activity breakdown sorted by message count."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM server_hourly_activity
                WHERE guild_id = ?
                ORDER BY message_count DESC
            """, (guild_id,))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Boost History
    # =========================================================================

    def record_boost(self, user_id: int, guild_id: int, action: str) -> None:
        """Record a boost/unboost event."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO boost_history (user_id, guild_id, action, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (user_id, guild_id, action, int(time.time())))
            logger.tree("DB: Boost Recorded", [
                ("ID", str(user_id)),
                ("Action", action),
            ], emoji="💎" if action == "boost" else "💔")
        except Exception as e:
            logger.tree("DB: Record Boost Error", [
                ("ID", str(user_id)),
                ("Action", action),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def get_boost_history(self, guild_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get boost history for a guild."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM boost_history
                WHERE guild_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    def get_user_boost_count(self, user_id: int, guild_id: int) -> int:
        """Get how many times a user has boosted."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as count FROM boost_history
                WHERE user_id = ? AND guild_id = ? AND action = 'boost'
            """, (user_id, guild_id))
            row = cur.fetchone()
            return row["count"] if row else 0

    # =========================================================================
    # Member Retention
    # =========================================================================

    def get_retention_stats(self, guild_id: int, days_ago: int = 7) -> Dict[str, Any]:
        """
        Get retention stats for members who joined N days ago.

        Returns dict with:
        - joined_count: How many joined N days ago
        - still_active: How many have been active in last 3 days
        - retention_rate: Percentage still active
        """
        now = int(time.time())

        join_start = now - ((days_ago + 1) * 86400)
        join_end = now - (days_ago * 86400)
        active_cutoff = now - (3 * 86400)

        with self._get_conn() as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT COUNT(*) as count FROM user_xp
                WHERE guild_id = ? AND first_message_at BETWEEN ? AND ?
            """, (guild_id, join_start, join_end))
            joined = cur.fetchone()["count"]

            cur.execute("""
                SELECT COUNT(*) as count FROM user_xp
                WHERE guild_id = ?
                    AND first_message_at BETWEEN ? AND ?
                    AND last_active_at > ?
            """, (guild_id, join_start, join_end, active_cutoff))
            active = cur.fetchone()["count"]

            retention = (active / joined * 100) if joined > 0 else 0

            return {
                "days_ago": days_ago,
                "joined_count": joined,
                "still_active": active,
                "retention_rate": round(retention, 1),
            }
