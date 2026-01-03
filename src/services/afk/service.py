"""
SyriaBot - AFK Service
======================

Dyno-style AFK system with nickname changes, mention notifications,
and ping tracking while away.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord.ext import commands

from src.core.logger import log
from src.core.colors import EMOJI_WAVE, EMOJI_MAILBOX, EMOJI_ZZZ
from src.services.database import db


class AFKService:
    """Service for managing AFK status."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log.tree("AFK Service Initialized", [], emoji="💤")

    async def set_afk(self, member: discord.Member, reason: str = "") -> bool:
        """
        Set a user as AFK.

        Returns True if nickname was changed.
        """
        # Set in database
        db.set_afk(
            user_id=member.id,
            guild_id=member.guild.id,
            reason=reason
        )
        log.tree("AFK Status Set", [
            ("User", f"{member.name} ({member.display_name})"),
            ("User ID", str(member.id)),
            ("Guild", member.guild.name),
            ("Reason", reason[:50] if reason else "None"),
        ], emoji="💤")

        # Add [AFK] prefix to nickname
        nickname_changed = False
        try:
            current_name = member.display_name
            if not current_name.startswith("[AFK] "):
                new_nick = f"[AFK] {current_name}"[:32]  # Discord limit
                await member.edit(nick=new_nick)
                nickname_changed = True
                log.tree("AFK Nickname Set", [
                    ("User", f"{member.name}"),
                    ("New Nick", new_nick),
                ], emoji="✏️")
            else:
                log.tree("AFK Nickname Skipped", [
                    ("User", f"{member.name}"),
                    ("Reason", "Already has [AFK] prefix"),
                ], emoji="ℹ️")
        except discord.Forbidden:
            log.tree("AFK Nickname Failed", [
                ("User", f"{member.name}"),
                ("Reason", "Missing permissions"),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            log.tree("AFK Nickname Failed", [
                ("User", f"{member.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        return nickname_changed

    async def on_message(self, message: discord.Message) -> None:
        """Handle AFK logic for a message - remove author's AFK and notify about mentioned AFKs."""
        if not message.guild:
            return

        guild_id = message.guild.id

        # Check if author is AFK and remove it
        was_afk = db.remove_afk(message.author.id, guild_id)
        if was_afk:
            await self._handle_return(message, guild_id)

        # Check if any mentioned users are AFK
        await self._handle_mentions(message, guild_id)

    async def _handle_return(self, message: discord.Message, guild_id: int) -> None:
        """Handle user returning from AFK."""
        # Get mention count while they were AFK
        mention_count = db.get_and_clear_afk_mentions(message.author.id, guild_id)

        # Remove [AFK] prefix from nickname
        if isinstance(message.author, discord.Member):
            try:
                current_nick = message.author.nick
                if current_nick and current_nick.startswith("[AFK] "):
                    new_nick = current_nick[6:]  # len("[AFK] ") = 6
                    if new_nick == message.author.name:
                        new_nick = None
                    await message.author.edit(nick=new_nick)
                    log.tree("AFK Nickname Removed", [
                        ("User", f"{message.author.name}"),
                        ("Old Nick", current_nick),
                        ("New Nick", new_nick or "None"),
                    ], emoji="✏️")
                else:
                    log.tree("AFK Nickname Not Changed", [
                        ("User", f"{message.author.name}"),
                        ("Reason", "No [AFK] prefix in nickname"),
                    ], emoji="ℹ️")
            except discord.Forbidden:
                log.tree("AFK Nickname Remove Failed", [
                    ("User", f"{message.author.name}"),
                    ("Reason", "Missing permissions"),
                ], emoji="⚠️")
            except discord.HTTPException as e:
                log.tree("AFK Nickname Remove Failed", [
                    ("User", f"{message.author.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        # Build welcome back message
        welcome_msg = f"{EMOJI_WAVE} Welcome back {message.author.mention}! Your AFK has been removed."
        if mention_count > 0:
            welcome_msg += f"\n{EMOJI_MAILBOX} You were mentioned **{mention_count}** time{'s' if mention_count != 1 else ''} while away."

        try:
            await message.reply(
                welcome_msg,
                mention_author=False,
                delete_after=8 if mention_count > 0 else 5
            )
            log.tree("AFK Auto-Removed", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("User ID", str(message.author.id)),
                ("Guild", message.guild.name),
                ("Mentions While AFK", str(mention_count)),
            ], emoji="👋")
        except discord.HTTPException as e:
            log.tree("AFK Welcome Back Failed", [
                ("User", str(message.author)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

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
                log.tree("AFK User Not In Guild", [
                    ("User ID", str(user_id)),
                    ("Guild", message.guild.name),
                    ("Reason", "Member left or not found"),
                ], emoji="⚠️")
                continue

            # Use Discord's relative timestamp format
            if reason:
                afk_messages.append(f"{EMOJI_ZZZ} **{member.display_name}** is AFK: {reason} (<t:{timestamp}:R>)")
            else:
                afk_messages.append(f"{EMOJI_ZZZ} **{member.display_name}** is AFK (<t:{timestamp}:R>)")

            # Track this mention for the AFK user
            db.increment_afk_mentions(user_id, guild_id)

        if afk_messages:
            try:
                await message.reply(
                    "\n".join(afk_messages),
                    mention_author=False,
                    delete_after=10
                )
                log.tree("AFK Mention Notification", [
                    ("Pinger", f"{message.author.name}"),
                    ("AFK Users", str(len(afk_messages))),
                    ("Guild", message.guild.name),
                ], emoji="💤")
            except discord.HTTPException as e:
                log.tree("AFK Notification Failed", [
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
