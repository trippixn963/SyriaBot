"""
SyriaBot - Reply Commands Handler
=================================

Handles reply commands: convert, quote, translate, download.
User replies to a message with a keyword to trigger the command.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import io
import re
import time
from collections import OrderedDict
from typing import Optional, TYPE_CHECKING

import discord

from src.core.logger import log
from src.core.constants import MAX_IMAGE_SIZE, MAX_VIDEO_SIZE, DELETE_DELAY_SHORT
from src.core.colors import COLOR_ERROR, COLOR_WARNING
from src.services.convert_service import convert_service
from src.services.quote_service import quote_service
from src.services.translate_service import translate_service, find_similar_language
from src.services.rate_limiter import check_rate_limit
from src.views.convert_view import start_convert_editor
from src.views.translate_view import TranslateView, create_translate_embed
from src.views.quote_view import QuoteView
from src.utils.footer import set_footer
from src.commands.download import handle_download

if TYPE_CHECKING:
    from discord.ext.commands import Bot


# Pre-compiled URL pattern for download detection (compiled once at module load)
DOWNLOAD_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:'
    # Instagram
    r'instagram\.com/(?:p|reel|reels|stories)/[\w-]+|'
    r'instagram\.com/[\w.]+/(?:p|reel)/[\w-]+|'
    # Twitter/X
    r'(?:twitter|x)\.com/\w+/status/\d+|'
    # TikTok
    r'tiktok\.com/@[\w.]+/video/\d+|'
    r'(?:vm|vt)\.tiktok\.com/[\w]+|'
    r'tiktok\.com/t/[\w]+|'
    # Reddit
    r'reddit\.com/r/\w+/comments/\w+|'
    r'v\.redd\.it/\w+|'
    # Facebook
    r'facebook\.com/.+/videos/\d+|'
    r'facebook\.com/watch/?\?v=\d+|'
    r'facebook\.com/reel/\d+|'
    r'fb\.watch/[\w-]+|'
    # Snapchat
    r'snapchat\.com/spotlight/[\w-]+|'
    r'snapchat\.com/t/[\w-]+|'
    # Twitch
    r'twitch\.tv/\w+/clip/[\w-]+|'
    r'clips\.twitch\.tv/[\w-]+'
    r')',
    re.IGNORECASE
)

# Max cooldown cache size before cleanup
MAX_COOLDOWN_CACHE_SIZE = 100


class ReplyHandler:
    """Handles reply commands (convert, quote, translate, download)."""

    # Download reply cooldown (5 minutes = 300 seconds)
    DOWNLOAD_REPLY_COOLDOWN = 300

    # Common typos/variations of "translate"
    TRANSLATE_TRIGGERS = (
        "translate to ",
        "translate ",
        "tanslate to ",  # missing r
        "tanslate ",
        "tranlate to ",  # missing s
        "tranlate ",
        "transalte to ",  # swapped a/l
        "transalte ",
        "trasnlate to ",  # swapped s/n
        "trasnlate ",
        "translte to ",  # missing a
        "translte ",
        "tarnslate to ",  # swapped a/r
        "tarnslate ",
        "tr to ",  # shorthand
        "tr ",
    )

    def __init__(self, bot: "Bot") -> None:
        """Initialize the reply handler with bot reference."""
        self.bot = bot
        self._download_cooldowns: OrderedDict[int, float] = OrderedDict()

    def _cleanup_download_cooldowns(self) -> None:
        """Remove expired cooldowns to prevent unbounded growth."""
        if len(self._download_cooldowns) <= MAX_COOLDOWN_CACHE_SIZE:
            return

        now = time.time()
        expired_users = [
            uid for uid, ts in self._download_cooldowns.items()
            if now - ts > self.DOWNLOAD_REPLY_COOLDOWN
        ]
        for uid in expired_users:
            del self._download_cooldowns[uid]

        while len(self._download_cooldowns) > MAX_COOLDOWN_CACHE_SIZE:
            self._download_cooldowns.popitem(last=False)

    def _is_translate_trigger(self, content: str) -> bool:
        """Check if content starts with a translate trigger (with typo tolerance)."""
        return any(content.startswith(trigger) for trigger in self.TRANSLATE_TRIGGERS)

    def _extract_translate_lang(self, content: str) -> str:
        """Extract the target language from a translate command."""
        for trigger in self.TRANSLATE_TRIGGERS:
            if content.startswith(trigger):
                return content[len(trigger):].strip()
        return ""

    async def handle(self, message: discord.Message) -> bool:
        """
        Handle reply commands: convert, quote, translate, download.
        Returns True if a command was processed, False otherwise.
        """
        # Must be a reply
        if not message.reference:
            return False

        content = message.content.strip().lower()

        if content == "convert":
            await self._handle_convert(message)
            return True
        elif content == "quote":
            await self._handle_quote(message)
            return True
        elif content in ("download", "dw", "dl"):
            await self._handle_download(message)
            return True
        elif content == "tr" or content == "translate":
            # Default to English
            await self._handle_translate(message, "en")
            return True
        elif self._is_translate_trigger(content):
            target_lang = self._extract_translate_lang(content)
            if target_lang:
                await self._handle_translate(message, target_lang)
                return True

        return False

    async def _handle_convert(self, message: discord.Message) -> None:
        """Handle replying 'convert' to an image/video - opens interactive editor."""
        log.tree("Convert Reply Started", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
            ("Channel", message.channel.name if hasattr(message.channel, 'name') else "DM"),
        ], emoji="🔄")

        allowed, usage = await check_rate_limit(message.author, "convert", message=message)
        if not allowed:
            return

        ref = message.reference
        if not ref or not ref.message_id:
            log.tree("Convert Reply Skipped", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Reason", "No message reference"),
            ], emoji="⚠️")
            return

        original = ref.cached_message
        if not original:
            try:
                original = await message.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden) as e:
                log.tree("Convert Fetch Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Message ID", str(ref.message_id)),
                    ("Error", type(e).__name__),
                ], emoji="⚠️")
                await message.reply("Couldn't access that message.", mention_author=False)
                return

        media_data = None
        source_name = "media"
        is_video = False

        for attachment in original.attachments:
            content_type = attachment.content_type or ""

            if content_type.startswith("image/"):
                if attachment.size > MAX_IMAGE_SIZE:
                    log.tree("Convert Image Too Large", [
                        ("User", f"{message.author.name}"),
                        ("ID", str(message.author.id)),
                        ("Size", f"{attachment.size // 1024}KB"),
                        ("Max", "8MB"),
                    ], emoji="⚠️")
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
                    log.tree("Convert Video Too Large", [
                        ("User", f"{message.author.name}"),
                        ("ID", str(message.author.id)),
                        ("Size", f"{attachment.size // (1024*1024)}MB"),
                        ("Max", "25MB"),
                    ], emoji="⚠️")
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

            elif convert_service.is_image(attachment.filename):
                if attachment.size > MAX_IMAGE_SIZE:
                    log.tree("Convert Image Too Large", [
                        ("User", f"{message.author.name}"),
                        ("ID", str(message.author.id)),
                        ("File", attachment.filename),
                        ("Size", f"{attachment.size // 1024}KB"),
                        ("Max", "8MB"),
                    ], emoji="⚠️")
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
                    log.tree("Convert Video Too Large", [
                        ("User", f"{message.author.name}"),
                        ("ID", str(message.author.id)),
                        ("File", attachment.filename),
                        ("Size", f"{attachment.size // (1024*1024)}MB"),
                        ("Max", "25MB"),
                    ], emoji="⚠️")
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

        if not media_data and original.embeds:
            for embed in original.embeds:
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
            log.tree("Convert No Media Found", [
                ("User", f"{message.author.name}"),
                ("ID", str(message.author.id)),
                ("Original Message", str(ref.message_id)),
            ], emoji="⚠️")
            await message.reply("No image or video found.", mention_author=False)
            return

        log.tree("Convert", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
            ("Type", "Video" if is_video else "Image"),
            ("Size", f"{len(media_data) // 1024}KB"),
        ], emoji="🔄")

        await start_convert_editor(
            interaction_or_message=message,
            image_data=media_data,
            source_name=source_name,
            is_video=is_video,
            original_message=original,
        )

    async def _handle_quote(self, message: discord.Message) -> None:
        """Handle replying 'quote' to a message - generates quote image."""
        log.tree("Quote Reply Started", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
        ], emoji="💬")

        allowed, usage = await check_rate_limit(message.author, "quote", message=message)
        if not allowed:
            return

        ref = message.reference
        if not ref or not ref.message_id:
            log.tree("Quote Reply Skipped", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Reason", "No message reference"),
            ], emoji="⚠️")
            return

        original = ref.cached_message
        if not original:
            try:
                original = await message.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden) as e:
                log.tree("Quote Fetch Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Message ID", str(ref.message_id)),
                    ("Error", type(e).__name__),
                ], emoji="⚠️")
                await message.reply("Couldn't access that message.", mention_author=False)
                return

        if not original.content or not original.content.strip():
            log.tree("Quote No Content", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Target Message", str(ref.message_id)),
            ], emoji="⚠️")
            await message.reply("That message has no text to quote.", mention_author=False)
            return

        author = original.author
        avatar_url = str(author.display_avatar.url)
        content = original.content

        def replace_user_mention(match) -> str:
            user_id = int(match.group(1))
            if message.guild:
                member = message.guild.get_member(user_id)
                if member:
                    return f"@{member.display_name}"
            return match.group(0)

        content = re.sub(r'<@!?(\d+)>', replace_user_mention, content)

        def replace_role_mention(match) -> str:
            role_id = int(match.group(1))
            if message.guild:
                role = message.guild.get_role(role_id)
                if role:
                    return f"@{role.name}"
            return match.group(0)

        content = re.sub(r'<@&(\d+)>', replace_role_mention, content)

        def replace_channel_mention(match) -> str:
            channel_id = int(match.group(1))
            channel = self.bot.get_channel(channel_id)
            if channel:
                return f"#{channel.name}"
            return match.group(0)

        content = re.sub(r'<#(\d+)>', replace_channel_mention, content)

        banner_url = None
        guild_id = None
        if message.guild:
            guild_id = message.guild.id
            if message.guild.banner:
                banner_url = str(message.guild.banner.url)

        log.tree("Quote", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
            ("Author", f"{author.name} ({author.display_name})"),
            ("Author ID", str(author.id)),
            ("Length", f"{len(original.content)} chars"),
            ("Banner", "Yes" if banner_url else "No"),
        ], emoji="💬")

        timestamp = original.created_at.strftime("%b %d, %Y")

        result = await quote_service.generate_quote(
            message_content=content,
            author_name=author.display_name,
            avatar_url=avatar_url,
            username=author.name,
            guild_id=guild_id,
            banner_url=banner_url,
            timestamp=timestamp,
        )

        if not result.success:
            log.tree("Quote Generation Failed", [
                ("User", f"{message.author.name}"),
                ("ID", str(message.author.id)),
                ("Error", result.error[:50] if result.error else "Unknown"),
            ], emoji="❌")
            await message.reply(f"Failed to generate quote: {result.error}", mention_author=False)
            return

        view = QuoteView(image_bytes=result.image_bytes, requester_id=message.author.id)
        file = discord.File(
            fp=io.BytesIO(result.image_bytes),
            filename="discord.gg-syria.png"
        )
        msg = await message.reply(file=file, view=view, mention_author=False)
        view.message = msg

        log.tree("Quote Sent", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
            ("Author", f"{author.name}"),
            ("Length", f"{len(original.content)} chars"),
        ], emoji="✅")

    async def _handle_translate(self, message: discord.Message, target_lang: str) -> None:
        """Handle replying 'translate to X' to a message."""
        log.tree("Translate Reply Started", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
            ("Target Lang", target_lang),
        ], emoji="🌐")

        ref = message.reference
        if not ref or not ref.message_id:
            log.tree("Translate Reply Skipped", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Reason", "No message reference"),
            ], emoji="⚠️")
            return

        original = ref.cached_message
        if not original:
            try:
                original = await message.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden) as e:
                log.tree("Translate Fetch Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Message ID", str(ref.message_id)),
                    ("Error", type(e).__name__),
                ], emoji="⚠️")
                await message.reply("Couldn't access that message.", mention_author=False)
                return

        if not original.content or not original.content.strip():
            log.tree("Translate No Content", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Target Message", str(ref.message_id)),
            ], emoji="⚠️")
            await message.reply("That message has no text to translate.", mention_author=False)
            return

        text = original.content.strip()

        log.tree("Translate Reply", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
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
                        # Don't suggest the same code they already typed
                        if code.lower() == target_lang.lower():
                            error_msg = "Translation service temporarily unavailable. Please try again."
                        else:
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
                ("ID", str(message.author.id)),
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
                ("ID", str(message.author.id)),
                ("Reason", f"Already in {result.target_name}"),
            ], emoji="⚠️")
            return

        embed, file = create_translate_embed(result)
        view = TranslateView(
            original_text=text,
            requester_id=message.author.id,
            current_lang=result.target_lang,
            source_lang=result.source_lang,
        )
        if file:
            msg = await message.reply(embed=embed, file=file, view=view, mention_author=False)
        else:
            msg = await message.reply(embed=embed, view=view, mention_author=False)
        view.message = msg

        log.tree("Translation Sent", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
            ("From", f"{result.source_name} ({result.source_lang})"),
            ("To", f"{result.target_name} ({result.target_lang})"),
        ], emoji="✅")

    async def _handle_download(self, message: discord.Message) -> None:
        """Handle replying 'download' or 'dw' to a message with a link."""
        log.tree("Download Reply Started", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
        ], emoji="📥")

        user_id = message.author.id

        # Check cooldown (everyone has cooldown, boosters only get unlimited weekly downloads)
        last_use = self._download_cooldowns.get(user_id, 0)
        time_since = time.time() - last_use
        if time_since < self.DOWNLOAD_REPLY_COOLDOWN:
            remaining = self.DOWNLOAD_REPLY_COOLDOWN - time_since
            embed = discord.Embed(
                description=f"Please wait **{remaining:.0f}s** before downloading again.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            msg = await message.reply(embed=embed, mention_author=False)
            await msg.delete(delay=DELETE_DELAY_SHORT)
            try:
                await message.delete()
            except discord.HTTPException as e:
                log.tree("Download Cooldown Delete Failed", [
                    ("User", f"{message.author.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
            log.tree("Download Reply Cooldown", [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(user_id)),
                ("Remaining", f"{remaining:.0f}s"),
            ], emoji="⏳")
            return

        ref = message.reference
        if not ref or not ref.message_id:
            log.tree("Download Reply No Reference", [
                ("User", f"{message.author.name}"),
                ("ID", str(message.author.id)),
                ("Reason", "No message reference found"),
            ], emoji="⚠️")
            return

        original = ref.cached_message
        if not original:
            try:
                original = await message.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden) as e:
                log.tree("Download Fetch Failed", [
                    ("User", f"{message.author.name} ({message.author.display_name})"),
                    ("ID", str(message.author.id)),
                    ("Message ID", str(ref.message_id)),
                    ("Error", type(e).__name__),
                ], emoji="⚠️")
                await message.reply("Couldn't access that message.", mention_author=False)
                return

        # Use pre-compiled regex pattern (module-level constant)
        urls = DOWNLOAD_URL_PATTERN.findall(original.content)

        if not urls:
            msg = await message.reply(
                "No supported URL found. Supported: Instagram, Twitter/X, TikTok, Reddit, Facebook, Snapchat, Twitch.",
                mention_author=False
            )
            await msg.delete(delay=DELETE_DELAY_SHORT)
            try:
                await message.delete()
            except discord.HTTPException as e:
                log.tree("Download No URL Delete Failed", [
                    ("User", f"{message.author.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")
            log.tree("Download No URL Found", [
                ("User", f"{message.author.name}"),
                ("ID", str(message.author.id)),
                ("Original Message", str(original.id)),
            ], emoji="⚠️")
            return

        url = urls[0]

        # Record cooldown and cleanup old entries
        self._download_cooldowns[user_id] = time.time()
        self._cleanup_download_cooldowns()

        log.tree("Reply Download", [
            ("User", f"{message.author.name} ({message.author.display_name})"),
            ("ID", str(message.author.id)),
            ("URL", url[:60] + "..." if len(url) > 60 else url),
        ], emoji="📥")

        await handle_download(message, url, is_reply=True)
