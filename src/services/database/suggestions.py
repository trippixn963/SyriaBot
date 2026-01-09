"""
SyriaBot - Database Suggestions Mixin
=====================================

Suggestion system database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import Optional, List, Dict, Any

from src.core.logger import log


class SuggestionsMixin:
    """Mixin for suggestions system database operations."""

    def create_suggestion(
        self,
        content: str,
        submitter_id: int,
        message_id: int
    ) -> Optional[int]:
        """
        Create a new suggestion.

        Args:
            content: The suggestion text
            submitter_id: Discord user ID of submitter
            message_id: Discord message ID of the suggestion post

        Returns:
            Suggestion ID if created, None on error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO suggestions (content, submitter_id, message_id, status, submitted_at)
                    VALUES (?, ?, ?, 'pending', ?)
                """, (content, submitter_id, message_id, int(time.time())))
                suggestion_id = cur.lastrowid

            log.tree("Suggestion Created", [
                ("ID", str(suggestion_id)),
                ("Submitter ID", str(submitter_id)),
                ("Message ID", str(message_id)),
                ("Length", f"{len(content)} chars"),
            ], emoji="💡")

            return suggestion_id

        except Exception as e:
            log.error_tree("Suggestion Create Failed", e, [
                ("Length", f"{len(content)} chars"),
            ])
            return None

    def get_suggestion(self, suggestion_id: int) -> Optional[Dict[str, Any]]:
        """Get a suggestion by ID."""
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            log.error_tree("Suggestion Get Failed", e, [
                ("ID", str(suggestion_id)),
            ])
            return None

    def get_suggestion_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Get a suggestion by its message ID."""
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute("SELECT * FROM suggestions WHERE message_id = ?", (message_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            log.error_tree("Suggestion Get By Message Failed", e, [
                ("Message ID", str(message_id)),
            ])
            return None

    def update_suggestion_status(
        self,
        suggestion_id: int,
        status: str,
        mod_id: int
    ) -> bool:
        """
        Update suggestion status (approve/reject/implement).

        Args:
            suggestion_id: The suggestion to update
            status: New status (approved, rejected, implemented)
            mod_id: Discord user ID of the moderator

        Returns:
            True if updated, False on error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return False
                cur = conn.cursor()
                cur.execute("""
                    UPDATE suggestions
                    SET status = ?, reviewed_at = ?, reviewed_by = ?
                    WHERE id = ?
                """, (status, int(time.time()), mod_id, suggestion_id))

                if cur.rowcount == 0:
                    log.tree("Suggestion Update Failed", [
                        ("ID", str(suggestion_id)),
                        ("Status", status),
                        ("Reason", "Not found"),
                    ], emoji="⚠️")
                    return False

            log.tree("Suggestion Status Updated", [
                ("ID", str(suggestion_id)),
                ("Status", status),
                ("Mod ID", str(mod_id)),
            ], emoji="✅")

            return True

        except Exception as e:
            log.error_tree("Suggestion Update Failed", e, [
                ("ID", str(suggestion_id)),
                ("Status", status),
            ])
            return False

    def get_suggestion_stats(self) -> Dict[str, int]:
        """Get suggestion statistics."""
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "implemented": 0}
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                        SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                        SUM(CASE WHEN status = 'implemented' THEN 1 ELSE 0 END) as implemented
                    FROM suggestions
                """)
                row = cur.fetchone()
                return {
                    "total": row["total"] or 0,
                    "pending": row["pending"] or 0,
                    "approved": row["approved"] or 0,
                    "rejected": row["rejected"] or 0,
                    "implemented": row["implemented"] or 0,
                }
        except Exception as e:
            log.error_tree("Suggestion Stats Failed", e)
            return {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "implemented": 0}

    def get_user_suggestion_count_today(self, submitter_id: int) -> int:
        """Get count of suggestions submitted by user today."""
        try:
            # Start of today (midnight)
            today_start = int(time.time()) - (int(time.time()) % 86400)

            with self._get_conn() as conn:
                if conn is None:
                    return 0
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) as count FROM suggestions
                    WHERE submitter_id = ? AND submitted_at >= ?
                """, (submitter_id, today_start))
                row = cur.fetchone()
                return row["count"] if row else 0
        except Exception as e:
            log.error_tree("User Suggestion Count Failed", e, [
                ("Submitter ID", str(submitter_id)),
            ])
            return 0
