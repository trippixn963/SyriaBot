"""
SyriaBot - Database Downloads Mixin
===================================

Lifetime download statistics database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import List, Dict, Any

from src.core.logger import log


class DownloadsMixin:
    """Mixin for download statistics database operations."""

    def record_download_stats(self, user_id: int, platform: str, file_count: int = 1) -> None:
        """
        Record a successful download for lifetime stats.

        Args:
            user_id: The user's Discord ID
            platform: Platform name (instagram, twitter, etc.)
            file_count: Number of files downloaded
        """
        now = int(time.time())

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO download_stats (user_id, platform, total_downloads, total_files, last_download_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(user_id, platform) DO UPDATE SET
                    total_downloads = total_downloads + 1,
                    total_files = total_files + ?,
                    last_download_at = ?
            """, (user_id, platform.lower(), file_count, now, file_count, now))

        log.tree("Download Stats Recorded", [
            ("User ID", str(user_id)),
            ("Platform", platform.title()),
            ("Files", str(file_count)),
        ], emoji="📊")

    def get_user_download_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Get user's lifetime download stats across all platforms.

        Returns:
            Dict with total_downloads, total_files, and per-platform breakdown
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT platform, total_downloads, total_files, last_download_at
                FROM download_stats
                WHERE user_id = ?
                ORDER BY total_downloads DESC
            """, (user_id,))
            rows = cur.fetchall()

            if not rows:
                return {
                    "total_downloads": 0,
                    "total_files": 0,
                    "platforms": {},
                }

            platforms = {}
            total_downloads = 0
            total_files = 0

            for row in rows:
                platform = row["platform"]
                platforms[platform] = {
                    "downloads": row["total_downloads"],
                    "files": row["total_files"],
                    "last_at": row["last_download_at"],
                }
                total_downloads += row["total_downloads"]
                total_files += row["total_files"]

            return {
                "total_downloads": total_downloads,
                "total_files": total_files,
                "platforms": platforms,
            }

    def get_download_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top users by total downloads.

        Returns:
            List of dicts with user_id, total_downloads, total_files
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT user_id,
                       SUM(total_downloads) as total_downloads,
                       SUM(total_files) as total_files
                FROM download_stats
                GROUP BY user_id
                ORDER BY total_downloads DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]
