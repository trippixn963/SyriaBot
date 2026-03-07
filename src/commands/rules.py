"""
SyriaBot - Rules Command
========================

Post formatted server rules with image banners per category.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import logger

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "rules"

# =============================================================================
# Rules Data — compact one-liner per rule
# =============================================================================

RULES_CATEGORIES = [
    {
        "banner": "foundation.png",
        "rules": [
            ("1. Mutual Respect", "No insults, harassment, racism, or sectarianism. Discuss politely without personal attacks."),
            ("2. Language", "English is primary; Arabic is welcome. Don't exclude others or mock language skills."),
        ],
    },
    {
        "banner": "presentation.png",
        "rules": [
            ("3. Appropriate Content", "No NSFW, graphic violence, or illegal content (drugs, weapons, hacking)."),
            ("4. Usernames & Avatars", "Keep names/avatars appropriate and pingable. No impersonation."),
        ],
    },
    {
        "banner": "behavior.png",
        "rules": [
            ("5. Spam & Disruption", "No spam, random mentions, or off-topic posts. Use the correct channels."),
            ("6. No Drama", "Keep arguments out of public channels. No callout posts. Handle disputes via ticket or DMs."),
            ("7. Advertising & Links", "No advertising or suspicious links. DM advertising = instant ban."),
        ],
    },
    {
        "banner": "sensitive_topics.png",
        "rules": [
            ("8. No Terrorism & Extremism", "No extremist content, propaganda, or incitement of violence."),
            ("9. No Religious Discussions", "Religious debates and preaching are prohibited. Respect all beliefs."),
            ("10. AI Misuse", "No deepfakes or AI harassment. Don't use AI on someone's likeness without consent."),
        ],
    },
    {
        "banner": "safety.png",
        "rules": [
            ("11. Privacy & Safety", "Don't share personal info. No doxxing. Report harassment via ticket."),
            ("12. Voice Channels", "VCs are self-moderated by owner. No recording. Only report nudity or extremism."),
        ],
    },
    {
        "banner": "authority.png",
        "rules": [
            ("13. Respecting Staff", "Follow mod instructions. Don't mini-mod. No ban evasion."),
            ("14. Discord Guidelines", "Follow Discord TOS. No alt accounts. Report serious violations to Discord."),
        ],
    },
]


# =============================================================================
# Command
# =============================================================================

class RulesCog(commands.Cog):
    """Rules command cog."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="rules", description="Post server rules (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def rules_command(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Purge the rules channel and post formatted server rules."""
        await interaction.response.defer(ephemeral=True)

        # Get the rules channel
        channel = interaction.guild.get_channel(config.RULES_CHANNEL_ID)
        if not channel:
            await interaction.followup.send(
                "❌ Rules channel not found. Check SYRIA_RULES_CH in config.",
                ephemeral=True,
            )
            return

        try:
            # Purge all messages in the channel
            await interaction.followup.send(
                f"🗑️ Purging {channel.mention}...",
                ephemeral=True,
            )
            deleted = await channel.purge(limit=100)

            logger.tree("Rules Channel Purged", [
                ("Channel", channel.name),
                ("Deleted", str(len(deleted))),
            ], emoji="🗑️")

            # Post each category: banner image + plain-text rules
            for i, category in enumerate(RULES_CATEGORIES):
                banner_path = ASSETS_DIR / category["banner"]
                await channel.send(file=discord.File(banner_path))

                lines = []
                for name, value in category["rules"]:
                    lines.append(f"◈ **{name}** — {value}")
                await channel.send("\n".join(lines))

                # Spacer between categories (not after the last one)
                if i < len(RULES_CATEGORIES) - 1:
                    await channel.send("\u200b")

            # Spacer before footer
            await channel.send("\u200b")

            # Footer banner + message
            await channel.send(file=discord.File(ASSETS_DIR / "need_help.png"))
            await channel.send(
                f"Staff reserves the right to take any action deemed appropriate.\n"
                f"<:ticket:1459987754942337024> **Questions?** Open a ticket in <#{config.TICKET_CHANNEL_ID}>\n"
                f"<:link:1479498358208069743> **Invite:** discord.gg/syria"
            )

            await interaction.edit_original_response(
                content=f"✅ Rules posted to {channel.mention} ({len(deleted)} messages purged)",
            )

            logger.tree("Rules Posted", [
                ("Channel", channel.name),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
            ], emoji="📜")

        except discord.Forbidden:
            await interaction.edit_original_response(
                content="❌ I don't have permission to manage messages in the rules channel.",
            )
        except Exception as e:
            logger.error_tree("Rules Post Failed", e)
            await interaction.edit_original_response(
                content=f"❌ An error occurred: {str(e)[:100]}",
            )


async def setup(bot: commands.Bot) -> None:
    """Register the rules cog."""
    await bot.add_cog(RulesCog(bot))
    logger.tree("Command Loaded", [
        ("Name", "rules"),
    ], emoji="✅")
