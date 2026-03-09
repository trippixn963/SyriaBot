"""
SyriaBot - Database Rate Limits Mixin
=====================================

Weekly usage tracking for rate-limited features.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Optional

from src.core.logger import logger
from .core import get_week_start_timestamp


class RateLimitsMixin:
    """Mixin for rate limiting database operations."""

    # =========================================================================
    # Unified Rate Limits Table (used by RateLimiter service)
    # =========================================================================

    def init_rate_limits_table(self) -> bool:
        """Create the unified rate_limits table if it doesn't exist."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rate_limits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        action_type TEXT NOT NULL,
                        week_start TEXT NOT NULL,
                        usage_count INTEGER DEFAULT 1,
                        last_used TEXT NOT NULL,
                        UNIQUE(user_id, action_type, week_start)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rate_limits_user_week
                    ON rate_limits(user_id, week_start)
                """)
            return True
        except Exception as e:
            logger.error_tree("DB: Rate Limits Table Init Failed", e)
            return False

    def rate_limit_get_usage(self, user_id: int, action_type: str, week_start: str) -> int:
        """Get current usage count for a user/action this week."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT usage_count FROM rate_limits
                    WHERE user_id = ? AND action_type = ? AND week_start = ?
                """, (user_id, action_type, week_start))
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.tree("DB: Rate Limit Get Usage Failed", [
                ("ID", str(user_id)),
                ("Action", action_type),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return 0

    def rate_limit_consume(self, user_id: int, action_type: str, week_start: str, now_iso: str) -> bool:
        """Increment usage count for a user/action this week."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO rate_limits (user_id, action_type, week_start, usage_count, last_used)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(user_id, action_type, week_start)
                    DO UPDATE SET usage_count = usage_count + 1, last_used = ?
                """, (user_id, action_type, week_start, now_iso, now_iso))
            return True
        except Exception as e:
            logger.tree("DB: Rate Limit Consume Failed", [
                ("ID", str(user_id)),
                ("Action", action_type),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    def rate_limit_cleanup(self, cutoff_date: str) -> int:
        """Delete rate limit records older than cutoff date."""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM rate_limits WHERE week_start < ?", (cutoff_date,))
                return cursor.rowcount
        except Exception as e:
            logger.tree("DB: Rate Limit Cleanup Failed", [
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return 0

    # =========================================================================
    # Convert Usage Tracking
    # =========================================================================

    def get_convert_usage(self, user_id: int) -> tuple[int, int]:
        """
        Get user's convert usage for this week.

        Returns:
            (uses_remaining, week_start_timestamp)
        """
        week_start = get_week_start_timestamp()

        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT uses_this_week, week_start_timestamp FROM convert_usage WHERE user_id = ?", (user_id,))
                row = cur.fetchone()

                if not row:
                    return (3, week_start)

                stored_week_start = row["week_start_timestamp"]
                uses_this_week = row["uses_this_week"]

                if week_start > stored_week_start:
                    return (3, week_start)

                return (max(0, 3 - uses_this_week), stored_week_start)
        except Exception as e:
            logger.error_tree("DB: Get Convert Usage Error", e, [
                ("ID", str(user_id)),
            ])
            return (3, week_start)

    def record_convert_usage(self, user_id: int) -> int:
        """
        Record a convert usage for a user.

        Returns:
            Number of uses remaining after this use
        """
        week_start = get_week_start_timestamp()

        try:
            with self._get_conn() as conn:
                cur = conn.cursor()

                cur.execute("SELECT uses_this_week, week_start_timestamp FROM convert_usage WHERE user_id = ?", (user_id,))
                row = cur.fetchone()

                if not row:
                    cur.execute("""
                        INSERT INTO convert_usage (user_id, uses_this_week, week_start_timestamp)
                        VALUES (?, 1, ?)
                    """, (user_id, week_start))
                    logger.tree("Convert Usage Recorded", [
                        ("ID", str(user_id)),
                        ("Uses", "1"),
                        ("Remaining", "2"),
                    ], emoji="🔄")
                    return 2

                stored_week_start = row["week_start_timestamp"]

                if week_start > stored_week_start:
                    cur.execute("""
                        UPDATE convert_usage SET uses_this_week = 1, week_start_timestamp = ?
                        WHERE user_id = ?
                    """, (week_start, user_id))
                    logger.tree("Convert Usage Reset (New Week)", [
                        ("ID", str(user_id)),
                        ("Uses", "1"),
                        ("Remaining", "2"),
                    ], emoji="🔄")
                    return 2

                new_uses = row["uses_this_week"] + 1
                cur.execute("""
                    UPDATE convert_usage SET uses_this_week = ?
                    WHERE user_id = ?
                """, (new_uses, user_id))
                remaining = max(0, 3 - new_uses)
                logger.tree("Convert Usage Recorded", [
                    ("ID", str(user_id)),
                    ("Uses", str(new_uses)),
                    ("Remaining", str(remaining)),
                ], emoji="🔄")
                return remaining
        except Exception as e:
            logger.error_tree("DB: Record Convert Usage Error", e, [
                ("ID", str(user_id)),
            ])
            return 0

    def get_next_reset_timestamp(self) -> int:
        """Get timestamp for next Monday 00:00 UTC."""
        return get_week_start_timestamp() + (7 * 86400)

    # =========================================================================
    # Download Usage (Weekly Limit)
    # =========================================================================

    def get_download_usage(self, user_id: int, weekly_limit: int = 5) -> tuple[int, int]:
        """
        Get user's download usage for this week.

        Args:
            user_id: The user's Discord ID
            weekly_limit: Weekly limit for free users (default 5)

        Returns:
            (uses_remaining, week_start_timestamp)
        """
        week_start = get_week_start_timestamp()

        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT uses_this_week, week_start_timestamp FROM download_usage WHERE user_id = ?", (user_id,))
                row = cur.fetchone()

                if not row:
                    return (weekly_limit, week_start)

                stored_week_start = row["week_start_timestamp"]
                uses_this_week = row["uses_this_week"]

                if week_start > stored_week_start:
                    return (weekly_limit, week_start)

                return (max(0, weekly_limit - uses_this_week), stored_week_start)
        except Exception as e:
            logger.error_tree("DB: Get Download Usage Error", e, [
                ("ID", str(user_id)),
            ])
            return (weekly_limit, week_start)

    def record_download_usage(self, user_id: int, weekly_limit: int = 5) -> int:
        """
        Record a download usage for a user.

        Returns:
            Number of uses remaining after this use
        """
        week_start = get_week_start_timestamp()

        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT uses_this_week, week_start_timestamp FROM download_usage WHERE user_id = ?", (user_id,))
                row = cur.fetchone()

                if not row:
                    cur.execute("""
                        INSERT INTO download_usage (user_id, uses_this_week, week_start_timestamp)
                        VALUES (?, 1, ?)
                    """, (user_id, week_start))
                    logger.tree("Download Usage Recorded", [
                        ("ID", str(user_id)),
                        ("Uses", "1"),
                        ("Remaining", str(weekly_limit - 1)),
                    ], emoji="📥")
                    return weekly_limit - 1

                stored_week_start = row["week_start_timestamp"]

                if week_start > stored_week_start:
                    cur.execute("""
                        UPDATE download_usage SET uses_this_week = 1, week_start_timestamp = ?
                        WHERE user_id = ?
                    """, (week_start, user_id))
                    logger.tree("Download Usage Reset (New Week)", [
                        ("ID", str(user_id)),
                        ("Uses", "1"),
                        ("Remaining", str(weekly_limit - 1)),
                    ], emoji="📥")
                    return weekly_limit - 1

                new_uses = row["uses_this_week"] + 1
                cur.execute("""
                    UPDATE download_usage SET uses_this_week = ?
                    WHERE user_id = ?
                """, (new_uses, user_id))
                remaining = max(0, weekly_limit - new_uses)
                logger.tree("Download Usage Recorded", [
                    ("ID", str(user_id)),
                    ("Uses", str(new_uses)),
                    ("Remaining", str(remaining)),
                ], emoji="📥")
                return remaining
        except Exception as e:
            logger.error_tree("DB: Record Download Usage Error", e, [
                ("ID", str(user_id)),
            ])
            return 0

    # =========================================================================
    # Image Search Usage (Weekly Limit)
    # =========================================================================

    def get_image_usage(self, user_id: int, weekly_limit: int = 5) -> tuple[int, int]:
        """
        Get user's image search usage for this week.

        Returns:
            (uses_remaining, week_start_timestamp)
        """
        week_start = get_week_start_timestamp()

        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT uses_this_week, week_start_timestamp FROM image_usage WHERE user_id = ?", (user_id,))
                row = cur.fetchone()

                if not row:
                    return (weekly_limit, week_start)

                stored_week_start = row["week_start_timestamp"]
                uses_this_week = row["uses_this_week"]

                if week_start > stored_week_start:
                    return (weekly_limit, week_start)

                return (max(0, weekly_limit - uses_this_week), stored_week_start)
        except Exception as e:
            logger.error_tree("DB: Get Image Usage Error", e, [
                ("ID", str(user_id)),
            ])
            return (weekly_limit, week_start)

    def record_image_usage(self, user_id: int, weekly_limit: int = 5) -> int:
        """
        Record an image search usage for a user.

        Returns:
            Number of uses remaining after this use
        """
        week_start = get_week_start_timestamp()

        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT uses_this_week, week_start_timestamp FROM image_usage WHERE user_id = ?", (user_id,))
                row = cur.fetchone()

                if not row:
                    cur.execute("""
                        INSERT INTO image_usage (user_id, uses_this_week, week_start_timestamp)
                        VALUES (?, 1, ?)
                    """, (user_id, week_start))
                    logger.tree("Image Usage Recorded", [
                        ("ID", str(user_id)),
                        ("Uses", "1"),
                        ("Remaining", str(weekly_limit - 1)),
                    ], emoji="🖼️")
                    return weekly_limit - 1

                stored_week_start = row["week_start_timestamp"]

                if week_start > stored_week_start:
                    cur.execute("""
                        UPDATE image_usage SET uses_this_week = 1, week_start_timestamp = ?
                        WHERE user_id = ?
                    """, (week_start, user_id))
                    logger.tree("Image Usage Reset (New Week)", [
                        ("ID", str(user_id)),
                        ("Uses", "1"),
                        ("Remaining", str(weekly_limit - 1)),
                    ], emoji="🖼️")
                    return weekly_limit - 1

                new_uses = row["uses_this_week"] + 1
                cur.execute("""
                    UPDATE image_usage SET uses_this_week = ?
                    WHERE user_id = ?
                """, (new_uses, user_id))
                remaining = max(0, weekly_limit - new_uses)
                logger.tree("Image Usage Recorded", [
                    ("ID", str(user_id)),
                    ("Uses", str(new_uses)),
                    ("Remaining", str(remaining)),
                ], emoji="🖼️")
                return remaining
        except Exception as e:
            logger.error_tree("DB: Record Image Usage Error", e, [
                ("ID", str(user_id)),
            ])
            return 0
