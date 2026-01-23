"""
SyriaBot - Suggestion Service
=============================

Suggestion system with threads and reactions.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
from typing import TYPE_CHECKING, Optional, Tuple, Dict, Any

import discord

from src.core.config import config
from src.core.logger import logger
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING, EMOJI_HEART, EMOJI_SUGGEST
from src.services.database import db
from src.utils.footer import set_footer


# =============================================================================
# Constants
# =============================================================================

# Limits
MAX_SUGGESTIONS_PER_DAY: int = 3
SUGGESTION_MIN_LENGTH: int = 20
SUGGESTION_MAX_LENGTH: int = 1000
LOG_CONTENT_TRUNCATE: int = 50

# Thread settings
THREAD_AUTO_ARCHIVE_MINUTES: int = 1440  # 24 hours

# Status display mappings
STATUS_DISPLAY: Dict[str, str] = {
    "pending": "⏳ Pending Review",
    "approved": "✅ Approved",
    "rejected": "❌ Rejected",
    "implemented": "🎉 Implemented",
}

STATUS_COLORS: Dict[str, int] = {
    "pending": COLOR_SYRIA_GREEN,
    "approved": COLOR_SYRIA_GREEN,
    "rejected": COLOR_SYRIA_GREEN,
    "implemented": 0xE6B84A,  # Gold
}

if TYPE_CHECKING:
    from src.bot import SyriaBot


class SuggestionService:
    """Service for managing suggestions."""

    def __init__(self, bot: "SyriaBot") -> None:
        """Initialize the suggestion service."""
        self.bot: "SyriaBot" = bot
        self._enabled: bool = False
        self._channel_id: Optional[int] = None
        self._submit_lock = asyncio.Lock()

    async def setup(self) -> None:
        """Initialize the suggestion service."""
        if not config.SUGGESTIONS_CHANNEL_ID:
            logger.tree("Suggestions Service", [
                ("Status", "Disabled"),
                ("Reason", "Missing SUGGESTIONS_CHANNEL_ID"),
            ], emoji="ℹ️")
            return

        channel = self.bot.get_channel(config.SUGGESTIONS_CHANNEL_ID)
        if not channel:
            logger.tree("Suggestions Service", [
                ("Status", "Error"),
                ("Reason", "Channel not found"),
                ("Channel ID", str(config.SUGGESTIONS_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        if not isinstance(channel, discord.TextChannel):
            logger.tree("Suggestions Service", [
                ("Status", "Error"),
                ("Reason", "Not a text channel"),
            ], emoji="⚠️")
            return

        self._enabled = True
        self._channel_id = channel.id

        stats = await asyncio.to_thread(db.get_suggestion_stats)

        logger.tree("Suggestions Service Ready", [
            ("Channel", channel.name),
            ("Total", str(stats["total"])),
            ("Pending", str(stats["pending"])),
            ("Approved", str(stats["approved"])),
        ], emoji="✅")

    def is_enabled(self) -> bool:
        """Check if service is enabled."""
        return self._enabled

    async def handle_message(self, message: discord.Message) -> bool:
        """
        Handle messages in suggestions channel - delete non-bot messages.

        Args:
            message: The message to handle

        Returns:
            True if message was handled, False otherwise
        """
        if message.author.bot:
            return False

        if not self._enabled or not self._channel_id:
            return False

        # Check if in suggestions channel
        if message.channel.id != self._channel_id:
            return False

        # Delete the message
        try:
            await message.delete()
            logger.tree("Suggestions Channel Message Deleted", [
                ("User", f"{message.author.name}"),
                ("ID", str(message.author.id)),
                ("Content", message.content[:LOG_CONTENT_TRUNCATE] if message.content else "(empty)"),
                ("Channel", message.channel.name if hasattr(message.channel, "name") else str(message.channel.id)),
            ], emoji="🗑️")
            return True
        except discord.NotFound:
            logger.tree("Suggestions Message Already Deleted", [
                ("User", f"{message.author.name}"),
                ("ID", str(message.author.id)),
            ], emoji="ℹ️")
            return True
        except discord.Forbidden:
            logger.tree("Suggestions Message Delete Forbidden", [
                ("User", f"{message.author.name}"),
                ("ID", str(message.author.id)),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
            return False
        except discord.HTTPException as e:
            logger.tree("Suggestions Message Delete Failed", [
                ("User", f"{message.author.name}"),
                ("ID", str(message.author.id)),
                ("Error", str(e)[:LOG_CONTENT_TRUNCATE]),
            ], emoji="❌")
            return False

    async def can_submit(self, user_id: int) -> Tuple[bool, str]:
        """
        Check if user can submit a suggestion.

        Args:
            user_id: Discord user ID to check

        Returns:
            Tuple of (can_submit, reason if blocked)
        """
        count = await asyncio.to_thread(db.get_user_suggestion_count_today, user_id)
        if count >= MAX_SUGGESTIONS_PER_DAY:
            logger.tree("Suggestion Rate Limited", [
                ("ID", str(user_id)),
                ("Count Today", str(count)),
                ("Limit", str(MAX_SUGGESTIONS_PER_DAY)),
            ], emoji="⏳")
            return False, f"You've reached the daily limit ({MAX_SUGGESTIONS_PER_DAY} suggestions/day)"
        return True, ""

    async def submit(
        self,
        content: str,
        submitter: discord.Member
    ) -> Tuple[bool, str]:
        """
        Submit a new suggestion.

        Args:
            content: The suggestion text
            submitter: Discord member who submitted

        Returns:
            Tuple of (success, message/error)
        """
        if not self._enabled:
            logger.tree("Suggestion Submit Blocked", [
                ("User", f"{submitter.name}"),
                ("ID", str(submitter.id)),
                ("Reason", "Service disabled"),
            ], emoji="⚠️")
            return False, "Suggestions are not enabled"

        channel = self.bot.get_channel(self._channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.tree("Suggestion Submit Blocked", [
                ("User", f"{submitter.name}"),
                ("ID", str(submitter.id)),
                ("Reason", "Channel not found"),
                ("Channel ID", str(self._channel_id)),
            ], emoji="⚠️")
            return False, "Suggestions channel not found"

        # Check daily limit
        can_submit, reason = await self.can_submit(submitter.id)
        if not can_submit:
            return False, reason

        # Lock to prevent concurrent submissions from getting same number
        async with self._submit_lock:
            try:
                # Get next suggestion number
                stats = await asyncio.to_thread(db.get_suggestion_stats)
                suggestion_num: int = stats["total"] + 1

                logger.tree("Suggestion Processing", [
                    ("User", f"{submitter.name}"),
                    ("ID", str(submitter.id)),
                    ("Number", f"#{suggestion_num}"),
                    ("Length", f"{len(content)} chars"),
                ], emoji="⏳")

                # Create embed
                embed = discord.Embed(
                    title=f"Suggestion #{suggestion_num}",
                    description=content,
                    color=COLOR_SYRIA_GREEN
                )
                embed.set_author(
                    name=submitter.display_name,
                    icon_url=submitter.display_avatar.url
                )
                embed.add_field(name="Status", value="⏳ Pending Review", inline=True)
                embed.add_field(
                    name="\u200b",
                    value="*Use `/suggest` to share yours*",
                    inline=False
                )
                set_footer(embed)

                # Send to channel
                msg = await channel.send(embed=embed)

                logger.tree("Suggestion Message Sent", [
                    ("Number", f"#{suggestion_num}"),
                    ("Message ID", str(msg.id)),
                    ("Channel", channel.name),
                ], emoji="📨")

                # Add heart reaction
                try:
                    await msg.add_reaction(EMOJI_HEART)
                    logger.tree("Suggestion Reaction Added", [
                        ("Number", f"#{suggestion_num}"),
                        ("Emoji", "Custom heart"),
                    ], emoji="❤️")
                except discord.Forbidden:
                    logger.tree("Suggestion Reaction Forbidden", [
                        ("Number", f"#{suggestion_num}"),
                        ("Reason", "Missing permissions"),
                    ], emoji="⚠️")
                except discord.HTTPException as e:
                    logger.tree("Suggestion Reaction Failed", [
                        ("Number", f"#{suggestion_num}"),
                        ("Error", str(e)[:LOG_CONTENT_TRUNCATE]),
                    ], emoji="⚠️")

                # Create thread for discussion
                thread: Optional[discord.Thread] = None
                try:
                    thread = await msg.create_thread(
                        name=f"Suggestion #{suggestion_num}",
                        auto_archive_duration=THREAD_AUTO_ARCHIVE_MINUTES
                    )

                    # Send welcome message in thread
                    thread_embed = discord.Embed(
                        description=(
                            "💬 **Discussion Thread**\n\n"
                            "Share your thoughts on this suggestion!\n"
                            "Staff will review and update the status."
                        ),
                        color=COLOR_SYRIA_GREEN
                    )
                    set_footer(thread_embed)
                    await thread.send(embed=thread_embed)

                    logger.tree("Suggestion Thread Created", [
                        ("Number", f"#{suggestion_num}"),
                        ("Thread ID", str(thread.id)),
                        ("Thread Name", thread.name),
                    ], emoji="🧵")
                except discord.Forbidden:
                    logger.tree("Suggestion Thread Forbidden", [
                        ("Number", f"#{suggestion_num}"),
                        ("Reason", "Missing permissions"),
                    ], emoji="⚠️")
                except discord.HTTPException as e:
                    logger.tree("Suggestion Thread Failed", [
                        ("Number", f"#{suggestion_num}"),
                        ("Error", str(e)[:LOG_CONTENT_TRUNCATE]),
                    ], emoji="⚠️")

                # Save to database
                suggestion_id = await asyncio.to_thread(
                    db.create_suggestion,
                    content,
                    submitter.id,
                    msg.id
                )

                if suggestion_id is None:
                    logger.tree("Suggestion Database Failed", [
                        ("Number", f"#{suggestion_num}"),
                        ("User", f"{submitter.name}"),
                        ("Reason", "Failed to create in database"),
                    ], emoji="❌")
                    try:
                        await msg.delete()
                        if thread:
                            await thread.delete()
                    except discord.HTTPException:
                        pass
                    return False, "Failed to save suggestion"

                logger.tree("Suggestion Submitted", [
                    ("Suggestion ID", str(suggestion_id)),
                    ("Number", f"#{suggestion_num}"),
                    ("User", f"{submitter.name}"),
                    ("ID", str(submitter.id)),
                    ("Message ID", str(msg.id)),
                    ("Thread", thread.name if thread else "None"),
                    ("Length", f"{len(content)} chars"),
                ], emoji="💡")

                # Send notification to general
                await self._send_notification(msg, suggestion_num, thread)

                return True, f"Suggestion #{suggestion_num} submitted!"

            except discord.Forbidden:
                logger.tree("Suggestion Submit Forbidden", [
                    ("User", f"{submitter.name}"),
                    ("ID", str(submitter.id)),
                    ("Reason", "Missing permissions"),
                ], emoji="⚠️")
                return False, "Missing permissions to post suggestions"
            except discord.HTTPException as e:
                logger.error_tree("Suggestion Submit Failed", e, [
                    ("User", f"{submitter.name}"),
                    ("ID", str(submitter.id)),
                ])
                return False, "Failed to submit suggestion"

    async def update_status(
        self,
        message: discord.Message,
        status: str,
        mod: discord.Member
    ) -> bool:
        """
        Update suggestion status.

        Args:
            message: The suggestion message
            status: New status (approved, rejected, implemented)
            mod: Moderator who made the decision

        Returns:
            True if updated successfully
        """
        logger.tree("Suggestion Status Update Started", [
            ("Message ID", str(message.id)),
            ("New Status", status),
            ("Mod", f"{mod.name}"),
            ("Mod ID", str(mod.id)),
        ], emoji="⏳")

        suggestion = await asyncio.to_thread(db.get_suggestion_by_message, message.id)
        if not suggestion:
            logger.tree("Suggestion Status Update Failed", [
                ("Message ID", str(message.id)),
                ("Reason", "Suggestion not found in database"),
            ], emoji="⚠️")
            return False

        # Update database
        success = await asyncio.to_thread(
            db.update_suggestion_status,
            suggestion["id"],
            status,
            mod.id
        )
        if not success:
            logger.tree("Suggestion Status Update Failed", [
                ("ID", str(suggestion["id"])),
                ("Reason", "Database update failed"),
            ], emoji="❌")
            return False

        # Update embed
        try:
            embed = message.embeds[0] if message.embeds else None
            if not embed:
                logger.tree("Suggestion Status Update Failed", [
                    ("ID", str(suggestion["id"])),
                    ("Reason", "No embed found on message"),
                ], emoji="⚠️")
                return False

            # Get display values from constants
            status_display: str = STATUS_DISPLAY.get(status, status)
            color: int = STATUS_COLORS.get(status, COLOR_WARNING)

            new_embed = discord.Embed(
                title=embed.title,
                description=embed.description,
                color=color
            )
            if embed.author:
                new_embed.set_author(
                    name=embed.author.name,
                    icon_url=embed.author.icon_url
                )

            new_embed.add_field(name="Status", value=status_display, inline=True)
            if status != "pending":
                new_embed.add_field(
                    name="Reviewed By",
                    value=f"{mod.mention}",
                    inline=True
                )
            new_embed.add_field(
                name="\u200b",
                value="*Use `/suggest` to share yours*",
                inline=False
            )
            set_footer(new_embed)

            await message.edit(embed=new_embed)

            logger.tree("Suggestion Status Updated", [
                ("ID", str(suggestion["id"])),
                ("Status", status),
                ("Display", status_display),
                ("Mod", f"{mod.name}"),
                ("Mod ID", str(mod.id)),
            ], emoji="✅")

            return True

        except discord.Forbidden:
            logger.tree("Suggestion Status Update Forbidden", [
                ("ID", str(suggestion["id"])),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
            return False
        except discord.HTTPException as e:
            logger.error_tree("Suggestion Status Update Failed", e, [
                ("ID", str(suggestion["id"])),
                ("Status", status),
            ])
            return False

    async def _send_notification(
        self,
        suggestion_msg: discord.Message,
        suggestion_num: int,
        thread: Optional[discord.Thread] = None
    ) -> None:
        """
        Send notification to general chat about new suggestion.

        Args:
            suggestion_msg: The suggestion message
            suggestion_num: The suggestion number
            thread: Optional thread to link to
        """
        if not config.GENERAL_CHANNEL_ID:
            logger.tree("Suggestion Notification Skipped", [
                ("Number", f"#{suggestion_num}"),
                ("Reason", "GENERAL_CHANNEL_ID not configured"),
            ], emoji="ℹ️")
            return

        general_channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not general_channel:
            logger.tree("Suggestion Notification Skipped", [
                ("Number", f"#{suggestion_num}"),
                ("Reason", "General channel not found"),
            ], emoji="⚠️")
            return

        embed = discord.Embed(
            description=(
                f"{EMOJI_SUGGEST} **New Suggestion Posted**\n\n"
                f"Someone just shared **Suggestion #{suggestion_num}**\n"
                f"Head over to the suggestions channel to read it!\n\n"
                f"Use `/suggest` to share yours."
            ),
            color=COLOR_SYRIA_GREEN
        )
        set_footer(embed)

        # Use thread URL if available, otherwise suggestion message
        jump_url = thread.jump_url if thread else suggestion_msg.jump_url

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label=f"View Suggestion #{suggestion_num}",
            style=discord.ButtonStyle.link,
            url=jump_url,
            emoji=EMOJI_SUGGEST
        ))

        try:
            await general_channel.send(embed=embed, view=view)
            logger.tree("Suggestion Notification Sent", [
                ("Number", f"#{suggestion_num}"),
                ("Channel", general_channel.name),
            ], emoji="📢")
        except discord.Forbidden:
            logger.tree("Suggestion Notification Forbidden", [
                ("Number", f"#{suggestion_num}"),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("Suggestion Notification Failed", [
                ("Number", f"#{suggestion_num}"),
                ("Error", str(e)[:LOG_CONTENT_TRUNCATE]),
            ], emoji="❌")

    def stop(self) -> None:
        """Stop the suggestion service."""
        self._enabled = False
        logger.tree("Suggestions Service Stopped", [], emoji="🛑")
