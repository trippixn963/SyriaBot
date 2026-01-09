"""
SyriaBot - Database Core
========================

Base database class with connection management and table initialization.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Optional

from src.core.config import config
from src.core.logger import log


def get_week_start_timestamp(timestamp: int = None) -> int:
    """Get Monday 00:00:00 UTC for a given timestamp.

    Args:
        timestamp: Unix timestamp. If None, uses current time.

    Returns:
        Unix timestamp for Monday 00:00:00 UTC of that week.
    """
    from datetime import datetime, timezone

    if timestamp is None:
        timestamp = int(time.time())

    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    days_since_monday = dt.weekday()
    # Set to Monday 00:00:00 UTC
    week_start = timestamp - (days_since_monday * 86400) - (dt.hour * 3600) - (dt.minute * 60) - dt.second
    return week_start


class DatabaseCore:
    """Base database class with connection management."""

    def __init__(self) -> None:
        """Initialize database connection and create tables if needed."""
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
            log.tree("Database Unhealthy", [
                ("Status", "Operation skipped"),
            ], emoji="⚠️")
            yield None
            return

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except sqlite3.DatabaseError as e:
            error_msg = str(e).lower()
            is_corruption = any(x in error_msg for x in [
                "disk i/o error",
                "database disk image is malformed",
                "file is not a database",
                "file is encrypted",
                "unable to open database",
            ])
            if is_corruption:
                self._healthy = False
                log.error_tree("Database Corruption Detected", e)
                self._backup_corrupted()
            else:
                log.tree("Database Error", [
                    ("Type", type(e).__name__),
                    ("Message", str(e)[:100]),
                ], emoji="⚠️")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _init_db(self) -> None:
        """Initialize database tables."""
        log.tree("Database Init", [
            ("Path", self.db_path),
            ("Status", "Starting"),
        ], emoji="🗄️")

        # Check integrity on startup
        if os.path.exists(self.db_path) and not self._check_integrity():
            log.tree("DATABASE CORRUPTION DETECTED", [
                ("Path", self.db_path),
                ("Status", "INTEGRITY CHECK FAILED"),
                ("Action", "Creating backup - MANUAL INTERVENTION REQUIRED"),
            ], emoji="🚨")
            self._backup_corrupted()
            self._healthy = False
            log.tree("MANUAL FIX REQUIRED", [
                ("Backup", f"{self.db_path}.corrupted.*"),
                ("Action", "Restore from backup or delete syria.db to recreate"),
                ("Warning", "Bot will not function until database is fixed"),
            ], emoji="⚠️")
            return

        with self._get_conn() as conn:
            if conn is None:
                log.tree("Database Init Failed", [
                    ("Reason", "Could not establish connection"),
                ], emoji="❌")
                return
            cur = conn.cursor()

            # =====================================================================
            # TempVoice Tables
            # =====================================================================

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

            # Migrations
            try:
                cur.execute("ALTER TABLE temp_channels ADD COLUMN panel_message_id INTEGER")
            except Exception:
                pass
            try:
                cur.execute("ALTER TABLE temp_channels ADD COLUMN base_name TEXT")
            except Exception:
                pass

            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    default_name TEXT,
                    default_limit INTEGER DEFAULT 0,
                    default_locked INTEGER DEFAULT 0,
                    default_region TEXT
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS trusted_users (
                    owner_id INTEGER NOT NULL,
                    trusted_id INTEGER NOT NULL,
                    PRIMARY KEY (owner_id, trusted_id)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS blocked_users (
                    owner_id INTEGER NOT NULL,
                    blocked_id INTEGER NOT NULL,
                    PRIMARY KEY (owner_id, blocked_id)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS waiting_rooms (
                    channel_id INTEGER PRIMARY KEY,
                    waiting_channel_id INTEGER NOT NULL,
                    FOREIGN KEY (channel_id) REFERENCES temp_channels(channel_id)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS text_channels (
                    channel_id INTEGER PRIMARY KEY,
                    text_channel_id INTEGER NOT NULL,
                    FOREIGN KEY (channel_id) REFERENCES temp_channels(channel_id)
                )
            """)

            # =====================================================================
            # Rate Limiting Tables
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS convert_usage (
                    user_id INTEGER PRIMARY KEY,
                    uses_this_week INTEGER DEFAULT 0,
                    week_start_timestamp INTEGER NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS download_usage (
                    user_id INTEGER PRIMARY KEY,
                    uses_this_week INTEGER DEFAULT 0,
                    week_start_timestamp INTEGER NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS image_usage (
                    user_id INTEGER PRIMARY KEY,
                    uses_this_week INTEGER DEFAULT 0,
                    week_start_timestamp INTEGER NOT NULL
                )
            """)

            # =====================================================================
            # XP System Tables
            # =====================================================================

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

            # XP Migrations
            try:
                cur.execute("ALTER TABLE user_xp ADD COLUMN created_at INTEGER DEFAULT 0")
            except Exception:
                pass

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
                ("activity_hours", "TEXT DEFAULT '{}'"),
                ("invited_by", "INTEGER DEFAULT 0"),
                ("is_active", "INTEGER DEFAULT 1"),
            ]
            for col_name, col_type in new_columns:
                try:
                    cur.execute(f"ALTER TABLE user_xp ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

            # =====================================================================
            # Server Stats Tables
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS server_daily_stats (
                    date TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    unique_users INTEGER DEFAULT 0,
                    total_messages INTEGER DEFAULT 0,
                    voice_peak_users INTEGER DEFAULT 0,
                    new_members INTEGER DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS channel_stats (
                    channel_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    channel_name TEXT,
                    total_messages INTEGER DEFAULT 0,
                    last_message_at INTEGER DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS server_hourly_activity (
                    guild_id INTEGER NOT NULL,
                    hour INTEGER NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    voice_joins INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, hour)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS boost_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                )
            """)

            # =====================================================================
            # AFK System Tables
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS afk_users (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    reason TEXT DEFAULT '',
                    timestamp INTEGER NOT NULL,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS afk_mentions (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    mention_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS afk_mention_pingers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    afk_user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    pinger_id INTEGER NOT NULL,
                    pinger_name TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                )
            """)

            # =====================================================================
            # Download Stats Tables
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS download_stats (
                    user_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    total_downloads INTEGER DEFAULT 0,
                    total_files INTEGER DEFAULT 0,
                    last_download_at INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, platform)
                )
            """)

            # =====================================================================
            # Confessions Tables
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS confessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    submitter_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    confession_number INTEGER,
                    image_url TEXT,
                    submitted_at INTEGER NOT NULL,
                    reviewed_at INTEGER,
                    reviewed_by INTEGER
                )
            """)

            # Confessions migration - add image_url column
            try:
                cur.execute("ALTER TABLE confessions ADD COLUMN image_url TEXT")
            except Exception:
                pass

            # =====================================================================
            # Action Stats Tables
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS action_stats (
                    user_id INTEGER NOT NULL,
                    target_id INTEGER,
                    guild_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    last_used_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, target_id, guild_id, action)
                )
            """)

            # =====================================================================
            # Suggestions Tables
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    submitter_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    submitted_at INTEGER NOT NULL,
                    reviewed_at INTEGER,
                    reviewed_by INTEGER
                )
            """)

            # =====================================================================
            # Giveaways Tables
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER UNIQUE,
                    channel_id INTEGER NOT NULL,
                    host_id INTEGER NOT NULL,
                    prize_type TEXT NOT NULL,
                    prize_description TEXT NOT NULL,
                    prize_amount INTEGER DEFAULT 0,
                    prize_coins INTEGER DEFAULT 0,
                    prize_role_id INTEGER,
                    required_role_id INTEGER,
                    min_level INTEGER DEFAULT 0,
                    winner_count INTEGER DEFAULT 1,
                    ends_at TIMESTAMP NOT NULL,
                    ended INTEGER DEFAULT 0,
                    winners TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration: Add prize_coins column if missing
            cur.execute("PRAGMA table_info(giveaways)")
            columns = [row[1] for row in cur.fetchall()]
            if "prize_coins" not in columns:
                cur.execute("ALTER TABLE giveaways ADD COLUMN prize_coins INTEGER DEFAULT 0")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    giveaway_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (giveaway_id, user_id),
                    FOREIGN KEY (giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
                )
            """)

            # =====================================================================
            # Indexes
            # =====================================================================

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_giveaways_ends_at
                ON giveaways(ends_at) WHERE ended = 0
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_giveaways_message
                ON giveaways(message_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_xp_leaderboard
                ON user_xp(guild_id, xp DESC)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_xp_user_guild
                ON user_xp(user_id, guild_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_temp_channels_guild
                ON temp_channels(guild_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_boost_history_guild
                ON boost_history(guild_id, timestamp DESC)
            """)

            log.tree("Database Initialized", [
                ("Tables", "All created/verified"),
                ("Status", "Ready"),
            ], emoji="✅")
