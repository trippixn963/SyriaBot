"""
SyriaBot - Database
===================

SQLite database for TempVoice system.

Author: حَـــــنَّـــــا
"""

import sqlite3
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from src.core.config import config
from src.core.logger import log


class Database:
    """SQLite database manager for TempVoice."""

    def __init__(self):
        self.db_path = config.DATABASE_PATH
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """Get database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database tables."""
        with self._get_conn() as conn:
            cur = conn.cursor()

            # Active temp voice channels
            cur.execute("""
                CREATE TABLE IF NOT EXISTS temp_channels (
                    channel_id INTEGER PRIMARY KEY,
                    owner_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    name TEXT,
                    user_limit INTEGER DEFAULT 0,
                    is_locked INTEGER DEFAULT 0,
                    is_hidden INTEGER DEFAULT 0,
                    panel_message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add panel_message_id column if it doesn't exist (migration)
            try:
                cur.execute("ALTER TABLE temp_channels ADD COLUMN panel_message_id INTEGER")
            except Exception:
                pass  # Column already exists

            # User settings (remembered for next VC)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    default_name TEXT,
                    default_limit INTEGER DEFAULT 0,
                    default_locked INTEGER DEFAULT 0,
                    default_region TEXT
                )
            """)

            # Trusted users per channel owner
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trusted_users (
                    owner_id INTEGER NOT NULL,
                    trusted_id INTEGER NOT NULL,
                    PRIMARY KEY (owner_id, trusted_id)
                )
            """)

            # Blocked users per channel owner
            cur.execute("""
                CREATE TABLE IF NOT EXISTS blocked_users (
                    owner_id INTEGER NOT NULL,
                    blocked_id INTEGER NOT NULL,
                    PRIMARY KEY (owner_id, blocked_id)
                )
            """)

            # Waiting room associations
            cur.execute("""
                CREATE TABLE IF NOT EXISTS waiting_rooms (
                    channel_id INTEGER PRIMARY KEY,
                    waiting_channel_id INTEGER NOT NULL,
                    FOREIGN KEY (channel_id) REFERENCES temp_channels(channel_id)
                )
            """)

            # Text channel associations
            cur.execute("""
                CREATE TABLE IF NOT EXISTS text_channels (
                    channel_id INTEGER PRIMARY KEY,
                    text_channel_id INTEGER NOT NULL,
                    FOREIGN KEY (channel_id) REFERENCES temp_channels(channel_id)
                )
            """)

            log.success("Database initialized")

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
        import time
        if created_at is None:
            created_at = int(time.time())
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO temp_channels (channel_id, owner_id, guild_id, name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (channel_id, owner_id, guild_id, name, created_at))

    def delete_temp_channel(self, channel_id: int) -> None:
        """Delete a temp channel record."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM temp_channels WHERE channel_id = ?", (channel_id,))
            cur.execute("DELETE FROM waiting_rooms WHERE channel_id = ?", (channel_id,))
            cur.execute("DELETE FROM text_channels WHERE channel_id = ?", (channel_id,))

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
        with self._get_conn() as conn:
            cur = conn.cursor()
            sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
            values = list(kwargs.values()) + [channel_id]
            cur.execute(f"UPDATE temp_channels SET {sets} WHERE channel_id = ?", values)

    def transfer_ownership(self, channel_id: int, new_owner_id: int) -> None:
        """Transfer channel ownership."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE temp_channels SET owner_id = ? WHERE channel_id = ?
            """, (new_owner_id, channel_id))

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

    # =========================================================================
    # Trusted Users
    # =========================================================================

    def add_trusted(self, owner_id: int, trusted_id: int) -> bool:
        """Add a trusted user. Returns False if already trusted."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO trusted_users (owner_id, trusted_id) VALUES (?, ?)
                """, (owner_id, trusted_id))
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_trusted(self, owner_id: int, trusted_id: int) -> bool:
        """Remove a trusted user. Returns False if wasn't trusted."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM trusted_users WHERE owner_id = ? AND trusted_id = ?
            """, (owner_id, trusted_id))
            return cur.rowcount > 0

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
        with self._get_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO blocked_users (owner_id, blocked_id) VALUES (?, ?)
                """, (owner_id, blocked_id))
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_blocked(self, owner_id: int, blocked_id: int) -> bool:
        """Unblock a user. Returns False if wasn't blocked."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM blocked_users WHERE owner_id = ? AND blocked_id = ?
            """, (owner_id, blocked_id))
            return cur.rowcount > 0

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

    def cleanup_stale_users(self, owner_id: int, valid_user_ids: set) -> int:
        """Remove trusted/blocked users who are no longer in the guild.

        Args:
            owner_id: The owner's user ID
            valid_user_ids: Set of user IDs that are still in the guild

        Returns:
            Number of stale entries removed
        """
        removed = 0
        with self._get_conn() as conn:
            cur = conn.cursor()

            # Get current trusted list
            cur.execute("SELECT trusted_id FROM trusted_users WHERE owner_id = ?", (owner_id,))
            for row in cur.fetchall():
                if row["trusted_id"] not in valid_user_ids:
                    cur.execute(
                        "DELETE FROM trusted_users WHERE owner_id = ? AND trusted_id = ?",
                        (owner_id, row["trusted_id"])
                    )
                    removed += 1

            # Get current blocked list
            cur.execute("SELECT blocked_id FROM blocked_users WHERE owner_id = ?", (owner_id,))
            for row in cur.fetchall():
                if row["blocked_id"] not in valid_user_ids:
                    cur.execute(
                        "DELETE FROM blocked_users WHERE owner_id = ? AND blocked_id = ?",
                        (owner_id, row["blocked_id"])
                    )
                    removed += 1

        return removed

    # =========================================================================
    # Waiting Rooms
    # =========================================================================

    def set_waiting_room(self, channel_id: int, waiting_channel_id: int) -> None:
        """Set waiting room for a temp channel."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO waiting_rooms (channel_id, waiting_channel_id) VALUES (?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET waiting_channel_id = ?
            """, (channel_id, waiting_channel_id, waiting_channel_id))

    def get_waiting_room(self, channel_id: int) -> Optional[int]:
        """Get waiting room channel ID."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT waiting_channel_id FROM waiting_rooms WHERE channel_id = ?", (channel_id,))
            row = cur.fetchone()
            return row["waiting_channel_id"] if row else None

    def remove_waiting_room(self, channel_id: int) -> None:
        """Remove waiting room association."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM waiting_rooms WHERE channel_id = ?", (channel_id,))

    # =========================================================================
    # Text Channels
    # =========================================================================

    def set_text_channel(self, channel_id: int, text_channel_id: int) -> None:
        """Set text channel for a temp channel."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO text_channels (channel_id, text_channel_id) VALUES (?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET text_channel_id = ?
            """, (channel_id, text_channel_id, text_channel_id))

    def get_text_channel(self, channel_id: int) -> Optional[int]:
        """Get text channel ID."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT text_channel_id FROM text_channels WHERE channel_id = ?", (channel_id,))
            row = cur.fetchone()
            return row["text_channel_id"] if row else None

    def remove_text_channel(self, channel_id: int) -> None:
        """Remove text channel association."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM text_channels WHERE channel_id = ?", (channel_id,))


# Global instance
db = Database()
