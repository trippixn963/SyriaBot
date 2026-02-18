"""
SyriaBot - Database XP Mixin
============================

XP/Leveling system database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import json
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from src.core.logger import logger


class XPMixin:
    """Mixin for XP system database operations."""

    # =========================================================================
    # Core XP Methods
    # =========================================================================

    def get_user_xp(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get user's XP data for a guild."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM user_xp WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_users_with_levels(self, guild_id: int) -> list:
        """Get all users with their levels for role sync."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id, level FROM user_xp WHERE guild_id = ? AND level >= 1",
                (guild_id,)
            )
            return cur.fetchall()

    def ensure_user_xp(self, user_id: int, guild_id: int) -> Dict[str, Any]:
        """Get or create user's XP data."""
        data = self.get_user_xp(user_id, guild_id)
        if data:
            return data

        now = int(time.time())
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_xp (user_id, guild_id, xp, level, total_messages, voice_minutes, created_at)
                VALUES (?, ?, 0, 0, 0, 0, ?)
            """, (user_id, guild_id, now))

            if cur.rowcount == 0:
                logger.tree("XP User Create Failed", [
                    ("ID", str(user_id)),
                    ("Guild ID", str(guild_id)),
                ], emoji="⚠️")

        return {
            "user_id": user_id,
            "guild_id": guild_id,
            "xp": 0,
            "level": 0,
            "total_messages": 0,
            "voice_minutes": 0,
            "last_message_xp": 0,
            "last_voice_xp": 0,
            "created_at": now,
        }

    def add_xp(
        self,
        user_id: int,
        guild_id: int,
        amount: int,
        source: str = "message"
    ) -> Dict[str, Any]:
        """
        Add XP to a user atomically.

        Args:
            user_id: User's Discord ID
            guild_id: Guild's Discord ID
            amount: XP amount to add
            source: "message" or "voice"

        Returns:
            Dict with old_level, new_level, old_xp, new_xp, leveled_up
        """
        from src.services.xp.utils import level_from_xp

        now = int(time.time())

        self.ensure_user_xp(user_id, guild_id)

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Use BEGIN IMMEDIATE to acquire write lock before reading
            # This prevents race conditions between SELECT and UPDATE
            cur.execute("BEGIN IMMEDIATE")

            try:
                cur.execute(
                    "SELECT xp, level FROM user_xp WHERE user_id = ? AND guild_id = ?",
                    (user_id, guild_id)
                )
                row = cur.fetchone()
                old_xp = row["xp"]
                old_level = row["level"]

                new_xp = old_xp + amount
                new_level = level_from_xp(new_xp)

                if source == "message":
                    cur.execute("""
                        UPDATE user_xp
                        SET xp = ?, level = ?, last_message_xp = ?
                        WHERE user_id = ? AND guild_id = ?
                    """, (new_xp, new_level, now, user_id, guild_id))
                else:  # voice
                    cur.execute("""
                        UPDATE user_xp
                        SET xp = ?, level = ?, last_voice_xp = ?, voice_minutes = voice_minutes + 1
                        WHERE user_id = ? AND guild_id = ?
                    """, (new_xp, new_level, now, user_id, guild_id))

                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return {
            "old_xp": old_xp,
            "new_xp": new_xp,
            "old_level": old_level,
            "new_level": new_level,
            "leveled_up": new_level > old_level,
        }

    def increment_message_count(self, user_id: int, guild_id: int) -> int:
        """
        Increment user's message count and server total atomically.

        Called on every message, regardless of XP cooldown.
        - User's personal count: useful for individual stats
        - Server counter: O(1) for real-time WebSocket broadcast

        Returns:
            New server-wide total message count
        """
        self.ensure_user_xp(user_id, guild_id)

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Increment user's personal count
            cur.execute("""
                UPDATE user_xp
                SET total_messages = total_messages + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

            # Increment server counter (O(1)) and return new value
            cur.execute("""
                INSERT INTO server_counters (guild_id, counter_name, value)
                VALUES (?, 'total_messages', 1)
                ON CONFLICT(guild_id, counter_name) DO UPDATE SET
                    value = value + 1
                RETURNING value
            """, (guild_id,))
            row = cur.fetchone()
            return row[0] if row else 1

    def set_user_level(self, user_id: int, guild_id: int, level: int) -> None:
        """Set user's level."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE user_xp SET level = ? WHERE user_id = ? AND guild_id = ?
                """, (level, user_id, guild_id))
        except Exception as e:
            logger.tree("DB: Set Level Error", [
                ("ID", str(user_id)),
                ("Level", str(level)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def set_xp(self, user_id: int, guild_id: int, xp: int, level: int) -> None:
        """
        Set user's XP and level directly (overwrites current values).

        Used by API for administrative XP adjustments.
        """
        try:
            # Ensure user exists first
            self.ensure_user_xp(user_id, guild_id)

            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE user_xp SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?
                """, (xp, level, user_id, guild_id))

            logger.tree("DB: XP Set", [
                ("ID", str(user_id)),
                ("XP", str(xp)),
                ("Level", str(level)),
            ], emoji="✏️")
        except Exception as e:
            logger.error_tree("DB: Set XP Error", e, [
                ("ID", str(user_id)),
                ("XP", str(xp)),
            ])

    def get_last_message_xp(self, user_id: int, guild_id: int) -> Optional[int]:
        """Get timestamp of last message XP gain. Returns None if user has no entry."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT last_message_xp FROM user_xp WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = cur.fetchone()
            # Return None if no entry exists, otherwise return the timestamp
            # (which could be 0 if user exists but never gained message XP)
            return row["last_message_xp"] if row else None

    # =========================================================================
    # Leaderboard Methods
    # =========================================================================

    def get_leaderboard(
        self,
        guild_id: int = None,
        limit: int = 10,
        offset: int = 0,
        period: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Get top users by XP in a guild with pagination (only active members).

        Args:
            guild_id: Guild ID (defaults to config.GUILD_ID)
            limit: Max results to return
            offset: Starting position
            period: Time period filter - "all", "month", "week", "today"
                    Filters by last_active_at timestamp

        Returns:
            List of user dicts with rank calculated based on filtered results
        """
        from src.core.config import config
        import time

        gid = guild_id or config.GUILD_ID

        # Calculate cutoff timestamp based on period
        now = int(time.time())
        if period == "today":
            cutoff = now - 86400  # 24 hours
        elif period == "week":
            cutoff = now - 604800  # 7 days
        elif period == "month":
            cutoff = now - 2592000  # 30 days
        else:
            cutoff = 0  # All time (no filter)

        with self._get_conn() as conn:
            cur = conn.cursor()

            if cutoff > 0:
                # Filter by last_active_at for time periods
                cur.execute("""
                    SELECT user_id, xp, level, total_messages, voice_minutes,
                           last_active_at, streak_days,
                           ROW_NUMBER() OVER (ORDER BY xp DESC) as rank
                    FROM user_xp
                    WHERE guild_id = ? AND is_active = 1 AND last_active_at >= ?
                    ORDER BY xp DESC
                    LIMIT ? OFFSET ?
                """, (gid, cutoff, limit, offset))
            else:
                # All time - no last_active_at filter
                cur.execute("""
                    SELECT user_id, xp, level, total_messages, voice_minutes,
                           last_active_at, streak_days,
                           ROW_NUMBER() OVER (ORDER BY xp DESC) as rank
                    FROM user_xp
                    WHERE guild_id = ? AND is_active = 1
                    ORDER BY xp DESC
                    LIMIT ? OFFSET ?
                """, (gid, limit, offset))

            return [dict(row) for row in cur.fetchall()]

    def get_total_ranked_users(self, guild_id: int = None, period: str = "all") -> int:
        """
        Get total number of active users with XP in a guild.

        Args:
            guild_id: Guild ID (defaults to config.GUILD_ID)
            period: Time period filter - "all", "month", "week", "today"
        """
        from src.core.config import config
        import time

        gid = guild_id or config.GUILD_ID

        # Calculate cutoff timestamp based on period
        now = int(time.time())
        if period == "today":
            cutoff = now - 86400
        elif period == "week":
            cutoff = now - 604800
        elif period == "month":
            cutoff = now - 2592000
        else:
            cutoff = 0

        with self._get_conn() as conn:
            cur = conn.cursor()

            if cutoff > 0:
                cur.execute("""
                    SELECT COUNT(*) as total
                    FROM user_xp
                    WHERE guild_id = ? AND is_active = 1 AND last_active_at >= ?
                """, (gid, cutoff))
            else:
                cur.execute("""
                    SELECT COUNT(*) as total
                    FROM user_xp
                    WHERE guild_id = ? AND is_active = 1
                """, (gid,))

            row = cur.fetchone()
            return row["total"] if row else 0

    def get_xp_stats(self, guild_id: int = None) -> Dict[str, Any]:
        """Get overall XP statistics for a guild (only active members)."""
        from src.core.config import config
        gid = guild_id or config.GUILD_ID

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Get user stats (excluding total_messages which uses server counter)
            cur.execute("""
                SELECT
                    COUNT(*) as total_users,
                    COALESCE(SUM(xp), 0) as total_xp,
                    COALESCE(SUM(voice_minutes), 0) as total_voice_minutes,
                    COALESCE(MAX(level), 0) as highest_level
                FROM user_xp
                WHERE guild_id = ? AND is_active = 1
            """, (gid,))
            row = cur.fetchone()
            stats = dict(row) if row else {
                "total_users": 0,
                "total_xp": 0,
                "total_voice_minutes": 0,
                "highest_level": 0,
            }

            # Get total messages from server counter (O(1) instead of SUM)
            cur.execute("""
                SELECT value FROM server_counters
                WHERE guild_id = ? AND counter_name = 'total_messages'
            """, (gid,))
            counter_row = cur.fetchone()
            stats["total_messages"] = counter_row[0] if counter_row else 0

            return stats

    def get_user_rank(self, user_id: int, guild_id: int) -> int:
        """Get user's rank position in the guild (1-indexed, only active members)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) + 1 as rank
                FROM user_xp
                WHERE guild_id = ? AND is_active = 1 AND xp > (
                    SELECT COALESCE(xp, 0) FROM user_xp
                    WHERE user_id = ? AND guild_id = ?
                )
            """, (guild_id, user_id, guild_id))
            row = cur.fetchone()
            return row["rank"] if row else 1

    # =========================================================================
    # Active Status
    # =========================================================================

    def set_user_active(self, user_id: int, guild_id: int) -> None:
        """Mark a user as active (in server) for leaderboard visibility."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE user_xp SET is_active = 1
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
                conn.commit()
            logger.tree("DB: User Active", [
                ("ID", str(user_id)),
                ("Status", "Active"),
            ], emoji="✅")
        except Exception as e:
            logger.tree("DB: Set Active Error", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def set_user_inactive(self, user_id: int, guild_id: int) -> None:
        """Mark a user as inactive (left server) to hide from leaderboard."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE user_xp SET is_active = 0
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
                conn.commit()
            logger.tree("DB: User Inactive", [
                ("ID", str(user_id)),
                ("Status", "Inactive"),
            ], emoji="👋")
        except Exception as e:
            logger.tree("DB: Set Inactive Error", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    # =========================================================================
    # Extended User Tracking
    # =========================================================================

    def increment_commands_used(self, user_id: int, guild_id: int) -> None:
        """Increment user's commands used count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET commands_used = commands_used + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    def increment_reactions_given(self, user_id: int, guild_id: int) -> None:
        """Increment user's reactions given count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET reactions_given = reactions_given + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    def increment_images_shared(self, user_id: int, guild_id: int) -> None:
        """Increment user's images shared count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET images_shared = images_shared + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    def increment_voice_sessions(self, user_id: int, guild_id: int) -> None:
        """Increment user's total voice sessions count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET total_voice_sessions = total_voice_sessions + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    def update_longest_voice_session(self, user_id: int, guild_id: int, minutes: int) -> None:
        """Update longest voice session if current is longer."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET longest_voice_session = MAX(longest_voice_session, ?)
                WHERE user_id = ? AND guild_id = ?
            """, (minutes, user_id, guild_id))

    def set_first_message_at(self, user_id: int, guild_id: int, timestamp: int) -> None:
        """Set first message timestamp (only if not already set)."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET first_message_at = ?
                WHERE user_id = ? AND guild_id = ? AND first_message_at = 0
            """, (timestamp, user_id, guild_id))

    def update_last_active(self, user_id: int, guild_id: int, timestamp: int) -> None:
        """Update last active timestamp."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET last_active_at = ?
                WHERE user_id = ? AND guild_id = ?
            """, (timestamp, user_id, guild_id))

    def update_streak(self, user_id: int, guild_id: int, today_date: str) -> int:
        """
        Update user's streak. Call this when user is active.

        Returns:
            New streak count
        """
        self.ensure_user_xp(user_id, guild_id)

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT streak_days, last_streak_date FROM user_xp
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()

            current_streak = row["streak_days"] if row else 0
            last_date = row["last_streak_date"] if row else ""

            if last_date == today_date:
                return current_streak

            if last_date:
                try:
                    last = datetime.strptime(last_date, "%Y-%m-%d").date()
                    today = datetime.strptime(today_date, "%Y-%m-%d").date()
                    yesterday = today - timedelta(days=1)

                    if last == yesterday:
                        new_streak = current_streak + 1
                    else:
                        new_streak = 1
                except ValueError:
                    new_streak = 1
            else:
                new_streak = 1

            cur.execute("""
                UPDATE user_xp SET streak_days = ?, last_streak_date = ?
                WHERE user_id = ? AND guild_id = ?
            """, (new_streak, today_date, user_id, guild_id))

            return new_streak

    def increment_activity_hour(self, user_id: int, guild_id: int, hour: int) -> None:
        """Increment activity count for a specific hour (0-23)."""
        self.ensure_user_xp(user_id, guild_id)

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT activity_hours FROM user_xp
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()

            hours_data = {}
            if row and row["activity_hours"]:
                try:
                    hours_data = json.loads(row["activity_hours"])
                except json.JSONDecodeError:
                    hours_data = {}

            hour_key = str(hour)
            hours_data[hour_key] = hours_data.get(hour_key, 0) + 1

            cur.execute("""
                UPDATE user_xp SET activity_hours = ?
                WHERE user_id = ? AND guild_id = ?
            """, (json.dumps(hours_data), user_id, guild_id))

    def get_peak_activity_hour(self, user_id: int, guild_id: int) -> tuple[int, int]:
        """Get user's peak activity hour. Returns (hour, count) or (-1, 0)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT activity_hours FROM user_xp
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()

            if not row or not row["activity_hours"]:
                return (-1, 0)

            try:
                hours_data = json.loads(row["activity_hours"])
                if not hours_data:
                    return (-1, 0)

                peak_hour = max(hours_data, key=lambda h: hours_data[h])
                return (int(peak_hour), hours_data[peak_hour])
            except (json.JSONDecodeError, ValueError):
                return (-1, 0)

    def set_invited_by(self, user_id: int, guild_id: int, inviter_id: int) -> None:
        """Set who invited this user."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET invited_by = ?
                WHERE user_id = ? AND guild_id = ?
            """, (inviter_id, user_id, guild_id))

    def get_invite_count(self, user_id: int, guild_id: int) -> int:
        """Get how many users this person has invited."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as count FROM user_xp
                WHERE guild_id = ? AND invited_by = ?
            """, (guild_id, user_id))
            row = cur.fetchone()
            return row["count"] if row else 0

    def increment_mentions_received(self, user_id: int, guild_id: int, count: int = 1) -> None:
        """Increment user's mentions received count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET mentions_received = mentions_received + ?
                WHERE user_id = ? AND guild_id = ?
            """, (count, user_id, guild_id))

    # =========================================================================
    # XP Snapshots (for period-based leaderboards)
    # =========================================================================

    def create_daily_snapshot(self, guild_id: int = None) -> int:
        """
        Create a snapshot of all users' current XP for period tracking.
        Should be called once daily (e.g., at midnight via scheduled task).

        Args:
            guild_id: Guild ID (defaults to config.GUILD_ID)

        Returns:
            Number of users snapshotted
        """
        from src.core.config import config
        from datetime import datetime, timezone

        gid = guild_id or config.GUILD_ID
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Insert or replace snapshots for all active users
            cur.execute("""
                INSERT OR REPLACE INTO xp_snapshots
                    (user_id, guild_id, date, xp_total, level, total_messages, voice_minutes)
                SELECT
                    user_id, guild_id, ?, xp, level, total_messages, voice_minutes
                FROM user_xp
                WHERE guild_id = ? AND is_active = 1
            """, (today, gid))

            count = cur.rowcount

        logger.tree("XP Snapshot Created", [
            ("Date", today),
            ("Guild", str(gid)),
            ("Users", str(count)),
        ], emoji="📸")

        return count

    def get_snapshot_date_for_period(self, period: str) -> str:
        """
        Get the reference date for a period (the date to compare against).

        Args:
            period: "today", "week", or "month"

        Returns:
            Date string (YYYY-MM-DD) of the comparison snapshot
        """
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)

        if period == "today":
            # Compare to yesterday's snapshot
            ref_date = now - timedelta(days=1)
        elif period == "week":
            # Compare to 7 days ago
            ref_date = now - timedelta(days=7)
        elif period == "month":
            # Compare to 30 days ago
            ref_date = now - timedelta(days=30)
        else:
            # All time - no snapshot needed
            return ""

        return ref_date.strftime("%Y-%m-%d")

    def get_period_leaderboard(
        self,
        guild_id: int = None,
        limit: int = 10,
        offset: int = 0,
        period: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard ranked by XP gained during a specific period.

        Unlike get_leaderboard (which filters by last_active_at),
        this calculates actual XP gained = current_xp - snapshot_xp.

        Args:
            guild_id: Guild ID (defaults to config.GUILD_ID)
            limit: Max results to return
            offset: Starting position
            period: Time period - "all", "month", "week", "today"

        Returns:
            List of user dicts with xp_gained field, ranked by XP gained
        """
        from src.core.config import config

        gid = guild_id or config.GUILD_ID

        # For "all" time, use regular leaderboard
        if period == "all":
            return self.get_leaderboard(guild_id=gid, limit=limit, offset=offset, period="all")

        snapshot_date = self.get_snapshot_date_for_period(period)

        logger.tree("Period Leaderboard Query", [
            ("Period", period),
            ("Snapshot Date", snapshot_date),
            ("Limit", str(limit)),
            ("Offset", str(offset)),
        ], emoji="📊")

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Join current XP with snapshot, calculate XP gained
            # Users without a snapshot get full current XP as "gained"
            cur.execute("""
                SELECT
                    u.user_id,
                    u.xp as current_xp,
                    u.level,
                    u.total_messages,
                    u.voice_minutes,
                    u.last_active_at,
                    u.streak_days,
                    COALESCE(s.xp_total, 0) as snapshot_xp,
                    (u.xp - COALESCE(s.xp_total, 0)) as xp_gained,
                    ROW_NUMBER() OVER (ORDER BY (u.xp - COALESCE(s.xp_total, 0)) DESC) as rank
                FROM user_xp u
                LEFT JOIN xp_snapshots s ON
                    u.user_id = s.user_id AND
                    u.guild_id = s.guild_id AND
                    s.date = ?
                WHERE u.guild_id = ? AND u.is_active = 1
                ORDER BY xp_gained DESC
                LIMIT ? OFFSET ?
            """, (snapshot_date, gid, limit, offset))

            results = []
            for row in cur.fetchall():
                results.append({
                    "user_id": row["user_id"],
                    "xp": row["current_xp"],
                    "xp_gained": row["xp_gained"],
                    "level": row["level"],
                    "total_messages": row["total_messages"],
                    "voice_minutes": row["voice_minutes"],
                    "last_active_at": row["last_active_at"],
                    "streak_days": row["streak_days"],
                    "rank": row["rank"],
                })

            # Log top gainer if results exist
            if results:
                top = results[0]
                logger.tree("Period Leaderboard Results", [
                    ("Period", period),
                    ("Results", str(len(results))),
                    ("Top Gainer", f"User {top['user_id']} (+{top['xp_gained']} XP)"),
                ], emoji="🏆")

            return results

    def get_total_period_users(self, guild_id: int = None, period: str = "all") -> int:
        """
        Get total number of users with XP gained during a period.

        Args:
            guild_id: Guild ID (defaults to config.GUILD_ID)
            period: Time period - "all", "month", "week", "today"
        """
        from src.core.config import config

        gid = guild_id or config.GUILD_ID

        if period == "all":
            return self.get_total_ranked_users(guild_id=gid, period="all")

        snapshot_date = self.get_snapshot_date_for_period(period)

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Count users who gained XP (current > snapshot or no snapshot exists)
            cur.execute("""
                SELECT COUNT(*) as total
                FROM user_xp u
                LEFT JOIN xp_snapshots s ON
                    u.user_id = s.user_id AND
                    u.guild_id = s.guild_id AND
                    s.date = ?
                WHERE u.guild_id = ? AND u.is_active = 1
                    AND (u.xp - COALESCE(s.xp_total, 0)) > 0
            """, (snapshot_date, gid))

            row = cur.fetchone()
            total = row["total"] if row else 0

            logger.tree("Period User Count", [
                ("Period", period),
                ("Snapshot Date", snapshot_date),
                ("Active Users", str(total)),
            ], emoji="👥")

            return total

    def get_previous_ranks(
        self,
        user_ids: List[int] = None,
        guild_id: int = None,
        snapshot_date: str = None
    ) -> Dict[int, int]:
        """
        Get user ranks from a previous snapshot date.

        Calculates what each user's rank would have been based on their
        XP at the snapshot date.

        Args:
            user_ids: Optional list of user IDs to fetch ranks for.
                     If provided, only returns ranks for these users (efficient).
                     If None, returns all ranks (expensive - avoid in production).
            guild_id: Guild ID (defaults to config.GUILD_ID)
            snapshot_date: Date string (YYYY-MM-DD) to get ranks from.
                          If None, uses yesterday.

        Returns:
            Dict mapping user_id to their rank at that snapshot
        """
        from src.core.config import config
        from datetime import datetime, timezone, timedelta

        gid = guild_id or config.GUILD_ID

        if not snapshot_date:
            snapshot_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        with self._get_conn() as conn:
            cur = conn.cursor()

            if user_ids:
                # Efficient: Only calculate ranks for specific users
                # Use a CTE to rank all users, then filter to the ones we need
                placeholders = ",".join("?" * len(user_ids))
                cur.execute(f"""
                    WITH ranked AS (
                        SELECT
                            user_id,
                            ROW_NUMBER() OVER (ORDER BY xp_total DESC) as rank
                        FROM xp_snapshots
                        WHERE guild_id = ? AND date = ?
                    )
                    SELECT user_id, rank FROM ranked
                    WHERE user_id IN ({placeholders})
                """, (gid, snapshot_date, *user_ids))
            else:
                # Fallback: Get all ranks (expensive, avoid in production)
                cur.execute("""
                    SELECT
                        user_id,
                        ROW_NUMBER() OVER (ORDER BY xp_total DESC) as rank
                    FROM xp_snapshots
                    WHERE guild_id = ? AND date = ?
                """, (gid, snapshot_date))

            ranks = {row["user_id"]: row["rank"] for row in cur.fetchall()}

        logger.tree("Previous Ranks Retrieved", [
            ("Date", snapshot_date),
            ("Requested", str(len(user_ids)) if user_ids else "All"),
            ("Found", str(len(ranks))),
        ], emoji="📈")

        return ranks

    def cleanup_old_snapshots(self, days_to_keep: int = 35, guild_id: int = None) -> int:
        """
        Delete snapshots older than specified days to prevent unbounded growth.

        Args:
            days_to_keep: Number of days of history to retain (default 35 for monthly)
            guild_id: Guild ID (defaults to config.GUILD_ID)

        Returns:
            Number of rows deleted
        """
        from src.core.config import config
        from datetime import datetime, timezone, timedelta

        gid = guild_id or config.GUILD_ID
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM xp_snapshots
                WHERE guild_id = ? AND date < ?
            """, (gid, cutoff_date))

            deleted = cur.rowcount

        if deleted > 0:
            logger.tree("XP Snapshots Cleanup", [
                ("Deleted", str(deleted)),
                ("Cutoff", cutoff_date),
            ], emoji="🧹")

        return deleted
