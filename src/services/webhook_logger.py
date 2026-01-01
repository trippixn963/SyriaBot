"""
SyriaBot - Interaction Logger Service
=====================================

Logs all bot interactions to a Discord webhook.

Tracked interactions:
- Button interactions (TempVoice, Convert, etc.)
- Slash command usage
- User actions (permit, block, kick, transfer)
- Any other bot interactions

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo

import discord

from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING, COLOR_INFO, COLOR_BUTTON
from src.core.config import config
from src.core.logger import log
from src.utils.footer import set_footer

if TYPE_CHECKING:
    from src.bot import SyriaBot


# =============================================================================
# Constants
# =============================================================================

# Eastern timezone (auto EST/EDT)
EASTERN_TZ = ZoneInfo("America/New_York")


# =============================================================================
# Interaction Logger Service
# =============================================================================

class InteractionLogger:
    """Logs bot interactions via webhook."""

    def __init__(self) -> None:
        self.webhook_url = config.LOGGING_WEBHOOK_URL
        self.enabled = bool(self.webhook_url)
        self._session: Optional[aiohttp.ClientSession] = None
        self._bot: Optional["SyriaBot"] = None

        if self.enabled:
            log.tree("Interaction Logger Initialized", [
                ("Status", "Enabled"),
                ("Webhook", "Configured"),
            ], emoji="📊")
        else:
            log.tree("Interaction Logger Disabled", [
                ("Reason", "SYRIA_LOGGING_WEBHOOK_URL not set"),
            ], emoji="⚠️")

    def set_bot(self, bot: "SyriaBot") -> None:
        """Set bot reference for avatar access."""
        self._bot = bot

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create persistent HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close HTTP session on shutdown."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _send_log(self, embed: discord.Embed) -> None:
        """Send a log embed via webhook."""
        if not self.enabled or not self.webhook_url:
            return

        try:
            session = await self._get_session()

            payload = {
                "embeds": [embed.to_dict()],
            }

            async with session.post(self.webhook_url, json=payload) as resp:
                if resp.status not in (200, 204):
                    log.tree("Interaction Webhook Error", [
                        ("Status", str(resp.status)),
                    ], emoji="❌")
        except Exception as e:
            log.tree("Interaction Webhook Failed", [
                ("Error", str(e)),
            ], emoji="❌")

    def _get_time_str(self) -> str:
        """Get formatted Eastern time string."""
        now_eastern = datetime.now(EASTERN_TZ)
        return now_eastern.strftime("%I:%M %p %Z")

    # =========================================================================
    # Generic Logging Methods
    # =========================================================================

    async def log_button(
        self,
        user: discord.User,
        button_label: str,
        action: str,
        success: bool = True,
        **fields
    ) -> None:
        """
        Log when a button is pressed.

        Args:
            user: The user who pressed the button
            button_label: Label shown on the button
            action: What the button does
            success: Whether the action succeeded
            **fields: Additional fields to add (name=value)
        """
        if not self.enabled:
            return

        time_str = self._get_time_str()
        color = COLOR_BUTTON if success else COLOR_ERROR
        status = "✅" if success else "❌"

        embed = discord.Embed(
            title=f"🔘 {button_label} {status}",
            color=color,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention} `[{user.id}]`", inline=True)
        embed.add_field(name="Action", value=f"`{action}`", inline=True)
        embed.add_field(name="Time", value=f"`{time_str}`", inline=True)

        # Add any extra fields
        for name, value in fields.items():
            if value is not None:
                embed.add_field(name=name, value=f"`{value}`", inline=True)

        set_footer(embed)
        await self._send_log(embed)

    async def log_user_action(
        self,
        actor: discord.User,
        target: discord.User,
        action: str,
        success: bool = True,
        **fields
    ) -> None:
        """
        Log an action performed on another user.

        Args:
            actor: The user performing the action
            target: The user being acted upon
            action: What action was performed
            success: Whether the action succeeded
            **fields: Additional fields to add (name=value)
        """
        if not self.enabled:
            return

        time_str = self._get_time_str()
        color = COLOR_INFO if success else COLOR_ERROR
        status = "✅" if success else "❌"

        embed = discord.Embed(
            title=f"👤 {action} {status}",
            color=color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Actor", value=f"{actor.mention} `[{actor.id}]`", inline=True)
        embed.add_field(name="Target", value=f"{target.mention} `[{target.id}]`", inline=True)
        embed.add_field(name="Time", value=f"`{time_str}`", inline=True)

        # Add any extra fields
        for name, value in fields.items():
            if value is not None:
                embed.add_field(name=name, value=f"`{value}`", inline=True)

        set_footer(embed)
        await self._send_log(embed)

    async def log_command(
        self,
        user: discord.User,
        command_name: str,
        success: bool = True,
        error: Optional[str] = None,
        **fields
    ) -> None:
        """
        Log when a slash command is used.

        Args:
            user: The user who used the command
            command_name: Name of the command (without /)
            success: Whether the command succeeded
            error: Error message if failed
            **fields: Additional fields (command arguments, etc.)
        """
        if not self.enabled:
            return

        time_str = self._get_time_str()
        color = COLOR_SUCCESS if success else COLOR_ERROR
        status = "✅ Success" if success else "❌ Failed"

        embed = discord.Embed(
            title=f"⚡ /{command_name}",
            color=color,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=f"{user.mention} `[{user.id}]`", inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Time", value=f"`{time_str}`", inline=True)

        # Add command arguments
        if fields:
            args_str = " • ".join([f"**{k}:** `{v}`" for k, v in fields.items() if v is not None])
            if args_str:
                embed.add_field(name="Args", value=args_str, inline=False)

        # Add error if failed
        if error:
            embed.add_field(name="Error", value=f"```{error[:200]}```", inline=False)

        set_footer(embed)
        await self._send_log(embed)

    async def log_event(
        self,
        title: str,
        user: Optional[discord.User] = None,
        color: int = COLOR_INFO,
        success: bool = True,
        description: Optional[str] = None,
        **fields
    ) -> None:
        """
        Log a generic event.

        Args:
            title: Event title
            user: User involved (optional)
            color: Embed color
            success: Whether the event was successful
            description: Optional description text
            **fields: Additional fields to add
        """
        if not self.enabled:
            return

        time_str = self._get_time_str()
        status = "✅" if success else "❌"

        embed = discord.Embed(
            title=f"{title} {status}",
            description=description,
            color=color if success else COLOR_ERROR,
        )

        if user:
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="User", value=f"{user.mention} `[{user.id}]`", inline=True)

        embed.add_field(name="Time", value=f"`{time_str}`", inline=True)

        for name, value in fields.items():
            if value is not None:
                embed.add_field(name=name, value=f"`{value}`" if not str(value).startswith("`") else value, inline=True)

        set_footer(embed)
        await self._send_log(embed)

    # =========================================================================
    # Convenience Wrappers (for common patterns)
    # =========================================================================

    def log_tempvoice(
        self,
        user: discord.User,
        action: str,
        channel_name: str,
        success: bool = True,
        target: Optional[discord.User] = None,
        **extra
    ) -> None:
        """
        Log a TempVoice interaction.

        Args:
            user: User performing the action
            action: Action name (Lock, Unlock, Rename, etc.)
            channel_name: Name of the voice channel
            success: Whether action succeeded
            target: Target user for user actions (permit, block, etc.)
            **extra: Additional fields
        """
        if not self.enabled:
            return

        if target:
            asyncio.create_task(
                self.log_user_action(user, target, f"TempVoice • {action}", success, Channel=channel_name, **extra)
            )
        else:
            asyncio.create_task(
                self.log_button(user, "TempVoice", action, success, Channel=channel_name, **extra)
            )

    def log_tempvoice_claim(
        self,
        requester: discord.User,
        owner: discord.User,
        channel_name: str,
        approved: Optional[bool] = None
    ) -> None:
        """
        Log a TempVoice claim request/response.

        Args:
            requester: User requesting the claim
            owner: Current channel owner
            channel_name: Name of the voice channel
            approved: None=requested, True=approved, False=denied
        """
        if not self.enabled:
            return

        if approved is None:
            action = "Claim Requested"
            # Requester is actor, owner is target
            asyncio.create_task(
                self.log_user_action(requester, owner, f"TempVoice • {action}", True, Channel=channel_name)
            )
        elif approved:
            action = "Claim Approved"
            # Owner approved, requester is target (new owner)
            asyncio.create_task(
                self.log_user_action(owner, requester, f"TempVoice • {action}", True, Channel=channel_name)
            )
        else:
            action = "Claim Denied"
            # Owner denied, requester is target
            asyncio.create_task(
                self.log_user_action(owner, requester, f"TempVoice • {action}", False, Channel=channel_name)
            )

    def log_convert(
        self,
        user: discord.User,
        source: str,
        media_type: str,
        success: bool = True,
        uses_left: Optional[int] = None
    ) -> None:
        """
        Log a convert command usage.

        Args:
            user: User who used convert
            source: Source filename
            media_type: Type of media (Image, Video, Animated GIF)
            success: Whether conversion succeeded
            uses_left: Remaining uses this week (None = unlimited)
        """
        if not self.enabled:
            return

        access = f"{uses_left}/week" if uses_left is not None else "Unlimited"
        asyncio.create_task(
            self.log_button(user, "Convert", media_type, success, Source=source[:30], Access=access)
        )

    def log_quote(
        self,
        user: discord.User,
        quoted_author: str,
        message_length: int,
        success: bool = True
    ) -> None:
        """
        Log a quote command usage.

        Args:
            user: User who used quote
            quoted_author: Name of the quoted author
            message_length: Length of the quoted message
            success: Whether quote generation succeeded
        """
        if not self.enabled:
            return

        asyncio.create_task(
            self.log_button(user, "Quote", "Generated", success, Author=quoted_author, Length=f"{message_length} chars")
        )


# =============================================================================
# Singleton
# =============================================================================

interaction_logger = InteractionLogger()

# Backwards compatibility alias
webhook_logger = interaction_logger
