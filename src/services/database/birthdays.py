"""
SyriaBot - Database Birthdays Mixin
===================================

Birthday tracking database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import Optional, List, Dict, Any

from src.core.logger import logger


class BirthdaysMixin:
    """Mixin for birthday database operations."""

    # =========================================================================
    # Birthday CRUD
    # =========================================================================

    def set_birthday(
        self,
        user_id: int,
        guild_id: int,
        month: int,
        day: int,
        year: int
    ) -> bool:
        """
        Set or update a user's birthday.

        Args:
            user_id: Discord user ID
            guild_id: Guild ID
            month: Birth month (1-12)
            day: Birth day (1-31)
            year: Birth year

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Birthday Set Failed", [
                        ("ID", str(user_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return False

                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO birthdays (user_id, guild_id, birth_month, birth_day, birth_year, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET
                        birth_month = excluded.birth_month,
                        birth_day = excluded.birth_day,
                        birth_year = excluded.birth_year
                """, (user_id, guild_id, month, day, year, int(time.time())))

                if cur.rowcount == 0:
                    logger.tree("DB: Birthday Set Failed", [
                        ("ID", str(user_id)),
                        ("Birthday", f"{month}/{day}/{year}"),
                        ("Reason", "No rows affected"),
                    ], emoji="⚠️")
                    return False

                logger.tree("DB: Birthday Set", [
                    ("ID", str(user_id)),
                    ("Birthday", f"{month}/{day}/{year}"),
                ], emoji="🎂")
                return True

        except Exception as e:
            logger.error_tree("DB: Set Birthday Error", e, [
                ("ID", str(user_id)),
                ("Birthday", f"{month}/{day}/{year}"),
            ])
            return False

    def remove_birthday(self, user_id: int, guild_id: int) -> bool:
        """
        Remove a user's birthday.

        Args:
            user_id: Discord user ID
            guild_id: Guild ID

        Returns:
            True if removed, False if not found or error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Birthday Remove Failed", [
                        ("ID", str(user_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return False

                cur = conn.cursor()
                cur.execute("""
                    DELETE FROM birthdays WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))

                if cur.rowcount > 0:
                    logger.tree("DB: Birthday Removed", [
                        ("ID", str(user_id)),
                        ("Rows", str(cur.rowcount)),
                    ], emoji="🗑️")
                    return True

                logger.tree("DB: Birthday Not Found", [
                    ("ID", str(user_id)),
                    ("Guild ID", str(guild_id)),
                ], emoji="ℹ️")
                return False

        except Exception as e:
            logger.error_tree("DB: Remove Birthday Error", e, [
                ("ID", str(user_id)),
                ("Guild ID", str(guild_id)),
            ])
            return False

    def get_birthday(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a user's birthday.

        Args:
            user_id: Discord user ID
            guild_id: Guild ID

        Returns:
            Dict with birth_month, birth_day, birth_year, or None if not found/error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Get Birthday Failed", [
                        ("ID", str(user_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return None

                cur = conn.cursor()
                cur.execute("""
                    SELECT birth_month, birth_day, birth_year, created_at
                    FROM birthdays
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))
                row = cur.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error_tree("DB: Get Birthday Error", e, [
                ("ID", str(user_id)),
                ("Guild ID", str(guild_id)),
            ])
            return None

    def get_todays_birthdays(self, guild_id: int, month: int, day: int) -> List[int]:
        """
        Get all users with birthday today.

        Args:
            guild_id: Guild ID
            month: Current month (1-12)
            day: Current day (1-31)

        Returns:
            List of user IDs with birthday today, empty list on error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Get Today's Birthdays Failed", [
                        ("Guild ID", str(guild_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return []

                cur = conn.cursor()
                cur.execute("""
                    SELECT user_id FROM birthdays
                    WHERE guild_id = ? AND birth_month = ? AND birth_day = ?
                """, (guild_id, month, day))
                user_ids = [row["user_id"] for row in cur.fetchall()]

                if user_ids:
                    logger.tree("DB: Today's Birthdays Found", [
                        ("Date", f"{month}/{day}"),
                        ("Count", str(len(user_ids))),
                    ], emoji="🎂")

                return user_ids

        except Exception as e:
            logger.error_tree("DB: Get Today's Birthdays Error", e, [
                ("Guild ID", str(guild_id)),
                ("Date", f"{month}/{day}"),
            ])
            return []

    def get_upcoming_birthdays(
        self,
        guild_id: int,
        current_month: int,
        current_day: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming birthdays sorted by nearest date.

        Args:
            guild_id: Guild ID
            current_month: Current month
            current_day: Current day
            limit: Max results

        Returns:
            List of birthday records sorted by upcoming date, empty list on error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Get Upcoming Birthdays Failed", [
                        ("Guild ID", str(guild_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return []

                cur = conn.cursor()
                # Order by days until birthday (handling year wrap)
                cur.execute("""
                    SELECT user_id, birth_month, birth_day, birth_year,
                        CASE
                            WHEN (birth_month > ? OR (birth_month = ? AND birth_day >= ?))
                            THEN (birth_month - ?) * 31 + (birth_day - ?)
                            ELSE (12 - ? + birth_month) * 31 + (31 - ? + birth_day)
                        END as days_until
                    FROM birthdays
                    WHERE guild_id = ?
                    ORDER BY days_until ASC
                    LIMIT ?
                """, (current_month, current_month, current_day, current_month, current_day,
                      current_month, current_day, guild_id, limit))
                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            logger.error_tree("DB: Get Upcoming Birthdays Error", e, [
                ("Guild ID", str(guild_id)),
                ("Limit", str(limit)),
            ])
            return []

    def get_birthday_count(self, guild_id: int) -> int:
        """
        Get total number of registered birthdays in a guild.

        Args:
            guild_id: Guild ID

        Returns:
            Count of birthdays, 0 on error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Get Birthday Count Failed", [
                        ("Guild ID", str(guild_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return 0

                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) as count FROM birthdays WHERE guild_id = ?
                """, (guild_id,))
                row = cur.fetchone()
                return row["count"] if row else 0

        except Exception as e:
            logger.error_tree("DB: Get Birthday Count Error", e, [
                ("Guild ID", str(guild_id)),
            ])
            return 0

    # =========================================================================
    # Birthday Role Tracking
    # =========================================================================

    def set_birthday_role_granted(
        self,
        user_id: int,
        guild_id: int,
        granted_at: int
    ) -> bool:
        """
        Track when birthday role was granted (for 24h removal).

        Args:
            user_id: Discord user ID
            guild_id: Guild ID
            granted_at: Unix timestamp when role was granted

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Set Role Granted Failed", [
                        ("ID", str(user_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return False

                cur = conn.cursor()
                cur.execute("""
                    UPDATE birthdays SET role_granted_at = ?
                    WHERE user_id = ? AND guild_id = ?
                """, (granted_at, user_id, guild_id))

                if cur.rowcount == 0:
                    logger.tree("DB: Set Role Granted Failed", [
                        ("ID", str(user_id)),
                        ("Reason", "User not found in birthdays"),
                    ], emoji="⚠️")
                    return False

                logger.tree("DB: Role Granted Timestamp Set", [
                    ("ID", str(user_id)),
                    ("Granted At", str(granted_at)),
                ], emoji="🎂")
                return True

        except Exception as e:
            logger.error_tree("DB: Set Role Granted Error", e, [
                ("ID", str(user_id)),
                ("Guild ID", str(guild_id)),
            ])
            return False

    def clear_birthday_role_granted(self, user_id: int, guild_id: int) -> bool:
        """
        Clear birthday role granted timestamp.

        Args:
            user_id: Discord user ID
            guild_id: Guild ID

        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Clear Role Granted Failed", [
                        ("ID", str(user_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return False

                cur = conn.cursor()
                cur.execute("""
                    UPDATE birthdays SET role_granted_at = NULL
                    WHERE user_id = ? AND guild_id = ?
                """, (user_id, guild_id))

                if cur.rowcount == 0:
                    logger.tree("DB: Clear Role Granted Skipped", [
                        ("ID", str(user_id)),
                        ("Reason", "User not found"),
                    ], emoji="ℹ️")
                    return False

                logger.tree("DB: Role Granted Cleared", [
                    ("ID", str(user_id)),
                ], emoji="🗑️")
                return True

        except Exception as e:
            logger.error_tree("DB: Clear Role Granted Error", e, [
                ("ID", str(user_id)),
                ("Guild ID", str(guild_id)),
            ])
            return False

    def get_active_birthday_roles(self, guild_id: int) -> List[int]:
        """
        Get users with currently active birthday roles (for restoring on bot restart).

        Args:
            guild_id: Guild ID

        Returns:
            List of user IDs with active birthday roles
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return []

                cur = conn.cursor()
                cur.execute("""
                    SELECT user_id FROM birthdays
                    WHERE guild_id = ? AND role_granted_at IS NOT NULL
                """, (guild_id,))
                return [row["user_id"] for row in cur.fetchall()]

        except Exception as e:
            logger.error_tree("DB: Get Active Birthday Roles Error", e, [
                ("Guild ID", str(guild_id)),
            ])
            return []

    def get_expired_birthday_roles(self, guild_id: int, cutoff_time: int) -> List[int]:
        """
        Get users whose birthday role should be removed (granted > 24h ago).

        Args:
            guild_id: Guild ID
            cutoff_time: Timestamp 24 hours ago

        Returns:
            List of user IDs to remove role from, empty list on error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    logger.tree("DB: Get Expired Roles Failed", [
                        ("Guild ID", str(guild_id)),
                        ("Reason", "No database connection"),
                    ], emoji="⚠️")
                    return []

                cur = conn.cursor()
                cur.execute("""
                    SELECT user_id FROM birthdays
                    WHERE guild_id = ? AND role_granted_at IS NOT NULL AND role_granted_at < ?
                """, (guild_id, cutoff_time))
                user_ids = [row["user_id"] for row in cur.fetchall()]

                if user_ids:
                    logger.tree("DB: Expired Birthday Roles Found", [
                        ("Count", str(len(user_ids))),
                        ("Cutoff", str(cutoff_time)),
                    ], emoji="⏰")

                return user_ids

        except Exception as e:
            logger.error_tree("DB: Get Expired Roles Error", e, [
                ("Guild ID", str(guild_id)),
                ("Cutoff", str(cutoff_time)),
            ])
            return []
