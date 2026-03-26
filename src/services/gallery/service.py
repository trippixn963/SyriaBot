"""
SyriaBot - Gallery Service
==========================

Heart reactions, guides, and notifications for Discord media channel.
Media validation and thread creation handled natively by Discord.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import io
from datetime import datetime

import discord
from discord.ext import commands

from src.core.logger import logger
from src.core.config import config
from src.core.colors import COLOR_GOLD, EMOJI_HEART, EMOJI_COMMENT
from src.core.constants import TIMEZONE_EST
from src.utils.divider import send_divider
from src.services.gallery.graphics import render_gallery_guide


class GalleryService:
    """
    Service for the gallery media channel.

    Discord handles media validation and thread creation.
    This service adds: heart reactions, guide graphic, divider,
    notifications to general, and reaction filtering.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def setup(self) -> None:
        """Initialize the gallery service."""
        logger.tree("Gallery Service Ready", [
            ("Channel ID", str(config.GALLERY_CHANNEL_ID)),
            ("Mode", "Discord Media Channel"),
        ], emoji="📸")

    def stop(self) -> None:
        """Stop the gallery service."""
        logger.tree("Gallery Service Stopped", [], emoji="📸")

    def _is_gallery(self, channel_id: int) -> bool:
        """Check if a channel is the gallery media channel."""
        return channel_id == config.GALLERY_CHANNEL_ID

    async def on_thread_create(self, thread: discord.Thread) -> bool:
        """
        Handle new post in gallery media channel.

        Returns True if handled, False if not the gallery.
        """
        if not thread.parent_id or not self._is_gallery(thread.parent_id):
            return False

        # Fetch the starter message (contains the media)
        starter = thread.starter_message
        if not starter:
            await asyncio.sleep(1)
            try:
                starter = await thread.fetch_message(thread.id)
            except discord.NotFound:
                try:
                    async for msg in thread.history(limit=1, oldest_first=True):
                        starter = msg
                        break
                except Exception:
                    pass

        if not starter or starter.author.bot:
            return False

        logger.tree("Gallery Post Detected", [
            ("User", f"{starter.author.name} ({starter.author.display_name})"),
            ("ID", str(starter.author.id)),
            ("Attachments", str(len(starter.attachments))),
        ], emoji="📸")

        # Rename thread: 📅 MM-DD-YY | Username
        try:
            date_str = datetime.now(TIMEZONE_EST).strftime("%m-%d-%y")
            new_name = f"📅 {date_str} | {starter.author.display_name}"[:100]
            await thread.edit(name=new_name)
        except discord.HTTPException as e:
            logger.error_tree("Gallery Rename Failed", e, [
                ("Thread", thread.name[:30]),
            ])

        # Add heart reaction
        try:
            await starter.add_reaction(EMOJI_HEART)
        except discord.HTTPException as e:
            logger.error_tree("Gallery Heart Failed", e, [
                ("User", f"{starter.author.name}"),
            ])

        # Detect media type
        is_video = False
        for attachment in starter.attachments:
            content_type = attachment.content_type or ""
            filename = attachment.filename.lower()
            if content_type.startswith("video/") or filename.endswith((".mp4", ".mov", ".webm", ".avi", ".mkv")):
                is_video = True
                break

        # Send gallery guide + divider inside the thread
        try:
            guide_bytes = await render_gallery_guide()
            if guide_bytes:
                await thread.send(file=discord.File(io.BytesIO(guide_bytes), "gallery_guide.png"))
                await send_divider(thread)
        except Exception as e:
            logger.error_tree("Gallery Guide Send Failed", e)

        # Send notification to general chat
        await self._send_notification(starter, thread, is_video)

        return True

    async def on_message(self, message: discord.Message) -> bool:
        """Check if message is in gallery (handled by on_thread_create)."""
        if not message.guild:
            return False
        parent_id = getattr(message.channel, 'parent_id', None)
        if parent_id and self._is_gallery(parent_id):
            return True
        return False

    async def _send_notification(
        self,
        message: discord.Message,
        thread: discord.Thread,
        is_video: bool = False,
    ) -> None:
        """Send a notification to general chat about a new gallery post."""
        if not config.GENERAL_CHANNEL_ID:
            return

        general_channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not general_channel:
            return

        try:
            media_type = "🎬 video" if is_video else "🖼️ image"

            embed = discord.Embed(
                title="🔔 New Gallery Post",
                description=f"<@{message.author.id}> posted a new {media_type}",
                color=COLOR_GOLD,
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)

            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="View Post",
                emoji=discord.PartialEmoji.from_str(EMOJI_COMMENT),
                url=thread.jump_url,
            ))

            await general_channel.send(embed=embed, view=view)
            logger.tree("Gallery Notification Sent", [
                ("User", f"{message.author.name}"),
                ("Media Type", "Video" if is_video else "Image"),
            ], emoji="📢")
        except discord.HTTPException as e:
            logger.error_tree("Gallery Notification Failed", e)

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> bool:
        """
        Handle reaction in gallery — only allow heart emoji.

        Returns True if handled, False if not the gallery.
        """
        parent_id = getattr(reaction.message.channel, 'parent_id', None) or reaction.message.channel.id
        if not self._is_gallery(parent_id):
            return False

        if str(reaction.emoji) != EMOJI_HEART:
            try:
                await reaction.remove(user)
            except discord.HTTPException:
                pass

        return True
