"""
SyriaBot - Actions Panel Service
================================

Manages persistent actions list panels in multiple channels.
Auto-sends on startup, auto-edits if actions change, auto-resends if deleted.
Includes rate limit protection against delete spam.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import hashlib
import time
from typing import Dict

import discord
from discord.ext import commands

from src.core.config import config
from src.core.colors import COLOR_GOLD
from src.core.logger import logger
from src.utils.footer import set_footer
from src.services.database import db
from .service import ACTIONS, SELF_ACTIONS


# Channels to post the actions panel in
PANEL_CHANNEL_IDS = [
    config.CMDS_CHANNEL_ID,      # Cmds channel
    config.GENERAL_CHANNEL_ID,   # General chat
]

# Rate limit: minimum seconds between resends per channel
RESEND_COOLDOWN = 60


class ActionsPanelService:
    """
    Service for managing persistent actions list panels.

    DESIGN:
        On startup, checks if panels exist in configured channels.
        If missing, sends and pins new ones.
        If actions changed, edits existing panels in place.
        Listens for message deletions and auto-resends if any panel is deleted.
        Rate limits resends to prevent abuse from repeated deletions.
        Stores panel message IDs and action hash in database for persistence.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # channel_id -> message_id mapping
        self._panel_message_ids: Dict[int, int] = {}
        # channel_id -> last resend timestamp (for rate limiting)
        self._last_resend: Dict[int, float] = {}
        self._enabled = False
        self._current_hash = self._compute_actions_hash()

    def _compute_actions_hash(self) -> str:
        """Compute a hash of current actions for change detection."""
        actions_str = ",".join(sorted(ACTIONS.keys())) + "|" + ",".join(sorted(SELF_ACTIONS.keys()))
        return hashlib.md5(actions_str.encode()).hexdigest()[:16]

    async def setup(self) -> None:
        """Initialize the actions panel service."""
        # Filter out unconfigured channels (0 or None)
        channel_ids = [cid for cid in PANEL_CHANNEL_IDS if cid]

        if not channel_ids:
            logger.tree("Actions Panel Disabled", [
                ("Reason", "No channels configured"),
            ], emoji="⚠️")
            return

        self._enabled = True

        # Load existing panel data from database
        stored_panels = db.get_all_actions_panel_data()

        for channel_id in channel_ids:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.tree("Actions Panel Channel Not Found", [
                    ("Channel ID", str(channel_id)),
                ], emoji="⚠️")
                continue

            # Check if we have stored data for this channel
            panel_data = stored_panels.get(channel_id)
            stored_msg_id = panel_data.get("message_id") if panel_data else None
            stored_hash = panel_data.get("actions_hash") if panel_data else None

            if stored_msg_id:
                try:
                    message = await channel.fetch_message(stored_msg_id)
                    self._panel_message_ids[channel_id] = stored_msg_id

                    # Check if actions changed - edit in place
                    if stored_hash != self._current_hash:
                        logger.tree("Actions Panel Outdated", [
                            ("Channel", channel.name),
                            ("Old Hash", stored_hash or "None"),
                            ("New Hash", self._current_hash),
                            ("Action", "Editing in place"),
                        ], emoji="📝")
                        await self._edit_panel(channel, message)
                    else:
                        logger.tree("Actions Panel Found", [
                            ("Channel", channel.name),
                            ("Message ID", str(stored_msg_id)),
                            ("Hash", self._current_hash),
                        ], emoji="📋")

                except discord.NotFound:
                    logger.tree("Actions Panel Missing", [
                        ("Channel", channel.name),
                        ("Old ID", str(stored_msg_id)),
                        ("Action", "Will resend"),
                    ], emoji="⚠️")
                    await self._send_panel(channel)
                except discord.HTTPException as e:
                    logger.tree("Actions Panel Fetch Failed", [
                        ("Channel", channel.name),
                        ("Message ID", str(stored_msg_id)),
                        ("Error", str(e)[:50]),
                    ], emoji="❌")
            else:
                # No stored panel, send new one
                await self._send_panel(channel)

        logger.tree("Actions Panel Service Ready", [
            ("Channels", str(len(self._panel_message_ids))),
            ("Actions Hash", self._current_hash),
        ], emoji="📋")

    def _build_embed(self) -> discord.Embed:
        """Build the actions list embed."""
        # Get all actions sorted
        target_actions = sorted(ACTIONS.keys())
        self_actions = sorted(SELF_ACTIONS.keys())

        embed = discord.Embed(
            title="Action Commands",
            description=(
                "Use these commands to express yourself with anime GIFs!\n\n"
                "**Usage:** Type the action name, optionally mention someone\n"
                "**Example:** `hug @user` or just `hug` (hugs yourself)"
            ),
            color=COLOR_GOLD
        )

        # Target actions
        target_formatted = "  ".join(f"`{a}`" for a in target_actions)
        embed.add_field(
            name=f"Target Actions ({len(target_actions)})",
            value=target_formatted,
            inline=False
        )

        # Self actions
        self_formatted = "  ".join(f"`{a}`" for a in self_actions)
        embed.add_field(
            name=f"Self Actions ({len(self_actions)})",
            value=self_formatted,
            inline=False
        )

        # Tips
        embed.add_field(
            name="Tips",
            value=(
                "**Combo:** Mention multiple users to action each one\n"
                "**Cooldown:** 60 seconds between actions\n"
                "**Self-target:** Use target actions alone to target yourself"
            ),
            inline=False
        )

        set_footer(embed)
        return embed

    async def _edit_panel(self, channel: discord.TextChannel, message: discord.Message) -> bool:
        """
        Edit an existing panel with updated content.

        Args:
            channel: The channel containing the panel.
            message: The panel message to edit.

        Returns:
            True if successful, False otherwise.
        """
        try:
            embed = self._build_embed()
            await message.edit(embed=embed)

            # Update hash in database
            db.set_actions_panel_data(channel.id, message.id, self._current_hash)

            logger.tree("Actions Panel Updated", [
                ("Channel", channel.name),
                ("Message ID", str(message.id)),
                ("New Hash", self._current_hash),
            ], emoji="📝")
            return True

        except discord.Forbidden:
            logger.tree("Actions Panel Edit Failed", [
                ("Channel", channel.name),
                ("Reason", "Missing permissions"),
            ], emoji="❌")
        except discord.HTTPException as e:
            logger.tree("Actions Panel Edit Failed", [
                ("Channel", channel.name),
                ("Error", str(e)[:50]),
            ], emoji="❌")
        except Exception as e:
            logger.error_tree("Actions Panel Edit Error", e, [
                ("Channel", channel.name),
                ("Message ID", str(message.id)),
            ])
        return False

    async def _send_panel(self, channel: discord.TextChannel) -> bool:
        """
        Send and pin the actions panel to a channel.

        Args:
            channel: The channel to send the panel to.

        Returns:
            True if successful, False otherwise.
        """
        try:
            embed = self._build_embed()
            msg = await channel.send(embed=embed)

            # Pin the message
            try:
                await msg.pin(reason="Actions list panel")
            except discord.HTTPException as e:
                logger.tree("Actions Panel Pin Failed", [
                    ("Channel", channel.name),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

            # Store message ID and hash
            self._panel_message_ids[channel.id] = msg.id
            db.set_actions_panel_data(channel.id, msg.id, self._current_hash)

            logger.tree("Actions Panel Sent", [
                ("Channel", channel.name),
                ("Message ID", str(msg.id)),
                ("Actions Hash", self._current_hash),
            ], emoji="📋")
            return True

        except discord.Forbidden:
            logger.tree("Actions Panel Send Failed", [
                ("Channel", channel.name),
                ("Reason", "Missing permissions"),
            ], emoji="❌")
        except discord.HTTPException as e:
            logger.tree("Actions Panel Send Failed", [
                ("Channel", channel.name),
                ("Error", str(e)[:50]),
            ], emoji="❌")
        except Exception as e:
            logger.error_tree("Actions Panel Send Error", e, [
                ("Channel", channel.name),
            ])
        return False

    async def handle_message_delete(self, message_id: int) -> None:
        """
        Handle message deletion events.

        If the deleted message is one of our panels, resend it (with rate limiting).
        """
        if not self._enabled:
            return

        # Find which channel this message belonged to
        channel_id = None
        for cid, mid in self._panel_message_ids.items():
            if mid == message_id:
                channel_id = cid
                break

        if channel_id is None:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        # Rate limit check
        now = time.time()
        last_resend = self._last_resend.get(channel_id, 0)
        time_since_last = now - last_resend

        if time_since_last < RESEND_COOLDOWN:
            remaining = int(RESEND_COOLDOWN - time_since_last)
            logger.tree("Actions Panel Resend Rate Limited", [
                ("Channel", channel.name),
                ("Message ID", str(message_id)),
                ("Cooldown Remaining", f"{remaining}s"),
            ], emoji="⏳")
            return

        logger.tree("Actions Panel Deleted", [
            ("Channel", channel.name),
            ("Message ID", str(message_id)),
            ("Action", "Resending..."),
        ], emoji="🔄")

        # Clear stored ID for this channel
        del self._panel_message_ids[channel_id]
        db.delete_actions_panel_data(channel_id)

        # Update rate limit timestamp
        self._last_resend[channel_id] = now

        # Resend panel
        await self._send_panel(channel)


# Singleton instance
actions_panel: ActionsPanelService | None = None
