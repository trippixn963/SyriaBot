"""
SyriaBot - Members Handler
==========================

Handles member join/leave/update events.

Author: حَـــــنَّـــــا
"""

import discord
from discord.ext import commands

from src.core.config import config
from src.core.logger import log
from src.utils.footer import set_footer

# Channel for boost announcements
GENERAL_CHANNEL_ID = 1350540215797940245


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

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Called when a member is updated - detects new boosts."""
        # Check if member started boosting (premium_since changed from None to datetime)
        if before.premium_since is None and after.premium_since is not None:
            await self._handle_new_boost(after)

    async def _handle_new_boost(self, member: discord.Member) -> None:
        """Send thank you message when someone boosts."""
        log.tree("New Boost", [
            ("User", f"{member.name} ({member.display_name})"),
            ("User ID", str(member.id)),
            ("Guild", member.guild.name),
        ], emoji="💎")

        # Get general channel
        channel = member.guild.get_channel(GENERAL_CHANNEL_ID)
        if not channel:
            log.tree("Boost Notification Failed", [
                ("User", str(member)),
                ("Reason", "General channel not found"),
                ("Channel ID", str(GENERAL_CHANNEL_ID)),
            ], emoji="⚠️")
            return

        # Build the thank you embed
        embed = discord.Embed(
            title="💎 New Server Booster!",
            description=(
                f"Thank you {member.mention} for boosting **{member.guild.name}**!\n\n"
                f"Your support helps keep the community thriving!"
            ),
            color=0x2ECC71  # Green
        )

        # Feature unlocks field
        embed.add_field(
            name="🏆 Booster Perks Unlocked",
            value=(
                "• **2x XP** on all messages and voice activity\n"
                "• **No cooldowns** on commands\n"
                "• **AI Translation** powered by GPT-4o"
            ),
            inline=False
        )

        # Check DMs reminder
        embed.add_field(
            name="📬 Check Your DMs",
            value="Other bots may have sent you additional perks and rewards!",
            inline=False
        )

        # Set booster avatar as thumbnail
        embed.set_thumbnail(url=member.display_avatar.url)

        # Gold accent on the side (using author field for visual appeal)
        embed.set_author(
            name="Server Boost",
            icon_url="https://cdn.discordapp.com/emojis/857628597716910100.webp"  # Boost emoji
        )

        set_footer(embed)

        try:
            await channel.send(content=member.mention, embed=embed)
            log.tree("Boost Notification Sent", [
                ("User", f"{member.name} ({member.display_name})"),
                ("User ID", str(member.id)),
                ("Channel", channel.name),
            ], emoji="✅")
        except discord.HTTPException as e:
            log.tree("Boost Notification Failed", [
                ("User", str(member)),
                ("Error", str(e)[:100]),
            ], emoji="❌")


async def setup(bot: commands.Bot) -> None:
    """Register the members handler cog with the bot."""
    await bot.add_cog(MembersHandler(bot))
    log.success("Loaded members handler")
