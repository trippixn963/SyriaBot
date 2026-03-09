"""
SyriaBot - Database Bump Mixin
==============================

Bump reminder state persistence.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Optional, Tuple

from src.core.logger import logger


class BumpMixin:
    """Mixin for bump reminder state database operations."""

    def bump_get_state(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Get bump state from database.

        Returns:
            Tuple of (last_bump_time, last_reminder_time), either may be None.
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT key, value FROM bump_state")
                rows = cur.fetchall()

                state = {}
                for row in rows:
                    state[row["key"]] = row["value"]

                return (
                    state.get("last_bump_time"),
                    state.get("last_reminder_time"),
                )
        except Exception as e:
            logger.error_tree("DB: Bump Get State Error", e)
            return None, None

    def bump_save_state(
        self,
        last_bump_time: Optional[float],
        last_reminder_time: Optional[float],
    ) -> None:
        """Save bump state to database."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                for key, value in [
                    ("last_bump_time", last_bump_time),
                    ("last_reminder_time", last_reminder_time),
                ]:
                    if value is not None:
                        cur.execute("""
                            INSERT INTO bump_state (key, value)
                            VALUES (?, ?)
                            ON CONFLICT(key) DO UPDATE SET value = ?
                        """, (key, value, value))
                    else:
                        cur.execute(
                            "DELETE FROM bump_state WHERE key = ?", (key,)
                        )
        except Exception as e:
            logger.error_tree("DB: Bump Save State Error", e)
