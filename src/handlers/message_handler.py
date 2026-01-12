"""
SyriaBot - Message Handler
==========================

Thin dispatcher that delegates to specialized handlers.
Coordinates: FunHandler, ActionHandler, ReplyHandler.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio

import discord
from discord.ext import commands

from src.core.logger import log
from src.core.config import config
from src.services.bump_service import bump_service
from src.services.database import db
from src.handlers.fun_handler import fun_handler
from src.handlers.action_handler import action_handler
from src.handlers.reply_handler import ReplyHandler
from src.handlers.faq_handler import faq_handler

# Disboard bot ID
DISBOARD_BOT_ID = 302050872383242240


class MessageHandler(commands.Cog):
    """Handles message events - thin dispatcher to specialized handlers."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the message handler with bot reference."""
        self.bot = bot
        self.reply_handler = ReplyHandler(bot)

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
                        break
            return

        if message.author.bot:
            return

        # City game - track activity and check guesses
        if hasattr(self.bot, 'city_game_service') and self.bot.city_game_service:
            try:
                # Track message for inactivity
                self.bot.city_game_service.on_message(message.channel.id)
                # Check if this is a correct guess
                await self.bot.city_game_service.check_guess(message)
            except Exception as e:
                log.tree("City Game Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # Confession channel (auto-delete messages to keep it clean)
        if hasattr(self.bot, 'confession_service') and self.bot.confession_service:
            try:
                if await self.bot.confession_service.handle_message(message):
                    return  # Message was deleted
            except Exception as e:
                log.tree("Confession Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # Suggestions channel (auto-delete messages to keep it clean)
        if hasattr(self.bot, 'suggestion_service') and self.bot.suggestion_service:
            try:
                if await self.bot.suggestion_service.handle_message(message):
                    return  # Message was deleted
            except Exception as e:
                log.tree("Suggestion Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # Gallery service (media-only channel)
        if hasattr(self.bot, 'gallery_service') and self.bot.gallery_service:
            try:
                if await self.bot.gallery_service.on_message(message):
                    return  # Gallery handled it
            except Exception as e:
                log.tree("Gallery Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # TempVoice sticky panel
        if hasattr(self.bot, 'tempvoice') and self.bot.tempvoice:
            try:
                await self.bot.tempvoice.on_message(message)
            except Exception as e:
                log.tree("TempVoice Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # XP gain from messages
        if hasattr(self.bot, 'xp_service') and self.bot.xp_service:
            try:
                await self.bot.xp_service.on_message(message)
            except Exception as e:
                log.tree("XP Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # Track images shared (non-blocking)
        if message.guild and message.guild.id == config.GUILD_ID and message.attachments:
            try:
                await asyncio.to_thread(db.increment_images_shared, message.author.id, message.guild.id)
            except Exception as e:
                log.tree("Image Track Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        # AFK service
        if message.guild and hasattr(self.bot, 'afk_service') and self.bot.afk_service:
            try:
                await self.bot.afk_service.on_message(message)
            except Exception as e:
                log.tree("AFK Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # FAQ auto-responder (watches for questions)
        if message.guild:
            try:
                if await faq_handler.handle(message):
                    return  # FAQ was sent
            except Exception as e:
                log.tree("FAQ Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # Action commands (slap @user, hug @user, cry, etc.)
        if message.guild:
            try:
                if await action_handler.handle(message):
                    return  # Action was handled
            except Exception as e:
                log.tree("Action Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # Fun commands (ship, simp, howgay, howsmart, bodyfat)
        if message.guild:
            try:
                if await fun_handler.handle(message):
                    return  # Fun command was handled
            except Exception as e:
                log.tree("Fun Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # Reply commands (convert, quote, translate, download)
        try:
            if await self.reply_handler.handle(message):
                return  # Reply command was handled
        except Exception as e:
            log.tree("Reply Handler Error", [
                ("Error", str(e)[:50]),
            ], emoji="❌")

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
                log.tree("Gallery Reaction Handler Error", [
                    ("Error", str(e)[:50]),
                ], emoji="❌")

        # Track reactions in main server (non-blocking)
        if reaction.message.guild.id != config.GUILD_ID:
            return

        try:
            await asyncio.to_thread(db.increment_reactions_given, user.id, reaction.message.guild.id)
        except Exception as e:
            log.tree("Reaction Track Failed", [
                ("User", f"{user.name} ({user.display_name})"),
                ("ID", str(user.id)),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")


async def setup(bot: commands.Bot) -> None:
    """Register the message handler cog with the bot."""
    await bot.add_cog(MessageHandler(bot))
    log.tree("Handler Loaded", [
        ("Name", "MessageHandler"),
        ("Delegates", "Fun, Action, Reply"),
    ], emoji="✅")
