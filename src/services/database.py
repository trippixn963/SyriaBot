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


def _get_week_start_timestamp(timestamp: int = None) -> int:
    """Get Monday 00:00:00 UTC for a given timestamp.

    Args:
        timestamp: Unix timestamp. If None, uses current time.

    Returns:
        Unix timestamp for Monday 00:00:00 UTC of that week.
    """
    import time
    from datetime import datetime, timezone

    if timestamp is None:
        timestamp = int(time.time())

    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    days_since_monday = dt.weekday()
    # Set to Monday 00:00:00 UTC
    week_start = timestamp - (days_since_monday * 86400) - (dt.hour * 3600) - (dt.minute * 60) - dt.second
    return week_start


class Database:
    """SQLite database manager for TempVoice."""

    def __init__(self):
        self.db_path = config.DATABASE_PATH
        self._healthy = True
        self._init_db()

    def _check_integrity(self) -> bool:
        """Check database integrity. Returns True if healthy."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            result = cur.fetchone()
            conn.close()
            return result[0] == "ok"
        except Exception as e:
            log.error_tree("DB Integrity Check Failed", e)
            return False

    def _backup_corrupted(self) -> None:
        """Backup corrupted database file."""
        import shutil
        import time
        backup_path = f"{self.db_path}.corrupted.{int(time.time())}"
        try:
            shutil.copy2(self.db_path, backup_path)
            log.tree("Corrupted DB Backed Up", [
                ("Backup", backup_path),
            ], emoji="💾")
        except Exception as e:
            log.error_tree("DB Backup Failed", e)

    @contextmanager
    def _get_conn(self):
        """Get database connection context manager."""
        if not self._healthy:
            # DB is corrupted, return None-yielding context
            log.warning("Database unhealthy, operation skipped")
            yield None
            return

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            self._healthy = False
            log.error_tree("Database Corruption Detected", e)
            self._backup_corrupted()
            yield None

    def _init_db(self) -> None:
        """Initialize database tables."""
        log.info(f"Initializing database: {self.db_path}")

        # Check integrity on startup
        import os
        if os.path.exists(self.db_path) and not self._check_integrity():
            log.critical("Database corrupted! Backing up and recreating...")
            self._backup_corrupted()
            # Delete corrupted file to recreate
            try:
                os.remove(self.db_path)
                log.info("Corrupted database removed, will recreate")
            except OSError as e:
                log.error_tree("Failed to remove corrupted DB", e)
                self._healthy = False
                return

        with self._get_conn() as conn:
            if conn is None:
                log.error("Failed to initialize database connection")
                return
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

            # Add base_name column if it doesn't exist (migration for positional numbering)
            try:
                cur.execute("ALTER TABLE temp_channels ADD COLUMN base_name TEXT")
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

            # Convert command usage tracking
            cur.execute("""
                CREATE TABLE IF NOT EXISTS convert_usage (
                    user_id INTEGER PRIMARY KEY,
                    uses_this_week INTEGER DEFAULT 0,
                    week_start_timestamp INTEGER NOT NULL
                )
            """)

            # XP System
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_xp (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    total_messages INTEGER DEFAULT 0,
                    voice_minutes INTEGER DEFAULT 0,
                    last_message_xp INTEGER DEFAULT 0,
                    last_voice_xp INTEGER DEFAULT 0,
                    created_at INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            # Add created_at column if it doesn't exist (migration)
            try:
                cur.execute("ALTER TABLE user_xp ADD COLUMN created_at INTEGER DEFAULT 0")
            except Exception:
                pass  # Column already exists

            # Add new tracking columns (migration)
            new_columns = [
                ("first_message_at", "INTEGER DEFAULT 0"),
                ("last_active_at", "INTEGER DEFAULT 0"),
                ("streak_days", "INTEGER DEFAULT 0"),
                ("last_streak_date", "TEXT DEFAULT ''"),
                ("longest_voice_session", "INTEGER DEFAULT 0"),
                ("total_voice_sessions", "INTEGER DEFAULT 0"),
                ("commands_used", "INTEGER DEFAULT 0"),
                ("reactions_given", "INTEGER DEFAULT 0"),
                ("images_shared", "INTEGER DEFAULT 0"),
            ]
            for col_name, col_type in new_columns:
                try:
                    cur.execute(f"ALTER TABLE user_xp ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass  # Column already exists

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
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO temp_channels (channel_id, owner_id, guild_id, name, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (channel_id, owner_id, guild_id, name, created_at))
            log.tree("DB: Channel Created", [
                ("Channel ID", str(channel_id)),
                ("Owner ID", str(owner_id)),
                ("Name", name),
            ], emoji="💾")
        except Exception as e:
            log.tree("DB: Create Channel Error", [
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
            log.tree("DB: Channel Deleted", [
                ("Channel ID", str(channel_id)),
            ], emoji="🗑️")
        except Exception as e:
            log.tree("DB: Delete Channel Error", [
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
        with self._get_conn() as conn:
            cur = conn.cursor()
            sets = ", ".join(f"{k} = ?" for k in kwargs.keys())
            values = list(kwargs.values()) + [channel_id]
            cur.execute(f"UPDATE temp_channels SET {sets} WHERE channel_id = ?", values)

    def transfer_ownership(self, channel_id: int, new_owner_id: int) -> None:
        """Transfer channel ownership."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE temp_channels SET owner_id = ? WHERE channel_id = ?
                """, (new_owner_id, channel_id))
            log.tree("DB: Ownership Transferred", [
                ("Channel ID", str(channel_id)),
                ("New Owner", str(new_owner_id)),
            ], emoji="👑")
        except Exception as e:
            log.tree("DB: Transfer Error", [
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

    def get_user_access_lists(self, owner_id: int) -> tuple[List[int], List[int]]:
        """Get both trusted and blocked lists in a single DB connection.

        Returns:
            (trusted_list, blocked_list) tuple
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT trusted_id FROM trusted_users WHERE owner_id = ?", (owner_id,))
            trusted = [row["trusted_id"] for row in cur.fetchall()]
            cur.execute("SELECT blocked_id FROM blocked_users WHERE owner_id = ?", (owner_id,))
            blocked = [row["blocked_id"] for row in cur.fetchall()]
            return (trusted, blocked)

    def cleanup_stale_users(self, owner_id: int, valid_user_ids: set) -> int:
        """Remove trusted/blocked users who are no longer in the guild.

        Uses batch SQL DELETE for efficiency instead of individual deletes.

        Args:
            owner_id: The owner's user ID
            valid_user_ids: Set of user IDs that are still in the guild

        Returns:
            Number of stale entries removed
        """
        if not valid_user_ids:
            return 0

        removed = 0
        with self._get_conn() as conn:
            cur = conn.cursor()

            # Get stale trusted users and batch delete
            cur.execute("SELECT trusted_id FROM trusted_users WHERE owner_id = ?", (owner_id,))
            stale_trusted = [row["trusted_id"] for row in cur.fetchall() if row["trusted_id"] not in valid_user_ids]
            if stale_trusted:
                placeholders = ",".join("?" * len(stale_trusted))
                cur.execute(
                    f"DELETE FROM trusted_users WHERE owner_id = ? AND trusted_id IN ({placeholders})",
                    [owner_id] + stale_trusted
                )
                removed += len(stale_trusted)

            # Get stale blocked users and batch delete
            cur.execute("SELECT blocked_id FROM blocked_users WHERE owner_id = ?", (owner_id,))
            stale_blocked = [row["blocked_id"] for row in cur.fetchall() if row["blocked_id"] not in valid_user_ids]
            if stale_blocked:
                placeholders = ",".join("?" * len(stale_blocked))
                cur.execute(
                    f"DELETE FROM blocked_users WHERE owner_id = ? AND blocked_id IN ({placeholders})",
                    [owner_id] + stale_blocked
                )
                removed += len(stale_blocked)

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

    # =========================================================================
    # Convert Usage Tracking
    # =========================================================================

    def get_convert_usage(self, user_id: int) -> tuple[int, int]:
        """
        Get user's convert usage for this week.

        Returns:
            (uses_remaining, week_start_timestamp)
            If user has no record or week has reset, returns (3, current_week_start)
        """
        week_start = _get_week_start_timestamp()

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT uses_this_week, week_start_timestamp FROM convert_usage WHERE user_id = ?", (user_id,))
            row = cur.fetchone()

            if not row:
                # New user, hasn't used before
                return (3, week_start)

            stored_week_start = row["week_start_timestamp"]
            uses_this_week = row["uses_this_week"]

            # Check if we're in a new week
            if week_start > stored_week_start:
                # New week, reset uses
                return (3, week_start)

            # Same week, return remaining uses
            return (max(0, 3 - uses_this_week), stored_week_start)

    def record_convert_usage(self, user_id: int) -> int:
        """
        Record a convert usage for a user.

        Returns:
            Number of uses remaining after this use
        """
        week_start = _get_week_start_timestamp()

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Check if user exists
            cur.execute("SELECT uses_this_week, week_start_timestamp FROM convert_usage WHERE user_id = ?", (user_id,))
            row = cur.fetchone()

            if not row:
                # New user
                cur.execute("""
                    INSERT INTO convert_usage (user_id, uses_this_week, week_start_timestamp)
                    VALUES (?, 1, ?)
                """, (user_id, week_start))
                return 2  # 3 - 1 = 2 remaining

            stored_week_start = row["week_start_timestamp"]

            if week_start > stored_week_start:
                # New week, reset and record new use
                cur.execute("""
                    UPDATE convert_usage SET uses_this_week = 1, week_start_timestamp = ?
                    WHERE user_id = ?
                """, (week_start, user_id))
                return 2  # 3 - 1 = 2 remaining

            # Same week, increment
            new_uses = row["uses_this_week"] + 1
            cur.execute("""
                UPDATE convert_usage SET uses_this_week = ?
                WHERE user_id = ?
            """, (new_uses, user_id))
            return max(0, 3 - new_uses)

    def get_next_reset_timestamp(self) -> int:
        """Get timestamp for next Monday 00:00 UTC."""
        # Current week start + 7 days = next Monday
        return _get_week_start_timestamp() + (7 * 86400)


    # =========================================================================
    # XP System
    # =========================================================================

    def get_user_xp(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get user's XP data for a guild."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM user_xp WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def ensure_user_xp(self, user_id: int, guild_id: int) -> Dict[str, Any]:
        """Get or create user's XP data."""
        import time

        data = self.get_user_xp(user_id, guild_id)
        if data:
            return data

        now = int(time.time())
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_xp (user_id, guild_id, xp, level, total_messages, voice_minutes, created_at)
                VALUES (?, ?, 0, 0, 0, 0, ?)
            """, (user_id, guild_id, now))

        return {
            "user_id": user_id,
            "guild_id": guild_id,
            "xp": 0,
            "level": 0,
            "total_messages": 0,
            "voice_minutes": 0,
            "last_message_xp": 0,
            "last_voice_xp": 0,
            "created_at": now,
        }

    def add_xp(
        self,
        user_id: int,
        guild_id: int,
        amount: int,
        source: str = "message"
    ) -> Dict[str, Any]:
        """
        Add XP to a user.

        Args:
            user_id: User's Discord ID
            guild_id: Guild's Discord ID
            amount: XP amount to add
            source: "message" or "voice"

        Returns:
            Dict with old_level, new_level, old_xp, new_xp, leveled_up
        """
        import time
        now = int(time.time())

        # Ensure user exists
        self.ensure_user_xp(user_id, guild_id)

        with self._get_conn() as conn:
            cur = conn.cursor()

            # Get current data
            cur.execute(
                "SELECT xp, level FROM user_xp WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = cur.fetchone()
            old_xp = row["xp"]
            old_level = row["level"]

            new_xp = old_xp + amount

            # Update based on source
            if source == "message":
                cur.execute("""
                    UPDATE user_xp
                    SET xp = ?, last_message_xp = ?, total_messages = total_messages + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (new_xp, now, user_id, guild_id))
            else:  # voice
                cur.execute("""
                    UPDATE user_xp
                    SET xp = ?, last_voice_xp = ?, voice_minutes = voice_minutes + 1
                    WHERE user_id = ? AND guild_id = ?
                """, (new_xp, now, user_id, guild_id))

        return {
            "old_xp": old_xp,
            "new_xp": new_xp,
            "old_level": old_level,
        }

    def set_user_level(self, user_id: int, guild_id: int, level: int) -> None:
        """Set user's level."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET level = ? WHERE user_id = ? AND guild_id = ?
            """, (level, user_id, guild_id))

    def get_last_message_xp(self, user_id: int, guild_id: int) -> int:
        """Get timestamp of last message XP gain."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT last_message_xp FROM user_xp WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = cur.fetchone()
            return row["last_message_xp"] if row else 0

    def get_leaderboard(self, guild_id: int = None, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get top users by XP in a guild with pagination."""
        from src.core.config import config
        gid = guild_id or config.GUILD_ID

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT user_id, xp, level, total_messages, voice_minutes,
                       ROW_NUMBER() OVER (ORDER BY xp DESC) as rank
                FROM user_xp
                WHERE guild_id = ?
                ORDER BY xp DESC
                LIMIT ? OFFSET ?
            """, (gid, limit, offset))
            return [dict(row) for row in cur.fetchall()]

    def get_total_ranked_users(self, guild_id: int = None) -> int:
        """Get total number of users with XP in a guild."""
        from src.core.config import config
        gid = guild_id or config.GUILD_ID

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as total
                FROM user_xp
                WHERE guild_id = ?
            """, (gid,))
            row = cur.fetchone()
            return row["total"] if row else 0

    def get_xp_stats(self, guild_id: int = None) -> Dict[str, Any]:
        """Get overall XP statistics for a guild."""
        from src.core.config import config
        gid = guild_id or config.GUILD_ID

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(*) as total_users,
                    COALESCE(SUM(xp), 0) as total_xp,
                    COALESCE(SUM(total_messages), 0) as total_messages,
                    COALESCE(SUM(voice_minutes), 0) as total_voice_minutes,
                    COALESCE(MAX(level), 0) as highest_level
                FROM user_xp
                WHERE guild_id = ?
            """, (gid,))
            row = cur.fetchone()
            return dict(row) if row else {
                "total_users": 0,
                "total_xp": 0,
                "total_messages": 0,
                "total_voice_minutes": 0,
                "highest_level": 0,
            }

    def get_user_rank(self, user_id: int, guild_id: int) -> int:
        """Get user's rank position in the guild (1-indexed)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) + 1 as rank
                FROM user_xp
                WHERE guild_id = ? AND xp > (
                    SELECT COALESCE(xp, 0) FROM user_xp
                    WHERE user_id = ? AND guild_id = ?
                )
            """, (guild_id, user_id, guild_id))
            row = cur.fetchone()
            return row["rank"] if row else 1

    # =========================================================================
    # Extended User Tracking
    # =========================================================================

    def increment_commands_used(self, user_id: int, guild_id: int) -> None:
        """Increment user's commands used count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET commands_used = commands_used + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    def increment_reactions_given(self, user_id: int, guild_id: int) -> None:
        """Increment user's reactions given count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET reactions_given = reactions_given + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    def increment_images_shared(self, user_id: int, guild_id: int) -> None:
        """Increment user's images shared count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET images_shared = images_shared + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    def increment_voice_sessions(self, user_id: int, guild_id: int) -> None:
        """Increment user's total voice sessions count."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET total_voice_sessions = total_voice_sessions + 1
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))

    def update_longest_voice_session(self, user_id: int, guild_id: int, minutes: int) -> None:
        """Update longest voice session if current is longer."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET longest_voice_session = MAX(longest_voice_session, ?)
                WHERE user_id = ? AND guild_id = ?
            """, (minutes, user_id, guild_id))

    def set_first_message_at(self, user_id: int, guild_id: int, timestamp: int) -> None:
        """Set first message timestamp (only if not already set)."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET first_message_at = ?
                WHERE user_id = ? AND guild_id = ? AND first_message_at = 0
            """, (timestamp, user_id, guild_id))

    def update_last_active(self, user_id: int, guild_id: int, timestamp: int) -> None:
        """Update last active timestamp."""
        self.ensure_user_xp(user_id, guild_id)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_xp SET last_active_at = ?
                WHERE user_id = ? AND guild_id = ?
            """, (timestamp, user_id, guild_id))

    def update_streak(self, user_id: int, guild_id: int, today_date: str) -> int:
        """
        Update user's streak. Call this when user is active.

        Args:
            user_id: User's Discord ID
            guild_id: Guild's Discord ID
            today_date: Today's date as 'YYYY-MM-DD'

        Returns:
            New streak count
        """
        from datetime import datetime, timedelta

        self.ensure_user_xp(user_id, guild_id)

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT streak_days, last_streak_date FROM user_xp
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = cur.fetchone()

            current_streak = row["streak_days"] if row else 0
            last_date = row["last_streak_date"] if row else ""

            if last_date == today_date:
                # Already recorded today
                return current_streak

            # Check if yesterday (continue streak) or older (reset)
            if last_date:
                try:
                    last = datetime.strptime(last_date, "%Y-%m-%d").date()
                    today = datetime.strptime(today_date, "%Y-%m-%d").date()
                    yesterday = today - timedelta(days=1)

                    if last == yesterday:
                        # Continue streak
                        new_streak = current_streak + 1
                    else:
                        # Streak broken, reset to 1
                        new_streak = 1
                except ValueError:
                    new_streak = 1
            else:
                # First activity
                new_streak = 1

            cur.execute("""
                UPDATE user_xp SET streak_days = ?, last_streak_date = ?
                WHERE user_id = ? AND guild_id = ?
            """, (new_streak, today_date, user_id, guild_id))

            return new_streak


# Global instance
db = Database()
