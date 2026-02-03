"""
SyriaBot - Periodic Announcements Service
=========================================

Manages scheduled announcements for server information.
Posts evergreen informational messages at configured intervals.

Features:
    - Configurable posting interval
    - Auto-delete previous announcement
    - Comprehensive logging
    - Graceful error handling

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Optional

import discord
from discord.ext import commands, tasks

from src.core.config import config
from src.core.colors import COLOR_FEMALE, COLOR_MALE, COLOR_GOLD
from src.core.emojis import EMOJI_TICKET
from src.core.logger import logger
from src.utils.footer import set_footer


# =============================================================================
# Constants
# =============================================================================

# Posting interval in hours
ANNOUNCEMENT_INTERVAL_HOURS = 12


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

    async def setup(self) -> None:
        """Initialize the announcement service."""
        # Validate configuration
        if not config.GENERAL_CHANNEL_ID:
            logger.tree("Announcement Service Disabled", [
                ("Reason", "GENERAL_CHANNEL_ID not configured"),
            ], emoji="⚠️")
            return

        if not config.TICKET_CHANNEL_ID:
            logger.tree("Announcement Service Disabled", [
                ("Reason", "TICKET_CHANNEL_ID not configured"),
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

        # Post immediately on startup
        await self._post_announcement()

        # Start the periodic task
        self._post_task.start()

        logger.tree("Announcement Service Ready", [
            ("Channel", f"{self._channel.name} ({self._channel.id})"),
            ("Interval", f"{ANNOUNCEMENT_INTERVAL_HOURS} hours"),
            ("Next Post", f"In {ANNOUNCEMENT_INTERVAL_HOURS} hours"),
        ], emoji="📢")

    def stop(self) -> None:
        """Stop the announcement service."""
        if self._post_task.is_running():
            self._post_task.cancel()
        self._enabled = False
        logger.tree("Announcement Service Stopped", [], emoji="📢")

    @tasks.loop(hours=ANNOUNCEMENT_INTERVAL_HOURS)
    async def _post_task(self) -> None:
        """Periodic task to post announcement."""
        if not self._enabled or not self._channel:
            return

        await self._post_announcement()

    @_post_task.before_loop
    async def _before_post_task(self) -> None:
        """Wait for bot to be ready before starting task."""
        await self.bot.wait_until_ready()

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

            logger.tree("Announcement Posted", [
                ("Channel", self._channel.name),
                ("Message ID", str(msg.id)),
                ("Next Post", f"In {ANNOUNCEMENT_INTERVAL_HOURS} hours"),
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
