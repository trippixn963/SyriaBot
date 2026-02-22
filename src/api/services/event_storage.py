"""
SyriaBot - Event Storage
========================

SQLite storage for Discord events with FTS5 search.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from src.core.logger import logger


# =============================================================================
# Constants
# =============================================================================

DEFAULT_RETENTION_DAYS = 30
EST = ZoneInfo("America/New_York")


# =============================================================================
# Event Types
# =============================================================================

class EventType:
    """Discord event type constants."""

    # Member events
    MEMBER_JOIN = "member.join"
    MEMBER_LEAVE = "member.leave"
    MEMBER_BAN = "member.ban"
    MEMBER_UNBAN = "member.unban"
    MEMBER_KICK = "member.kick"
    MEMBER_TIMEOUT = "member.timeout"
    MEMBER_TIMEOUT_REMOVE = "member.timeout_remove"
    MEMBER_ROLE_ADD = "member.role_add"
    MEMBER_ROLE_REMOVE = "member.role_remove"
    MEMBER_NICK_CHANGE = "member.nick_change"
    MEMBER_WARN = "member.warn"
    MEMBER_BOOST = "member.boost"
    MEMBER_UNBOOST = "member.unboost"
    MEMBER_AVATAR_CHANGE = "member.avatar_change"

    # Message events
    MESSAGE_DELETE = "message.delete"
    MESSAGE_BULK_DELETE = "message.bulk_delete"
    MESSAGE_EDIT = "message.edit"

    # Voice events
    VOICE_JOIN = "voice.join"
    VOICE_LEAVE = "voice.leave"
    VOICE_SWITCH = "voice.switch"
    VOICE_DISCONNECT = "voice.disconnect"
    VOICE_MUTE = "voice.mute"
    VOICE_UNMUTE = "voice.unmute"
    VOICE_DEAFEN = "voice.deafen"
    VOICE_UNDEAFEN = "voice.undeafen"
    VOICE_STREAM_START = "voice.stream_start"
    VOICE_STREAM_END = "voice.stream_end"

    # Channel events
    CHANNEL_CREATE = "channel.create"
    CHANNEL_DELETE = "channel.delete"
    CHANNEL_UPDATE = "channel.update"

    # Role events
    ROLE_CREATE = "role.create"
    ROLE_DELETE = "role.delete"
    ROLE_UPDATE = "role.update"

    # Server events
    SERVER_BUMP = "server.bump"
    SERVER_UPDATE = "server.update"

    # Thread events
    THREAD_CREATE = "thread.create"
    THREAD_DELETE = "thread.delete"

    # Invite events
    INVITE_CREATE = "invite.create"
    INVITE_DELETE = "invite.delete"

    # Emoji events
    EMOJI_CREATE = "emoji.create"
    EMOJI_DELETE = "emoji.delete"

    # XP events
    XP_LEVEL_UP = "xp.level_up"
    XP_ROLE_REWARD = "xp.role_reward"

    # Moderation events
    MOD_CASE_CREATE = "mod.case_create"
    MOD_WARN = "mod.warn"

    # Bot events
    BOT_ADD = "bot.add"
    BOT_REMOVE = "bot.remove"

    @classmethod
    def get_category(cls, event_type: str) -> str:
        """Get category from event type."""
        if event_type.startswith("member."):
            return "member"
        if event_type.startswith("message."):
            return "message"
        if event_type.startswith("voice."):
            return "voice"
        if event_type.startswith("channel."):
            return "channel"
        if event_type.startswith("server."):
            return "server"
        if event_type.startswith("thread."):
            return "thread"
        if event_type.startswith("xp."):
            return "xp"
        if event_type.startswith("invite."):
            return "invite"
        if event_type.startswith("bot."):
            return "bot"
        if event_type.startswith("role."):
            return "role"
        if event_type.startswith("emoji."):
            return "emoji"
        if event_type.startswith("mod."):
            return "mod"
        return "other"


# =============================================================================
# Data Model
# =============================================================================

@dataclass
class StoredEvent:
    """Stored event data model."""

    id: int
    timestamp: datetime
    event_type: str
    guild_id: int
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    actor_avatar: Optional[str] = None
    target_id: Optional[int] = None
    target_name: Optional[str] = None
    target_avatar: Optional[str] = None
    channel_id: Optional[int] = None
    channel_name: Optional[str] = None
    reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API response dict."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "guild_id": str(self.guild_id),
            "actor": {
                "id": str(self.actor_id) if self.actor_id else None,
                "name": self.actor_name,
                "avatar": self.actor_avatar,
            } if self.actor_id or self.actor_name else None,
            "target": {
                "id": str(self.target_id) if self.target_id else None,
                "name": self.target_name,
                "avatar": self.target_avatar,
            } if self.target_id or self.target_name else None,
            "channel": {
                "id": str(self.channel_id) if self.channel_id else None,
                "name": self.channel_name,
            } if self.channel_id or self.channel_name else None,
            "reason": self.reason,
            "details": self.details,
        }


# =============================================================================
# Event Storage
# =============================================================================

class EventStorage:
    """SQLite storage for Discord events."""

    def __init__(self, db_path: str = "data/events.db"):
        """Initialize storage with database path."""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._on_event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # Main events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    guild_id INTEGER NOT NULL,
                    actor_id INTEGER,
                    actor_name TEXT,
                    actor_avatar TEXT,
                    target_id INTEGER,
                    target_name TEXT,
                    target_avatar TEXT,
                    channel_id INTEGER,
                    channel_name TEXT,
                    reason TEXT,
                    details TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_guild ON events(guild_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_target ON events(target_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_channel ON events(channel_id)")

            # FTS5 for search
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                    actor_name,
                    target_name,
                    channel_name,
                    reason,
                    details,
                    content='events',
                    content_rowid='id'
                )
            """)

            # Triggers for FTS sync
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
                    INSERT INTO events_fts(rowid, actor_name, target_name, channel_name, reason, details)
                    VALUES (new.id, new.actor_name, new.target_name, new.channel_name, new.reason, new.details);
                END
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
                    INSERT INTO events_fts(events_fts, rowid, actor_name, target_name, channel_name, reason, details)
                    VALUES ('delete', old.id, old.actor_name, old.target_name, old.channel_name, old.reason, old.details);
                END
            """)

            conn.commit()
            conn.close()

    def set_on_event(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback for new events (for WebSocket broadcast)."""
        self._on_event_callback = callback

    def add(
        self,
        event_type: str,
        guild_id: int,
        actor_id: Optional[int] = None,
        actor_name: Optional[str] = None,
        actor_avatar: Optional[str] = None,
        target_id: Optional[int] = None,
        target_name: Optional[str] = None,
        target_avatar: Optional[str] = None,
        channel_id: Optional[int] = None,
        channel_name: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add an event to storage."""
        timestamp = datetime.now(EST)
        details_json = json.dumps(details or {})

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO events (
                    timestamp, event_type, guild_id,
                    actor_id, actor_name, actor_avatar,
                    target_id, target_name, target_avatar,
                    channel_id, channel_name,
                    reason, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp.isoformat(),
                event_type,
                guild_id,
                actor_id,
                actor_name,
                actor_avatar,
                target_id,
                target_name,
                target_avatar,
                channel_id,
                channel_name,
                reason,
                details_json,
            ))

            event_id = cursor.lastrowid
            conn.commit()
            conn.close()

        # Trigger callback for WebSocket broadcast
        if self._on_event_callback and event_id:
            event = StoredEvent(
                id=event_id,
                timestamp=timestamp,
                event_type=event_type,
                guild_id=guild_id,
                actor_id=actor_id,
                actor_name=actor_name,
                actor_avatar=actor_avatar,
                target_id=target_id,
                target_name=target_name,
                target_avatar=target_avatar,
                channel_id=channel_id,
                channel_name=channel_name,
                reason=reason,
                details=details or {},
            )
            try:
                self._on_event_callback(event.to_dict())
            except Exception:
                pass

        return event_id or 0

    def get_events(
        self,
        guild_id: int,
        limit: int = 50,
        offset: int = 0,
        event_type: Optional[str] = None,
        category: Optional[str] = None,
        actor_id: Optional[int] = None,
        target_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        search: Optional[str] = None,
        hours: Optional[int] = None,
    ) -> Tuple[List[StoredEvent], int]:
        """Get events with filtering."""
        conditions = ["guild_id = ?"]
        params: List[Any] = [guild_id]

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        if category:
            conditions.append("event_type LIKE ?")
            params.append(f"{category}.%")

        if actor_id:
            conditions.append("actor_id = ?")
            params.append(actor_id)

        if target_id:
            conditions.append("target_id = ?")
            params.append(target_id)

        if channel_id:
            conditions.append("channel_id = ?")
            params.append(channel_id)

        if hours:
            cutoff = datetime.now(EST) - timedelta(hours=hours)
            conditions.append("timestamp >= ?")
            params.append(cutoff.isoformat())

        where_clause = " AND ".join(conditions)

        # Handle FTS search
        if search:
            where_clause += " AND id IN (SELECT rowid FROM events_fts WHERE events_fts MATCH ?)"
            params.append(f'"{search}"*')

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM events WHERE {where_clause}", params)
            total = cursor.fetchone()[0]

            # Get events
            cursor.execute(f"""
                SELECT * FROM events
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset])

            events = []
            for row in cursor.fetchall():
                events.append(StoredEvent(
                    id=row["id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    event_type=row["event_type"],
                    guild_id=row["guild_id"],
                    actor_id=row["actor_id"],
                    actor_name=row["actor_name"],
                    actor_avatar=row["actor_avatar"],
                    target_id=row["target_id"],
                    target_name=row["target_name"],
                    target_avatar=row["target_avatar"],
                    channel_id=row["channel_id"],
                    channel_name=row["channel_name"],
                    reason=row["reason"],
                    details=json.loads(row["details"] or "{}"),
                ))

            conn.close()

        return events, total

    def get_stats(self, guild_id: int) -> Dict[str, Any]:
        """Get event statistics."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            # Total count
            cursor.execute("SELECT COUNT(*) FROM events WHERE guild_id = ?", (guild_id,))
            total = cursor.fetchone()[0]

            # By type
            cursor.execute("""
                SELECT event_type, COUNT(*) as count
                FROM events WHERE guild_id = ?
                GROUP BY event_type
            """, (guild_id,))
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

            # By category
            by_category: Dict[str, int] = {}
            for event_type, count in by_type.items():
                category = EventType.get_category(event_type)
                by_category[category] = by_category.get(category, 0) + count

            # By hour (last 24h)
            cutoff = datetime.now(EST) - timedelta(hours=24)
            cursor.execute("""
                SELECT strftime('%H', timestamp) as hour, COUNT(*) as count
                FROM events
                WHERE guild_id = ? AND timestamp >= ?
                GROUP BY hour
            """, (guild_id, cutoff.isoformat()))
            by_hour = {row[0]: row[1] for row in cursor.fetchall()}

            # Top actors (moderators)
            cursor.execute("""
                SELECT actor_id, actor_name, actor_avatar, COUNT(*) as count
                FROM events
                WHERE guild_id = ? AND actor_id IS NOT NULL
                GROUP BY actor_id
                ORDER BY count DESC
                LIMIT 10
            """, (guild_id,))
            top_actors = [
                {
                    "id": str(row[0]),
                    "name": row[1],
                    "avatar": row[2],
                    "count": row[3],
                }
                for row in cursor.fetchall()
            ]

            conn.close()

        return {
            "total": total,
            "by_type": by_type,
            "by_category": by_category,
            "by_hour": by_hour,
            "top_actors": top_actors,
            "retention_days": DEFAULT_RETENTION_DAYS,
        }

    def cleanup_old_events(self, days: int = DEFAULT_RETENTION_DAYS) -> int:
        """Delete events older than retention period."""
        cutoff = datetime.now(EST) - timedelta(days=days)

        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM events WHERE timestamp < ?",
                (cutoff.isoformat(),)
            )
            deleted = cursor.rowcount

            conn.commit()
            conn.close()

        if deleted > 0:
            logger.tree("Events Cleanup", [
                ("Deleted", str(deleted)),
                ("Retention", f"{days} days"),
            ], emoji="🗑️")

        return deleted


# =============================================================================
# Singleton
# =============================================================================

_event_storage: Optional[EventStorage] = None


def get_event_storage() -> EventStorage:
    """Get the event storage singleton."""
    global _event_storage
    if _event_storage is None:
        _event_storage = EventStorage()
    return _event_storage


__all__ = [
    "EventType",
    "StoredEvent",
    "EventStorage",
    "get_event_storage",
]
