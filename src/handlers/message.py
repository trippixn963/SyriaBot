"""
SyriaBot - Message Handler
==========================

Handles message events including the "convert" and "quote" reply features.
Optimized for speed and efficiency.

Author: حَـــــنَّـــــا
"""

import io
import re
import discord
from discord.ext import commands

from src.core.logger import log
from src.core.config import config
from src.core.constants import MAX_IMAGE_SIZE, MAX_VIDEO_SIZE
from src.core.colors import COLOR_ERROR, COLOR_WARNING
from src.services.convert_service import convert_service
from src.services.quote_service import quote_service
from src.services.translate_service import translate_service, find_similar_language
from src.services.database import db
from src.services.rate_limiter import check_rate_limit
from src.views.convert_view import start_convert_editor
from src.views.translate_view import TranslateView, create_translate_embed
from src.views.quote_view import QuoteView
from src.utils.footer import set_footer


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
            except (discord.NotFound, discord.Forbidden) as e:
                log.tree("Convert Fetch Failed", [
                    ("User", str(message.author)),
                    ("Message ID", str(ref.message_id)),
                    ("Error", type(e).__name__),
                ], emoji="⚠️")
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
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
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
            except (discord.NotFound, discord.Forbidden) as e:
                log.tree("Quote Fetch Failed", [
                    ("User", str(message.author)),
                    ("Message ID", str(ref.message_id)),
                    ("Error", type(e).__name__),
                ], emoji="⚠️")
                await message.reply("Couldn't access that message.", mention_author=False)
                return

        # Check if message has content
        if not original.content or not original.content.strip():
            log.tree("Quote No Content", [
                ("User", str(message.author)),
                ("Target Message", str(ref.message_id)),
            ], emoji="⚠️")
            await message.reply("That message has no text to quote.", mention_author=False)
            return

        # Get author info
        author = original.author
        avatar_url = str(author.display_avatar.url)

        # Convert mentions to readable @username format
        content = original.content

        # Replace user mentions <@123> or <@!123> with @username
        def replace_user_mention(match) -> str:
            """Convert user mention to @username format."""
            user_id = int(match.group(1))
            if message.guild:
                member = message.guild.get_member(user_id)
                if member:
                    return f"@{member.display_name}"
            return match.group(0)  # Keep original if not found

        content = re.sub(r'<@!?(\d+)>', replace_user_mention, content)

        # Replace role mentions <@&123> with @rolename
        def replace_role_mention(match) -> str:
            """Convert role mention to @rolename format."""
            role_id = int(match.group(1))
            if message.guild:
                role = message.guild.get_role(role_id)
                if role:
                    return f"@{role.name}"
            return match.group(0)

        content = re.sub(r'<@&(\d+)>', replace_role_mention, content)

        # Replace channel mentions <#123> with #channelname
        def replace_channel_mention(match) -> str:
            """Convert channel mention to #channelname format."""
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
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("User ID", str(message.author.id)),
            ("Author", f"{author.name} ({author.display_name})"),
            ("Author ID", str(author.id)),
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

        # Create view with Save button
        view = QuoteView(image_bytes=result.image_bytes)

        # Send the quote image with Save button
        file = discord.File(
            fp=io.BytesIO(result.image_bytes),
            filename="discord.gg-syria.png"
        )
        msg = await message.reply(file=file, view=view, mention_author=False)
        view.message = msg

    async def _handle_reply_translate(self, message: discord.Message, target_lang: str) -> None:
        """Handle replying 'translate to X' to a message - translates the text."""
        # Translate is free for everyone - no rate limit

        ref = message.reference
        if not ref or not ref.message_id:
            return

        # Use cached message if available (faster)
        original = ref.cached_message
        if not original:
            try:
                original = await message.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden) as e:
                log.tree("Translate Fetch Failed", [
                    ("User", str(message.author)),
                    ("Message ID", str(ref.message_id)),
                    ("Error", type(e).__name__),
                ], emoji="⚠️")
                await message.reply("Couldn't access that message.", mention_author=False)
                return

        # Check if message has content
        if not original.content or not original.content.strip():
            log.tree("Translate No Content", [
                ("User", str(message.author)),
                ("Target Message", str(ref.message_id)),
            ], emoji="⚠️")
            await message.reply("That message has no text to translate.", mention_author=False)
            return

        text = original.content.strip()

        log.tree("Translate Reply", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("User ID", str(message.author.id)),
            ("Text", text[:50] + "..." if len(text) > 50 else text),
            ("To", target_lang),
        ], emoji="🌐")

        result = await translate_service.translate(text, target_lang=target_lang)

        if not result.success:
            error_msg = "Translation failed. Please try again."
            if result.error:
                if "Unknown language" in result.error or "No support for the provided language" in result.error:
                    similar = find_similar_language(target_lang)
                    if similar:
                        code, name, flag = similar
                        error_msg = f"Language `{target_lang}` is not supported. Did you mean {flag} **{name}** (`{code}`)?"
                    else:
                        error_msg = f"Language `{target_lang}` is not supported."
                elif len(result.error) < 100:
                    error_msg = result.error

            embed = discord.Embed(description=f"❌ {error_msg}", color=COLOR_ERROR)
            set_footer(embed)
            await message.reply(embed=embed, mention_author=False)

            log.tree("Translation Failed", [
                ("User", f"{message.author.name}"),
                ("User ID", str(message.author.id)),
                ("Target", target_lang),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            return

        if result.source_lang == result.target_lang:
            embed = discord.Embed(
                title="🌐 Already in Target Language",
                description=f"This text is already in {result.target_name}.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await message.reply(embed=embed, mention_author=False)
            log.tree("Translation Skipped", [
                ("User", f"{message.author.name}"),
                ("User ID", str(message.author.id)),
                ("Reason", f"Already in {result.target_name}"),
            ], emoji="⚠️")
            return

        embed = create_translate_embed(result)

        view = TranslateView(
            original_text=text,
            requester_id=message.author.id,
            current_lang=result.target_lang,
            source_lang=result.source_lang,
        )

        msg = await message.reply(embed=embed, view=view, mention_author=False)
        view.message = msg

        log.tree("Translation Sent", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("User ID", str(message.author.id)),
            ("From", f"{result.source_name} ({result.source_lang})"),
            ("To", f"{result.target_name} ({result.target_lang})"),
        ], emoji="✅")

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

        # Handle XP gain from messages
        if hasattr(self.bot, 'xp_service') and self.bot.xp_service:
            try:
                await self.bot.xp_service.on_message(message)
            except Exception as e:
                log.tree("XP Message Handler Error", [
                    ("Error", str(e)),
                ], emoji="❌")

        # Track images shared (only in main server)
        if message.guild and message.guild.id == config.GUILD_ID and message.attachments:
            try:
                db.increment_images_shared(message.author.id, message.guild.id)
            except Exception:
                pass  # Silent fail for tracking

        if not message.reference:
            return

        # Quick check: is it "convert", "quote", or "translate to X"?
        content = message.content.strip().lower()

        if content == "convert":
            await self._handle_reply_convert(message)
        elif content == "quote":
            await self._handle_reply_quote(message)
        elif content.startswith("translate to ") or content.startswith("translate "):
            # Extract target language
            if content.startswith("translate to "):
                target_lang = content[13:].strip()  # len("translate to ") = 13
            else:
                target_lang = content[10:].strip()  # len("translate ") = 10

            if target_lang:
                await self._handle_reply_translate(message, target_lang)


    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> None:
        """Track reactions given by users."""
        if user.bot:
            return

        # Only track in main server
        if not reaction.message.guild or reaction.message.guild.id != config.GUILD_ID:
            return

        try:
            db.increment_reactions_given(user.id, reaction.message.guild.id)
        except Exception:
            pass  # Silent fail for tracking


async def setup(bot: commands.Bot) -> None:
    """Register the message handler cog with the bot."""
    await bot.add_cog(MessageHandler(bot))
    log.success("Loaded message handler")
