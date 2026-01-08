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

from src.core.logger import log


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
        Add XP to a user.

        Args:
            user_id: User's Discord ID
            guild_id: Guild's Discord ID
            amount: XP amount to add
            source: "message" or "voice"

        Returns:
            Dict with old_level, new_level, old_xp, new_xp, leveled_up
        """
        now = int(time.time())

        self.ensure_user_xp(user_id, guild_id)

        with self._get_conn() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT xp, level FROM user_xp WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = cur.fetchone()
            old_xp = row["xp"]
            old_level = row["level"]

            new_xp = old_xp + amount

            if source == "message":
                cur.execute("""
                    UPDATE user_xp
                    SET xp = ?, last_message_xp = ?, total_messages = total_messages + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (new_xp, now, user_id, guild_id))
            else:  # voice
                cur.execute("""
                    UPDATE user_xp
                    SET xp = ?, last_voice_xp = ?, voice_minutes = voice_minutes + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (new_xp, now, user_id, guild_id))

        return {
            "old_xp": old_xp,
            "new_xp": new_xp,
            "old_level": old_level,
        }

    def set_user_level(self, user_id: int, guild_id: int, level: int) -> None:
        """Set user's level."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE user_xp SET level = ? WHERE user_id = ? AND guild_id = ?
                """, (level, user_id, guild_id))
        except Exception as e:
            log.tree("DB: Set Level Error", [
                ("User ID", str(user_id)),
                ("Level", str(level)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def get_last_message_xp(self, user_id: int, guild_id: int) -> int:
        """Get timestamp of last message XP gain."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT last_message_xp FROM user_xp WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = cur.fetchone()
            return row["last_message_xp"] if row else 0

    # =========================================================================
    # Leaderboard Methods
    # =========================================================================

    def get_leaderboard(self, guild_id: int = None, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get top users by XP in a guild with pagination (only active members)."""
        from src.core.config import config
        gid = guild_id or config.GUILD_ID

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT user_id, xp, level, total_messages, voice_minutes,
                       ROW_NUMBER() OVER (ORDER BY xp DESC) as rank
                FROM user_xp
                WHERE guild_id = ? AND is_active = 1
                ORDER BY xp DESC
                LIMIT ? OFFSET ?
            """, (gid, limit, offset))
            return [dict(row) for row in cur.fetchall()]

    def get_total_ranked_users(self, guild_id: int = None) -> int:
        """Get total number of active users with XP in a guild."""
        from src.core.config import config
        gid = guild_id or config.GUILD_ID

        with self._get_conn() as conn:
            cur = conn.cursor()
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
            cur.execute("""
                SELECT
                    COUNT(*) as total_users,
                    COALESCE(SUM(xp), 0) as total_xp,
                    COALESCE(SUM(total_messages), 0) as total_messages,
                    COALESCE(SUM(voice_minutes), 0) as total_voice_minutes,
                    COALESCE(MAX(level), 0) as highest_level
                FROM user_xp
                WHERE guild_id = ? AND is_active = 1
            """, (gid,))
            row = cur.fetchone()
            return dict(row) if row else {
                "total_users": 0,
                "total_xp": 0,
                "total_messages": 0,
                "total_voice_minutes": 0,
                "highest_level": 0,
            }

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
            log.tree("DB: User Active", [
                ("User ID", str(user_id)),
                ("Status", "Active"),
            ], emoji="✅")
        except Exception as e:
            log.tree("DB: Set Active Error", [
                ("User ID", str(user_id)),
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
            log.tree("DB: User Inactive", [
                ("User ID", str(user_id)),
                ("Status", "Inactive"),
            ], emoji="👋")
        except Exception as e:
            log.tree("DB: Set Inactive Error", [
                ("User ID", str(user_id)),
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
