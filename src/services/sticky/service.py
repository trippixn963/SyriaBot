"""
SyriaBot - Sticky Message Service
=================================

Manages sticky messages in role-verified channels.
Resends the sticky message after a configurable number of messages.

Features:
    - Data-driven channel configuration
    - Automatic old message cleanup
    - Configurable message threshold
    - Comprehensive logging

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import discord
from discord.ext import commands

from src.core.config import config
from src.core.colors import COLOR_FEMALE, COLOR_MALE
from src.core.emojis import EMOJI_TICKET
from src.core.logger import logger
from src.utils.footer import set_footer


# =============================================================================
# Channel Configuration
# =============================================================================

@dataclass
class StickyChannelConfig:
    """Configuration for a sticky message channel."""
    channel_id: int
    role_id: int
    name: str
    emoji: str
    color: int


def _get_channel_configs() -> List[StickyChannelConfig]:
    """Build channel configurations from config values."""
    configs = []

    # Female chat
    if config.FEMALE_CHAT_CHANNEL_ID and config.FEMALE_VERIFIED_ROLE_ID:
        configs.append(StickyChannelConfig(
            channel_id=config.FEMALE_CHAT_CHANNEL_ID,
            role_id=config.FEMALE_VERIFIED_ROLE_ID,
            name="Female",
            emoji="👩",
            color=COLOR_FEMALE,
        ))

    # Male chat
    if config.MALE_CHAT_CHANNEL_ID and config.MALE_VERIFIED_ROLE_ID:
        configs.append(StickyChannelConfig(
            channel_id=config.MALE_CHAT_CHANNEL_ID,
            role_id=config.MALE_VERIFIED_ROLE_ID,
            name="Male",
            emoji="👨",
            color=COLOR_MALE,
        ))

    return configs


# =============================================================================
# Sticky View (Button)
# =============================================================================

class StickyView(discord.ui.View):
    """Persistent view with button to open ticket channel."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

        # Build ticket URL using config
        ticket_url = f"https://discord.com/channels/{config.GUILD_ID}/{config.TICKET_CHANNEL_ID}"

        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Open a Ticket",
            emoji=discord.PartialEmoji.from_str(EMOJI_TICKET),
            url=ticket_url,
        ))


# =============================================================================
# Sticky Message Service
# =============================================================================

