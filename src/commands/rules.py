"""
SyriaBot - Rules Command
========================

Admin command to post server rules to a channel.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import config
from src.core.logger import log


# =============================================================================
# Rules Content
# =============================================================================

RULES_HEADER = """# Server Rules

```
By joining this server, you agree to follow these rules.
Ignorance is not an excuse. Staff decisions are final.
```"""

RULES = [
    # Rule 1 - Zero tolerance, instant ban
    """## 1. Terrorism & Extremism
```
• Zero tolerance for ISIS, Al-Qaeda, or any extremist groups
• No praise, support, propaganda, or jokes about terrorism
• Includes usernames, avatars, banners, media → instant ban
```""",

    # Rule 2 - Zero tolerance
    """## 2. Hate Speech
```
• No racial, religious, or ethnic slurs
• No dehumanizing language toward any group
• All backgrounds are respected here
```""",

    # Rule 3 - Core community value
    """## 3. Respect & Conduct
```
• No harassment, bullying, threats, or personal attacks
• No insults based on religion, ethnicity, region, or family
• Stay civil even when disagreeing
```""",

    # Rule 4 - Serious, instant ban possible
    """## 4. NSFW Content
```
• No pornography, sexual media, or explicit content
• No sexual jokes or comments toward minors
• Unwanted sexual DMs → instant ban
```""",

    # Rule 5 - Serious, doxxing
    """## 5. Privacy & Security
```
• No doxxing or leaking personal information
• No sharing DMs or screenshots without consent
• No phishing links, malware, or fake giveaways
```""",

    # Rule 6 - Instant ban
    """## 6. Advertising & Self-Promotion
```
• No promoting servers, communities, or content through DMs
• No self-promotion (YouTube, TikTok, social media, etc.)
• Contact 📥・inbox for partnerships → private recruiting = ban
```""",

    # Rule 7 - Trust/identity
    """## 7. Impersonation
```
• No impersonating staff, members, or public figures
• No alt accounts to evade bans or restrictions
• Includes copying names, avatars, or profiles
```""",

    # Rule 8 - Important for Syrian server
    """## 8. Politics & Sensitive Topics
```
• Political discussions only in ⚔️・debates
• No targeted harassment or agenda-pushing
• Staff may end discussions that escalate
```""",

    # Rule 9 - Visual identity
    """## 9. Profiles & Nicknames
```
• No offensive usernames or avatars
• No terror symbols, hate symbols, or sexual content
• Staff may change names that break rules
```""",

    # Rule 10 - Modern concern
    """## 10. AI-Generated Media
```
• No AI-generated content of server members
• No deepfakes or manipulated identity content
• Violation → instant ban
```""",

    # Rule 11 - Day to day
    """## 11. Spam & Channels
```
• No spam, text walls, or repetitive pinging
• Use the correct channel for each topic
• No pinging staff without a valid reason
```""",

    # Rule 12 - VC specific
    """## 12. Voice Channels
```
• No ear rape, soundboards, excessive noise, or offensive language
• No NSFW or offensive streams/screen shares
• No recording without consent or channel hopping to disrupt
```""",

    # Rule 13 - Minor
    """## 13. Bot Usage
```
• No spamming bot commands
• No exploiting bugs or glitches
• Report exploits to staff instead of abusing them
```""",

    # Rule 14 - Minor
    """## 14. Mini-Modding
```
• Don't act as staff if you're not staff
• Report issues privately in 📥・inbox
• Let moderators handle enforcement
```""",

    # Rule 15 - Language
    """## 15. Language
```
• Arabic and English are both welcome
• Keep conversations readable for others
• No spamming in other languages to exclude people
```""",
]

RULES_FOOTER = """## Reporting Issues
```
Report rule violations in 📥・inbox
Do not ping staff in public channels
Staff does not handle reports in general chat
```

## Discord Terms of Service
```
All users must follow Discord ToS
No accounts under 13 years old
Violations may be reported to Discord
```
-# [Terms of Service](https://discord.com/terms) • [Privacy Policy](https://discord.com/privacy) • [Safety Center](https://discord.com/safety)"""


# =============================================================================
# Rules Cog
# =============================================================================

class RulesCog(commands.Cog):
    """Admin commands for posting server rules."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="rules",
        description="Post server rules to a channel (Admin only)"
    )
    @app_commands.describe(
        channel="Channel to post rules in (default: current channel)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))
    async def rules(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None
    ) -> None:
        """Post all server rules to a channel."""
        target = channel or interaction.channel

        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Rules can only be posted in text channels.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        log.tree("Rules Post Started", [
            ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("Channel", target.name),
            ("Rules Count", str(len(RULES))),
        ], emoji="📜")

        try:
            # Purge all messages in channel first
            deleted = await target.purge(limit=None)
            log.tree("Channel Purged", [
                ("Channel", target.name),
                ("Messages Deleted", str(len(deleted))),
            ], emoji="🗑️")

            # Send header
            await target.send(RULES_HEADER)

            # Send each rule
            for rule in RULES:
                await target.send(rule)

            # Send footer
            await target.send(RULES_FOOTER)

            await interaction.followup.send(
                f"✅ Rules posted to {target.mention}",
                ephemeral=True
            )

            log.tree("Rules Posted", [
                ("Admin", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("Channel", target.name),
                ("Messages", str(len(RULES) + 2)),
            ], emoji="✅")

        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Missing permissions to send messages in {target.mention}",
                ephemeral=True
            )
            log.tree("Rules Post Failed", [
                ("Channel", target.name),
                ("Reason", "Missing permissions"),
            ], emoji="❌")

        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Failed to post rules: {e}",
                ephemeral=True
            )
            log.error_tree("Rules Post Error", e, [
                ("Channel", target.name),
            ])


# =============================================================================
# Setup
# =============================================================================

async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(RulesCog(bot))
    log.tree("Command Loaded", [
        ("Name", "rules"),
    ], emoji="✅")
