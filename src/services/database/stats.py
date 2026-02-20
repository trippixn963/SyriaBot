"""
SyriaBot - Database Stats Mixin
===============================

Server-level statistics database operations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from typing import List, Dict, Any

from src.core.logger import logger


class StatsMixin:
    """
    Mixin for server statistics database operations.

    DESIGN:
        Tracks server-level metrics: daily stats, hourly activity patterns,
        channel usage, boost history. Uses server_counters table for O(1)
        message count lookups instead of aggregating user_xp.
    """

    # =========================================================================
    # Daily Stats
    # =========================================================================

    def record_daily_activity(self, guild_id: int, user_id: int, date: str) -> None:
        """Record a user's activity for the day (for DAU tracking)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, unique_users, total_messages)
                VALUES (?, ?, 1, 1)
                ON CONFLICT(date) DO UPDATE SET
                    total_messages = total_messages + 1
            """, (date, guild_id))

    def increment_daily_unique_user(self, guild_id: int, date: str) -> None:
        """Increment unique user count for the day."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, unique_users, total_messages)
                VALUES (?, ?, 1, 0)
                ON CONFLICT(date) DO UPDATE SET
                    unique_users = unique_users + 1
            """, (date, guild_id))

    def increment_daily_messages(self, guild_id: int, date: str) -> None:
        """Increment total messages for the day."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, total_messages)
                VALUES (?, ?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    total_messages = total_messages + 1
            """, (date, guild_id))

    def update_voice_peak(self, guild_id: int, date: str, current_users: int) -> None:
        """Update voice peak if current is higher."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, voice_peak_users)
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    voice_peak_users = MAX(voice_peak_users, ?)
            """, (date, guild_id, current_users, current_users))

    def increment_new_members(self, guild_id: int, date: str) -> None:
        """Increment new members count for the day."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_daily_stats (date, guild_id, new_members)
                VALUES (?, ?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    new_members = new_members + 1
            """, (date, guild_id))

    def get_daily_stats(self, guild_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily stats for the last N days."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM server_daily_stats
                WHERE guild_id = ?
                ORDER BY date DESC
                LIMIT ?
            """, (guild_id, days))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Channel Activity
    # =========================================================================

    def increment_channel_messages(self, channel_id: int, guild_id: int, channel_name: str) -> None:
        """Increment message count for a channel."""
        now = int(time.time())
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO channel_stats (channel_id, guild_id, channel_name, total_messages, last_message_at)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    total_messages = total_messages + 1,
                    last_message_at = ?,
                    channel_name = ?
            """, (channel_id, guild_id, channel_name, now, now, channel_name))

    def get_channel_stats(self, guild_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get channel activity stats sorted by message count."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM channel_stats
                WHERE guild_id = ?
                ORDER BY total_messages DESC
                LIMIT ?
            """, (guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    def get_inactive_channels(self, guild_id: int, days_inactive: int = 7) -> List[Dict[str, Any]]:
        """Get channels with no activity in the last N days."""
        cutoff = int(time.time()) - (days_inactive * 86400)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM channel_stats
                WHERE guild_id = ? AND last_message_at < ?
                ORDER BY last_message_at ASC
            """, (guild_id, cutoff))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # User Channel Activity (per-user-per-channel tracking)
    # =========================================================================

    def increment_user_channel_messages(
        self,
        user_id: int,
        channel_id: int,
        guild_id: int,
        channel_name: str
    ) -> None:
        """Increment message count for a user in a specific channel."""
        now = int(time.time())
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_channel_activity
                    (user_id, channel_id, guild_id, channel_name, message_count, last_message_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(user_id, channel_id) DO UPDATE SET
                    message_count = message_count + 1,
                    last_message_at = ?,
                    channel_name = ?
            """, (user_id, channel_id, guild_id, channel_name, now, now, channel_name))

    def get_user_channel_activity(
        self,
        user_id: int,
        guild_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top channels for a user sorted by message count.
        
        Excludes private channels like appeals, tickets, and mod channels.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT channel_id, channel_name, message_count, last_message_at
                FROM user_channel_activity
                WHERE user_id = ? AND guild_id = ?
                  AND channel_name NOT LIKE '%appeal%'
                  AND channel_name NOT LIKE '%ticket%'
                  AND channel_name NOT LIKE 't___-%'
                  AND channel_name NOT LIKE '%-closed'
                ORDER BY message_count DESC
                LIMIT ?
            """, (user_id, guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Server Hourly Activity
    # =========================================================================

    def increment_server_hour_activity(self, guild_id: int, hour: int, activity_type: str = "message") -> None:
        """Increment hourly activity counter."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            if activity_type == "message":
                cur.execute("""
                    INSERT INTO server_hourly_activity (guild_id, hour, message_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(guild_id, hour) DO UPDATE SET
                        message_count = message_count + 1
                """, (guild_id, hour))
            else:  # voice
                cur.execute("""
                    INSERT INTO server_hourly_activity (guild_id, hour, voice_joins)
                    VALUES (?, ?, 1)
                    ON CONFLICT(guild_id, hour) DO UPDATE SET
                        voice_joins = voice_joins + 1
                """, (guild_id, hour))

    def get_server_peak_hours(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get hourly activity breakdown sorted by message count."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM server_hourly_activity
                WHERE guild_id = ?
                ORDER BY message_count DESC
            """, (guild_id,))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Boost History
    # =========================================================================

    def record_boost(self, user_id: int, guild_id: int, action: str) -> None:
        """Record a boost/unboost event."""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO boost_history (user_id, guild_id, action, timestamp)
                    VALUES (?, ?, ?, ?)
                """, (user_id, guild_id, action, int(time.time())))
            logger.tree("DB: Boost Recorded", [
                ("ID", str(user_id)),
                ("Action", action),
            ], emoji="💎" if action == "boost" else "💔")
        except Exception as e:
            logger.tree("DB: Record Boost Error", [
                ("ID", str(user_id)),
                ("Action", action),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def get_boost_history(self, guild_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get boost history for a guild."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM boost_history
                WHERE guild_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    def get_user_boost_count(self, user_id: int, guild_id: int) -> int:
        """Get how many times a user has boosted."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as count FROM boost_history
                WHERE user_id = ? AND guild_id = ? AND action = 'boost'
            """, (user_id, guild_id))
            row = cur.fetchone()
            return row["count"] if row else 0

    # =========================================================================
    # Member Retention
    # =========================================================================

    def get_retention_stats(self, guild_id: int, days_ago: int = 7) -> Dict[str, Any]:
        """
        Get retention stats for members who joined N days ago.

        Returns dict with:
        - joined_count: How many joined N days ago
        - still_active: How many have been active in last 3 days
        - retention_rate: Percentage still active
        """
        now = int(time.time())

        join_start = now - ((days_ago + 1) * 86400)
        join_end = now - (days_ago * 86400)
        active_cutoff = now - (3 * 86400)

        with self._get_conn() as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT COUNT(*) as count FROM user_xp
                WHERE guild_id = ? AND first_message_at BETWEEN ? AND ?
            """, (guild_id, join_start, join_end))
            joined = cur.fetchone()["count"]

            cur.execute("""
                SELECT COUNT(*) as count FROM user_xp
                WHERE guild_id = ?
                    AND first_message_at BETWEEN ? AND ?
                    AND last_active_at > ?
            """, (guild_id, join_start, join_end, active_cutoff))
            active = cur.fetchone()["count"]

            retention = (active / joined * 100) if joined > 0 else 0

            return {
                "days_ago": days_ago,
                "joined_count": joined,
                "still_active": active,
                "retention_rate": round(retention, 1),
            }

    # =========================================================================
    # Server Counters (O(1) atomic operations)
    # =========================================================================

    def increment_server_counter(self, guild_id: int, counter_name: str, amount: int = 1) -> int:
        """
        Atomically increment a server counter and return new value.

        This is O(1) - no scanning or aggregation needed.
        Used for fast real-time counters like total messages.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_counters (guild_id, counter_name, value)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, counter_name) DO UPDATE SET
                    value = value + ?
                RETURNING value
            """, (guild_id, counter_name, amount, amount))
            row = cur.fetchone()
            return row[0] if row else amount

    def get_server_counter(self, guild_id: int, counter_name: str) -> int:
        """Get a server counter value."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT value FROM server_counters
                WHERE guild_id = ? AND counter_name = ?
            """, (guild_id, counter_name))
            row = cur.fetchone()
            return row[0] if row else 0

    def set_server_counter(self, guild_id: int, counter_name: str, value: int) -> None:
        """Set a server counter to a specific value."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO server_counters (guild_id, counter_name, value)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, counter_name) DO UPDATE SET
                    value = ?
            """, (guild_id, counter_name, value, value))

    def init_message_counter_from_sum(self, guild_id: int) -> int:
        """
        Initialize the message counter from the sum of all user messages.

        Called on startup. If counter exists and is close to user sum, returns it.
        If counter is way off (migration not done), recalculates from user sum.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()

            # Calculate sum from all users (ground truth)
            cur.execute("""
                SELECT COALESCE(SUM(total_messages), 0) as total
                FROM user_xp WHERE guild_id = ?
            """, (guild_id,))
            user_sum = cur.fetchone()[0]

            # Check if counter exists
            cur.execute("""
                SELECT value FROM server_counters
                WHERE guild_id = ? AND counter_name = 'total_messages'
            """, (guild_id,))
            existing = cur.fetchone()

            if existing:
                counter_value = existing[0]
                # Counter should be >= user_sum (might be slightly higher due to timing)
                # If counter is way lower, it wasn't properly initialized
                if counter_value >= user_sum - 100:  # Allow small margin
                    return counter_value

            # Initialize or fix the counter
            cur.execute("""
                INSERT INTO server_counters (guild_id, counter_name, value)
                VALUES (?, 'total_messages', ?)
                ON CONFLICT(guild_id, counter_name) DO UPDATE SET
                    value = ?
            """, (guild_id, user_sum, user_sum))

            logger.tree("Message Counter Initialized", [
                ("Guild", str(guild_id)),
                ("Total", f"{user_sum:,}"),
            ], emoji="📊")

            return user_sum


    # =========================================================================
    # Extended Stats Methods (StatBot-like functionality)
    # =========================================================================

    def get_daily_stats_range(
        self,
        guild_id: int,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """Get daily stats for a date range (YYYY-MM-DD format)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM server_daily_stats
                WHERE guild_id = ? AND date >= ? AND date <= ?
                ORDER BY date ASC
            """, (guild_id, start_date, end_date))
            return [dict(row) for row in cur.fetchall()]

    def get_all_daily_stats(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get all daily stats for a guild (no limit)."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM server_daily_stats
                WHERE guild_id = ?
                ORDER BY date ASC
            """, (guild_id,))
            return [dict(row) for row in cur.fetchall()]

    def get_monthly_stats(self, guild_id: int) -> List[Dict[str, Any]]:
        """
        Get monthly aggregated stats.
        Returns list of months with aggregated data.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    strftime('%Y-%m', date) as month,
                    SUM(total_messages) as total_messages,
                    SUM(new_members) as new_members,
                    AVG(unique_users) as avg_daily_active,
                    MAX(voice_peak_users) as max_voice_peak,
                    COUNT(*) as days_recorded
                FROM server_daily_stats
                WHERE guild_id = ?
                GROUP BY strftime('%Y-%m', date)
                ORDER BY month DESC
            """, (guild_id,))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Member Events (join/leave tracking)
    # =========================================================================

    def record_member_event(self, guild_id: int, user_id: int, event_type: str) -> None:
        """Record a member join or leave event."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO member_events (guild_id, user_id, event_type, timestamp)
                VALUES (?, ?, ?, ?)
            """, (guild_id, user_id, event_type, int(time.time())))

    def get_member_events(
        self,
        guild_id: int,
        start_timestamp: int = None,
        end_timestamp: int = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get member events within a time range."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            if start_timestamp and end_timestamp:
                cur.execute("""
                    SELECT * FROM member_events
                    WHERE guild_id = ? AND timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (guild_id, start_timestamp, end_timestamp, limit))
            elif start_timestamp:
                cur.execute("""
                    SELECT * FROM member_events
                    WHERE guild_id = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (guild_id, start_timestamp, limit))
            else:
                cur.execute("""
                    SELECT * FROM member_events
                    WHERE guild_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    def get_member_growth_daily(self, guild_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily member growth (joins - leaves) for the last N days.
        Returns list with date, joins, leaves, and net change.
        """
        cutoff = int(time.time()) - (days * 86400)
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    date(timestamp, 'unixepoch') as date,
                    SUM(CASE WHEN event_type = 'join' THEN 1 ELSE 0 END) as joins,
                    SUM(CASE WHEN event_type = 'leave' THEN 1 ELSE 0 END) as leaves,
                    SUM(CASE WHEN event_type = 'join' THEN 1 ELSE -1 END) as net_change
                FROM member_events
                WHERE guild_id = ? AND timestamp >= ?
                GROUP BY date(timestamp, 'unixepoch')
                ORDER BY date ASC
            """, (guild_id, cutoff))
            return [dict(row) for row in cur.fetchall()]

    def get_member_growth_monthly(self, guild_id: int) -> List[Dict[str, Any]]:
        """
        Get monthly member growth aggregates.
        Returns list with month, joins, leaves, and net change.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    strftime('%Y-%m', timestamp, 'unixepoch') as month,
                    SUM(CASE WHEN event_type = 'join' THEN 1 ELSE 0 END) as joins,
                    SUM(CASE WHEN event_type = 'leave' THEN 1 ELSE 0 END) as leaves,
                    SUM(CASE WHEN event_type = 'join' THEN 1 ELSE -1 END) as net_change
                FROM member_events
                WHERE guild_id = ?
                GROUP BY strftime('%Y-%m', timestamp, 'unixepoch')
                ORDER BY month DESC
            """, (guild_id,))
            return [dict(row) for row in cur.fetchall()]


    # =========================================================================
    # Retention & Health Score Methods
    # =========================================================================

    def get_retention_stats(self, guild_id: int, days: int = 30) -> Dict[str, Any]:
        """
        Calculate retention rate for members who joined in the last N days.
        A member is "retained" if they have sent at least 1 message.
        """
        cutoff = int(time.time()) - (days * 86400)
        with self._get_conn() as conn:
            cur = conn.cursor()
            
            # Get members who joined in the period
            cur.execute("""
                SELECT COUNT(DISTINCT user_id) as new_members
                FROM member_events
                WHERE guild_id = ? AND event_type = 'join' AND timestamp >= ?
            """, (guild_id, cutoff))
            new_members = cur.fetchone()[0] or 0
            
            # Get members who joined AND have messages
            cur.execute("""
                SELECT COUNT(DISTINCT me.user_id) as active_new
                FROM member_events me
                INNER JOIN user_xp ux ON me.user_id = ux.user_id AND me.guild_id = ux.guild_id
                WHERE me.guild_id = ? 
                  AND me.event_type = 'join' 
                  AND me.timestamp >= ?
                  AND ux.total_messages > 0
            """, (guild_id, cutoff))
            active_new = cur.fetchone()[0] or 0
            
            # Get members who left
            cur.execute("""
                SELECT COUNT(DISTINCT user_id) as left_members
                FROM member_events
                WHERE guild_id = ? AND event_type = 'leave' AND timestamp >= ?
            """, (guild_id, cutoff))
            left_members = cur.fetchone()[0] or 0
            
            retention_rate = (active_new / new_members * 100) if new_members > 0 else 0
            churn_rate = (left_members / new_members * 100) if new_members > 0 else 0
            
            return {
                "period_days": days,
                "new_members": new_members,
                "active_new_members": active_new,
                "left_members": left_members,
                "retention_rate": round(retention_rate, 1),
                "churn_rate": round(churn_rate, 1),
            }

    def get_health_score_data(self, guild_id: int) -> Dict[str, Any]:
        """
        Get data needed to calculate server health score.
        Returns activity metrics for the last 7 days vs previous 7 days.
        """
        now = int(time.time())
        week_ago = now - (7 * 86400)
        two_weeks_ago = now - (14 * 86400)
        
        with self._get_conn() as conn:
            cur = conn.cursor()
            
            # This week stats
            cur.execute("""
                SELECT 
                    COALESCE(SUM(total_messages), 0) as messages,
                    COALESCE(AVG(unique_users), 0) as avg_dau,
                    COALESCE(MAX(voice_peak_users), 0) as voice_peak
                FROM server_daily_stats
                WHERE guild_id = ? AND date >= date(?, 'unixepoch')
            """, (guild_id, week_ago))
            this_week = cur.fetchone()
            
            # Last week stats
            cur.execute("""
                SELECT 
                    COALESCE(SUM(total_messages), 0) as messages,
                    COALESCE(AVG(unique_users), 0) as avg_dau,
                    COALESCE(MAX(voice_peak_users), 0) as voice_peak
                FROM server_daily_stats
                WHERE guild_id = ? 
                  AND date >= date(?, 'unixepoch') 
                  AND date < date(?, 'unixepoch')
            """, (guild_id, two_weeks_ago, week_ago))
            last_week = cur.fetchone()
            
            # Member growth this week
            cur.execute("""
                SELECT 
                    SUM(CASE WHEN event_type = 'join' THEN 1 ELSE 0 END) as joins,
                    SUM(CASE WHEN event_type = 'leave' THEN 1 ELSE 0 END) as leaves
                FROM member_events
                WHERE guild_id = ? AND timestamp >= ?
            """, (guild_id, week_ago))
            growth = cur.fetchone()
            
            return {
                "this_week": {
                    "messages": this_week[0] if this_week else 0,
                    "avg_dau": round(this_week[1], 1) if this_week else 0,
                    "voice_peak": this_week[2] if this_week else 0,
                },
                "last_week": {
                    "messages": last_week[0] if last_week else 0,
                    "avg_dau": round(last_week[1], 1) if last_week else 0,
                    "voice_peak": last_week[2] if last_week else 0,
                },
                "growth": {
                    "joins": growth[0] if growth else 0,
                    "leaves": growth[1] if growth else 0,
                }
            }

    def get_channel_daily_stats(self, guild_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get daily message counts per channel.
        Uses channel_daily_stats table for per-channel time series.
        """
        cutoff_date = time.strftime("%Y-%m-%d", time.localtime(time.time() - (days * 86400)))
        
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    cds.date,
                    cds.channel_id,
                    ca.channel_name,
                    cds.message_count
                FROM channel_daily_stats cds
                LEFT JOIN channel_stats ca ON cds.channel_id = ca.channel_id AND cds.guild_id = ca.guild_id
                WHERE cds.guild_id = ? AND cds.date >= ?
                ORDER BY cds.date ASC, cds.message_count DESC
            """, (guild_id, cutoff_date))
            return [dict(row) for row in cur.fetchall()]


    def increment_channel_daily(self, guild_id: int, channel_id: int, date: str) -> None:
        """Increment daily message count for a channel."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO channel_daily_stats (guild_id, channel_id, date, message_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(guild_id, channel_id, date) DO UPDATE SET
                    message_count = message_count + 1
            """, (guild_id, channel_id, date))

    # =========================================================================
    # Voice Channel Stats
    # =========================================================================

    def record_voice_channel_activity(
        self,
        channel_id: int,
        guild_id: int,
        channel_name: str,
        minutes: int,
        user_count: int
    ) -> None:
        """Record voice channel activity when user leaves."""
        now = int(time.time())
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO voice_channel_stats
                    (channel_id, guild_id, channel_name, total_minutes, peak_users, session_count, last_active_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(channel_id, guild_id) DO UPDATE SET
                    total_minutes = total_minutes + ?,
                    peak_users = MAX(peak_users, ?),
                    session_count = session_count + 1,
                    last_active_at = ?,
                    channel_name = ?
            """, (channel_id, guild_id, channel_name, minutes, user_count, now,
                  minutes, user_count, now, channel_name))

    def get_voice_channel_breakdown(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get voice channel usage breakdown sorted by total minutes."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    channel_id,
                    channel_name,
                    total_minutes,
                    peak_users,
                    session_count,
                    last_active_at
                FROM voice_channel_stats
                WHERE guild_id = ?
                ORDER BY total_minutes DESC
                LIMIT ?
            """, (guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Role Snapshots
    # =========================================================================

    def snapshot_role_distribution(self, guild_id: int, role_data: List[Dict[str, Any]]) -> None:
        """
        Save a daily snapshot of role distribution.

        Args:
            guild_id: Guild ID
            role_data: List of dicts with role_id, role_name, member_count
        """
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        with self._get_conn() as conn:
            cur = conn.cursor()
            for role in role_data:
                cur.execute("""
                    INSERT INTO role_snapshots (date, guild_id, role_id, role_name, member_count)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(date, guild_id, role_id) DO UPDATE SET
                        role_name = ?,
                        member_count = ?
                """, (today, guild_id, role["role_id"], role["role_name"], role["member_count"],
                      role["role_name"], role["member_count"]))

        logger.tree("Role Snapshot Saved", [
            ("Date", today),
            ("Roles", str(len(role_data))),
        ], emoji="📸")

    def get_role_distribution(self, guild_id: int, date: str = None) -> List[Dict[str, Any]]:
        """
        Get role distribution for a specific date.

        Args:
            guild_id: Guild ID
            date: Date string (YYYY-MM-DD). If None, uses latest snapshot.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()

            if date:
                cur.execute("""
                    SELECT role_id, role_name, member_count
                    FROM role_snapshots
                    WHERE guild_id = ? AND date = ?
                    ORDER BY member_count DESC
                """, (guild_id, date))
            else:
                # Get latest date first
                cur.execute("""
                    SELECT DISTINCT date FROM role_snapshots
                    WHERE guild_id = ?
                    ORDER BY date DESC
                    LIMIT 1
                """, (guild_id,))
                row = cur.fetchone()
                if not row:
                    return []

                latest_date = row[0]
                cur.execute("""
                    SELECT role_id, role_name, member_count
                    FROM role_snapshots
                    WHERE guild_id = ? AND date = ?
                    ORDER BY member_count DESC
                """, (guild_id, latest_date))

            return [dict(row) for row in cur.fetchall()]

    def get_role_history(self, guild_id: int, role_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Get historical member counts for a specific role."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT date, member_count
                FROM role_snapshots
                WHERE guild_id = ? AND role_id = ?
                ORDER BY date DESC
                LIMIT ?
            """, (guild_id, role_id, days))
            return [dict(row) for row in cur.fetchall()]

    def cleanup_old_role_snapshots(self, days_to_keep: int = 90, guild_id: int = None) -> int:
        """Delete role snapshots older than specified days."""
        from src.core.config import config
        from datetime import datetime, timezone, timedelta

        gid = guild_id or config.GUILD_ID
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM role_snapshots
                WHERE guild_id = ? AND date < ?
            """, (gid, cutoff_date))

            deleted = cur.rowcount

        if deleted > 0:
            logger.tree("Role Snapshots Cleanup", [
                ("Deleted", str(deleted)),
                ("Cutoff", cutoff_date),
            ], emoji="🧹")

        return deleted

    # Alias for backwards compatibility
