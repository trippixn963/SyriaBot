"""
SyriaBot - Gallery Service
==========================

Instagram-style media channel with auto-threads, heart reactions,
and empty thread cleanup.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import time
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands, tasks

from src.core.logger import log
from src.core.config import config
from src.core.colors import COLOR_GOLD
from src.utils.footer import set_footer


class GalleryService:
    """Service for managing the gallery channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cleanup_task.start()
        log.tree("Gallery Service Initialized", [
            ("Channel ID", str(config.GALLERY_CHANNEL_ID)),
        ], emoji="📸")

    def stop(self):
        """Stop the cleanup task."""
        self.cleanup_task.cancel()
        log.tree("Gallery Service Stopped", [], emoji="📸")

    @tasks.loop(hours=1)
    async def cleanup_task(self):
        """Clean up empty gallery threads older than 1 hour."""
        if not config.GALLERY_CHANNEL_ID:
            return

        try:
            channel = self.bot.get_channel(config.GALLERY_CHANNEL_ID)
            if not channel:
                log.tree("Gallery Cleanup Skipped", [
                    ("Reason", "Channel not found"),
                ], emoji="⚠️")
                return

            now = time.time()
            deleted_count = 0

            for thread in channel.threads:
                # Check if thread is older than 1 hour
                thread_age = now - thread.created_at.timestamp()
                if thread_age < 3600:
                    continue

                # Check if thread has no messages
                if thread.message_count == 0:
                    try:
                        await thread.delete()
                        deleted_count += 1
                        log.tree("Gallery Empty Thread Deleted", [
                            ("Thread", thread.name),
                            ("Age", f"{int(thread_age // 3600)}h"),
                        ], emoji="🗑️")
                    except discord.HTTPException as e:
                        log.tree("Gallery Thread Delete Failed", [
                            ("Thread", thread.name),
                            ("Error", str(e)[:50]),
                        ], emoji="⚠️")

            if deleted_count > 0:
                log.tree("Gallery Cleanup Complete", [
                    ("Deleted", str(deleted_count)),
                ], emoji="🧹")

        except Exception as e:
            log.tree("Gallery Cleanup Error", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def on_message(self, message: discord.Message) -> bool:
        """
        Handle gallery channel message.

        Returns True if message was handled (valid or deleted).
        Returns False if not a gallery channel message.
        """
        if not message.guild or message.channel.id != config.GALLERY_CHANNEL_ID:
            return False

        # Check for valid image/video attachments (no GIFs)
        valid_media = False
        for attachment in message.attachments:
            content_type = attachment.content_type or ""
            filename = attachment.filename.lower()

            # Allow images (but not GIFs)
            if content_type.startswith("image/") and "gif" not in content_type:
                valid_media = True
                break
            # Allow videos
            elif content_type.startswith("video/"):
                valid_media = True
                break
            # Fallback: check extension (no GIFs)
            elif filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                valid_media = True
                break
            elif filename.endswith((".mp4", ".mov", ".webm", ".avi", ".mkv")):
                valid_media = True
                break

        if not valid_media:
            await self._delete_invalid(message)
            return True

        # Valid media - add heart and create thread
        await self._handle_valid_post(message)
        return True

    async def _delete_invalid(self, message: discord.Message) -> None:
        """Delete invalid gallery message."""
        try:
            await message.delete()
            log.tree("Gallery Message Deleted", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("User ID", str(message.author.id)),
                ("Reason", "No valid image/video attachment"),
                ("Content", message.content[:50] if message.content else "None"),
            ], emoji="🗑️")
        except discord.HTTPException as e:
            log.tree("Gallery Delete Failed", [
                ("User", f"{message.author.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def _handle_valid_post(self, message: discord.Message) -> None:
        """Handle a valid gallery post - add heart and create thread."""
        # Determine media type and get thumbnail URL
        is_video = False
        thumbnail_url = None
        for attachment in message.attachments:
            content_type = attachment.content_type or ""
            filename = attachment.filename.lower()

            if content_type.startswith("video/") or filename.endswith((".mp4", ".mov", ".webm", ".avi", ".mkv")):
                is_video = True
                break
            elif content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                thumbnail_url = attachment.url
                break

        # Add heart reaction
        try:
            await message.add_reaction(config.GALLERY_HEART_EMOJI)
            log.tree("Gallery Heart Added", [
                ("User", f"{message.author.name}"),
                ("Message ID", str(message.id)),
            ], emoji="❤️")
        except discord.HTTPException as e:
            log.tree("Gallery Heart Failed", [
                ("User", f"{message.author.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Create comment thread
        thread = None
        try:
            date_str = datetime.now().strftime("%b %-d")
            thread_name = f"📸 {message.author.display_name} • {date_str}"[:100]

            thread = await message.create_thread(
                name=thread_name,
                auto_archive_duration=10080,  # 7 days
            )
            log.tree("Gallery Thread Created", [
                ("User", f"{message.author.name}"),
                ("Thread", thread_name),
                ("Thread ID", str(thread.id)),
            ], emoji="💬")
        except discord.HTTPException as e:
            log.tree("Gallery Thread Failed", [
                ("User", f"{message.author.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

        # Send notification to general chat
        await self._send_notification(message, thread, is_video, thumbnail_url)

    async def _send_notification(
        self,
        message: discord.Message,
        thread: Optional[discord.Thread],
        is_video: bool = False,
        thumbnail_url: Optional[str] = None
    ) -> None:
        """Send a notification to general chat about a new gallery post."""
        if not config.GENERAL_CHANNEL_ID:
            log.tree("Gallery Notification Skipped", [
                ("Reason", "No general channel configured"),
            ], emoji="ℹ️")
            return

        general_channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not general_channel:
            log.tree("Gallery Notification Skipped", [
                ("Reason", "General channel not found"),
                ("Channel ID", str(config.GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        try:
            # Build embed
            media_type = "🎬 video" if is_video else "🖼️ image"
            embed = discord.Embed(
                title="🔔 New Gallery Post",
                description=f"Posted a new {media_type}",
                color=COLOR_GOLD
            )
            embed.set_author(name=message.author.display_name)
            if thumbnail_url:
                embed.set_image(url=thumbnail_url)
            set_footer(embed)

            # Create view with comment button if thread exists
            view = None
            if thread:
                view = discord.ui.View()
                comment_button = discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label="Comment",
                    emoji=discord.PartialEmoji.from_str("<:comment:1456791204636135507>"),
                    url=thread.jump_url
                )
                view.add_item(comment_button)

            await general_channel.send(embed=embed, view=view)
            log.tree("Gallery Notification Sent", [
                ("User", f"{message.author.name}"),
                ("Channel", general_channel.name),
                ("Post ID", str(message.id)),
                ("Media Type", "Video" if is_video else "Image"),
                ("Thread", thread.name if thread else "None"),
            ], emoji="📢")
        except discord.Forbidden:
            log.tree("Gallery Notification Failed", [
                ("Reason", "Missing permissions"),
                ("Channel", str(config.GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
        except discord.HTTPException as e:
            log.tree("Gallery Notification Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> bool:
        """
        Handle reaction in gallery - only allow heart emoji.

        Returns True if reaction was handled (gallery channel).
        Returns False if not a gallery channel reaction.
        """
        if reaction.message.channel.id != config.GALLERY_CHANNEL_ID:
            return False

        # Check if it's the allowed heart emoji
        emoji_str = str(reaction.emoji)
        if emoji_str != config.GALLERY_HEART_EMOJI:
            try:
                await reaction.remove(user)
                log.tree("Gallery Reaction Removed", [
                    ("User", f"{user.name}"),
                    ("Emoji", emoji_str[:20]),
                    ("Message ID", str(reaction.message.id)),
                ], emoji="🚫")
            except discord.HTTPException as e:
                log.tree("Gallery Reaction Remove Failed", [
                    ("User", f"{user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

        return True
