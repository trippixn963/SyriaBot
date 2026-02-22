"""
SyriaBot - Message Handler
==========================

Thin dispatcher that delegates to specialized handlers.
Coordinates: FunHandler, ActionHandler, ReplyHandler.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import re

import discord
from discord.ext import commands

from src.core.logger import logger
from src.core.config import config
from src.core.constants import DISBOARD_BOT_ID
from src.services.bump import bump_service
from src.services.database import db
from src.api.services.websocket import get_ws_manager
from src.handlers.fun import fun
from src.handlers.action import action
from src.handlers.reply import ReplyHandler
from src.handlers.faq import faq
from src.api.services.event_logger import event_logger

# URL regex pattern for link tracking
URL_PATTERN = re.compile(r'https?://\S+')


class MessageHandler(commands.Cog):
    """
    Central message handler that dispatches to specialized handlers.

    DESIGN:
        Acts as thin coordinator, routing messages to:
        - FunHandler: Fun responses and reactions
        - ActionHandler: Action GIF commands (slap, hug, etc.)
        - ReplyHandler: Reply-based commands (convert, quote, translate)
        - FAQHandler: Automatic FAQ responses
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the message handler.

        Args:
            bot: Main bot instance for Discord API access.
        """
        self.bot = bot
        self.reply = ReplyHandler(bot)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages - dispatch to specialized handlers."""
        # Check for Disboard bump confirmation (before skipping bots)
        if message.author.id == DISBOARD_BOT_ID:
            if message.embeds:
                for embed in message.embeds:
                    desc = (embed.description or "").lower()
                    if "bump done" in desc:
                        bump_service.record_bump()
                        # Log to events system (for dashboard Events tab)
                        event_logger.log_bump(message.guild)
                        break
            return

        if message.author.bot:
            return

        # Confession channel (auto-delete messages to keep it clean)
        if hasattr(self.bot, 'confession_service') and self.bot.confession_service:
            try:
                if await self.bot.confession_service.handle_message(message):
                    return  # Message was deleted
            except Exception as e:
                logger.error_tree("Confession Handler Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])


        # Gallery service (media-only channel)
        if hasattr(self.bot, 'gallery_service') and self.bot.gallery_service:
            try:
                if await self.bot.gallery_service.on_message(message):
                    return  # Gallery handled it
            except Exception as e:
                logger.error_tree("Gallery Handler Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Channel", str(message.channel.id)),
                ])

        # TempVoice sticky panel
        if hasattr(self.bot, 'tempvoice') and self.bot.tempvoice:
            try:
                await self.bot.tempvoice.on_message(message)
            except Exception as e:
                logger.error_tree("TempVoice Handler Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # Roulette activity tracking (for spawn timing)
        if hasattr(self.bot, 'roulette_service') and self.bot.roulette_service:
            try:
                self.bot.roulette_service.on_message(message)
            except Exception as e:
                logger.error_tree("Roulette Activity Track Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # Track message count (every message, regardless of XP cooldown)
        if message.guild and message.guild.id == config.GUILD_ID:
            try:
                # Increment message count and get new total
                new_total = await asyncio.to_thread(
                    db.increment_message_count,
                    message.author.id,
                    message.guild.id
                )

                # Broadcast to WebSocket clients immediately
                ws_manager = get_ws_manager()
                if ws_manager.connection_count > 0:
                    await ws_manager.broadcast_message_count(new_total)
            except Exception as e:
                logger.error_tree("Message Count Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # XP gain from messages (with cooldown)
        if hasattr(self.bot, 'xp_service') and self.bot.xp_service:
            try:
                await self.bot.xp_service.on_message(message)
            except Exception as e:
                logger.error_tree("XP Handler Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # Track images shared (non-blocking)
        if message.guild and message.guild.id == config.GUILD_ID and message.attachments:
            try:
                await asyncio.to_thread(db.increment_images_shared, message.author.id, message.guild.id)
            except Exception as e:
                logger.error_tree("Image Track Failed", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # =================================================================
        # Social Interaction Tracking (mentions + replies)
        # =================================================================
        # We handle these together because Discord includes the replied-to
        # user in message.mentions, so we need to exclude them to avoid
        # double-counting. Fetch replied-to author ONCE and reuse.
        # =================================================================

        if message.guild and message.guild.id == config.GUILD_ID:
            replied_to_author: discord.Member | None = None

            # Determine replied-to author (if this is a reply)
            if message.reference and message.reference.message_id:
                try:
                    # Try cached first (fast path)
                    ref_msg = message.reference.resolved
                    if not ref_msg:
                        # Not cached, fetch from API (slow path)
                        ref_msg = await message.channel.fetch_message(message.reference.message_id)

                    if ref_msg and ref_msg.author and not ref_msg.author.bot:
                        if ref_msg.author.id != message.author.id:
                            replied_to_author = ref_msg.author
                except discord.NotFound:
                    pass  # Original message was deleted
                except discord.HTTPException as e:
                    logger.error_tree("Reply Fetch Failed", e, [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                        ("Reference", str(message.reference.message_id)),
                    ])

            # Track replies (if we found a valid replied-to author)
            if replied_to_author:
                try:
                    # Track reply count in user_xp
                    await asyncio.to_thread(
                        db.increment_replies_sent,
                        message.author.id,
                        message.guild.id
                    )
                    # Track interaction (who they replied to)
                    await asyncio.to_thread(
                        db.increment_interaction_reply,
                        message.author.id,
                        replied_to_author.id,
                        message.guild.id
                    )
                except Exception as e:
                    logger.error_tree("Reply Track Failed", e, [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                        ("Replied To", str(replied_to_author.id)),
                    ])

            # Track mentions (excluding replied-to user to avoid double-counting)
            if message.mentions:
                try:
                    replied_to_id = replied_to_author.id if replied_to_author else None
                    valid_mentions = [
                        m for m in message.mentions
                        if m.id != message.author.id and not m.bot and m.id != replied_to_id
                    ]
                    for mentioned_user in valid_mentions:
                        # Track in user_xp (mentions_received for the mentioned user)
                        await asyncio.to_thread(
                            db.increment_mentions_received,
                            mentioned_user.id,
                            message.guild.id,
                            1
                        )
                        # Track in user_interactions (who the author mentions)
                        await asyncio.to_thread(
                            db.increment_interaction_mention,
                            message.author.id,
                            mentioned_user.id,
                            message.guild.id
                        )
                except Exception as e:
                    logger.error_tree("Mention Track Failed", e, [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                    ])

        # Track links shared (non-blocking)
        if message.guild and message.guild.id == config.GUILD_ID:
            if URL_PATTERN.search(message.content):
                try:
                    await asyncio.to_thread(
                        db.increment_links_shared,
                        message.author.id,
                        message.guild.id
                    )
                except Exception as e:
                    logger.error_tree("Link Track Failed", e, [
                        ("User", f"{message.author.name} ({message.author.display_name})"),
                        ("ID", str(message.author.id)),
                    ])

        # AFK service
        if message.guild and hasattr(self.bot, 'afk_service') and self.bot.afk_service:
            try:
                await self.bot.afk_service.on_message(message)
            except Exception as e:
                logger.error_tree("AFK Handler Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # FAQ auto-responder (watches for questions)
        if message.guild:
            try:
                if await faq.handle(message):
                    return  # FAQ was sent
            except Exception as e:
                logger.error_tree("FAQ Handler Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # Action commands (slap @user, hug @user, cry, etc.)
        if message.guild:
            try:
                if await action.handle(message):
                    return  # Action was handled
            except Exception as e:
                logger.error_tree("Action Handler Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # Fun commands (ship, howsimp, howgay, howsmart, howfat)
        if message.guild:
            try:
                if await fun.handle(message):
                    return  # Fun command was handled
            except Exception as e:
                logger.error_tree("Fun Handler Error", e, [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                ])

        # Reply commands (convert, quote, translate, download)
        try:
            if await self.reply.handle(message):
                return  # Reply command was handled
        except Exception as e:
            logger.error_tree("Reply Handler Error", e, [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
            ])

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> None:
        """Track reactions and delegate to services."""
        if user.bot:
            return

        if not reaction.message.guild:
            return

        # Gallery service handles its reactions
        if hasattr(self.bot, 'gallery_service') and self.bot.gallery_service:
            try:
                if await self.bot.gallery_service.on_reaction_add(reaction, user):
                    return  # Gallery handled it
            except Exception as e:
                logger.error_tree("Gallery Reaction Handler Error", e, [
                    ("User", f"{user.name} ({user.display_name})"),
                    ("ID", str(user.id)),
                ])

        # Track reactions in main server (non-blocking)
        if reaction.message.guild.id != config.GUILD_ID:
            return

        try:
            # Track reaction given by user
            await asyncio.to_thread(db.increment_reactions_given, user.id, reaction.message.guild.id)

            # Track reaction received by message author (if not a bot and not self-react)
            if reaction.message.author and not reaction.message.author.bot:
                if reaction.message.author.id != user.id:
                    await asyncio.to_thread(
                        db.increment_reactions_received,
                        reaction.message.author.id,
                        reaction.message.guild.id
                    )
        except Exception as e:
            logger.error_tree("Reaction Track Failed", e, [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
            ])

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        """Track thread creation."""
        if not thread.guild or thread.guild.id != config.GUILD_ID:
            return

        if thread.owner_id:
            try:
                await asyncio.to_thread(
                    db.increment_threads_created,
                    thread.owner_id,
                    thread.guild.id
                )
                # Log to events system (for dashboard Events tab)
                owner = thread.guild.get_member(thread.owner_id)
                event_logger.log_thread_create(thread, owner)
            except Exception as e:
                logger.error_tree("Thread Track Failed", e, [
                    ("Thread", thread.name),
                    ("Owner", str(thread.owner_id)),
                ])

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """Handle raw message deletions for persistent panels and event logging."""
        # Actions panel auto-resend on delete
        if hasattr(self.bot, 'actions_panel') and self.bot.actions_panel:
            try:
                await self.bot.actions_panel.handle_message_delete(payload.message_id)
            except Exception as e:
                logger.error_tree("Actions Panel Delete Handler Error", e, [
                    ("Message ID", str(payload.message_id)),
                ])

        # Log message delete to events (only for main server)
        if payload.guild_id == config.GUILD_ID:
            try:
                guild = self.bot.get_guild(payload.guild_id)
                channel = guild.get_channel(payload.channel_id) if guild else None

                # Get cached message info if available
                author = None
                content = None
                if payload.cached_message:
                    author = payload.cached_message.author
                    content = payload.cached_message.content
                    # Skip bot messages
                    if author and author.bot:
                        return

                if guild and channel:
                    event_logger.log_message_delete(guild, channel, author, content)
            except Exception as e:
                logger.error_tree("Message Delete Event Log Error", e, [
                    ("Message ID", str(payload.message_id)),
                ])

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        """Handle bulk message deletions (purge commands)."""
        if payload.guild_id != config.GUILD_ID:
            return

        try:
            guild = self.bot.get_guild(payload.guild_id)
            channel = guild.get_channel(payload.channel_id) if guild else None

            if guild and channel:
                event_logger.log_bulk_delete(guild, channel, len(payload.message_ids))
        except Exception as e:
            logger.error_tree("Bulk Delete Event Log Error", e, [
                ("Channel ID", str(payload.channel_id)),
                ("Count", str(len(payload.message_ids))),
            ])

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Handle message edits for event logging."""
        # Skip bots and DMs
        if after.author.bot or not after.guild:
            return

        # Only track in main server
        if after.guild.id != config.GUILD_ID:
            return

        # Skip if content didn't change (could be embed update)
        if before.content == after.content:
            return

        try:
            event_logger.log_message_edit(
                after.guild,
                after.channel,
                after.author,
                before.content,
                after.content
            )
        except Exception as e:
            logger.error_tree("Message Edit Event Log Error", e, [
                ("Author", str(after.author.id)),
                ("Channel", str(after.channel.id)),
            ])

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Handle channel creation for event logging."""
        if channel.guild.id != config.GUILD_ID:
            return

        # Try to get creator from audit log
        creator = None
        try:
            async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
                if entry.target and entry.target.id == channel.id:
                    creator = entry.user
                    break
        except discord.Forbidden:
            pass

        event_logger.log_channel_create(channel, creator)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Handle channel deletion for event logging."""
        if channel.guild.id != config.GUILD_ID:
            return

        # Try to get deleter from audit log
        deleter = None
        try:
            async for entry in channel.guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
                if entry.target and entry.target.id == channel.id:
                    deleter = entry.user
                    break
        except discord.Forbidden:
            pass

        event_logger.log_channel_delete(channel, deleter)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        """Handle thread deletion for event logging."""
        if not thread.guild or thread.guild.id != config.GUILD_ID:
            return

        # Try to get deleter from audit log
        deleter = None
        try:
            async for entry in thread.guild.audit_logs(limit=5, action=discord.AuditLogAction.thread_delete):
                if entry.target and entry.target.id == thread.id:
                    deleter = entry.user
                    break
        except discord.Forbidden:
            pass

        event_logger.log_thread_delete(thread, deleter)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """Handle role creation for event logging."""
        if role.guild.id != config.GUILD_ID:
            return

        # Try to get creator from audit log
        creator = None
        try:
            async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_create):
                if entry.target and entry.target.id == role.id:
                    creator = entry.user
                    break
        except discord.Forbidden:
            pass

        event_logger.log_role_create(role, creator)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Handle role deletion for event logging."""
        if role.guild.id != config.GUILD_ID:
            return

        # Try to get deleter from audit log
        deleter = None
        try:
            async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_delete):
                if entry.target and entry.target.id == role.id:
                    deleter = entry.user
                    break
        except discord.Forbidden:
            pass

        event_logger.log_role_delete(role, deleter)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Handle role update for event logging."""
        if after.guild.id != config.GUILD_ID:
            return

        # Only log if something meaningful changed
        if before.name == after.name and before.color == after.color and before.permissions == after.permissions:
            return

        # Try to get updater from audit log
        updater = None
        try:
            async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_update):
                if entry.target and entry.target.id == after.id:
                    updater = entry.user
                    break
        except discord.Forbidden:
            pass

        event_logger.log_role_update(before, after, updater)

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: tuple[discord.Emoji, ...],
        after: tuple[discord.Emoji, ...]
    ) -> None:
        """Handle emoji create/delete for event logging."""
        if guild.id != config.GUILD_ID:
            return

        before_ids = {e.id for e in before}
        after_ids = {e.id for e in after}

        # Find added emojis
        added_ids = after_ids - before_ids
        for emoji in after:
            if emoji.id in added_ids:
                # Try to get creator from audit log
                creator = None
                try:
                    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.emoji_create):
                        if entry.target and entry.target.id == emoji.id:
                            creator = entry.user
                            break
                except discord.Forbidden:
                    pass
                event_logger.log_emoji_create(emoji, creator)

        # Find removed emojis
        removed_ids = before_ids - after_ids
        for emoji in before:
            if emoji.id in removed_ids:
                # Try to get deleter from audit log
                deleter = None
                try:
                    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.emoji_delete):
                        if entry.target and entry.target.id == emoji.id:
                            deleter = entry.user
                            break
                except discord.Forbidden:
                    pass
                event_logger.log_emoji_delete(emoji, deleter)


async def setup(bot: commands.Bot) -> None:
    """Register the message handler cog with the bot."""
    await bot.add_cog(MessageHandler(bot))
    logger.tree("Handler Loaded", [
        ("Name", "MessageHandler"),
        ("Delegates", "Fun, Action, Reply"),
    ], emoji="✅")
