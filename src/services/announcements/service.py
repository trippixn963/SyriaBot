"""
SyriaBot - Periodic Announcements Service
=========================================

Manages scheduled announcements for server information.
Posts evergreen informational messages at configured intervals.

Features:
    - Configurable posting interval via config
    - Auto-delete previous announcement (persists across restarts)
    - Comprehensive logging
    - Graceful error handling

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import json
from typing import Optional

import discord
from discord.ext import commands

from src.core.config import config, DATA_DIR
from src.core.colors import COLOR_GOLD
from src.core.emojis import EMOJI_TICKET
from src.core.logger import logger
from src.utils.footer import set_footer


# =============================================================================
# Persistence
# =============================================================================

STATE_FILE = DATA_DIR / "announcement_state.json"


def _load_state() -> dict:
    """Load persisted state from file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.tree("Announcement State Load Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")
    return {}


def _save_state(state: dict) -> None:
    """Save state to file."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except IOError as e:
        logger.tree("Announcement State Save Failed", [
            ("Error", str(e)[:50]),
        ], emoji="⚠️")


# =============================================================================
# Announcement View (Button)
# =============================================================================

class AnnouncementView(discord.ui.View):
    """Persistent view with ticket button."""

    def __init__(self):
        super().__init__(timeout=None)

        ticket_url = f"https://discord.com/channels/{config.GUILD_ID}/{config.TICKET_CHANNEL_ID}"

        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Open a Ticket",
            emoji=discord.PartialEmoji.from_str(EMOJI_TICKET),
            url=ticket_url,
        ))


# =============================================================================
# Announcement Service
# =============================================================================

class AnnouncementService:
    """
    Service for posting periodic announcements.

    Posts informational messages about server features at regular intervals,
    deleting the previous message to avoid clutter.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._enabled = False
        self._last_message_id: Optional[int] = None
        self._channel: Optional[discord.TextChannel] = None
        self._task: Optional[asyncio.Task] = None

        # Load persisted message ID
        state = _load_state()
        self._last_message_id = state.get("last_message_id")

    async def setup(self) -> None:
        """Initialize the announcement service."""
        # Validate required configuration
        missing_config = []

        if not config.GENERAL_CHANNEL_ID:
            missing_config.append("GENERAL_CHANNEL_ID")
        if not config.TICKET_CHANNEL_ID:
            missing_config.append("TICKET_CHANNEL_ID")
        if not config.FEMALE_CHAT_CHANNEL_ID:
            missing_config.append("FEMALE_CHAT_CHANNEL_ID")
        if not config.MALE_CHAT_CHANNEL_ID:
            missing_config.append("MALE_CHAT_CHANNEL_ID")
        if not config.FEMALE_VERIFIED_ROLE_ID:
            missing_config.append("FEMALE_VERIFIED_ROLE_ID")
        if not config.MALE_VERIFIED_ROLE_ID:
            missing_config.append("MALE_VERIFIED_ROLE_ID")

        if missing_config:
            logger.tree("Announcement Service Disabled", [
                ("Reason", "Missing configuration"),
                ("Missing", ", ".join(missing_config)),
            ], emoji="⚠️")
            return

        # Get channel
        self._channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not self._channel:
            logger.tree("Announcement Service Disabled", [
                ("Reason", "General channel not found"),
                ("Channel ID", str(config.GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        self._enabled = True

        # Start the periodic task
        self._task = asyncio.create_task(self._announcement_loop())

        logger.tree("Announcement Service Ready", [
            ("Channel", f"{self._channel.name} ({self._channel.id})"),
            ("Interval", f"{config.ANNOUNCEMENT_INTERVAL_HOURS} hours"),
            ("Persisted Message", str(self._last_message_id) if self._last_message_id else "None"),
        ], emoji="📢")

    def stop(self) -> None:
        """Stop the announcement service."""
        self._enabled = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.tree("Announcement Service Stopped", [], emoji="📢")

    async def _announcement_loop(self) -> None:
        """Main loop that posts announcements at configured intervals."""
        await self.bot.wait_until_ready()

        while self._enabled:
            try:
                await self._post_announcement()

                # Sleep for configured interval
                interval_seconds = config.ANNOUNCEMENT_INTERVAL_HOURS * 3600
                logger.tree("Announcement Scheduled", [
                    ("Next Post", f"In {config.ANNOUNCEMENT_INTERVAL_HOURS} hours"),
                    ("Interval", f"{interval_seconds} seconds"),
                ], emoji="⏰")

                await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                logger.tree("Announcement Loop Cancelled", [], emoji="ℹ️")
                break
            except Exception as e:
                logger.error_tree("Announcement Loop Error", e, [
                    ("Action", "Will retry in 1 hour"),
                ])
                # Wait 1 hour before retrying on error
                await asyncio.sleep(3600)

    async def _delete_previous(self) -> None:
        """Delete the previous announcement message."""
        if not self._last_message_id or not self._channel:
            return

        try:
            old_message = await self._channel.fetch_message(self._last_message_id)
            await old_message.delete()
            logger.tree("Previous Announcement Deleted", [
                ("Message ID", str(self._last_message_id)),
            ], emoji="🗑️")
        except discord.NotFound:
            logger.tree("Previous Announcement Already Gone", [
                ("Message ID", str(self._last_message_id)),
            ], emoji="ℹ️")
        except discord.Forbidden:
            logger.tree("Previous Announcement Delete Forbidden", [
                ("Message ID", str(self._last_message_id)),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("Previous Announcement Delete Failed", [
                ("Message ID", str(self._last_message_id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        self._last_message_id = None
        _save_state({"last_message_id": None})

    def _build_embed(self) -> discord.Embed:
        """Build the announcement embed."""
        # Role mentions
        female_role = f"<@&{config.FEMALE_VERIFIED_ROLE_ID}>"
        male_role = f"<@&{config.MALE_VERIFIED_ROLE_ID}>"

        # Channel mentions
        female_chat = f"<#{config.FEMALE_CHAT_CHANNEL_ID}>"
        male_chat = f"<#{config.MALE_CHAT_CHANNEL_ID}>"
        ticket_channel = f"<#{config.TICKET_CHANNEL_ID}>"

        embed = discord.Embed(
            title="👩 👨 Gender-Verified Channels",
            description=(
                "We have exclusive spaces for verified members!\n\n"
                f"**{female_chat}** → For members with {female_role}\n"
                f"**{male_chat}** → For members with {male_role}"
            ),
            color=COLOR_GOLD
        )

        embed.add_field(
            name="📋 How to Get Verified",
            value=(
                f"1. Open a ticket in {ticket_channel}\n"
                "2. Follow the verification instructions\n"
                "3. A staff member will review your request\n\n"
                "Once approved, you'll receive the verified role and gain access to the channel."
            ),
            inline=False
        )

        embed.add_field(
            name="⚠️ Important",
            value=(
                "• Verification requires identity confirmation\n"
                "• Impersonation results in a permanent ban\n"
                "• These channels are safe spaces - be respectful"
            ),
            inline=False
        )

        set_footer(embed)

        return embed

    async def _post_announcement(self) -> None:
        """Post the announcement to the channel."""
        if not self._channel:
            return

        # Delete previous announcement
        await self._delete_previous()

        # Build embed and view
        embed = self._build_embed()
        view = AnnouncementView()

        try:
            msg = await self._channel.send(embed=embed, view=view)
            self._last_message_id = msg.id

            # Persist message ID
            _save_state({"last_message_id": msg.id})

            logger.tree("Announcement Posted", [
                ("Channel", self._channel.name),
                ("Message ID", str(msg.id)),
            ], emoji="📢")

        except discord.Forbidden:
            logger.tree("Announcement Post Forbidden", [
                ("Channel", self._channel.name),
                ("Reason", "Missing permissions"),
            ], emoji="❌")
        except discord.HTTPException as e:
            logger.tree("Announcement Post Failed", [
                ("Channel", self._channel.name),
                ("Error Type", type(e).__name__),
                ("Error", str(e)[:100]),
            ], emoji="❌")

    async def post_now(self) -> bool:
        """
        Manually trigger an announcement post.

        Returns:
            True if posted successfully, False otherwise.
        """
        if not self._enabled or not self._channel:
            return False

        await self._post_announcement()
        return self._last_message_id is not None
