"""
SyriaBot - Sticky Message Service
=================================

Manages sticky messages in role-verified channels (female/male only).
Resends the sticky message after every N messages.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord.ext import commands
from typing import Dict, Optional

from src.core.logger import logger
from src.core.colors import COLOR_GOLD
from src.utils.footer import set_footer


# =============================================================================
# Configuration
# =============================================================================

# Channel IDs
FEMALE_CHAT_ID = 1468272030574055652
MALE_CHAT_ID = 1468273741799886952
TICKET_CHANNEL_ID = 1406750411779604561

# Role IDs
FEMALE_VERIFIED_ROLE_ID = 1468272342429073440
MALE_VERIFIED_ROLE_ID = 1468272986527236438

# Messages between sticky resends
MESSAGES_THRESHOLD = 50


# =============================================================================
# Sticky View (Button)
# =============================================================================

class StickyView(discord.ui.View):
    """Persistent view with button to open ticket channel."""

    def __init__(self, ticket_channel_id: int):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Open a Ticket",
            emoji="🎫",
            url=f"https://discord.com/channels/1406750392280465511/{ticket_channel_id}",
        ))


# =============================================================================
# Sticky Message Service
# =============================================================================

class StickyService:
    """Service for managing sticky messages in verified channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Track message counts per channel
        self._message_counts: Dict[int, int] = {
            FEMALE_CHAT_ID: 0,
            MALE_CHAT_ID: 0,
        }
        # Track last sticky message IDs per channel
        self._sticky_message_ids: Dict[int, Optional[int]] = {
            FEMALE_CHAT_ID: None,
            MALE_CHAT_ID: None,
        }
        self._enabled = True

    async def setup(self) -> None:
        """Initialize the sticky service and send initial messages."""
        # Send initial sticky messages to both channels
        for channel_id in [FEMALE_CHAT_ID, MALE_CHAT_ID]:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await self._send_sticky(channel)
            else:
                logger.tree("Sticky Channel Not Found", [
                    ("Channel ID", str(channel_id)),
                ], emoji="⚠️")

        logger.tree("Sticky Service Ready", [
            ("Female Chat", str(FEMALE_CHAT_ID)),
            ("Male Chat", str(MALE_CHAT_ID)),
            ("Threshold", f"{MESSAGES_THRESHOLD} messages"),
        ], emoji="📌")

    def stop(self) -> None:
        """Stop the sticky service."""
        self._enabled = False
        logger.tree("Sticky Service Stopped", [], emoji="📌")

    async def handle_message(self, message: discord.Message) -> bool:
        """
        Handle a message in sticky channels.

        Returns True if this is a sticky channel message.
        Returns False otherwise.
        """
        if not self._enabled:
            return False

        channel_id = message.channel.id
        if channel_id not in self._message_counts:
            return False

        # Don't count bot messages
        if message.author.bot:
            return True

        # Increment counter
        self._message_counts[channel_id] += 1

        # Check if we need to resend sticky
        if self._message_counts[channel_id] >= MESSAGES_THRESHOLD:
            self._message_counts[channel_id] = 0
            await self._send_sticky(message.channel)

        return True

    async def _delete_old_sticky(self, channel: discord.TextChannel) -> None:
        """Delete the previous sticky message if it exists."""
        old_id = self._sticky_message_ids.get(channel.id)
        if not old_id:
            return

        try:
            old_message = await channel.fetch_message(old_id)
            await old_message.delete()
            logger.tree("Old Sticky Deleted", [
                ("Channel", channel.name),
                ("Message ID", str(old_id)),
            ], emoji="🗑️")
        except discord.NotFound:
            pass  # Already deleted
        except discord.HTTPException as e:
            logger.tree("Old Sticky Delete Failed", [
                ("Channel", channel.name),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        self._sticky_message_ids[channel.id] = None

    async def _send_sticky(self, channel: discord.TextChannel) -> None:
        """Send the sticky message to a channel."""
        # Delete old sticky first
        await self._delete_old_sticky(channel)

        # Determine channel type
        is_female = channel.id == FEMALE_CHAT_ID
        role_id = FEMALE_VERIFIED_ROLE_ID if is_female else MALE_VERIFIED_ROLE_ID
        role_mention = f"<@&{role_id}>"
        emoji = "👩" if is_female else "👨"
        color = 0xFF69B4 if is_female else 0x4169E1  # Pink for female, Royal Blue for male

        # Build the embed
        embed = discord.Embed(
            title=f"{emoji} Role-Verified Channel",
            description=(
                f"This channel is exclusively for members with the {role_mention} role.\n\n"
                f"To gain access to this channel, you must verify your identity."
            ),
            color=color
        )

        embed.add_field(
            name="📋 How to Get Verified",
            value=(
                "1. Open a ticket using the button below\n"
                "2. Follow the verification instructions\n"
                "3. A staff member will review your request"
            ),
            inline=False
        )

        embed.add_field(
            name="⚠️ Important",
            value=(
                f"• Only members with {role_mention} can access this channel\n"
                "• Impersonation will result in a permanent ban\n"
                "• Keep conversations respectful"
            ),
            inline=False
        )

        # Set footer with server icon
        set_footer(embed)

        # Create view with ticket button
        view = StickyView(TICKET_CHANNEL_ID)

        try:
            msg = await channel.send(embed=embed, view=view)
            self._sticky_message_ids[channel.id] = msg.id
            logger.tree("Sticky Message Sent", [
                ("Channel", channel.name),
                ("Type", role_name),
                ("Message ID", str(msg.id)),
            ], emoji="📌")
        except discord.HTTPException as e:
            logger.tree("Sticky Send Failed", [
                ("Channel", channel.name),
                ("Error", str(e)[:100]),
            ], emoji="❌")
