"""
SyriaBot - Database Actions Mixin
=================================

Action command statistics database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import List, Dict, Any, Optional

from src.core.logger import log


class ActionsMixin:
    """Mixin for action statistics database operations."""

    def record_action(
        self,
        user_id: int,
        guild_id: int,
        action: str,
        target_id: Optional[int] = None
    ) -> None:
        """
        Record an action usage.

        Args:
            user_id: The user who performed the action
            guild_id: The guild where it happened
            action: The action name (slap, hug, etc.)
            target_id: The target user ID (None for self-actions)
        """
        now = int(time.time())
        # Use 0 for self-actions to have a consistent key
        target_key = target_id if target_id is not None else 0

        with self._get_conn() as conn:
            if conn is None:
                log.tree("Action Record Skipped", [
                    ("Reason", "Database unavailable"),
                ], emoji="⚠️")
                return

            cur = conn.cursor()
            cur.execute("""
                INSERT INTO action_stats (user_id, target_id, guild_id, action, count, last_used_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(user_id, target_id, guild_id, action) DO UPDATE SET
                    count = count + 1,
                    last_used_at = ?
            """, (user_id, target_key, guild_id, action.lower(), now, now))

        log.tree("Action Recorded", [
            ("ID", str(user_id)),
            ("Target ID", str(target_id) if target_id else "Self"),
            ("Action", action),
            ("Guild ID", str(guild_id)),
        ], emoji="📊")

    def get_user_action_stats(self, user_id: int, guild_id: int) -> Dict[str, Any]:
        """
        Get a user's action statistics for a guild.

        Returns:
            Dict with total_actions, actions_given, actions_received
        """
        with self._get_conn() as conn:
            if conn is None:
                return {"total_given": 0, "total_received": 0, "given": {}, "received": {}}

            cur = conn.cursor()

            # Actions given by this user
            cur.execute("""
                SELECT action, SUM(count) as total
                FROM action_stats
                WHERE user_id = ? AND guild_id = ?
                GROUP BY action
                ORDER BY total DESC
            """, (user_id, guild_id))
            given_rows = cur.fetchall()

            # Actions received by this user
            cur.execute("""
                SELECT action, SUM(count) as total
                FROM action_stats
                WHERE target_id = ? AND guild_id = ? AND target_id != 0
                GROUP BY action
                ORDER BY total DESC
            """, (user_id, guild_id))
            received_rows = cur.fetchall()

            given = {row["action"]: row["total"] for row in given_rows}
            received = {row["action"]: row["total"] for row in received_rows}

            return {
                "total_given": sum(given.values()),
                "total_received": sum(received.values()),
                "given": given,
                "received": received,
            }

    def get_action_pair_count(
        self,
        user_id: int,
        target_id: int,
        guild_id: int,
        action: str
    ) -> int:
        """
        Get how many times user has performed an action on target.

        Returns:
            Count of times user did action to target
        """
        with self._get_conn() as conn:
            if conn is None:
                return 0

            cur = conn.cursor()
            cur.execute("""
                SELECT count FROM action_stats
                WHERE user_id = ? AND target_id = ? AND guild_id = ? AND action = ?
            """, (user_id, target_id, guild_id, action.lower()))
            row = cur.fetchone()
            return row["count"] if row else 0

    def get_action_leaderboard(
        self,
        guild_id: int,
        action: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top users for a specific action (given).

        Returns:
            List of dicts with user_id and total count
        """
        with self._get_conn() as conn:
            if conn is None:
                return []

            cur = conn.cursor()
            cur.execute("""
                SELECT user_id, SUM(count) as total
                FROM action_stats
                WHERE guild_id = ? AND action = ?
                GROUP BY user_id
                ORDER BY total DESC
                LIMIT ?
            """, (guild_id, action.lower(), limit))
            return [dict(row) for row in cur.fetchall()]

    def get_most_targeted_user(
        self,
        guild_id: int,
        action: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get users who received the most of a specific action.

        Returns:
            List of dicts with target_id and total count
        """
        with self._get_conn() as conn:
            if conn is None:
                return []

            cur = conn.cursor()
            cur.execute("""
                SELECT target_id, SUM(count) as total
                FROM action_stats
                WHERE guild_id = ? AND action = ? AND target_id != 0
                GROUP BY target_id
                ORDER BY total DESC
                LIMIT ?
            """, (guild_id, action.lower(), limit))
            return [dict(row) for row in cur.fetchall()]

    def get_top_action_pairs(
        self,
        guild_id: int,
        action: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top user pairs for an action (who slaps who the most).

        Returns:
            List of dicts with user_id, target_id, count
        """
        with self._get_conn() as conn:
            if conn is None:
                return []

            cur = conn.cursor()
            cur.execute("""
                SELECT user_id, target_id, count
                FROM action_stats
                WHERE guild_id = ? AND action = ? AND target_id != 0
                ORDER BY count DESC
                LIMIT ?
            """, (guild_id, action.lower(), limit))
            return [dict(row) for row in cur.fetchall()]

    def get_global_action_stats(self, guild_id: int) -> Dict[str, int]:
        """
        Get total counts for all actions in a guild.

        Returns:
            Dict mapping action name to total count
        """
        with self._get_conn() as conn:
            if conn is None:
                return {}

            cur = conn.cursor()
            cur.execute("""
                SELECT action, SUM(count) as total
                FROM action_stats
                WHERE guild_id = ?
                GROUP BY action
                ORDER BY total DESC
            """, (guild_id,))
            return {row["action"]: row["total"] for row in cur.fetchall()}
