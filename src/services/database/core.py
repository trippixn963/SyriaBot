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
from src.core.logger import logger


class DatabaseUnavailableError(Exception):
    """Raised when the database is unhealthy and operations cannot proceed."""
    pass


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
        self._corruption_reason: Optional[str] = None
        self._init_db()

    @property
    def is_healthy(self) -> bool:
        """Check if database is healthy and operational."""
        return self._healthy

    @property
    def corruption_reason(self) -> Optional[str]:
        """Get the reason for database corruption if unhealthy."""
        return self._corruption_reason

    def require_healthy(self) -> None:
        """Raise RuntimeError if database is unhealthy.

        Use this at service startup to fail fast if DB is corrupted.
        """
        if not self._healthy:
            raise RuntimeError(
                f"Database is unhealthy: {self._corruption_reason or 'Unknown error'}. "
                "Manual intervention required - check logs for backup location."
            )

    def _check_integrity(self) -> bool:
        """Check database integrity. Returns True if healthy."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check")
            result = cur.fetchone()
            conn.close()
            return result[0] == "ok"
        except Exception as e:
            logger.error_tree("DB Integrity Check Failed", e)
            return False

    def _backup_corrupted(self) -> None:
        """Backup corrupted database file."""
        import shutil
        backup_path = f"{self.db_path}.corrupted.{int(time.time())}"
        try:
            shutil.copy2(self.db_path, backup_path)
            logger.tree("Corrupted DB Backed Up", [
                ("Backup", backup_path),
            ], emoji="💾")
        except Exception as e:
            logger.error_tree("DB Backup Failed", e)

    @contextmanager
    def _get_conn(self) -> "Generator[sqlite3.Connection, None, None]":
        """Get database connection context manager.

        Raises:
            DatabaseUnavailableError: If the database is unhealthy.
        """
        if not self._healthy:
            logger.tree("Database Unhealthy", [
                ("Status", "Operation rejected"),
                ("Reason", self._corruption_reason or "Unknown"),
            ], emoji="⚠️")
            raise DatabaseUnavailableError(
                f"Database is unavailable: {self._corruption_reason or 'unhealthy'}"
            )

        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
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
                self._corruption_reason = str(e)
                logger.error_tree("Database Corruption Detected", e)
                self._backup_corrupted()
            elif isinstance(e, sqlite3.IntegrityError):
                # IntegrityError is expected for UNIQUE constraint violations
                # (e.g., blocking already-blocked users) - re-raise for handlers
                raise
            else:
                logger.tree("Database Error", [
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
        logger.tree("Database Init", [
            ("Path", self.db_path),
            ("Status", "Starting"),
        ], emoji="🗄️")

        # Check integrity on startup
        if os.path.exists(self.db_path) and not self._check_integrity():
            self._corruption_reason = "PRAGMA integrity_check failed on startup"
            logger.tree("DATABASE CORRUPTION DETECTED", [
                ("Path", self.db_path),
                ("Status", "INTEGRITY CHECK FAILED"),
                ("Action", "Creating backup - MANUAL INTERVENTION REQUIRED"),
            ], emoji="🚨")
            self._backup_corrupted()
            self._healthy = False
            logger.tree("MANUAL FIX REQUIRED", [
                ("Backup", f"{self.db_path}.corrupted.*"),
                ("Action", "Restore from backup or delete syria.db to recreate"),
                ("Warning", "Bot will not function until database is fixed"),
            ], emoji="⚠️")
            return

        with self._get_conn() as conn:
            if conn is None:
                logger.tree("Database Init Failed", [
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

            # Migrations (OperationalError = column already exists, which is expected)
            try:
                cur.execute("ALTER TABLE temp_channels ADD COLUMN panel_message_id INTEGER")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cur.execute("ALTER TABLE temp_channels ADD COLUMN base_name TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

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
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Safe column definitions - names are validated against whitelist
            VALID_COLUMN_NAMES = frozenset([
                "first_message_at", "last_active_at", "streak_days", "last_streak_date",
                "longest_voice_session", "total_voice_sessions", "commands_used",
                "reactions_given", "images_shared", "activity_hours", "invited_by", "is_active",
                "mentions_received", "reactions_received", "replies_sent", "threads_created",
                "links_shared"
            ])
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
                ("mentions_received", "INTEGER DEFAULT 0"),
                # New columns for enhanced analytics
                ("reactions_received", "INTEGER DEFAULT 0"),
                ("replies_sent", "INTEGER DEFAULT 0"),
                ("threads_created", "INTEGER DEFAULT 0"),
                ("links_shared", "INTEGER DEFAULT 0"),
            ]
            for col_name, col_type in new_columns:
                # Validate column name against whitelist to prevent injection
                if col_name not in VALID_COLUMN_NAMES:
                    logger.tree("Invalid Column Name Skipped", [
                        ("Column", col_name),
                    ], emoji="⚠️")
                    continue
                try:
                    cur.execute(f"ALTER TABLE user_xp ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass  # Column already exists

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

            # Server-level counters (fast O(1) lookups)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS server_counters (
                    guild_id INTEGER NOT NULL,
                    counter_name TEXT NOT NULL,
                    value INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, counter_name)
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
            # Voice Channel Stats Table (NEW)
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS voice_channel_stats (
                    channel_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    channel_name TEXT NOT NULL,
                    total_minutes INTEGER DEFAULT 0,
                    peak_users INTEGER DEFAULT 0,
                    session_count INTEGER DEFAULT 0,
                    last_active_at INTEGER DEFAULT 0,
                    PRIMARY KEY (channel_id, guild_id)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_voice_channel_stats_guild
                ON voice_channel_stats(guild_id, total_minutes DESC)
            """)

            # =====================================================================
            # Role Snapshots Table (NEW)
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS role_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    role_name TEXT NOT NULL,
                    member_count INTEGER DEFAULT 0,
                    UNIQUE(date, guild_id, role_id)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_role_snapshots_date
                ON role_snapshots(guild_id, date DESC)
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
            except sqlite3.OperationalError:
                pass  # Column already exists

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
            # Birthdays Table
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS birthdays (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    birth_month INTEGER NOT NULL,
                    birth_day INTEGER NOT NULL,
                    birth_year INTEGER,
                    role_granted_at INTEGER,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            # Birthday migration - add birth_year column
            try:
                cur.execute("ALTER TABLE birthdays ADD COLUMN birth_year INTEGER")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # =====================================================================
            # Actions Panel Table (persistent actions list messages per channel)
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS actions_panel (
                    channel_id INTEGER PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    actions_hash TEXT
                )
            """)

            # =====================================================================
            # XP History / Snapshots Table (for period leaderboards)
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS xp_snapshots (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    xp_total INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    total_messages INTEGER DEFAULT 0,
                    voice_minutes INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id, date)
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
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_afk_users_guild
                ON afk_users(guild_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_action_stats_guild
                ON action_stats(guild_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_server_daily_stats_guild_date
                ON server_daily_stats(guild_id, date)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_birthdays_date
                ON birthdays(guild_id, birth_month, birth_day)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_xp_snapshots_date
                ON xp_snapshots(guild_id, date)
            """)

            # =====================================================================
            # Member Events Table (join/leave tracking for growth charts)
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS member_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_member_events_guild_time
                ON member_events(guild_id, timestamp DESC)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_member_events_type
                ON member_events(guild_id, event_type, timestamp)
            """)

            # =====================================================================
            # User Channel Activity Table (per-user-per-channel message counts)
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_channel_activity (
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    channel_name TEXT,
                    message_count INTEGER DEFAULT 0,
                    last_message_at INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, channel_id)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_channel_activity_user
                ON user_channel_activity(user_id, guild_id, message_count DESC)
            """)

            # =====================================================================
            # Channel Daily Stats Table (for per-channel trends)
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS channel_daily_stats (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, channel_id, date)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_daily_stats_date
                ON channel_daily_stats(guild_id, date DESC)
            """)

            # =====================================================================
            # User Interactions Table (tracks social connections)
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_interactions (
                    user_id INTEGER NOT NULL,
                    target_user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    mentions INTEGER DEFAULT 0,
                    replies INTEGER DEFAULT 0,
                    voice_minutes_together INTEGER DEFAULT 0,
                    last_interaction INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, target_user_id, guild_id)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_interactions_user
                ON user_interactions(user_id, guild_id)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_interactions_target
                ON user_interactions(target_user_id, guild_id)
            """)

            # =====================================================================
            # Migrations Table
            # =====================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    name TEXT PRIMARY KEY,
                    applied_at INTEGER NOT NULL
                )
            """)

            # Run one-time migrations
            self._run_migrations(cur)

            logger.tree("Database Initialized", [
                ("Tables", "All created/verified"),
                ("Status", "Ready"),
            ], emoji="✅")

    def _run_migrations(self, cur) -> None:
        """Run one-time data migrations."""
        # Check which migrations have been applied
        cur.execute("SELECT name FROM migrations")
        applied = {row[0] for row in cur.fetchall()}

        # Migration: Adjust XP to match levels for new formula (Jan 2026)
        if "xp_formula_v2_adjustment" not in applied:
            self._migrate_xp_formula_v2(cur)
            cur.execute(
                "INSERT INTO migrations (name, applied_at) VALUES (?, ?)",
                ("xp_formula_v2_adjustment", int(time.time()))
            )

    def _migrate_xp_formula_v2(self, cur) -> None:
        """
        Migrate XP values to match current levels under the new formula.

        The XP formula changed from:
            Old: 100 * level^1.5 (linear-ish growth)
            New: Levels 1-5: 100 * level^1.5
                 Levels 6+: 1118 + 100 * (level-5)^2 (quadratic growth)

        This migration preserves everyone's current level by setting their XP
        to the exact amount required for that level in the new formula.
        """
        # Inline formula to avoid circular import during DB init
        def xp_for_level(level: int) -> int:
            if level <= 0:
                return 0
            if level <= 5:
                return int(100 * (level ** 1.5))
            xp_at_5 = int(100 * (5 ** 1.5))  # 1118
            return xp_at_5 + int(100 * ((level - 5) ** 2))

        logger.tree("XP Formula Migration Starting", [
            ("Migration", "xp_formula_v2_adjustment"),
            ("Action", "Adjusting XP to match levels in new formula"),
        ], emoji="🔄")

        # Get all users with their current levels
        cur.execute("SELECT user_id, guild_id, level, xp FROM user_xp WHERE level > 0")
        users = cur.fetchall()

        if not users:
            logger.tree("XP Formula Migration", [
                ("Status", "No users to migrate"),
            ], emoji="ℹ️")
            return

        migrated = 0
        total_xp_before = 0
        total_xp_after = 0

        for row in users:
            user_id = row[0]
            guild_id = row[1]
            current_level = row[2]
            old_xp = row[3]

            # Calculate the XP needed for their current level in new formula
            new_xp = xp_for_level(current_level)

            total_xp_before += old_xp
            total_xp_after += new_xp

            # Update XP to match level in new formula
            cur.execute(
                "UPDATE user_xp SET xp = ? WHERE user_id = ? AND guild_id = ?",
                (new_xp, user_id, guild_id)
            )
            migrated += 1

        logger.tree("XP Formula Migration Complete", [
            ("Users Migrated", str(migrated)),
            ("Total XP Before", f"{total_xp_before:,}"),
            ("Total XP After", f"{total_xp_after:,}"),
            ("Note", "All levels preserved, XP adjusted to new formula"),
        ], emoji="✅")
