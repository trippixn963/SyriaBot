"""
SyriaBot - Actions Panel Database Mixin
=======================================

Database operations for actions panel persistence.
Supports multiple channels with hash-based change detection.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Dict, Any, Optional

from src.core.logger import logger


class ActionsPanelMixin:
    """Database mixin for actions panel operations."""

    def get_all_actions_panel_data(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all actions panel data.

        Returns:
            Dict of channel_id -> {message_id, actions_hash}.
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT channel_id, message_id, actions_hash FROM actions_panel")
                rows = cur.fetchall()
                result = {
                    row[0]: {"message_id": row[1], "actions_hash": row[2]}
                    for row in rows
                }
                logger.tree("Actions Panel DB Loaded", [
                    ("Panels", str(len(result))),
                ], emoji="💾")
                return result
        except Exception as e:
            logger.error_tree("Actions Panel DB Get All Failed", e)
            return {}

    def get_actions_panel_data(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """
        Get actions panel data for a specific channel.

        Args:
            channel_id: The channel ID.

        Returns:
            Dict with message_id and actions_hash, or None if not found.
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT message_id, actions_hash FROM actions_panel WHERE channel_id = ?",
                    (channel_id,)
                )
                row = cur.fetchone()
                if row:
                    return {"message_id": row[0], "actions_hash": row[1]}
                return None
        except Exception as e:
            logger.error_tree("Actions Panel DB Get Failed", e, [
                ("Channel ID", str(channel_id)),
            ])
            return None

    def set_actions_panel_data(self, channel_id: int, message_id: int, actions_hash: str) -> bool:
        """
        Set the actions panel data for a channel.

        Args:
            channel_id: The channel ID.
            message_id: The message ID to store.
            actions_hash: Hash of the actions list for change detection.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO actions_panel (channel_id, message_id, actions_hash)
                    VALUES (?, ?, ?)
                    ON CONFLICT(channel_id) DO UPDATE SET
                        message_id = excluded.message_id,
                        actions_hash = excluded.actions_hash
                    """,
                    (channel_id, message_id, actions_hash)
                )
                conn.commit()
                logger.tree("Actions Panel DB Saved", [
                    ("Channel ID", str(channel_id)),
                    ("Message ID", str(message_id)),
                    ("Hash", actions_hash),
                ], emoji="💾")
                return True
        except Exception as e:
            logger.error_tree("Actions Panel DB Set Failed", e, [
                ("Channel ID", str(channel_id)),
                ("Message ID", str(message_id)),
            ])
            return False

    def delete_actions_panel_data(self, channel_id: int) -> bool:
        """
        Delete the actions panel data for a channel.

        Args:
            channel_id: The channel ID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM actions_panel WHERE channel_id = ?",
                    (channel_id,)
                )
                conn.commit()
                logger.tree("Actions Panel DB Deleted", [
                    ("Channel ID", str(channel_id)),
                ], emoji="🗑️")
                return True
        except Exception as e:
            logger.error_tree("Actions Panel DB Delete Failed", e, [
                ("Channel ID", str(channel_id)),
            ])
            return False
