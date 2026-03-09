"""
SyriaBot - Database Social Monitor Mixin
========================================

Social media posted-ID tracking to avoid duplicate notifications.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import Set

from src.core.logger import logger


class SocialMonitorMixin:
    """Mixin for social monitor posted-ID database operations."""

    def social_get_posted_ids(self, platform: str) -> Set[str]:
        """Get all posted video IDs for a platform."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT video_id FROM social_posted_ids WHERE platform = ?",
                    (platform,),
                )
                return {row["video_id"] for row in cur.fetchall()}
        except Exception as e:
            logger.error_tree("DB: Social Get Posted IDs Error", e, [
                ("Platform", platform),
            ])
            return set()

    def social_add_posted_id(self, platform: str, video_id: str) -> None:
        """Add a posted video ID for a platform."""
        now = int(time.time())
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT OR IGNORE INTO social_posted_ids (platform, video_id, posted_at)
                    VALUES (?, ?, ?)
                """, (platform, video_id, now))
        except Exception as e:
            logger.error_tree("DB: Social Add Posted ID Error", e, [
                ("Platform", platform),
                ("Video ID", video_id),
            ])

    def social_cleanup(self, platform: str, max_ids: int = 100) -> int:
        """
        Keep only the most recent max_ids entries per platform.

        Returns:
            Number of rows deleted.
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    DELETE FROM social_posted_ids
                    WHERE platform = ? AND rowid NOT IN (
                        SELECT rowid FROM social_posted_ids
                        WHERE platform = ?
                        ORDER BY posted_at DESC
                        LIMIT ?
                    )
                """, (platform, platform, max_ids))
                deleted = cur.rowcount
                if deleted > 0:
                    logger.tree("Social Cleanup", [
                        ("Platform", platform),
                        ("Deleted", str(deleted)),
                    ], emoji="🧹")
                return deleted
        except Exception as e:
            logger.error_tree("DB: Social Cleanup Error", e, [
                ("Platform", platform),
            ])
            return 0
