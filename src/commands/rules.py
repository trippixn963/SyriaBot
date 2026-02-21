"""
SyriaBot - Rules Command
========================

Post formatted server rules to the rules channel.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import logger


# =============================================================================
# Rules Data
# =============================================================================

TABLE_OF_CONTENTS = """## 📋 Table of Contents

```
FOUNDATION           →  1-2
PRESENTATION         →  3-4
BEHAVIOR             →  5-7
SENSITIVE TOPICS     →  8-10
SAFETY               →  11-12
AUTHORITY            →  13-14
```
══════════════════════"""

RULES_SECTIONS = [
    {
        "category": "FOUNDATION",
        "rules": [
            {
                "title": "1. Mutual Respect",
                "bullets": [
                    "Respect all members — Insults, mockery, harassment, and bullying are strictly prohibited.",
                    "No racism or sectarianism — Hate speech targeting race, religion, sect, or nationality is forbidden.",
                    "Accept differences — Discuss politely and respectfully without personal attacks or insults.",
                ],
            },
            {
                "title": "2. Language",
                "bullets": [
                    "English is the primary language — Use English in public channels so everyone can participate.",
                    "Arabic is also welcome — Feel free to chat in Arabic, but don't exclude others from conversations.",
                    "No language discrimination — Do not mock or belittle someone for their language skills or accent.",
                ],
            },
        ],
    },
    {
        "category": "PRESENTATION",
        "rules": [
            {
                "title": "3. Appropriate Content",
                "bullets": [
                    "No NSFW content — Pornographic or suggestive images, videos, or text is prohibited. This includes avatars.",
                    "No extreme violence — Do not post images or videos containing graphic violence, torture, or death.",
                    "No illegal content — Content involving drugs, weapons, hacking, or fraud is completely forbidden.",
                ],
            },
            {
                "title": "4. Usernames & Avatars",
                "bullets": [
                    "Keep it appropriate — Usernames and avatars must not contain NSFW, offensive, or hateful content.",
                    "Must be pingable — Avoid excessive symbols or unicode that makes your name impossible to type or mention.",
                    "No impersonation — Do not pretend to be staff, other members, or public figures.",
                ],
            },
        ],
    },
    {
        "category": "BEHAVIOR",
        "rules": [
            {
                "title": "5. Spam & Disruption",
                "bullets": [
                    "No spamming — Repetitive messages, random characters, or excessive emojis are prohibited.",
                    "No random mentions — Do not mention members, roles, or @everyone without a valid reason.",
                    "Use correct channels — Each channel has a purpose. Post content in the appropriate channel.",
                ],
            },
            {
                "title": "6. No Drama",
                "bullets": [
                    "Keep it out of public channels — Do not bring personal beef, arguments, or drama into the server.",
                    "No callout posts — Do not publicly accuse, expose, or start witch hunts against other members.",
                    "Handle disputes privately — If you have issues with someone, open a ticket or handle it in DMs.",
                ],
            },
            {
                "title": "7. Advertising & Links",
                "bullets": [
                    "No advertising — Promoting servers, YouTube channels, or social media without permission is forbidden.",
                    "No suspicious links — Shortened URLs or potentially harmful links will be deleted immediately.",
                    "No DM advertising — Sending ads in private messages to members results in an immediate ban.",
                ],
            },
        ],
    },
    {
        "category": "SENSITIVE TOPICS",
        "rules": [
            {
                "title": "8. No Terrorism & Extremism",
                "bullets": [
                    "No extremist content — Promoting, glorifying, or supporting terrorist organizations or ideologies is banned.",
                    "No propaganda — Spreading extremist propaganda, recruitment material, or radical content is forbidden.",
                    "No incitement of violence — Encouraging violence, war crimes, or attacks against any group is prohibited.",
                ],
            },
            {
                "title": "9. No Religious Discussions",
                "bullets": [
                    "Religious debates are banned — To maintain peace, all religious arguments and debates are prohibited.",
                    "No preaching or proselytizing — Do not attempt to convert others or push religious beliefs on members.",
                    "Respect all beliefs — You may mention your faith, but do not attack or mock others' religions.",
                ],
            },
            {
                "title": "10. AI Misuse",
                "bullets": [
                    "No deepfakes — Using AI to manipulate someone's face onto inappropriate or offensive content is banned.",
                    "No AI harassment — Creating AI-generated content to mock, harass, or defame any member is prohibited.",
                    "Respect consent — Do not use AI tools on someone's photos or likeness without their permission.",
                ],
            },
        ],
    },
    {
        "category": "SAFETY",
        "rules": [
            {
                "title": "11. Privacy & Safety",
                "bullets": [
                    "Don't share personal info — Do not post your phone number, address, or sensitive information.",
                    "No doxxing — Publishing personal information about others results in a permanent ban.",
                    "Report harassment — If you experience harassment, open a ticket. Staff will handle it confidentially.",
                ],
            },
            {
                "title": "12. Voice Channels",
                "bullets": [
                    "Channels are self-moderated — The VC owner can kick and block users. Handle issues yourself first.",
                    "No recording calls — Recording or streaming voice conversations without consent is not allowed.",
                    "Only report serious issues — Contact staff only for nudity or extremism displayed on stream.",
                ],
            },
        ],
    },
    {
        "category": "AUTHORITY",
        "rules": [
            {
                "title": "13. Respecting Staff",
                "bullets": [
                    "Follow moderator instructions — If a mod asks you to stop, stop immediately. Appeal via ticket.",
                    "Don't act as a moderator — If you see a violation, report it. Don't handle it yourself.",
                    "No ban evasion — Creating new accounts to evade punishment results in a permanent ban.",
                ],
            },
            {
                "title": "14. Discord Guidelines",
                "bullets": [
                    "Follow Discord TOS — You must be 13+ and comply with all official Discord rules.",
                    "No alt accounts — Only one account per person is allowed. Multiple accounts are not permitted.",
                    "Report serious violations — Issues like child exploitation must be reported to Discord directly.",
                ],
            },
        ],
    },
]

RULES_FOOTER = """══════════════════════

Staff reserves the right to take any action deemed appropriate.

🎫 **Questions?** Open a ticket in <#1406750411779604561>
🔗 **Invite:** discord.gg/syria"""


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

            # Table of Contents
            await channel.send(TABLE_OF_CONTENTS)

            # Each section with category header and rules
            for i, section in enumerate(RULES_SECTIONS):
                # Build the section message
                section_text = f"# {section['category']}\n"

                for rule in section["rules"]:
                    bullets_text = "\n".join(f"• {bullet}" for bullet in rule["bullets"])
                    section_text += f"\n## {rule['title']}\n```\n{bullets_text}\n```"

                # Add separator except for the last section
                if i < len(RULES_SECTIONS) - 1:
                    section_text += "\n\n══════════════════════"

                await channel.send(section_text)

            # Footer
            await channel.send(RULES_FOOTER)

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
