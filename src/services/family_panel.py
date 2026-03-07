"""
SyriaBot - Family Panel Service
================================

Persistent family commands panel in configured channels.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from discord.ext import commands

from src.core.logger import logger


class FamilyPanelService:
    """Placeholder for family panel service."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def setup(self) -> None:
        logger.tree("Family Panel Service Ready", [], emoji="👨‍👩‍👧‍👦")
