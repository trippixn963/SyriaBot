"""
SyriaBot - Database AFK Mixin
=============================

AFK system database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import Optional, List, Dict, Any

from src.core.logger import log


class AFKMixin:
    """Mixin for AFK system database operations."""

    def set_afk(self, user_id: int, guild_id: int, reason: str = "") -> None:
        """Set a user as AFK."""
        now = int(time.time())

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO afk_users (user_id, guild_id, reason, timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    reason = ?, timestamp = ?
            """, (user_id, guild_id, reason, now, reason, now))

        log.tree("AFK Set", [
            ("ID", str(user_id)),
            ("Guild ID", str(guild_id)),
            ("Reason", reason[:50] if reason else "None"),
        ], emoji="💤")

    def remove_afk(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Remove AFK status. Returns AFK data if was AFK, None otherwise."""
        with self._get_conn() as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT * FROM afk_users WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()

            if not row:
                return None

            afk_data = dict(row)

            cur.execute("""
                DELETE FROM afk_users WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

        log.tree("AFK Removed", [
            ("ID", str(user_id)),
            ("Guild ID", str(guild_id)),
        ], emoji="👋")

        return afk_data

    def get_afk(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get user's AFK status. Returns None if not AFK."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM afk_users WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_afk_users(self, user_ids: List[int], guild_id: int) -> List[Dict[str, Any]]:
        """Get AFK status for multiple users (for mention checking)."""
        if not user_ids:
            return []

        with self._get_conn() as conn:
            cur = conn.cursor()
            placeholders = ",".join("?" * len(user_ids))
            cur.execute(f"""
                SELECT * FROM afk_users
                WHERE user_id IN ({placeholders}) AND guild_id = ?
            """, user_ids + [guild_id])
            return [dict(row) for row in cur.fetchall()]

    def increment_afk_mentions(self, user_id: int, guild_id: int, pinger_id: int = None, pinger_name: str = None) -> None:
        """Increment mention count for an AFK user and track who pinged."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO afk_mentions (user_id, guild_id, mention_count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    mention_count = mention_count + 1
            """, (user_id, guild_id))

            if pinger_id and pinger_name:
                cur.execute("""
                    INSERT INTO afk_mention_pingers (afk_user_id, guild_id, pinger_id, pinger_name, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, guild_id, pinger_id, pinger_name, int(time.time())))

        log.tree("AFK Mention Tracked", [
            ("ID", str(user_id)),
            ("Pinger", pinger_name or "Unknown"),
        ], emoji="📬")

    def get_and_clear_afk_mentions(self, user_id: int, guild_id: int) -> tuple[int, List[str]]:
        """
        Get mention count and pinger names, then clear.
        Returns (count, list of unique pinger names).
        """
        with self._get_conn() as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT mention_count FROM afk_mentions
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()

            count = row["mention_count"] if row else 0

            cur.execute("""
                SELECT DISTINCT pinger_name FROM afk_mention_pingers
                WHERE afk_user_id = ? AND guild_id = ?
                ORDER BY timestamp DESC
                LIMIT 5
            """, (user_id, guild_id))
            pinger_names = [r["pinger_name"] for r in cur.fetchall()]

            cur.execute("""
                DELETE FROM afk_mentions WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

            cur.execute("""
                DELETE FROM afk_mention_pingers WHERE afk_user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

            if count > 0:
                log.tree("AFK Mentions Cleared", [
                    ("ID", str(user_id)),
                    ("Count", str(count)),
                    ("Pingers", ", ".join(pinger_names) if pinger_names else "None"),
                ], emoji="📭")

            return count, pinger_names
