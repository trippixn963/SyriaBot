"""
SyriaBot - Giveaways Database Mixin
===================================

Database operations for the giveaway system.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.logger import log


class GiveawaysMixin:
    """Mixin for giveaway database operations."""

    def create_giveaway(
        self,
        message_id: int,
        channel_id: int,
        host_id: int,
        prize_type: str,
        prize_description: str,
        prize_amount: int,
        prize_coins: int,
        prize_role_id: Optional[int],
        required_role_id: Optional[int],
        min_level: int,
        winner_count: int,
        ends_at: datetime
    ) -> Optional[int]:
        """
        Create a new giveaway.

        Returns:
            Giveaway ID or None if failed.
        """
        with self._get_conn() as conn:
            if conn is None:
                return None
            try:
                cursor = conn.execute("""
                    INSERT INTO giveaways (
                        message_id, channel_id, host_id,
                        prize_type, prize_description, prize_amount, prize_coins, prize_role_id,
                        required_role_id, min_level, winner_count, ends_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_id, channel_id, host_id,
                    prize_type, prize_description, prize_amount, prize_coins, prize_role_id,
                    required_role_id, min_level, winner_count, ends_at.isoformat()
                ))
                giveaway_id = cursor.lastrowid

                log.tree("Giveaway Created", [
                    ("ID", str(giveaway_id)),
                    ("Message ID", str(message_id)),
                    ("Prize", prize_description[:30]),
                    ("Type", prize_type),
                    ("Winners", str(winner_count)),
                    ("Ends", ends_at.strftime("%Y-%m-%d %H:%M")),
                ], emoji="🎉")

                return giveaway_id
            except Exception as e:
                log.tree("Giveaway Create Failed", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")
                return None

    def get_giveaway(self, giveaway_id: int) -> Optional[Dict[str, Any]]:
        """Get giveaway by ID."""
        with self._get_conn() as conn:
            if conn is None:
                return None
            cursor = conn.execute(
                "SELECT * FROM giveaways WHERE id = ?",
                (giveaway_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_giveaway_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Get giveaway by message ID."""
        with self._get_conn() as conn:
            if conn is None:
                return None
            cursor = conn.execute(
                "SELECT * FROM giveaways WHERE message_id = ?",
                (message_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_active_giveaways(self) -> List[Dict[str, Any]]:
        """Get all active (not ended) giveaways."""
        with self._get_conn() as conn:
            if conn is None:
                return []
            cursor = conn.execute(
                "SELECT * FROM giveaways WHERE ended = 0 ORDER BY ends_at ASC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_expired_giveaways(self) -> List[Dict[str, Any]]:
        """Get giveaways that have expired but not ended."""
        with self._get_conn() as conn:
            if conn is None:
                return []
            cursor = conn.execute("""
                SELECT * FROM giveaways
                WHERE ended = 0 AND ends_at <= datetime('now')
                ORDER BY ends_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def add_giveaway_entry(self, giveaway_id: int, user_id: int) -> bool:
        """
        Add a user entry to a giveaway.

        Returns:
            True if entry added, False if already entered or error.
        """
        with self._get_conn() as conn:
            if conn is None:
                return False
            try:
                conn.execute("""
                    INSERT INTO giveaway_entries (giveaway_id, user_id)
                    VALUES (?, ?)
                """, (giveaway_id, user_id))

                log.tree("Giveaway Entry Added", [
                    ("Giveaway ID", str(giveaway_id)),
                    ("ID", str(user_id)),
                ], emoji="🎟️")

                return True
            except Exception:
                # Already entered (primary key violation)
                return False

    def remove_giveaway_entry(self, giveaway_id: int, user_id: int) -> bool:
        """Remove a user entry from a giveaway."""
        with self._get_conn() as conn:
            if conn is None:
                return False
            cursor = conn.execute("""
                DELETE FROM giveaway_entries
                WHERE giveaway_id = ? AND user_id = ?
            """, (giveaway_id, user_id))

            if cursor.rowcount > 0:
                log.tree("Giveaway Entry Removed", [
                    ("Giveaway ID", str(giveaway_id)),
                    ("ID", str(user_id)),
                ], emoji="🎟️")
                return True
            return False

    def get_giveaway_entries(self, giveaway_id: int) -> List[int]:
        """Get all user IDs entered in a giveaway."""
        with self._get_conn() as conn:
            if conn is None:
                return []
            cursor = conn.execute(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?",
                (giveaway_id,)
            )
            return [row["user_id"] for row in cursor.fetchall()]

    def get_giveaway_entry_count(self, giveaway_id: int) -> int:
        """Get number of entries in a giveaway."""
        with self._get_conn() as conn:
            if conn is None:
                return 0
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM giveaway_entries WHERE giveaway_id = ?",
                (giveaway_id,)
            )
            row = cursor.fetchone()
            return row["count"] if row else 0

    def has_entered_giveaway(self, giveaway_id: int, user_id: int) -> bool:
        """Check if user has entered a giveaway."""
        with self._get_conn() as conn:
            if conn is None:
                return False
            cursor = conn.execute("""
                SELECT 1 FROM giveaway_entries
                WHERE giveaway_id = ? AND user_id = ?
            """, (giveaway_id, user_id))
            return cursor.fetchone() is not None

    def end_giveaway(self, giveaway_id: int, winners: List[int]) -> bool:
        """
        Mark giveaway as ended with winners.

        Args:
            giveaway_id: Giveaway ID
            winners: List of winner user IDs

        Returns:
            True if updated successfully.
        """
        with self._get_conn() as conn:
            if conn is None:
                return False
            try:
                conn.execute("""
                    UPDATE giveaways
                    SET ended = 1, winners = ?
                    WHERE id = ?
                """, (json.dumps(winners), giveaway_id))

                log.tree("Giveaway Ended (DB)", [
                    ("ID", str(giveaway_id)),
                    ("Winners", str(len(winners))),
                    ("Winner IDs", ", ".join(str(w) for w in winners[:5])),
                ], emoji="🏆")

                return True
            except Exception as e:
                log.tree("Giveaway End Failed (DB)", [
                    ("ID", str(giveaway_id)),
                    ("Error", str(e)[:50]),
                ], emoji="❌")
                return False

    def cancel_giveaway(self, giveaway_id: int) -> bool:
        """Cancel/delete a giveaway."""
        with self._get_conn() as conn:
            if conn is None:
                return False
            try:
                # Delete entries first
                conn.execute(
                    "DELETE FROM giveaway_entries WHERE giveaway_id = ?",
                    (giveaway_id,)
                )
                # Delete giveaway
                conn.execute(
                    "DELETE FROM giveaways WHERE id = ?",
                    (giveaway_id,)
                )

                log.tree("Giveaway Cancelled (DB)", [
                    ("ID", str(giveaway_id)),
                ], emoji="🗑️")

                return True
            except Exception as e:
                log.tree("Giveaway Cancel Failed (DB)", [
                    ("ID", str(giveaway_id)),
                    ("Error", str(e)[:50]),
                ], emoji="❌")
                return False

    def update_giveaway_message(self, giveaway_id: int, message_id: int) -> bool:
        """Update the message ID for a giveaway."""
        with self._get_conn() as conn:
            if conn is None:
                return False
            try:
                conn.execute("""
                    UPDATE giveaways SET message_id = ? WHERE id = ?
                """, (message_id, giveaway_id))
                return True
            except Exception as e:
                log.tree("Giveaway Message Update Failed", [
                    ("ID", str(giveaway_id)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
                return False
