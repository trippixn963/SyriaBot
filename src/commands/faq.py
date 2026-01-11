"""
SyriaBot - FAQ Command
======================

Moderator command to quickly respond with FAQ templates.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_SYRIA_GREEN


# =============================================================================
# FAQ Templates
# =============================================================================

FAQ_TEMPLATES = {
    "xp": {
        "title": "📊 How XP & Leveling Works",
        "description": """**Earning XP:**
• **Messages:** 8-12 XP per message (60 second cooldown)
• **Voice:** 3 XP per minute (must have 2+ people, not deafened)
• **Boosters:** Get 2x XP multiplier

**Level Rewards:**
• Level 1 → Connect to voice channels
• Level 5 → Attach files & embed links
• Level 10 → Use external emojis
• Level 20 → Use external stickers
• Level 30 → Change nickname

Check your rank with `/rank`""",
    },
    "roles": {
        "title": "🎭 How to Get Roles",
        "description": """**Auto Roles:**
• You get <@&{auto_role}> automatically when you join
• Level roles are given automatically as you level up

**Self-Assign Roles:**
• Go to <id:customize> to pick your roles
• Choose colors, pronouns, notifications, etc.

**Purchasable Roles (Economy):**
• Earn coins by chatting, playing games, and being active
• Check your balance in <#1459658497879707883>
• Buy custom roles in <#1459644341361447181>
• Use Jawdat bot commands to manage your coins

**Special Roles:**
• Booster roles are given when you boost the server
• Staff roles are given by admins only""",
    },
    "tempvoice": {
        "title": "🎤 TempVoice (Custom Voice Channels)",
        "description": """**How to Create:**
1. Join the "Create VC" channel
2. You'll be moved to your own private channel
3. Use the control panel in <#{vc_interface}> to manage it

**What You Can Do:**
• Rename your channel
• Set user limit
• Lock/unlock the channel
• Kick/ban users from your channel
• Transfer ownership

Your channel is deleted when everyone leaves.""",
    },
    "report": {
        "title": "📥 How to Report Someone",
        "description": """**To report a rule violation:**
1. Go to <id:browse> and find 📥・inbox
2. Create a ticket with details
3. Include screenshots/evidence if possible

**Do NOT:**
• Ping staff in public channels
• Report in general chat
• Mini-mod or confront the person yourself

Staff will handle it privately.""",
    },
    "confess": {
        "title": "🤫 Anonymous Confessions",
        "description": """**How to Confess:**
1. Use `/confess` command anywhere
2. Type your confession (text only)
3. It will be posted anonymously

**Rules:**
• No hate speech or harassment
• No doxxing or personal info
• No NSFW content
• Keep it respectful

Confessions can be traced by staff if rules are broken.""",
    },
    "language": {
        "title": "🌍 Language Rules",
        "description": """**Both Arabic and English are welcome!**

• You can chat in either language
• Keep conversations readable for others
• Don't spam in other languages to exclude people

**Arabic Channels:**
Some channels may be Arabic-focused - check channel descriptions.

نرحب بالعربية والإنجليزية في هذا السيرفر 🇸🇾""",
    },
    "staff": {
        "title": "👮 How to Become Staff",
        "description": """**We don't accept staff applications.**

Staff members are hand-picked based on:
• Activity and engagement
• Helpfulness to other members
• Following the rules consistently
• Being a positive presence

**Don't ask to be staff** - it won't help your chances.
Just be a good community member and you might get noticed.""",
    },
    "invite": {
        "title": "🔗 Server Invite",
        "description": """**Permanent Invite Link:**
https://discord.gg/syria

Feel free to share this with friends!

**Note:** Advertising other servers in DMs is against the rules.""",
    },
    "download": {
        "title": "📥 Download Command",
        "description": """**How to Download Videos:**
Use `/download` with a video URL

**Supported Sites:**
• YouTube, TikTok, Instagram, Twitter/X
• Reddit, Facebook, and many more

**Limits:**
• 5 downloads per week
• Max file size depends on boost level

Reply to a message with a link and say `download` to download it.""",
    },
    "convert": {
        "title": "🔄 Convert to GIF",
        "description": """**How to Convert Videos to GIF:**
1. Reply to a message with a video/image
2. Type `convert` or `gif`
3. Use the editor to adjust (crop, speed, etc.)
4. Save the GIF

