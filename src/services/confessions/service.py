"""
SyriaBot - Confession Service
=============================

Anonymous confessions system with auto-approval.
Posts confessions to text channel with auto-thread.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import time
import discord
from typing import TYPE_CHECKING, Optional, Tuple, Set, Dict
from collections import OrderedDict

from src.core.config import config
from src.core.logger import logger
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_WARNING, EMOJI_HEART, EMOJI_CONFESSION
from src.core.constants import DELETE_DELAY_MEDIUM
from src.services.database import db
from src.utils.footer import set_footer

# Rate limit: 1 confession per hour
CONFESSION_COOLDOWN_SECONDS = 3600

if TYPE_CHECKING:
    from src.bot import SyriaBot


class ConfessionService:
    """Service for managing anonymous confessions."""

    # Letters for anon-ids (A-Z)
    ANON_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    # Color palette for anon avatars (hex without #)
    ANON_COLORS = [
        "E53935",  # A - Red
        "1E88E5",  # B - Blue
        "43A047",  # C - Green
        "FB8C00",  # D - Orange
        "8E24AA",  # E - Purple
        "00ACC1",  # F - Cyan
        "F4511E",  # G - Deep Orange
        "3949AB",  # H - Indigo
        "7CB342",  # I - Light Green
        "FFB300",  # J - Amber
        "D81B60",  # K - Pink
        "039BE5",  # L - Light Blue
        "00897B",  # M - Teal
        "C0CA33",  # N - Lime
        "5E35B1",  # O - Deep Purple
        "6D4C41",  # P - Brown
        "EC407A",  # Q - Pink Light
        "26A69A",  # R - Teal Light
        "AB47BC",  # S - Purple Light
        "FFA726",  # T - Orange Light
        "42A5F5",  # U - Blue Light
        "66BB6A",  # V - Green Light
        "EF5350",  # W - Red Light
        "7E57C2",  # X - Violet
        "26C6DA",  # Y - Cyan Light
        "FFCA28",  # Z - Yellow
    ]

    # OP gets a special gold/star color
    OP_COLOR = "FFD700"  # Gold

    # Cache size limits
    MAX_CACHE_SIZE = 100

    def __init__(self, bot: "SyriaBot") -> None:
        """Initialize the confession service."""
        self.bot: "SyriaBot" = bot
        self._enabled: bool = False
        self._channel_id: Optional[int] = None
        self._warned_users: OrderedDict[Tuple[int, int], bool] = OrderedDict()  # (thread_id, user_id) -> True
        # Anon-ID tracking: thread_id -> {user_id -> anon_id}
        self._thread_anon_ids: OrderedDict[int, Dict[int, str]] = OrderedDict()
        # Track who submitted each confession: confession_number -> submitter_id
        self._confession_submitters: OrderedDict[int, int] = OrderedDict()
        # Cached webhook for anonymous replies
        self._webhook: Optional[discord.Webhook] = None

    def _trim_cache(self, cache: OrderedDict, max_size: int = None) -> None:
        """
        Trim an OrderedDict cache to max size, removing oldest entries.

        Args:
            cache: The OrderedDict to trim
            max_size: Maximum size (defaults to MAX_CACHE_SIZE)
        """
        if max_size is None:
            max_size = self.MAX_CACHE_SIZE

        while len(cache) > max_size:
            removed_key, _ = cache.popitem(last=False)
            logger.tree("Cache Entry Trimmed", [
                ("Cache", type(cache).__name__),
                ("Removed Key", str(removed_key)[:50]),
                ("Size", str(len(cache))),
            ], emoji="🗑️")

    async def handle_message(self, message: discord.Message) -> bool:
        """
        Handle messages in confessions channel and threads.
        - Main channel: delete non-bot messages
        - Threads: warn users to use `/reply`

        Args:
            message: The message to handle

        Returns:
            True if message was handled, False otherwise
        """
        if message.author.bot:
            return False

        # Skip if service not enabled
        if not self._enabled or not self._channel_id:
            return False

        # Check if in main confessions channel
        if self._channel_id and message.channel.id == self._channel_id:
            try:
                await message.delete()
                logger.tree("Confessions Channel Message Deleted", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Content", message.content[:50] if message.content else "(empty)"),
                ], emoji="🗑️")
                return True
            except discord.NotFound:
                logger.tree("Confessions Message Already Deleted", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ], emoji="ℹ️")
                return True
            except discord.Forbidden:
                logger.tree("Confessions Message Delete Forbidden", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Reason", "Missing permissions"),
                ], emoji="⚠️")
                return False
            except discord.HTTPException as e:
                logger.tree("Confessions Message Delete Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Error", str(e)[:50]),
                ], emoji="❌")
                return False

        # Check if in a confession thread
        if isinstance(message.channel, discord.Thread):
            # Verify it's a confession thread (name check + parent channel check)
            is_confession_thread = (
                message.channel.name.startswith("Confession #") and
                message.channel.parent_id == self._channel_id
            )

            if is_confession_thread:
                logger.tree("Confession Thread Message Detected", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Thread", message.channel.name),
                    ("Content", message.content[:30] if message.content else "(empty)"),
                ], emoji="🔍")

                # Delete the message
                try:
                    await message.delete()
                    logger.tree("Confession Thread Message Deleted", [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                        ("Thread", message.channel.name),
                    ], emoji="🗑️")
                except discord.NotFound:
                    logger.tree("Thread Message Already Deleted", [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                        ("Thread", message.channel.name),
                    ], emoji="ℹ️")
                except discord.Forbidden:
                    logger.tree("Thread Message Delete Forbidden", [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                        ("Thread", message.channel.name),
                        ("Reason", "Missing permissions"),
                    ], emoji="⚠️")
                except discord.HTTPException as e:
                    logger.tree("Thread Message Delete Failed", [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                        ("Thread", message.channel.name),
                        ("Error", str(e)[:50]),
                    ], emoji="❌")

                # Warn user (only once per thread per user)
                warn_key = (message.channel.id, message.author.id)
                if warn_key not in self._warned_users:
                    self._warned_users[warn_key] = True
                    self._trim_cache(self._warned_users)
                    try:
                        embed = discord.Embed(
                            description=(
                                f"Hey {message.author.mention}! 👋\n\n"
                                "To keep identities hidden, please use `/reply` to respond to this confession anonymously."
                            ),
                            color=COLOR_WARNING
                        )
                        set_footer(embed)
                        warn_msg = await message.channel.send(embed=embed)
                        await warn_msg.delete(delay=DELETE_DELAY_MEDIUM)

                        logger.tree("Thread Reply Warning Sent", [
                            ("User", f"{message.author.name} ({message.author.display_name})"),
                            ("ID", str(message.author.id)),
                            ("Thread", message.channel.name),
                        ], emoji="⚠️")
                    except discord.HTTPException as e:
                        logger.tree("Thread Warning Failed", [
                            ("User", f"{message.author.name} ({message.author.display_name})"),
                            ("ID", str(message.author.id)),
                            ("Error", str(e)[:50]),
                        ], emoji="❌")
                else:
                    logger.tree("Thread Warning Skipped", [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                        ("Thread", message.channel.name),
                        ("Reason", "Already warned"),
                    ], emoji="ℹ️")

                return True

        return False

    async def _get_webhook(self, channel: discord.TextChannel) -> Optional[discord.Webhook]:
        """
        Get or create a webhook for anonymous replies.

        Args:
            channel: The confessions channel

        Returns:
            Webhook instance or None if failed
        """
        # Return cached webhook if available
        if self._webhook is not None:
            return self._webhook

        try:
            # Look for existing webhook
            webhooks = await channel.webhooks()
            for webhook in webhooks:
                if webhook.name == "Anonymous Confessions":
                    self._webhook = webhook
                    logger.tree("Webhook Found", [
                        ("Channel", channel.name),
                        ("Webhook ID", str(webhook.id)),
                    ], emoji="🔗")
                    return self._webhook

            # Create new webhook
            self._webhook = await channel.create_webhook(
                name="Anonymous Confessions",
                reason="For anonymous confession replies"
            )
            logger.tree("Webhook Created", [
                ("Channel", channel.name),
                ("Webhook ID", str(self._webhook.id)),
            ], emoji="🔗")
            return self._webhook

        except discord.Forbidden:
            logger.tree("Webhook Creation Forbidden", [
                ("Channel", channel.name),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
            return None
        except discord.HTTPException as e:
            logger.tree("Webhook Creation Failed", [
                ("Channel", channel.name),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return None

    def _get_avatar_url(self, letter: str, is_op: bool = False) -> str:
        """
        Generate an avatar URL for an anon-id using UI Avatars API.

        Args:
            letter: The letter for the avatar (A, B, C, etc.)
            is_op: Whether this is the OP (uses gold color)

        Returns:
            URL for the avatar image
        """
        if is_op:
            color = self.OP_COLOR
            name = "OP"
        else:
            # Get color based on letter index
            index = self.ANON_LETTERS.index(letter) if letter in self.ANON_LETTERS else 0
            color = self.ANON_COLORS[index % len(self.ANON_COLORS)]
            name = letter

        return f"https://ui-avatars.com/api/?name={name}&background={color}&color=fff&bold=true&size=128"

    def _get_anon_id(self, thread_id: int, user_id: int) -> str:
        """
        Get or generate an anonymous ID for a user in a thread.
        Uses hash-based assignment so the same user gets different letters
        in different threads (prevents pattern detection across threads).

        Args:
            thread_id: The thread ID
            user_id: The user ID

        Returns:
            Anon-ID like "Anon-A", "Anon-B", etc.
        """
        # Initialize thread tracking if needed
        if thread_id not in self._thread_anon_ids:
            self._thread_anon_ids[thread_id] = {}
            self._trim_cache(self._thread_anon_ids)

        thread_users = self._thread_anon_ids[thread_id]

        # Return existing ID if user already has one
        if user_id in thread_users:
            existing_id = thread_users[user_id]
            logger.tree("Anon-ID Reused", [
                ("Thread ID", str(thread_id)),
                ("ID", str(user_id)),
                ("Anon-ID", existing_id),
            ], emoji="🎭")
            return existing_id

        # Generate a hash-based letter index (different per thread+user combo)
        # This ensures the same user gets different letters in different threads
        hash_input = f"{thread_id}:{user_id}:syria_anon_salt"
        hash_value = hash(hash_input)
        base_index = abs(hash_value) % len(self.ANON_LETTERS)

        # Find an unused letter starting from the hash-based index
        used_ids = set(thread_users.values())
        for offset in range(len(self.ANON_LETTERS) + 26):  # Try all letters + overflow
            if offset < len(self.ANON_LETTERS):
                check_index = (base_index + offset) % len(self.ANON_LETTERS)
                candidate = f"Anon-{self.ANON_LETTERS[check_index]}"
            else:
                # Overflow: Anon-A1, Anon-B1, etc.
                overflow_offset = offset - len(self.ANON_LETTERS)
                letter = self.ANON_LETTERS[overflow_offset % len(self.ANON_LETTERS)]
                number = (overflow_offset // len(self.ANON_LETTERS)) + 1
                candidate = f"Anon-{letter}{number}"

            if candidate not in used_ids:
                anon_id = candidate
                break
        else:
            # Fallback (should never happen with 26+ slots)
            anon_id = f"Anon-{len(thread_users) + 1}"

        thread_users[user_id] = anon_id

        logger.tree("Anon-ID Assigned", [
            ("Thread ID", str(thread_id)),
            ("ID", str(user_id)),
            ("Anon-ID", anon_id),
        ], emoji="🎭")

        return anon_id

    async def check_rate_limit(self, user_id: int) -> Tuple[bool, Optional[int]]:
        """
        Check if user can submit a confession.

        Args:
            user_id: Discord user ID to check

        Returns:
            Tuple of (can_submit, seconds_remaining)
        """
        last_time = await asyncio.to_thread(db.get_user_last_confession_time, user_id)
        if last_time is None:
            return True, None

        elapsed = int(time.time()) - last_time
        if elapsed >= CONFESSION_COOLDOWN_SECONDS:
            return True, None

        remaining = CONFESSION_COOLDOWN_SECONDS - elapsed
        return False, remaining

    async def setup(self) -> None:
        """Initialize the confession service."""
        # Check if required channel is configured
        if not config.CONFESSIONS_CHANNEL_ID:
            logger.tree("Confessions Service", [
                ("Status", "Disabled"),
                ("Reason", "Missing CONFESSIONS_CHANNEL_ID"),
            ], emoji="ℹ️")
            return

        # Get the confessions channel
        channel = self.bot.get_channel(config.CONFESSIONS_CHANNEL_ID)
        if not channel:
            logger.tree("Confessions Service", [
                ("Status", "Error"),
                ("Reason", "Channel not found"),
                ("Channel ID", str(config.CONFESSIONS_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        if not isinstance(channel, discord.TextChannel):
            logger.tree("Confessions Service", [
                ("Status", "Error"),
                ("Reason", "Not a text channel"),
                ("Channel ID", str(config.CONFESSIONS_CHANNEL_ID)),
                ("Channel Type", type(channel).__name__),
            ], emoji="⚠️")
            return

        self._enabled = True
        self._channel_id = channel.id

        # Get stats for log
        stats = await asyncio.to_thread(db.get_confession_stats)

        logger.tree("Confessions Service Ready", [
            ("Channel", channel.name),
            ("Channel ID", str(channel.id)),
            ("Total Published", str(stats["approved"])),
            ("Commands", "`/confess`, `/reply`"),
            ("Auto-Approve", "Enabled"),
        ], emoji="✅")

    async def submit_confession(
        self,
        content: str,
        submitter: discord.Member
    ) -> bool:
        """
        Submit and auto-publish a confession.

        Args:
            content: The confession text (already stripped of mentions/emojis)
            submitter: Discord member who submitted

        Returns:
            True if submitted and published successfully
        """
        if not self._enabled:
            logger.tree("Confession Submit Blocked", [
                ("User", f"{submitter.name} ({submitter.display_name})"),
                ("ID", str(submitter.id)),
                ("Reason", "Service disabled"),
            ], emoji="⚠️")
            return False

        # Create confession in database
        confession_id = await asyncio.to_thread(db.create_confession, content, submitter.id, None)
        if confession_id is None:
            logger.tree("Confession Database Error", [
                ("User", f"{submitter.name} ({submitter.display_name})"),
                ("ID", str(submitter.id)),
                ("Reason", "Failed to create in database"),
            ], emoji="❌")
            return False

        # Auto-approve and publish
        confession_number = await asyncio.to_thread(db.approve_confession, confession_id, self.bot.user.id)
        if confession_number is None:
            logger.tree("Confession Auto-Approve Failed", [
                ("DB ID", str(confession_id)),
                ("User", f"{submitter.name}"),
                ("ID", str(submitter.id)),
                ("Reason", "Database approval failed"),
            ], emoji="❌")
            return False

        logger.tree("Confession Submitted", [
            ("Confession", f"#{confession_number}"),
            ("User", f"{submitter.name}"),
            ("ID", str(submitter.id)),
            ("Length", f"{len(content)} chars"),
        ], emoji="📝")

        # Store submitter for OP tracking in replies
        self._confession_submitters[confession_number] = submitter.id
        self._trim_cache(self._confession_submitters)

        # Publish to channel
        success = await self._publish_confession(confession_id, confession_number, content, submitter)

        if success:
            logger.tree("Confession Published", [
                ("Confession", f"#{confession_number}"),
                ("User", f"{submitter.name}"),
                ("ID", str(submitter.id)),
            ], emoji="📢")
        else:
            logger.tree("Confession Publish Failed", [
                ("Confession", f"#{confession_number}"),
                ("User", f"{submitter.name}"),
                ("ID", str(submitter.id)),
            ], emoji="❌")

        return success

    async def _publish_confession(
        self,
        confession_id: int,
        confession_number: int,
        content: str,
        submitter: discord.Member
    ) -> bool:
        """
        Publish a confession to the confessions channel.

        Args:
            confession_id: Database ID
            confession_number: Public confession number
            content: Confession text
            submitter: Who submitted (for logging)

        Returns:
            True if published successfully
        """
        channel = self.bot.get_channel(config.CONFESSIONS_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.tree("Confession Channel Not Found", [
                ("ID", str(confession_id)),
                ("Number", f"#{confession_number}"),
                ("Expected ID", str(config.CONFESSIONS_CHANNEL_ID)),
            ], emoji="⚠️")
            return False

        try:
            # Create the confession embed
            embed = discord.Embed(
                title=f"Anonymous Confession (#{confession_number})",
                description=f"```{content}```",
                color=COLOR_SYRIA_GREEN
            )

            # Add tutorial line
            embed.add_field(
                name="\u200b",
                value="*Use `/confess` to share yours*",
                inline=False
            )

            set_footer(embed)

            # Send the confession
            confession_msg = await channel.send(embed=embed)

            logger.tree("Confession Message Sent", [
                ("ID", str(confession_id)),
                ("Number", f"#{confession_number}"),
                ("Message ID", str(confession_msg.id)),
                ("Channel", channel.name),
            ], emoji="📨")

            # Add heart reaction
            try:
                await confession_msg.add_reaction(EMOJI_HEART)
                logger.tree("Confession Reaction Added", [
                    ("Number", f"#{confession_number}"),
                    ("Emoji", EMOJI_HEART),
                ], emoji="❤️")
            except discord.Forbidden:
                logger.tree("Confession Reaction Forbidden", [
                    ("Number", f"#{confession_number}"),
                    ("Reason", "Missing permissions"),
                ], emoji="⚠️")
            except discord.HTTPException as e:
                logger.tree("Confession Reaction Failed", [
                    ("Number", f"#{confession_number}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

            # Create thread for discussion
            thread: Optional[discord.Thread] = None
            try:
                thread = await confession_msg.create_thread(
                    name=f"Confession #{confession_number}",
                    auto_archive_duration=1440
                )

                logger.tree("Confession Thread Created", [
                    ("Number", f"#{confession_number}"),
                    ("Thread ID", str(thread.id)),
                    ("Thread Name", thread.name),
                ], emoji="🧵")

                # Send welcome message with reply button
                from src.services.confessions.views import ConfessionReplyView

                thread_embed = discord.Embed(
                    description=(
                        "💬 **Discussion Thread**\n\n"
                        "Click the button or use `/reply` to respond anonymously.\n"
                        "You'll get a unique ID (Anon-A, Anon-B, etc.)\n"
                        "The confessor shows as **OP** when they reply."
                    ),
                    color=COLOR_SYRIA_GREEN
                )
                set_footer(thread_embed)
                view = ConfessionReplyView(confession_number)
                await thread.send(embed=thread_embed, view=view)

                logger.tree("Thread Welcome Sent", [
                    ("Number", f"#{confession_number}"),
                    ("Thread", thread.name),
                ], emoji="👋")

            except discord.Forbidden:
                logger.tree("Thread Creation Forbidden", [
                    ("Number", f"#{confession_number}"),
                    ("Reason", "Missing permissions"),
                ], emoji="⚠️")
            except discord.HTTPException as e:
                logger.tree("Thread Creation Failed", [
                    ("Number", f"#{confession_number}"),
                    ("Error", str(e)[:50]),
                ], emoji="❌")

            # Send notification to general
            await self._send_notification(confession_msg, confession_number, thread)

            return True

        except discord.Forbidden:
            logger.tree("Confession Send Forbidden", [
                ("ID", str(confession_id)),
                ("Number", f"#{confession_number}"),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
            return False
        except discord.HTTPException as e:
            logger.tree("Confession Send Failed", [
                ("ID", str(confession_id)),
                ("Number", f"#{confession_number}"),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    async def post_anonymous_reply(
        self,
        thread: discord.Thread,
        content: str,
        user: discord.Member,
        confession_number: int
    ) -> bool:
        """
        Post an anonymous reply in a confession thread using webhook.

        Args:
            thread: The thread to post in
            content: The reply content
            user: The user who submitted (for logging)
            confession_number: The confession number

        Returns:
            True if posted successfully
        """
        try:
            # Check if user is the original confessor (OP)
            # First check in-memory cache, then fallback to database
            submitter_id = self._confession_submitters.get(confession_number)
            if submitter_id is None:
                # Fallback to database (handles bot restart case)
                submitter_id = await asyncio.to_thread(db.get_confession_submitter, confession_number)
                if submitter_id:
                    # Cache it for future lookups
                    self._confession_submitters[confession_number] = submitter_id
                    self._trim_cache(self._confession_submitters)
                    logger.tree("OP Loaded from Database", [
                        ("Confession", f"#{confession_number}"),
                        ("Submitter ID", str(submitter_id)),
                    ], emoji="📥")

            is_op = submitter_id is not None and user.id == submitter_id

            if is_op:
                author_name = "OP"
                avatar_url = self._get_avatar_url("", is_op=True)
                logger.tree("Reply from OP", [
                    ("User", f"{user.name}"),
                    ("ID", str(user.id)),
                    ("Confession", f"#{confession_number}"),
                ], emoji="👤")
            else:
                # Get or generate anon-id for this user in this thread
                anon_id = self._get_anon_id(thread.id, user.id)
                author_name = anon_id
                # Extract letter from anon_id (e.g., "Anon-A" -> "A")
                letter = anon_id.split("-")[-1][0] if "-" in anon_id else "A"
                avatar_url = self._get_avatar_url(letter)

            # Get the parent channel for webhook
            parent_channel = thread.parent
            if not parent_channel or not isinstance(parent_channel, discord.TextChannel):
                logger.tree("Reply Parent Channel Not Found", [
                    ("Thread", thread.name),
                    ("Confession", f"#{confession_number}"),
                ], emoji="⚠️")
                return False

            # Get or create webhook
            webhook = await self._get_webhook(parent_channel)
            if not webhook:
                logger.tree("Reply Webhook Unavailable", [
                    ("Thread", thread.name),
                    ("Confession", f"#{confession_number}"),
                    ("Reason", "Could not get/create webhook"),
                ], emoji="⚠️")
                return False

            # Send via webhook to the thread (with retry on failure)
            try:
                await webhook.send(
                    content=content,
                    username=author_name,
                    avatar_url=avatar_url,
                    thread=thread
                )
            except discord.NotFound:
                # Webhook was deleted, clear cache and retry once
                logger.tree("Webhook Deleted, Retrying", [
                    ("Thread", thread.name),
                    ("Confession", f"#{confession_number}"),
                ], emoji="🔄")
                self._webhook = None
                webhook = await self._get_webhook(parent_channel)
                if not webhook:
                    return False
                await webhook.send(
                    content=content,
                    username=author_name,
                    avatar_url=avatar_url,
                    thread=thread
                )

            logger.tree("Anonymous Reply Posted", [
                ("Anon-ID", author_name),
                ("User", f"{user.name}"),
                ("ID", str(user.id)),
                ("Confession", f"#{confession_number}"),
                ("Thread", thread.name),
                ("Length", f"{len(content)} chars"),
            ], emoji="💬")

            return True

        except discord.Forbidden:
            logger.tree("Anonymous Reply Forbidden", [
                ("User", f"{user.name}"),
                ("ID", str(user.id)),
                ("Confession", f"#{confession_number}"),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
            return False
        except discord.HTTPException as e:
            logger.tree("Anonymous Reply Failed", [
                ("User", f"{user.name}"),
                ("ID", str(user.id)),
                ("Confession", f"#{confession_number}"),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False

    async def _send_notification(
        self,
        confession_msg: discord.Message,
        confession_number: int,
        thread: Optional[discord.Thread] = None
    ) -> None:
        """
        Send notification to general chat about new confession.

        Args:
            confession_msg: The confession message
            confession_number: The confession number
            thread: Optional thread to link to
        """
        if not config.GENERAL_CHANNEL_ID:
            logger.tree("Confession Notification Skipped", [
                ("Number", f"#{confession_number}"),
                ("Reason", "GENERAL_CHANNEL_ID not configured"),
            ], emoji="ℹ️")
            return

        general_channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not general_channel:
            logger.tree("Confession Notification Skipped", [
                ("Number", f"#{confession_number}"),
                ("Reason", "General channel not found"),
            ], emoji="⚠️")
            return

        embed = discord.Embed(
            description=(
                f"{EMOJI_CONFESSION} **New Confession Posted**\n\n"
                f"Someone just shared **Confession #{confession_number}**\n"
                f"Head over to the confessions channel to read it!\n\n"
                f"Use `/confess` to share yours anonymously.\n"
                f"Use `/reply` in threads to respond anonymously!"
            ),
            color=COLOR_SYRIA_GREEN
        )
        set_footer(embed)

        # Use thread URL if available, otherwise confession message
        jump_url = thread.jump_url if thread else confession_msg.jump_url

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label=f"View Confession #{confession_number}",
            style=discord.ButtonStyle.link,
            url=jump_url,
            emoji=EMOJI_CONFESSION
        ))

        try:
            await general_channel.send(embed=embed, view=view)
            logger.tree("Confession Notification Sent", [
                ("Number", f"#{confession_number}"),
                ("Channel", general_channel.name),
            ], emoji="📢")
        except discord.Forbidden:
            logger.tree("Confession Notification Forbidden", [
                ("Number", f"#{confession_number}"),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("Confession Notification Failed", [
                ("Number", f"#{confession_number}"),
                ("Error", str(e)[:50]),
            ], emoji="❌")

    def stop(self) -> None:
        """Stop the confession service."""
        self._enabled = False
        logger.tree("Confessions Service Stopped", [], emoji="🛑")
