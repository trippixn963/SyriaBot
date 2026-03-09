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

from src.core.logger import logger
from src.core.config import config
from src.core.colors import COLOR_GOLD, EMOJI_HEART, EMOJI_COMMENT
from src.core.constants import TIMEZONE_EST


class GalleryService:
    """
    Service for managing gallery and memes channels.

    DESIGN:
        Instagram-style media channels with automatic features:
        - Validates media (images/videos only, no GIFs)
        - Adds heart reactions and creates comment threads
        - Sends notifications to general chat
        - Removes invalid messages automatically
    """

    # Channel types for identification
    GALLERY = "gallery"
    MEMES = "memes"

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialize the gallery service.

        Args:
            bot: Main bot instance for Discord API access.
        """
        self.bot = bot
        # Cleanup disabled - let Discord's 7-day auto-archive handle empty threads
        # self.cleanup_task.start()

    async def setup(self) -> None:
        """Initialize the gallery service."""
        logger.tree("Gallery Service Ready", [
            ("Gallery ID", str(config.GALLERY_CHANNEL_ID)),
            ("Memes ID", str(config.MEMES_CHANNEL_ID)),
            ("Thread Cleanup", "Disabled"),
        ], emoji="📸")

    def stop(self) -> None:
        """Stop the cleanup task (if running)."""
        if self.cleanup_task.is_running():
            self.cleanup_task.cancel()
        logger.tree("Gallery Service Stopped", [], emoji="📸")

    @tasks.loop(hours=1)
    async def cleanup_task(self) -> None:
        """Clean up empty threads older than 1 hour from gallery and memes channels."""
        channel_ids = [
            (config.GALLERY_CHANNEL_ID, "Gallery"),
            (config.MEMES_CHANNEL_ID, "Memes"),
        ]

        for channel_id, channel_name in channel_ids:
            if not channel_id:
                continue

            try:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    logger.tree(f"{channel_name} Cleanup Skipped", [
                        ("Reason", "Channel not found"),
                    ], emoji="⚠️")
                    continue

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
                            logger.tree(f"{channel_name} Empty Thread Deleted", [
                                ("Thread", thread.name),
                                ("Age", f"{int(thread_age // 3600)}h"),
                            ], emoji="🗑️")
                        except discord.HTTPException as e:
                            logger.error_tree(f"{channel_name} Thread Delete Failed", e, [
                                ("Thread", thread.name),
                            ])

                if deleted_count > 0:
                    logger.tree(f"{channel_name} Cleanup Complete", [
                        ("Deleted", str(deleted_count)),
                    ], emoji="🧹")

            except Exception as e:
                logger.error_tree(f"{channel_name} Cleanup Error", e, [])

    @cleanup_task.before_loop
    async def before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    def _get_channel_type(self, channel_id: int) -> Optional[str]:
        """Get the channel type (gallery/memes) or None if not a media channel."""
        if channel_id == config.GALLERY_CHANNEL_ID:
            return self.GALLERY
        elif channel_id == config.MEMES_CHANNEL_ID:
            return self.MEMES
        return None

    async def on_message(self, message: discord.Message) -> bool:
        """
        Handle gallery/memes channel message.

        Returns True if message was handled (valid or deleted).
        Returns False if not a media channel message.
        """
        if not message.guild:
            return False

        channel_type = self._get_channel_type(message.channel.id)
        if not channel_type:
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
            await self._delete_invalid(message, channel_type)
            return True

        # Valid media - add heart and create thread
        channel_name = "Gallery" if channel_type == self.GALLERY else "Memes"
        logger.tree(f"{channel_name} Valid Post Detected", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
            ("Attachments", str(len(message.attachments))),
        ], emoji="📸")

        await self._handle_valid_post(message, channel_type)
        return True

    async def _delete_invalid(self, message: discord.Message, channel_type: str) -> None:
        """Delete invalid media channel message."""
        channel_name = "Gallery" if channel_type == self.GALLERY else "Memes"
        try:
            await message.delete()
            logger.tree(f"{channel_name} Message Deleted", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Reason", "No valid image/video attachment"),
                ("Content", message.content[:50] if message.content else "None"),
            ], emoji="🗑️")
        except discord.HTTPException as e:
            logger.error_tree(f"{channel_name} Delete Failed", e, [
                ("User", f"{message.author.name}"),
            ])

    async def _handle_valid_post(self, message: discord.Message, channel_type: str) -> None:
        """Handle a valid media post - add heart and create thread."""
        channel_name = "Gallery" if channel_type == self.GALLERY else "Memes"
        thread_emoji = "📸" if channel_type == self.GALLERY else "😂"

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
            await message.add_reaction(EMOJI_HEART)
            logger.tree(f"{channel_name} Heart Added", [
                ("User", f"{message.author.name}"),
                ("Message ID", str(message.id)),
            ], emoji="❤️")
        except discord.HTTPException as e:
            logger.error_tree(f"{channel_name} Heart Failed", e, [
                ("User", f"{message.author.name}"),
            ])

        # Create comment thread
        thread = None
        try:
            date_str = datetime.now(TIMEZONE_EST).strftime("%b %-d")
            thread_name = f"{thread_emoji} {message.author.display_name} • {date_str}"[:100]

            thread = await message.create_thread(
                name=thread_name,
                auto_archive_duration=10080,  # 7 days
            )
            logger.tree(f"{channel_name} Thread Created", [
                ("User", f"{message.author.name}"),
                ("Thread", thread_name),
                ("Thread ID", str(thread.id)),
            ], emoji="💬")
        except discord.HTTPException as e:
            logger.error_tree(f"{channel_name} Thread Failed", e, [
                ("User", f"{message.author.name}"),
            ])

        # Send notification to general chat
        await self._send_notification(message, thread, is_video, thumbnail_url, channel_type)

    async def _send_notification(
        self,
        message: discord.Message,
        thread: Optional[discord.Thread],
        is_video: bool = False,
        thumbnail_url: Optional[str] = None,
        channel_type: str = GALLERY
    ) -> None:
        """Send a notification to general chat about a new media post."""
        channel_name = "Gallery" if channel_type == self.GALLERY else "Memes"

        if not config.GENERAL_CHANNEL_ID:
            logger.tree(f"{channel_name} Notification Skipped", [
                ("Reason", "No general channel configured"),
            ], emoji="ℹ️")
            return

        general_channel = self.bot.get_channel(config.GENERAL_CHANNEL_ID)
        if not general_channel:
            logger.tree(f"{channel_name} Notification Skipped", [
                ("Reason", "General channel not found"),
                ("Channel ID", str(config.GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        try:
            # Build embed - different title for gallery vs memes
            media_type = "🎬 video" if is_video else "🖼️ image"
            title = "🔔 New Gallery Post" if channel_type == self.GALLERY else "🔔 New Meme Post"

            embed = discord.Embed(
                title=title,
                description=f"<@{message.author.id}> posted a new {media_type}",
                color=COLOR_GOLD
            )
            embed.set_thumbnail(url=message.author.display_avatar.url)

            # Create view with comment button if thread exists
            view = None
            if thread:
                view = discord.ui.View()
                comment_button = discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label="Comment",
                    emoji=discord.PartialEmoji.from_str(EMOJI_COMMENT),
                    url=thread.jump_url
                )
                view.add_item(comment_button)

            await general_channel.send(embed=embed, view=view)
            logger.tree(f"{channel_name} Notification Sent", [
                ("User", f"{message.author.name}"),
                ("Channel", general_channel.name),
                ("Post ID", str(message.id)),
                ("Media Type", "Video" if is_video else "Image"),
                ("Thread", thread.name if thread else "None"),
            ], emoji="📢")
        except discord.Forbidden as e:
            logger.error_tree(f"{channel_name} Notification Failed", e, [
                ("Channel", str(config.GENERAL_CHANNEL_ID)),
            ])
        except discord.HTTPException as e:
            logger.error_tree(f"{channel_name} Notification Failed", e, [])

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> bool:
        """
        Handle reaction in gallery/memes - only allow heart emoji.

        Returns True if reaction was handled (media channel).
        Returns False if not a media channel reaction.
        """
        channel_type = self._get_channel_type(reaction.message.channel.id)
        if not channel_type:
            return False

        channel_name = "Gallery" if channel_type == self.GALLERY else "Memes"

        # Check if it's the allowed heart emoji
        emoji_str = str(reaction.emoji)
        if emoji_str != EMOJI_HEART:
            try:
                await reaction.remove(user)
                logger.tree(f"{channel_name} Reaction Removed", [
                    ("User", f"{user.name}"),
                    ("Emoji", emoji_str[:20]),
                    ("Message ID", str(reaction.message.id)),
                ], emoji="🚫")
            except discord.HTTPException as e:
                logger.error_tree(f"{channel_name} Reaction Remove Failed", e, [
                    ("User", f"{user.name}"),
                ])
        else:
            logger.tree(f"{channel_name} Heart Reaction", [
                ("User", f"{user.name}"),
                ("Message ID", str(reaction.message.id)),
            ], emoji="❤️")

        return True
