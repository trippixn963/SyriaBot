"""
SyriaBot - Members Handler
==========================

Handles member join/leave events.

Author: حَـــــنَّـــــا
"""

import discord
from discord.ext import commands

from src.core.config import config
from src.core.logger import log


class MembersHandler(commands.Cog):
    """Handles member events."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Called when a member joins the server."""
        if member.bot:
            return

        if not config.AUTO_ROLE_ID:
            return  # Auto-role not configured

        role = member.guild.get_role(config.AUTO_ROLE_ID)
        if not role:
            log.error(f"Auto-role {config.AUTO_ROLE_ID} not found")
            return

        try:
            await member.add_roles(role, reason="Auto-role on join")
            log.tree("Member Joined", [
                ("User", str(member)),
                ("ID", str(member.id)),
                ("Role Given", role.name),
            ], emoji="👋")
        except discord.HTTPException as e:
            log.error(f"Failed to give auto-role to {member}: {e}")


async def setup(bot):
    await bot.add_cog(MembersHandler(bot))
