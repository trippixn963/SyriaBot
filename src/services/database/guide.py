"""
SyriaBot - Database Guide Mixin
===============================

Guide panel message tracking.

Author: John Hamwi
Server: discord.gg/syria
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional, Dict, Any

from src.core.logger import log

if TYPE_CHECKING:
    pass


class GuideMixin:
    """Database mixin for guide panel operations."""

    def get_guide_panel(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the guide panel message info for a guild.

        Args:
            guild_id: The guild ID.

        Returns:
            Dict with channel_id, message_id, updated_at or None if not found.
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return None
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT channel_id, message_id, updated_at
                    FROM guide_panel
                    WHERE guild_id = ?
                    """,
                    (guild_id,)
                )
                row = cur.fetchone()
                if row:
                    result = {
                        "channel_id": row["channel_id"],
                        "message_id": row["message_id"],
                        "updated_at": row["updated_at"],
                    }
                    log.tree("Guide Panel Fetched", [
                        ("Guild", str(guild_id)),
                        ("Channel", str(result["channel_id"])),
                        ("Message", str(result["message_id"])),
                    ], emoji="📋")
                    return result
                return None
        except Exception as e:
            log.error_tree("Guide Panel Fetch Failed", e, [
                ("Guild", str(guild_id)),
            ])
            return None

    def set_guide_panel(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int
    ) -> bool:
        """
        Set or update the guide panel message info for a guild.

        Args:
            guild_id: The guild ID.
            channel_id: The channel ID where the panel is posted.
            message_id: The message ID of the panel.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return False
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO guide_panel (guild_id, channel_id, message_id, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        channel_id = excluded.channel_id,
                        message_id = excluded.message_id,
                        updated_at = excluded.updated_at
                    """,
                    (guild_id, channel_id, message_id, int(time.time()))
                )
                log.tree("Guide Panel Saved", [
                    ("Guild", str(guild_id)),
                    ("Channel", str(channel_id)),
                    ("Message", str(message_id)),
                ], emoji="💾")
                return True
        except Exception as e:
            log.error_tree("Guide Panel Save Failed", e, [
                ("Guild", str(guild_id)),
                ("Channel", str(channel_id)),
                ("Message", str(message_id)),
            ])
            return False

    def update_guide_panel_timestamp(self, guild_id: int) -> bool:
        """
        Update the updated_at timestamp for a guide panel.

        Args:
            guild_id: The guild ID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return False
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE guide_panel
                    SET updated_at = ?
                    WHERE guild_id = ?
                    """,
                    (int(time.time()), guild_id)
                )
                if cur.rowcount > 0:
                    log.tree("Guide Panel Timestamp Updated", [
                        ("Guild", str(guild_id)),
                    ], emoji="🕐")
                    return True
                return False
        except Exception as e:
            log.error_tree("Guide Panel Timestamp Update Failed", e, [
                ("Guild", str(guild_id)),
            ])
            return False

    def delete_guide_panel(self, guild_id: int) -> bool:
        """
        Delete the guide panel info for a guild.

        Args:
            guild_id: The guild ID.

        Returns:
            True if deleted, False otherwise.
        """
        try:
            with self._get_conn() as conn:
                if conn is None:
                    return False
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM guide_panel WHERE guild_id = ?",
                    (guild_id,)
                )
                if cur.rowcount > 0:
                    log.tree("Guide Panel Deleted", [
                        ("Guild", str(guild_id)),
                    ], emoji="🗑️")
                    return True
                return False
        except Exception as e:
            log.error_tree("Guide Panel Delete Failed", e, [
                ("Guild", str(guild_id)),
            ])
            return False
