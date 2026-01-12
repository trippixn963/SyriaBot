"""
SyriaBot - Database Confessions Mixin
=====================================

Anonymous confessions system database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import Optional, List, Dict, Any

from src.core.logger import log


class ConfessionsMixin:
    """Mixin for confessions system database operations."""

    def create_confession(self, content: str, submitter_id: int, image_url: Optional[str] = None) -> Optional[int]:
        """
        Create a new pending confession.

        Args:
            content: The confession text
            submitter_id: Discord user ID of submitter (never exposed publicly)
            image_url: Optional image URL to attach

        Returns:
            Confession ID if created, None on error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO confessions (content, submitter_id, status, image_url, submitted_at)
                    VALUES (?, ?, 'pending', ?, ?)
                """, (content, submitter_id, image_url, int(time.time())))
                confession_id = cur.lastrowid

            log.tree("Confession Created", [
                ("ID", str(confession_id)),
                ("Length", f"{len(content)} chars"),
                ("Image", "Yes" if image_url else "No"),
                ("Status", "pending"),
            ], emoji="📝")

            return confession_id

        except Exception as e:
            log.error_tree("Confession Create Failed", e, [
                ("Length", f"{len(content)} chars"),
            ])
            return None

    def get_confession(self, confession_id: int) -> Optional[Dict[str, Any]]:
        """Get a confession by ID."""
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute("""
                    SELECT * FROM confessions WHERE id = ?
                """, (confession_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            log.error_tree("Confession Get Failed", e, [
                ("ID", str(confession_id)),
            ])
            return None

    def get_pending_confessions(self) -> List[Dict[str, Any]]:
        """Get all pending confessions ordered by submission time."""
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return []
                cur = conn.cursor()
                cur.execute("""
                    SELECT * FROM confessions
                    WHERE status = 'pending'
                    ORDER BY submitted_at ASC
                """)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            log.error_tree("Pending Confessions Get Failed", e)
            return []

    def get_next_confession_number(self) -> int:
        """Get the next confession number (max + 1)."""
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return 1
                cur = conn.cursor()
                cur.execute("""
                    SELECT COALESCE(MAX(confession_number), 0) + 1 as next_num
                    FROM confessions
                    WHERE status = 'approved'
                """)
                row = cur.fetchone()
                return row["next_num"] if row else 1
        except Exception as e:
            log.error_tree("Next Confession Number Failed", e)
            return 1

    def approve_confession(self, confession_id: int, mod_id: int) -> Optional[int]:
        """
        Approve a confession and assign it a number.

        Since all confessions are auto-approved, we use the DB ID as the
        confession number to keep them in sync.

        Args:
            confession_id: The confession to approve
            mod_id: Discord user ID of the moderator

        Returns:
            The assigned confession number, or None on error
        """
        try:
            # Use DB ID as confession number (they'll always match)
            confession_number = confession_id

            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute("""
                    UPDATE confessions
                    SET status = 'approved',
                        confession_number = ?,
                        reviewed_at = ?,
                        reviewed_by = ?
                    WHERE id = ? AND status = 'pending'
                """, (confession_number, int(time.time()), mod_id, confession_id))

                if cur.rowcount == 0:
                    log.tree("Confession Approve Failed", [
                        ("ID", str(confession_id)),
                        ("Reason", "Not found or not pending"),
                    ], emoji="⚠️")
                    return None

            log.tree("Confession Approved", [
                ("ID", str(confession_id)),
                ("Number", f"#{confession_number}"),
                ("Mod ID", str(mod_id)),
            ], emoji="✅")

            return confession_number

        except Exception as e:
            log.error_tree("Confession Approve Failed", e, [
                ("ID", str(confession_id)),
                ("Mod ID", str(mod_id)),
            ])
            return None

    def reject_confession(self, confession_id: int, mod_id: int) -> bool:
        """
        Reject a confession.

        Args:
            confession_id: The confession to reject
            mod_id: Discord user ID of the moderator

        Returns:
            True if rejected, False on error
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return False
                cur = conn.cursor()
                cur.execute("""
                    UPDATE confessions
                    SET status = 'rejected',
                        reviewed_at = ?,
                        reviewed_by = ?
                    WHERE id = ? AND status = 'pending'
                """, (int(time.time()), mod_id, confession_id))

                if cur.rowcount == 0:
                    log.tree("Confession Reject Failed", [
                        ("ID", str(confession_id)),
                        ("Reason", "Not found or not pending"),
                    ], emoji="⚠️")
                    return False

            log.tree("Confession Rejected", [
                ("ID", str(confession_id)),
                ("Mod ID", str(mod_id)),
            ], emoji="🚫")

            return True

        except Exception as e:
            log.error_tree("Confession Reject Failed", e, [
                ("ID", str(confession_id)),
                ("Mod ID", str(mod_id)),
            ])
            return False

    def get_user_last_confession_time(self, submitter_id: int) -> Optional[int]:
        """Get the timestamp of user's most recent confession submission."""
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute("""
                    SELECT submitted_at FROM confessions
                    WHERE submitter_id = ?
                    ORDER BY submitted_at DESC
                    LIMIT 1
                """, (submitter_id,))
                row = cur.fetchone()
                return row["submitted_at"] if row else None
        except Exception as e:
            log.error_tree("Get User Last Confession Failed", e, [
                ("Submitter ID", str(submitter_id)),
            ])
            return None

    def get_confession_submitter(self, confession_number: int) -> Optional[int]:
        """
        Get the submitter ID for a confession by its public number.

        Args:
            confession_number: The public confession number (e.g., #1, #2)

        Returns:
            Submitter's Discord user ID, or None if not found
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute("""
                    SELECT submitter_id FROM confessions
                    WHERE confession_number = ? AND status = 'approved'
                """, (confession_number,))
                row = cur.fetchone()
                return row["submitter_id"] if row else None
        except Exception as e:
            log.error_tree("Get Confession Submitter Failed", e, [
                ("Confession Number", f"#{confession_number}"),
            ])
            return None

    def get_confession_stats(self) -> Dict[str, int]:
        """Get confession statistics."""
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                        SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
                    FROM confessions
                """)
                row = cur.fetchone()
                return {
                    "total": row["total"] or 0,
                    "pending": row["pending"] or 0,
                    "approved": row["approved"] or 0,
                    "rejected": row["rejected"] or 0,
                }
        except Exception as e:
            log.error_tree("Confession Stats Failed", e)
            return {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
