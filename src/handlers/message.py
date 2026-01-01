"""
SyriaBot - Message Handler
==========================

Handles message events including the "convert" and "quote" reply features.
Optimized for speed and efficiency.

Author: حَـــــنَّـــــا
"""

import io
import discord
from discord.ext import commands

from src.core.logger import log
from src.services.convert_service import convert_service
from src.services.quote_service import quote_service
from src.services.rate_limiter import check_rate_limit
from src.services.webhook_logger import webhook_logger
from src.views.convert_view import start_convert_editor

# Size limits (bytes)
MAX_IMAGE_SIZE = 8 * 1024 * 1024  # 8MB
MAX_VIDEO_SIZE = 25 * 1024 * 1024  # 25MB


class MessageHandler(commands.Cog):
    """Handles message events."""

    def __init__(self, bot):
        self.bot = bot

    async def _handle_reply_convert(self, message: discord.Message) -> None:
        """Handle replying 'convert' to an image/video - opens interactive editor."""
        # Check rate limit
        if not await check_rate_limit(message.author, "convert", message=message):
            return

        ref = message.reference
        if not ref or not ref.message_id:
            return

        # Use cached message if available (faster)
        original = ref.cached_message
        if not original:
            try:
                original = await message.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden):
                await message.reply("Couldn't access that message.", mention_author=False)
                return

        # Fast path: Check attachments first (most common)
        media_data = None
        source_name = "media"
        is_video = False

        for attachment in original.attachments:
            content_type = attachment.content_type or ""

            # Quick content-type check
            if content_type.startswith("image/"):
                if attachment.size > MAX_IMAGE_SIZE:
                    await message.reply("Image too large (max 8MB).", mention_author=False)
                    return
                try:
                    media_data = await attachment.read()
                    source_name = attachment.filename
                    is_video = False
                    break
                except Exception as e:
                    log.tree("Attachment Read Failed", [
                        ("File", attachment.filename),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")
                    continue

            elif content_type.startswith("video/"):
                if attachment.size > MAX_VIDEO_SIZE:
                    await message.reply("Video too large (max 25MB).", mention_author=False)
                    return
                try:
                    media_data = await attachment.read()
                    source_name = attachment.filename
                    is_video = True
                    break
                except Exception as e:
                    log.tree("Attachment Read Failed", [
                        ("File", attachment.filename),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")
                    continue

            # Fallback: Check by extension
            elif convert_service.is_image(attachment.filename):
                if attachment.size > MAX_IMAGE_SIZE:
                    await message.reply("Image too large (max 8MB).", mention_author=False)
                    return
                try:
                    media_data = await attachment.read()
                    source_name = attachment.filename
                    is_video = False
                    break
                except Exception as e:
                    log.tree("Attachment Read Failed", [
                        ("File", attachment.filename),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")
                    continue

            elif convert_service.is_video(attachment.filename):
                if attachment.size > MAX_VIDEO_SIZE:
                    await message.reply("Video too large (max 25MB).", mention_author=False)
                    return
                try:
                    media_data = await attachment.read()
                    source_name = attachment.filename
                    is_video = True
                    break
                except Exception as e:
                    log.tree("Attachment Read Failed", [
                        ("File", attachment.filename),
                        ("Error", str(e)[:50]),
                    ], emoji="⚠️")
                    continue

        # Check embeds only if no attachment found
        if not media_data and original.embeds:
            for embed in original.embeds:
                # Priority: video > image > thumbnail
                url = None
                if embed.video and embed.video.url:
                    url = embed.video.url
                    is_video = not url.lower().split("?")[0].endswith(".gif")
                elif embed.image and embed.image.url:
                    url = embed.image.url
                    is_video = False
                elif embed.thumbnail and embed.thumbnail.url:
                    url = embed.thumbnail.url
                    is_video = False

                if url:
                    media_data = await convert_service.fetch_media(url)
                    if media_data:
                        source_name = url.split("/")[-1].split("?")[0] or "embed"
                        break

        if not media_data:
            await message.reply("No image or video found.", mention_author=False)
            return

        log.tree("Convert", [
            ("User", str(message.author)),
            ("Type", "Video" if is_video else "Image"),
            ("Size", f"{len(media_data) // 1024}KB"),
        ], emoji="CONVERT")

        # Start editor (non-blocking)
        await start_convert_editor(
            interaction_or_message=message,
            image_data=media_data,
            source_name=source_name,
            is_video=is_video,
            original_message=original,
        )

    async def _handle_reply_quote(self, message: discord.Message) -> None:
        """Handle replying 'quote' to a message - generates quote image."""
        # Check rate limit
        if not await check_rate_limit(message.author, "quote", message=message):
            return

        ref = message.reference
        if not ref or not ref.message_id:
            return

        # Use cached message if available (faster)
        original = ref.cached_message
        if not original:
            try:
                original = await message.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden):
                await message.reply("Couldn't access that message.", mention_author=False)
                return

        # Check if message has content
        if not original.content or not original.content.strip():
            await message.reply("That message has no text to quote.", mention_author=False)
            return

        # Get author info
        author = original.author
        avatar_url = str(author.display_avatar.url)

        # Convert mentions to readable @username format
        import re
        content = original.content

        # Replace user mentions <@123> or <@!123> with @username
        def replace_user_mention(match):
            user_id = int(match.group(1))
            if message.guild:
                member = message.guild.get_member(user_id)
                if member:
                    return f"@{member.display_name}"
            return match.group(0)  # Keep original if not found

        content = re.sub(r'<@!?(\d+)>', replace_user_mention, content)

        # Replace role mentions <@&123> with @rolename
        def replace_role_mention(match):
            role_id = int(match.group(1))
            if message.guild:
                role = message.guild.get_role(role_id)
                if role:
                    return f"@{role.name}"
            return match.group(0)

        content = re.sub(r'<@&(\d+)>', replace_role_mention, content)

        # Replace channel mentions <#123> with #channelname
        def replace_channel_mention(match):
            channel_id = int(match.group(1))
            channel = self.bot.get_channel(channel_id)
            if channel:
                return f"#{channel.name}"
            return match.group(0)

        content = re.sub(r'<#(\d+)>', replace_channel_mention, content)

        # Get server banner if available
        banner_url = None
        guild_id = None
        if message.guild:
            guild_id = message.guild.id
            if message.guild.banner:
                banner_url = str(message.guild.banner.url)

        log.tree("Quote", [
            ("User", str(message.author)),
            ("Author", str(author)),
            ("Length", f"{len(original.content)} chars"),
            ("Banner", "Yes" if banner_url else "No"),
        ], emoji="💬")

        # Format timestamp
        timestamp = original.created_at.strftime("%b %d, %Y")

        # Generate quote image
        result = await quote_service.generate_quote(
            message_content=content,  # Use processed content with readable mentions
            author_name=author.display_name,
            avatar_url=avatar_url,
            username=author.name,
            guild_id=guild_id,
            banner_url=banner_url,
            timestamp=timestamp,
        )

        if not result.success:
            await message.reply(f"Failed to generate quote: {result.error}", mention_author=False)
            return

        # Send the quote image
        file = discord.File(
            fp=io.BytesIO(result.image_bytes),
            filename="discord.gg-syria.png"
        )
        await message.reply(file=file, mention_author=False)

        # Webhook logging
        webhook_logger.log_quote(message.author, str(author), len(original.content))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages."""
        # Fast bail-out checks
        if message.author.bot:
            return

        # Handle TempVoice sticky panel (runs for all non-bot messages)
        if hasattr(self.bot, 'tempvoice') and self.bot.tempvoice:
            try:
                await self.bot.tempvoice.on_message(message)
            except Exception as e:
                log.tree("TempVoice Message Handler Error", [
                    ("Error", str(e)),
                ], emoji="❌")

        if not message.reference:
            return

        # Quick check: is it "convert" or "quote"?
        content = message.content.strip().lower()
        if len(content) > 10:  # "convert" is 7 chars, allow some whitespace
            return

        if content == "convert":
            await self._handle_reply_convert(message)
        elif content == "quote":
            await self._handle_reply_quote(message)


async def setup(bot):
    await bot.add_cog(MessageHandler(bot))
