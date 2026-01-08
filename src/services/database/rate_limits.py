"""
SyriaBot - Database Rate Limits Mixin
=====================================

Weekly usage tracking for rate-limited features.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from src.core.logger import log
from .core import get_week_start_timestamp


class RateLimitsMixin:
    """Mixin for rate limiting database operations."""

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

    def record_convert_usage(self, user_id: int) -> int:
        """
        Record a convert usage for a user.

        Returns:
            Number of uses remaining after this use
        """
        week_start = get_week_start_timestamp()

        with self._get_conn() as conn:
            cur = conn.cursor()

            cur.execute("SELECT uses_this_week, week_start_timestamp FROM convert_usage WHERE user_id = ?", (user_id,))
            row = cur.fetchone()

            if not row:
                cur.execute("""
                    INSERT INTO convert_usage (user_id, uses_this_week, week_start_timestamp)
                    VALUES (?, 1, ?)
                """, (user_id, week_start))
                log.tree("Convert Usage Recorded", [
                    ("User ID", str(user_id)),
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
                log.tree("Convert Usage Reset (New Week)", [
                    ("User ID", str(user_id)),
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
            log.tree("Convert Usage Recorded", [
                ("User ID", str(user_id)),
                ("Uses", str(new_uses)),
                ("Remaining", str(remaining)),
            ], emoji="🔄")
            return remaining

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

    def record_download_usage(self, user_id: int, weekly_limit: int = 5) -> int:
        """
        Record a download usage for a user.

        Returns:
            Number of uses remaining after this use
        """
        week_start = get_week_start_timestamp()

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT uses_this_week, week_start_timestamp FROM download_usage WHERE user_id = ?", (user_id,))
            row = cur.fetchone()

            if not row:
                cur.execute("""
                    INSERT INTO download_usage (user_id, uses_this_week, week_start_timestamp)
                    VALUES (?, 1, ?)
                """, (user_id, week_start))
                log.tree("Download Usage Recorded", [
                    ("User ID", str(user_id)),
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
                log.tree("Download Usage Reset (New Week)", [
                    ("User ID", str(user_id)),
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
            log.tree("Download Usage Recorded", [
                ("User ID", str(user_id)),
                ("Uses", str(new_uses)),
                ("Remaining", str(remaining)),
            ], emoji="📥")
            return remaining

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

    def record_image_usage(self, user_id: int, weekly_limit: int = 5) -> int:
        """
        Record an image search usage for a user.

        Returns:
            Number of uses remaining after this use
        """
        week_start = get_week_start_timestamp()

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT uses_this_week, week_start_timestamp FROM image_usage WHERE user_id = ?", (user_id,))
            row = cur.fetchone()

            if not row:
                cur.execute("""
                    INSERT INTO image_usage (user_id, uses_this_week, week_start_timestamp)
                    VALUES (?, 1, ?)
                """, (user_id, week_start))
                log.tree("Image Usage Recorded", [
                    ("User ID", str(user_id)),
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
                log.tree("Image Usage Reset (New Week)", [
                    ("User ID", str(user_id)),
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
            log.tree("Image Usage Recorded", [
                ("User ID", str(user_id)),
                ("Uses", str(new_uses)),
                ("Remaining", str(remaining)),
            ], emoji="🖼️")
            return remaining