class StickyService:
    """
    Service for managing sticky messages in verified channels.

    DESIGN:
        Tracks message counts per channel and resends the sticky embed
        after a configured threshold is reached. Used in gender-verified
        channels to keep verification instructions visible.
        Automatically deletes old stickies before posting new ones.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the sticky service.

        Loads channel configurations and sets up message tracking state.

        Args:
            bot: Main bot instance for Discord API access.
        """
        self.bot = bot
        self._enabled = False

        # Load channel configurations
        self._channel_configs: Dict[int, StickyChannelConfig] = {}
        for cfg in _get_channel_configs():
            self._channel_configs[cfg.channel_id] = cfg

        # Track message counts per channel
        self._message_counts: Dict[int, int] = {
            channel_id: 0 for channel_id in self._channel_configs
        }

        # Track last sticky message IDs per channel
        self._sticky_message_ids: Dict[int, Optional[int]] = {
            channel_id: None for channel_id in self._channel_configs
        }

    async def setup(self) -> None:
        """Initialize the sticky service."""
        if not self._channel_configs:
            logger.tree("Sticky Service Disabled", [
                ("Reason", "No channels configured"),
            ], emoji="⚠️")
            return

        # Validate channels exist
        valid_channels = []
        for channel_id, cfg in self._channel_configs.items():
            channel = self.bot.get_channel(channel_id)
            if channel:
                valid_channels.append(f"{cfg.name} ({channel.name})")
            else:
                logger.tree("Sticky Channel Not Found", [
                    ("Type", cfg.name),
                    ("Channel ID", str(channel_id)),
                ], emoji="⚠️")

        if not valid_channels:
            logger.tree("Sticky Service Disabled", [
                ("Reason", "No valid channels found"),
            ], emoji="⚠️")
            return

        self._enabled = True

        logger.tree("Sticky Service Ready", [
            ("Channels", ", ".join(valid_channels)),
            ("Threshold", f"{config.STICKY_MESSAGE_THRESHOLD} messages"),
            ("Ticket Channel", str(config.TICKET_CHANNEL_ID)),
        ], emoji="📌")

    def stop(self) -> None:
        """Stop the sticky service."""
        self._enabled = False
        logger.tree("Sticky Service Stopped", [], emoji="📌")

    async def handle_message(self, message: discord.Message) -> bool:
        """
        Handle a message in sticky channels.

        Increments the message counter and triggers sticky resend
        when threshold is reached.

        Args:
            message: The Discord message to process.

        Returns:
            True if this is a sticky channel message, False otherwise.
        """
        if not self._enabled:
            return False

        channel_id = message.channel.id
        if channel_id not in self._channel_configs:
            return False

        # Don't count bot messages
        if message.author.bot:
            return True

        # Increment counter
        self._message_counts[channel_id] += 1
        current_count = self._message_counts[channel_id]

        # Log progress at intervals (every 10 messages)
        if current_count % 10 == 0:
            cfg = self._channel_configs[channel_id]
            remaining = config.STICKY_MESSAGE_THRESHOLD - current_count
            logger.tree("Sticky Counter Update", [
                ("Channel", cfg.name),
                ("Count", f"{current_count}/{config.STICKY_MESSAGE_THRESHOLD}"),
                ("Remaining", str(remaining)),
            ], emoji="📊")

        # Check if we need to resend sticky
        if current_count >= config.STICKY_MESSAGE_THRESHOLD:
            self._message_counts[channel_id] = 0
            cfg = self._channel_configs[channel_id]

            logger.tree("Sticky Threshold Reached", [
                ("Channel", cfg.name),
                ("Threshold", str(config.STICKY_MESSAGE_THRESHOLD)),
            ], emoji="🔔")

            await self._send_sticky(message.channel, cfg)

        return True

    async def _delete_old_sticky(self, channel: discord.TextChannel, cfg: StickyChannelConfig) -> None:
        """
        Delete the previous sticky message if it exists.

        Args:
            channel: The channel to delete from.
            cfg: The channel configuration.
        """
        old_id = self._sticky_message_ids.get(channel.id)
        if not old_id:
            return

        try:
            old_message = await channel.fetch_message(old_id)
            await old_message.delete()
            logger.tree("Old Sticky Deleted", [
                ("Channel", cfg.name),
                ("Message ID", str(old_id)),
            ], emoji="🗑️")
        except discord.NotFound:
            logger.tree("Old Sticky Already Gone", [
                ("Channel", cfg.name),
                ("Message ID", str(old_id)),
            ], emoji="ℹ️")
        except discord.Forbidden:
            logger.tree("Old Sticky Delete Forbidden", [
                ("Channel", cfg.name),
                ("Message ID", str(old_id)),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("Old Sticky Delete Failed", [
                ("Channel", cfg.name),
                ("Message ID", str(old_id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        self._sticky_message_ids[channel.id] = None

    async def _send_sticky(self, channel: discord.TextChannel, cfg: StickyChannelConfig) -> None:
        """
        Send the sticky message to a channel.

        Args:
            channel: The channel to send to.
            cfg: The channel configuration.
        """
        # Delete old sticky first
        await self._delete_old_sticky(channel, cfg)

        # Build role mention
        role_mention = f"<@&{cfg.role_id}>"

        # Build the embed
        embed = discord.Embed(
            title=f"{cfg.emoji} Role-Verified Channel",
            description=(
                f"This channel is exclusively for members with the {role_mention} role.\n\n"
                f"To gain access to this channel, you must verify your identity."
            ),
            color=cfg.color
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
        view = StickyView()

        try:
            msg = await channel.send(embed=embed, view=view)
            self._sticky_message_ids[channel.id] = msg.id
            logger.tree("Sticky Message Sent", [
                ("Channel", cfg.name),
                ("Role", role_mention),
                ("Message ID", str(msg.id)),
            ], emoji="📌")
        except discord.Forbidden:
            logger.tree("Sticky Send Forbidden", [
                ("Channel", cfg.name),
                ("Reason", "Missing permissions"),
            ], emoji="❌")
        except discord.HTTPException as e:
            logger.tree("Sticky Send Failed", [
                ("Channel", cfg.name),
                ("Error Type", type(e).__name__),
                ("Error", str(e)[:100]),
            ], emoji="❌")
