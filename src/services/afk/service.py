"""
SyriaBot - AFK Service
======================

Dyno-style AFK system with nickname changes, mention notifications,
and ping tracking while away.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import re
import time

import discord
from discord.ext import commands

from src.core.logger import logger
from src.services.database import db

# Constants
EMOJI_ZZZ = "💤"


class AFKService:
    """Service for managing AFK status."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def setup(self) -> None:
        """Initialize the AFK service."""
        logger.tree("AFK Service Ready", [], emoji="💤")

    def convert_emoji_shortcodes(self, text: str, guild: discord.Guild) -> str:
        """
        Convert :emoji: shortcodes to actual emojis.
        Looks up custom emojis in the guild.
        Cleans malformed emoji syntax from Discord picker.
        """
        if not text:
            return text

        # Safety check for DMs or missing guild
        if not guild:
            return text

        original_text = text

        # Check if input already has valid Discord emoji format - return unchanged
        # Valid: <:name:id> or <a:name:id>
        if re.search(r'<a?:\w+:\d{17,20}>', text):
            return text

        # Step 2: Remove malformed emoji syntax (leaked IDs without proper format)
        # Only remove IDs that look like broken emoji/mention syntax (preceded by : or <)
        text = re.sub(r'<[^>]*\d{17,20}[^>]*>', '', text)
        text = re.sub(r':\d{17,20}>?', '', text)  # :12345678901234567> patterns
        text = re.sub(r'<a?:\w*(?=\s|$)', '', text)  # Incomplete <a:name patterns

        # Step 3: Clean up extra spaces
        text = re.sub(r'\s+', ' ', text).strip()

        if not text or ":" not in text:
            return text

        # Step 4: Convert :emoji_name: shortcodes to Discord emoji format
        shortcode_pattern = re.compile(r':([a-zA-Z0-9_]+):')

        def replace_emoji(match):
            emoji_name = match.group(1)

            # Look up in guild emojis (case-insensitive)
            for emoji in guild.emojis:
                if emoji.name.lower() == emoji_name.lower():
                    if emoji.animated:
                        return f"<a:{emoji.name}:{emoji.id}>"
                    else:
                        return f"<:{emoji.name}:{emoji.id}>"

            # Not found in guild, return original shortcode
            return match.group(0)

        converted = shortcode_pattern.sub(replace_emoji, text)

        if converted != original_text:
            logger.tree("AFK Emoji Converted", [
                ("Original", original_text[:50]),
                ("Result", converted[:50]),
            ], emoji="✨")

        return converted

    async def set_afk(self, member: discord.Member, reason: str = "") -> tuple[bool, str]:
        """
        Set a user as AFK.

        Returns (nickname_changed, converted_reason).
        """
        # Convert emoji shortcodes in reason and truncate to prevent abuse
        converted_reason = self.convert_emoji_shortcodes(reason, member.guild) if reason else ""
        if len(converted_reason) > 200:
            converted_reason = converted_reason[:197] + "..."

        # Set in database
        db.set_afk(
            user_id=member.id,
            guild_id=member.guild.id,
            reason=converted_reason
        )
        logger.tree("AFK Status Set", [
            ("User", f"{member.name} ({member.display_name})"),
            ("ID", str(member.id)),
            ("Guild", member.guild.name),
            ("Reason", converted_reason[:50] if converted_reason else "None"),
        ], emoji="💤")

        # Add [AFK] prefix to nickname
        nickname_changed = False
        try:
            current_name = member.display_name
            if not current_name.startswith("[AFK] "):
                new_nick = f"[AFK] {current_name}"[:32]  # Discord limit
                await member.edit(nick=new_nick)
                nickname_changed = True
                logger.tree("AFK Nickname Set", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("New Nick", new_nick),
                ], emoji="✏️")
            else:
                logger.tree("AFK Nickname Skipped", [
                    ("User", f"{member.name} ({member.display_name})"),
                    ("Reason", "Already has [AFK] prefix"),
                ], emoji="ℹ️")
        except discord.Forbidden:
            logger.tree("AFK Nickname Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            logger.tree("AFK Nickname Failed", [
                ("User", f"{member.name} ({member.display_name})"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        return nickname_changed, converted_reason

    async def on_message(self, message: discord.Message) -> None:
        """Handle AFK logic for a message - remove author's AFK and notify about mentioned AFKs."""
        if not message.guild:
            return

        guild_id = message.guild.id

        # Check if author is AFK and remove it (returns timestamp if was AFK)
        afk_data = db.remove_afk(message.author.id, guild_id)
        if afk_data:
            await self._handle_return(message, guild_id, afk_data.get("timestamp", 0))

        # Check if any mentioned users are AFK
        await self._handle_mentions(message, guild_id)

    async def _handle_return(self, message: discord.Message, guild_id: int, afk_timestamp: int) -> None:
        """Handle user returning from AFK."""
        # Get mention count and pinger names while they were AFK
        mention_count, pinger_names = db.get_and_clear_afk_mentions(message.author.id, guild_id)

        # Calculate AFK duration
        duration_seconds = int(time.time()) - afk_timestamp
        duration_str = self._format_duration(duration_seconds)

        # Remove [AFK] prefix from nickname
        if isinstance(message.author, discord.Member):
            try:
                current_nick = message.author.nick
                if current_nick and current_nick.startswith("[AFK] "):
                    new_nick = current_nick[6:]  # len("[AFK] ") = 6
                    if new_nick == message.author.name:
                        new_nick = None
                    await message.author.edit(nick=new_nick)
                    logger.tree("AFK Nickname Removed", [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("Old Nick", current_nick),
                        ("New Nick", new_nick or "None"),
                    ], emoji="✏️")
                else:
                    logger.tree("AFK Nickname Not Changed", [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("Reason", "No [AFK] prefix in nickname"),
                    ], emoji="ℹ️")
            except discord.Forbidden:
                logger.tree("AFK Nickname Remove Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("Reason", "Missing permissions"),
                ], emoji="⚠️")
            except discord.HTTPException as e:
                logger.tree("AFK Nickname Remove Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        # Build welcome back message - clean design
        welcome_msg = f"Welcome back {message.author.mention}! Your AFK has been removed."
        welcome_msg += f"\n-# You were away for {duration_str}"

        if mention_count > 0:
            if pinger_names:
                # Show who mentioned them as plain usernames (no ping)
                mentions_str = ", ".join(f"**{name}**" for name in pinger_names)
                if mention_count > len(pinger_names):
                    # More mentions than unique pingers shown
                    welcome_msg += f" · Mentioned by {mentions_str} (+{mention_count - len(pinger_names)} more)"
                else:
                    welcome_msg += f" · Mentioned by {mentions_str}"
            else:
                welcome_msg += f" · {mention_count} mention{'s' if mention_count != 1 else ''}"

        try:
            await message.reply(
                welcome_msg,
                mention_author=False,
                delete_after=10 if mention_count > 0 else 5
            )
            logger.tree("AFK Auto-Removed", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Guild", message.guild.name),
                ("Duration", duration_str),
                ("Mentions", str(mention_count)),
                ("Pingers", ", ".join(pinger_names) if pinger_names else "None"),
            ], emoji="👋")
        except discord.HTTPException as e:
            logger.tree("AFK Welcome Back Failed", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    def _format_duration(self, seconds: int) -> str:
        """Format seconds into human readable duration."""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours}h {minutes}m"
            return f"{hours}h"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            if hours > 0:
                return f"{days}d {hours}h"
            return f"{days}d"

    async def _handle_mentions(self, message: discord.Message, guild_id: int) -> None:
        """Handle notifying about AFK users that were mentioned."""
        if not message.mentions:
            return

        # Get mentioned user IDs (excluding bots)
        mentioned_ids = [u.id for u in message.mentions if not u.bot]
        if not mentioned_ids:
            return

        # Query AFK status for all mentioned users at once
        afk_users = db.get_afk_users(mentioned_ids, guild_id)
        if not afk_users:
            return

        # Build notification message
        afk_messages = []
        for afk_data in afk_users:
            user_id = afk_data["user_id"]
            reason = afk_data["reason"]
            timestamp = afk_data["timestamp"]

            member = message.guild.get_member(user_id)
            if not member:
                logger.tree("AFK User Not In Guild", [
                    ("ID", str(user_id)),
                    ("Guild", message.guild.name),
                    ("Reason", "Member left or not found"),
                ], emoji="⚠️")
                continue

            # Use Discord's relative timestamp format
            if reason:
                afk_messages.append(f"{EMOJI_ZZZ} **{member.display_name}** is AFK: {reason} (<t:{timestamp}:R>)")
            else:
                afk_messages.append(f"{EMOJI_ZZZ} **{member.display_name}** is AFK (<t:{timestamp}:R>)")

            # Track this mention for the AFK user (with pinger info)
            db.increment_afk_mentions(
                user_id,
                guild_id,
                pinger_id=message.author.id,
                pinger_name=message.author.display_name  # Store display name (no ping)
            )

        if afk_messages:
            try:
                await message.reply(
                    "\n".join(afk_messages),
                    mention_author=False,
                    delete_after=10
                )
                logger.tree("AFK Mention Notification", [
                    ("Pinger", f"{message.author.name}"),
                    ("AFK Users", str(len(afk_messages))),
                    ("Guild", message.guild.name),
                ], emoji="💤")
            except discord.HTTPException as e:
                logger.tree("AFK Notification Failed", [
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