**Tip:** Works with videos, images, and stickers!""",
    },
    "economy": {
        "title": "💰 Economy System (Jawdat Bot)",
        "description": """**How to Earn Coins:**
• Chat in the server (passive income)
• Play casino games (roulette, blackjack, slots)
• Win minigames and events
• Daily rewards

**Commands:**
• Check your balance in <#1459658497879707883>
• Use `/balance` to see your coins
• Use `/daily` to claim daily reward

**Spending Coins:**
• Buy custom roles in <#1459644341361447181>
• Gamble in the casino (at your own risk!)

**Casino Games:**
Games are in the casino forum - each game has its own post.""",
    },
    "casino": {
        "title": "🎰 Casino Games",
        "description": """**Available Games:**
• 🎡 **Roulette** - Bet on numbers, colors, or ranges
• 🃏 **Blackjack** - Classic 21 card game
• 🎰 **Slots** - Spin to win

**How to Play:**
1. Go to the Casino forum
2. Find the game you want to play
3. Use the bot commands in that post

**Warning:** Gambling can drain your coins fast!
Only bet what you're willing to lose.""",
    },
    "games": {
        "title": "🎮 Minigames & Activities",
        "description": """**Available Games:**
• 🎰 Casino (roulette, blackjack, slots)
• 🚩 Flag guessing game
• 🔢 Counting channel
• More coming soon!

**Flag Game:**
Guess countries from their flags in <#1402445407312941158>

**Counting:**
Count together in <#1457434957772488714> - don't break the chain!

Win coins for participating in games.""",
    },
    "giveaway": {
        "title": "🎉 Giveaways",
        "description": """**How Giveaways Work:**
• Staff will post giveaways in the server
• Click the button to enter
• Winners are picked randomly when it ends

**Requirements:**
• Some giveaways may require certain roles or levels
• Make sure you meet the requirements before entering

**Tips:**
• Keep notifications on so you don't miss giveaways
• Being active increases your chances in some giveaways""",
    },
}


# =============================================================================
# FAQ Cog
# =============================================================================

class FAQCog(commands.Cog):
    """Moderator FAQ response system."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def faq_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for FAQ topics."""
        choices = []
        for key, faq in FAQ_TEMPLATES.items():
            title = faq["title"]
            if current.lower() in key.lower() or current.lower() in title.lower():
                choices.append(app_commands.Choice(name=title, value=key))

        return choices[:25]  # Discord limit

    @app_commands.command(
        name="faq",
        description="Send a FAQ response (Moderator only)"
    )
    @app_commands.describe(
        topic="The FAQ topic to send",
        user="Optional: mention a user in the response"
    )
    @app_commands.autocomplete(topic=faq_autocomplete)
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))
    async def faq(
        self,
        interaction: discord.Interaction,
        topic: str,
        user: Optional[discord.Member] = None,
    ) -> None:
        """Send a FAQ response."""
        if topic not in FAQ_TEMPLATES:
            await interaction.response.send_message(
                f"❌ Unknown FAQ topic: `{topic}`\n"
                f"Available: {', '.join(FAQ_TEMPLATES.keys())}",
                ephemeral=True
            )
            return

        faq = FAQ_TEMPLATES[topic]

        # Format description with config values
        description = faq["description"]
        try:
            description = description.format(
                auto_role=config.AUTO_ROLE_ID,
                vc_interface=config.VC_INTERFACE_CHANNEL_ID,
            )
        except KeyError:
            pass  # Some templates don't need formatting

        embed = discord.Embed(
            title=faq["title"],
            description=description,
            color=COLOR_SYRIA_GREEN,
        )
        embed.set_footer(text="Syria • discord.gg/syria")

        # Build response content
        content = None
        if user:
            content = f"{user.mention}"

        await interaction.response.send_message(
            content=content,
            embed=embed,
        )

        log.tree("FAQ Sent", [
            ("Moderator", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("Topic", topic),
            ("Target User", user.name if user else "None"),
        ], emoji="📋")


# =============================================================================
# Setup
# =============================================================================

async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(FAQCog(bot))
    log.tree("Command Loaded", [
        ("Name", "faq"),
        ("Topics", str(len(FAQ_TEMPLATES))),
    ], emoji="✅")
