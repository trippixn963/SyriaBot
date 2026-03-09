"""
SyriaBot - Asset Storage
========================

Upload files to Discord asset storage channel for permanent URLs.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import io
import discord
from typing import Optional

from src.core.config import config
from src.core.logger import logger


async def upload_to_storage(bot, file_bytes: bytes, filename: str, context: str = "Asset") -> Optional[str]:
    """
    Upload file to asset storage channel for permanent URL.

    Args:
        bot: The bot instance
        file_bytes: Raw file bytes to upload
        filename: Filename for the upload
        context: Context for logging (e.g., "Image", "Quote", "Convert")

    Returns:
        Permanent CDN URL or None if storage not configured/failed
    """
    if not config.ASSET_STORAGE_CHANNEL_ID:
        logger.tree(f"{context} Asset Storage Skipped", [
            ("Reason", "SYRIA_ASSET_CH not configured"),
            ("Filename", filename),
        ], emoji="ℹ️")
        return None

    try:
        channel = bot.get_channel(config.ASSET_STORAGE_CHANNEL_ID)
        if not channel:
            logger.tree(f"{context} Asset Storage Channel Not Found", [
                ("Channel ID", str(config.ASSET_STORAGE_CHANNEL_ID)),
                ("Filename", filename),
            ], emoji="⚠️")
            return None

        file = discord.File(fp=io.BytesIO(file_bytes), filename=filename)
        msg = await channel.send(file=file)

        if msg.attachments:
            url = msg.attachments[0].url
            logger.tree(f"{context} Asset Stored", [
                ("Filename", filename),
                ("Size", f"{len(file_bytes) / 1024:.1f} KB"),
                ("Message ID", str(msg.id)),
                ("URL", url[:80] + "..." if len(url) > 80 else url),
            ], emoji="💾")
            return url
        else:
            logger.tree(f"{context} Asset Storage No Attachment", [
                ("Filename", filename),
                ("Message ID", str(msg.id)),
                ("Reason", "Message sent but no attachment returned"),
            ], emoji="⚠️")
            return None

    except Exception as e:
        logger.error_tree(f"{context} Asset Storage Failed", e, [
            ("Filename", filename),
            ("Size", f"{len(file_bytes) / 1024:.1f} KB"),
            ("Channel ID", str(config.ASSET_STORAGE_CHANNEL_ID)),
        ])
        return None
