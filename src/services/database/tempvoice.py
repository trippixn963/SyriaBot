"""
SyriaBot - Database TempVoice Mixin
===================================

TempVoice-related database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import sqlite3
import time
from typing import Optional, List, Dict, Any

from src.core.logger import logger


class TempVoiceMixin:
    """
    Mixin for TempVoice database operations.

    DESIGN:
        Provides CRUD operations for temp channels, user settings, and access
        control (trusted/blocked users). Uses composite primary keys for
        relationships (owner_id + trusted_id) to prevent duplicates.
    """

    # =========================================================================
    # Temp Channels
    # =========================================================================

    def create_temp_channel(
        self,
        channel_id: int,
        owner_id: int,
        guild_id: int,
        name: str,
        created_at: int = None
    ) -> None:
        """Create a new temp channel record."""
        if created_at is None:
            created_at = int(time.time())
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO temp_channels (channel_id, owner_id, guild_id, name, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (channel_id, owner_id, guild_id, name, created_at))

                if cur.rowcount == 0:
                    logger.tree("DB: Channel Create Failed", [
                        ("Channel ID", str(channel_id)),
                        ("Owner ID", str(owner_id)),
                        ("Reason", "No rows inserted"),
                    ], emoji="⚠️")
                    return

            logger.tree("DB: Channel Created", [
                ("Channel ID", str(channel_id)),
                ("Owner ID", str(owner_id)),
                ("Name", name),
            ], emoji="💾")
        except Exception as e:
            logger.tree("DB: Create Channel Error", [
                ("Channel ID", str(channel_id)),
                ("Error", str(e)),
            ], emoji="❌")

    def delete_temp_channel(self, channel_id: int) -> None:
        """Delete a temp channel record."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM temp_channels WHERE channel_id = ?", (channel_id,))
                cur.execute("DELETE FROM waiting_rooms WHERE channel_id = ?", (channel_id,))
                cur.execute("DELETE FROM text_channels WHERE channel_id = ?", (channel_id,))
            logger.tree("DB: Channel Deleted", [
                ("Channel ID", str(channel_id)),
            ], emoji="🗑️")
        except Exception as e:
            logger.tree("DB: Delete Channel Error", [
                ("Channel ID", str(channel_id)),
                ("Error", str(e)),
            ], emoji="❌")

    def get_temp_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Get temp channel info."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM temp_channels WHERE channel_id = ?", (channel_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_owner_channel(self, owner_id: int, guild_id: int) -> Optional[int]:
        """Get the channel ID owned by a user in a guild."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT channel_id FROM temp_channels
                WHERE owner_id = ? AND guild_id = ?
            """, (owner_id, guild_id))
            row = cur.fetchone()
            return row["channel_id"] if row else None

    def is_temp_channel(self, channel_id: int) -> bool:
        """Check if a channel is a temp channel."""
        return self.get_temp_channel(channel_id) is not None

    def update_temp_channel(self, channel_id: int, **kwargs) -> None:
        """Update temp channel properties."""
        if not kwargs:
            return
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
                values = list(kwargs.values()) + [channel_id]
                cur.execute(f"UPDATE temp_channels SET {sets} WHERE channel_id = ?", values)
        except Exception as e:
            logger.tree("DB: Update Channel Error", [
                ("Channel ID", str(channel_id)),
                ("Fields", ", ".join(kwargs.keys())),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def transfer_ownership(self, channel_id: int, new_owner_id: int) -> None:
        """Transfer channel ownership."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE temp_channels SET owner_id = ? WHERE channel_id = ?
                """, (new_owner_id, channel_id))
            logger.tree("DB: Ownership Transferred", [
                ("Channel ID", str(channel_id)),
                ("New Owner", str(new_owner_id)),
            ], emoji="👑")
        except Exception as e:
            logger.tree("DB: Transfer Error", [
                ("Channel ID", str(channel_id)),
                ("Error", str(e)),
            ], emoji="❌")

    def get_all_temp_channels(self, guild_id: int = None) -> List[Dict[str, Any]]:
        """Get all temp channels, optionally filtered by guild."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            if guild_id:
                cur.execute("SELECT * FROM temp_channels WHERE guild_id = ?", (guild_id,))
            else:
                cur.execute("SELECT * FROM temp_channels")
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # User Settings
    # =========================================================================

    def get_user_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's default settings."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def save_user_settings(self, user_id: int, **kwargs) -> None:
        """Save user's default settings."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO user_settings (user_id) VALUES (?)
                    ON CONFLICT(user_id) DO NOTHING
                """, (user_id,))
                if kwargs:
                    sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
                    values = list(kwargs.values()) + [user_id]
                    cur.execute(f"UPDATE user_settings SET {sets} WHERE user_id = ?", values)
        except Exception as e:
            logger.tree("DB: Save User Settings Error", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    # =========================================================================
    # Trusted Users
    # =========================================================================

    def add_trusted(self, owner_id: int, trusted_id: int) -> bool:
        """Add a trusted user. Returns False if already trusted."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO trusted_users (owner_id, trusted_id) VALUES (?, ?)
                """, (owner_id, trusted_id))
                logger.tree("DB: Trusted Added", [
                    ("Owner ID", str(owner_id)),
                    ("Trusted ID", str(trusted_id)),
                ], emoji="✅")
                return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.tree("DB: Add Trusted Error", [
                ("Owner ID", str(owner_id)),
                ("Trusted ID", str(trusted_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    def remove_trusted(self, owner_id: int, trusted_id: int) -> bool:
        """Remove a trusted user. Returns False if wasn't trusted."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    DELETE FROM trusted_users WHERE owner_id = ? AND trusted_id = ?
                """, (owner_id, trusted_id))
                removed = cur.rowcount > 0
                if removed:
                    logger.tree("DB: Trusted Removed", [
                        ("Owner ID", str(owner_id)),
                        ("Trusted ID", str(trusted_id)),
                    ], emoji="🗑️")
                return removed
        except Exception as e:
            logger.tree("DB: Remove Trusted Error", [
                ("Owner ID", str(owner_id)),
                ("Trusted ID", str(trusted_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    def is_trusted(self, owner_id: int, user_id: int) -> bool:
        """Check if user is trusted by owner."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM trusted_users WHERE owner_id = ? AND trusted_id = ?
            """, (owner_id, user_id))
            return cur.fetchone() is not None

    def get_trusted_list(self, owner_id: int) -> List[int]:
        """Get list of trusted user IDs."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT trusted_id FROM trusted_users WHERE owner_id = ?", (owner_id,))
            return [row["trusted_id"] for row in cur.fetchall()]

    # =========================================================================
    # Blocked Users
    # =========================================================================

    def add_blocked(self, owner_id: int, blocked_id: int) -> bool:
        """Block a user. Returns False if already blocked."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO blocked_users (owner_id, blocked_id) VALUES (?, ?)
                """, (owner_id, blocked_id))
                logger.tree("DB: Blocked Added", [
                    ("Owner ID", str(owner_id)),
                    ("Blocked ID", str(blocked_id)),
                ], emoji="🚫")
                return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.tree("DB: Add Blocked Error", [
                ("Owner ID", str(owner_id)),
                ("Blocked ID", str(blocked_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    def remove_blocked(self, owner_id: int, blocked_id: int) -> bool:
        """Unblock a user. Returns False if wasn't blocked."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    DELETE FROM blocked_users WHERE owner_id = ? AND blocked_id = ?
                """, (owner_id, blocked_id))
                removed = cur.rowcount > 0
                if removed:
                    logger.tree("DB: Blocked Removed", [
                        ("Owner ID", str(owner_id)),
                        ("Blocked ID", str(blocked_id)),
                    ], emoji="✅")
                return removed
        except Exception as e:
            logger.tree("DB: Remove Blocked Error", [
                ("Owner ID", str(owner_id)),
                ("Blocked ID", str(blocked_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    def is_blocked(self, owner_id: int, user_id: int) -> bool:
        """Check if user is blocked by owner."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM blocked_users WHERE owner_id = ? AND blocked_id = ?
            """, (owner_id, user_id))
            return cur.fetchone() is not None

    def get_blocked_list(self, owner_id: int) -> List[int]:
        """Get list of blocked user IDs."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT blocked_id FROM blocked_users WHERE owner_id = ?", (owner_id,))
            return [row["blocked_id"] for row in cur.fetchall()]

    def get_user_access_lists(self, owner_id: int) -> tuple[List[int], List[int]]:
        """Get both trusted and blocked lists in a single DB connection."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT trusted_id FROM trusted_users WHERE owner_id = ?", (owner_id,))
            trusted = [row["trusted_id"] for row in cur.fetchall()]
            cur.execute("SELECT blocked_id FROM blocked_users WHERE owner_id = ?", (owner_id,))
            blocked = [row["blocked_id"] for row in cur.fetchall()]
            return (trusted, blocked)

    def cleanup_stale_users(self, owner_id: int, valid_user_ids: set) -> int:
        """Remove trusted/blocked users who are no longer in the guild."""
        if not valid_user_ids:
            return 0

        removed = 0
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()

                cur.execute("SELECT trusted_id FROM trusted_users WHERE owner_id = ?", (owner_id,))
                stale_trusted = [row["trusted_id"] for row in cur.fetchall() if row["trusted_id"] not in valid_user_ids]
                if stale_trusted:
                    placeholders = ",".join("?" * len(stale_trusted))
                    cur.execute(
                        f"DELETE FROM trusted_users WHERE owner_id = ? AND trusted_id IN ({placeholders})",
                        [owner_id] + stale_trusted
                    )
                    removed += len(stale_trusted)

                cur.execute("SELECT blocked_id FROM blocked_users WHERE owner_id = ?", (owner_id,))
                stale_blocked = [row["blocked_id"] for row in cur.fetchall() if row["blocked_id"] not in valid_user_ids]
                if stale_blocked:
                    placeholders = ",".join("?" * len(stale_blocked))
                    cur.execute(
                        f"DELETE FROM blocked_users WHERE owner_id = ? AND blocked_id IN ({placeholders})",
                        [owner_id] + stale_blocked
                    )
                    removed += len(stale_blocked)

            if removed > 0:
                logger.tree("DB: Stale Users Cleaned", [
                    ("Owner ID", str(owner_id)),
                    ("Removed", str(removed)),
                ], emoji="🧹")
        except Exception as e:
            logger.tree("DB: Cleanup Stale Error", [
                ("Owner ID", str(owner_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

        return removed

    # =========================================================================
    # Waiting Rooms
    # =========================================================================

    def set_waiting_room(self, channel_id: int, waiting_channel_id: int) -> None:
        """Set waiting room for a temp channel."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO waiting_rooms (channel_id, waiting_channel_id) VALUES (?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET waiting_channel_id = ?
                """, (channel_id, waiting_channel_id, waiting_channel_id))
            logger.tree("DB: Waiting Room Set", [
                ("Channel ID", str(channel_id)),
                ("Waiting ID", str(waiting_channel_id)),
            ], emoji="⏳")
        except Exception as e:
            logger.tree("DB: Set Waiting Room Error", [
                ("Channel ID", str(channel_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def get_waiting_room(self, channel_id: int) -> Optional[int]:
        """Get waiting room channel ID."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT waiting_channel_id FROM waiting_rooms WHERE channel_id = ?", (channel_id,))
            row = cur.fetchone()
            return row["waiting_channel_id"] if row else None

    def remove_waiting_room(self, channel_id: int) -> None:
        """Remove waiting room association."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM waiting_rooms WHERE channel_id = ?", (channel_id,))
            logger.tree("DB: Waiting Room Removed", [
                ("Channel ID", str(channel_id)),
            ], emoji="🗑️")
        except Exception as e:
            logger.tree("DB: Remove Waiting Room Error", [
                ("Channel ID", str(channel_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    # =========================================================================
    # Text Channels
    # =========================================================================

    def set_text_channel(self, channel_id: int, text_channel_id: int) -> None:
        """Set text channel for a temp channel."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO text_channels (channel_id, text_channel_id) VALUES (?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET text_channel_id = ?
                """, (channel_id, text_channel_id, text_channel_id))
            logger.tree("DB: Text Channel Set", [
                ("Channel ID", str(channel_id)),
                ("Text ID", str(text_channel_id)),
            ], emoji="💬")
        except Exception as e:
            logger.tree("DB: Set Text Channel Error", [
                ("Channel ID", str(channel_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def get_text_channel(self, channel_id: int) -> Optional[int]:
        """Get text channel ID."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT text_channel_id FROM text_channels WHERE channel_id = ?", (channel_id,))
            row = cur.fetchone()
            return row["text_channel_id"] if row else None

    def remove_text_channel(self, channel_id: int) -> None:
        """Remove text channel association."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM text_channels WHERE channel_id = ?", (channel_id,))
            logger.tree("DB: Text Channel Removed", [
                ("Channel ID", str(channel_id)),
            ], emoji="🗑️")
        except Exception as e:
            logger.tree("DB: Remove Text Channel Error", [
                ("Channel ID", str(channel_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
