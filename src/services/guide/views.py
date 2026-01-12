"""
SyriaBot - Guide Views
======================

Persistent button views for the server guide panel.
All sections have nested dropdowns for better organization.

Author: John Hamwi
Server: discord.gg/syria
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Tuple, Optional

import discord
from discord import ui

from src.core.logger import log
from src.core.config import config
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_GOLD
from src.core.constants import (
    GUIDE_EMOJI_RULES,
    GUIDE_EMOJI_COMMANDS,
    GUIDE_EMOJI_FAQ,
    GUIDE_EMOJI_ROLES,
)
from src.utils.footer import set_footer
from src.services.faq.service import FAQ_DATA

if TYPE_CHECKING:
    from discord import Client


# =============================================================================
# Type Aliases
# =============================================================================

RuleEntry = Tuple[str, str]  # (title, content)


# =============================================================================
# Rules Section (Nested)
# =============================================================================

RULES_CATEGORIES: Dict[str, Dict[str, str]] = {
    "conduct": {
        "label": "General Conduct",
        "emoji": "🤝",
    },
    "content": {
        "label": "Content Rules",
        "emoji": "📝",
    },
    "voice": {
        "label": "Voice & Chat Rules",
        "emoji": "🎤",
    },
    "moderation": {
        "label": "Moderation Info",
        "emoji": "🛡️",
    },
}


class RulesTopicSelect(ui.Select["RulesSelectView"]):
    """Dropdown for selecting rules categories."""

    def __init__(self) -> None:
        options: List[discord.SelectOption] = []

        for key, data in RULES_CATEGORIES.items():
            label = str(data.get("label", key))
            emoji = str(data.get("emoji", "📋"))
            options.append(discord.SelectOption(
                label=label,
                value=key,
                emoji=emoji,
            ))

        if not options:
            log.tree("Rules Select Init", [
                ("Status", "No categories available"),
                ("Fallback", "Adding placeholder option"),
            ], emoji="⚠️")
            options.append(discord.SelectOption(
                label="No categories available",
                value="none",
            ))

        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="guide:rules:select",
        )

        log.tree("Rules Select Initialized", [
            ("Options", str(len(options))),
        ], emoji="📜")

    def _build_rules_content(self, category: str) -> List[Tuple[str, str]]:
        """Build rules content for a category with config channel/role mentions."""
        # Get channel/role mentions with fallbacks
        inbox_ch: str = f"<#{config.INBOX_CHANNEL_ID}>" if config.INBOX_CHANNEL_ID else "the inbox channel"
        mod_role: str = f"<@&{config.MOD_ROLE_ID}>" if config.MOD_ROLE_ID else "staff"

        if not config.INBOX_CHANNEL_ID:
            log.tree("Config Fallback", [
                ("Field", "INBOX_CHANNEL_ID"),
                ("Using", "the inbox channel (text)"),
            ], emoji="ℹ️")
        if not config.MOD_ROLE_ID:
            log.tree("Config Fallback", [
                ("Field", "MOD_ROLE_ID"),
                ("Using", "staff (text)"),
            ], emoji="ℹ️")

        if category == "conduct":
            return [
                ("No Harassment", "Bullying, threats, doxxing, or targeted harassment of any kind is forbidden."),
                ("Respect Everyone", "Treat all members with respect regardless of background, religion, or ethnicity."),
                ("No Drama", f"Keep personal conflicts out of public channels. Handle disputes privately or with {mod_role}."),
                ("English & Arabic Only", "Main chat is English/Arabic. Other languages in appropriate channels only."),
            ]

        elif category == "content":
            return [
                ("No NSFW", "Explicit sexual content, gore, or disturbing imagery is strictly prohibited."),
                ("No Illegal Content", "Drug deals, piracy links, hacking services, or illegal activities are banned."),
                ("No Spam", "Flooding chat, excessive caps, repeated messages, or unicode spam is not allowed."),
                ("No Self-Promo", "Advertising servers, social media, or services without permission is prohibited."),
            ]

        elif category == "voice":
            return [
                ("No Mic Spam", "Loud noises, soundboards, or voice changers that disrupt others are forbidden."),
                ("No Channel Hopping", "Rapidly joining/leaving voice channels to annoy others will result in mutes."),
                ("Respect VC Owners", "In TempVoice channels, the owner's rules apply. Don't argue, just leave."),
                ("No Recording", "Recording voice chats without consent from all participants is prohibited."),
            ]

        elif category == "moderation":
            return [
                ("Staff Decisions Final", f"Do not argue with {mod_role} publicly. Appeal in tickets if needed."),
                ("No Mini-Modding", f"Let {mod_role} handle rule breakers. Use reports instead of calling people out."),
                ("Ban Evasion", "Creating alt accounts to evade bans results in permanent IP bans."),
                ("Report Properly", f"Use {inbox_ch} for reports. Include evidence when possible."),
            ]

        log.tree("Unknown Rules Category", [
            ("Category", category),
        ], emoji="⚠️")
        return []

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle category selection."""
        category: str = self.values[0]

        log.tree("Rules Select Callback", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Category", category),
        ], emoji="📜")

        if category == "none":
            try:
                await interaction.response.send_message(
                    "No rules categories are configured.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                log.error_tree("Rules Select Response Failed", e, [
                    ("User", str(interaction.user.id)),
                    ("Category", category),
                ])
            return

        data: Optional[Dict[str, str]] = RULES_CATEGORIES.get(category)

        if not data:
            log.tree("Rules Category Not Found", [
                ("User", str(interaction.user.id)),
                ("Category", category),
                ("Available", ", ".join(RULES_CATEGORIES.keys())),
            ], emoji="❌")
            try:
                await interaction.response.send_message(
                    "Category not found.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                log.error_tree("Rules Error Response Failed", e, [
                    ("User", str(interaction.user.id)),
                ])
            return

        try:
            label: str = data.get("label", category)
            emoji: str = data.get("emoji", "📋")
            rules: List[Tuple[str, str]] = self._build_rules_content(category)

            embed = discord.Embed(
                title=f"{emoji} {label}",
                color=COLOR_GOLD,
            )

            if rules:
                for title, content in rules:
                    embed.add_field(name=title, value=content, inline=False)
                log.tree("Rules Embed Built", [
                    ("Category", label),
                    ("Rules", str(len(rules))),
                ], emoji="✅")
            else:
                embed.description = "No rules defined for this category."
                log.tree("Rules Category Empty", [
                    ("Category", label),
                ], emoji="⚠️")

            set_footer(embed)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            log.tree("Guide Rules Selected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Category", label),
                ("Rules Shown", str(len(rules))),
            ], emoji="📜")

        except discord.HTTPException as e:
            log.error_tree("Rules Response Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Category", category),
            ])
        except Exception as e:
            log.error_tree("Rules Callback Error", e, [
                ("User", str(interaction.user.id)),
                ("Category", category),
            ])
            try:
                await interaction.response.send_message(
                    "An error occurred while loading rules.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass


class RulesSelectView(ui.View):
    """View with rules category dropdown."""

    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_item(RulesTopicSelect())


# =============================================================================
# Roles Section (Nested)
# =============================================================================

ROLES_CATEGORIES: Dict[str, Dict[str, str]] = {
    "auto": {
        "label": "Auto Roles",
        "emoji": "🤖",
    },
    "self_assign": {
        "label": "Self-Assign Roles",
        "emoji": "✋",
    },
    "purchasable": {
        "label": "Purchasable Roles",
        "emoji": "💰",
    },
    "special": {
        "label": "Special Roles",
        "emoji": "⭐",
    },
    "level_perks": {
        "label": "Level Permissions",
        "emoji": "📈",
    },
}


class RolesTopicSelect(ui.Select["RolesSelectView"]):
    """Dropdown for selecting role categories."""

    def __init__(self) -> None:
        options: List[discord.SelectOption] = []

        for key, data in ROLES_CATEGORIES.items():
            options.append(discord.SelectOption(
                label=data.get("label", key),
                value=key,
                emoji=data.get("emoji", "🎭"),
            ))

        if not options:
            log.tree("Roles Select Init", [
                ("Status", "No categories available"),
            ], emoji="⚠️")
            options.append(discord.SelectOption(
                label="No categories available",
                value="none",
            ))

        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="guide:roles:select",
        )

        log.tree("Roles Select Initialized", [
            ("Options", str(len(options))),
        ], emoji="🎭")

    def _build_role_content(self, category: str) -> str:
        """Build role content for a category with config fallbacks."""
        if category == "auto":
            citizen: str = f"<@&{config.AUTO_ROLE_ID}>" if config.AUTO_ROLE_ID else "Citizens"
            if not config.AUTO_ROLE_ID:
                log.tree("Config Fallback", [
                    ("Field", "AUTO_ROLE_ID"),
                    ("Using", "Citizens (text)"),
                ], emoji="ℹ️")
            return (
                f"**{citizen}**\n"
                "Automatically given when you join the server.\n\n"
                "**Level Roles**\n"
                "Assigned automatically as you level up through activity.\n"
                "Chat and spend time in voice to earn XP!"
            )

        elif category == "self_assign":
            return (
                "**How to Get Roles:**\n"
                "1. Click **Browse Channels** at the top of the channel list\n"
                "2. Select **Channels & Roles**\n"
                "3. Pick your roles!\n\n"
                "**Available Categories:**\n"
                "• Gender (Male/Female)\n"
                "• Age Range\n"
                "• Ethnicity\n"
                "• Religion\n"
                "• Notification Pings"
            )

        elif category == "purchasable":
            roles_ch: str = f"<#{config.ROLES_CHANNEL_ID}>" if config.ROLES_CHANNEL_ID else "the roles channel"
            if not config.ROLES_CHANNEL_ID:
                log.tree("Config Fallback", [
                    ("Field", "ROLES_CHANNEL_ID"),
                    ("Using", "the roles channel (text)"),
                ], emoji="ℹ️")
            return (
                "**How to Get Coins:**\n"
                "• Chat in the server\n"
                "• Play minigames and casino\n"
                "• Win giveaways\n\n"
                f"**Where to Buy:**\n"
                f"Visit {roles_ch} to rent cosmetic roles with your coins.\n\n"
                "**Note:** Purchased roles are rentals and expire after a set time."
            )

        elif category == "special":
            booster: str = f"<@&{config.BOOSTER_ROLE_ID}>" if config.BOOSTER_ROLE_ID else "Booster"
            mod: str = f"<@&{config.MOD_ROLE_ID}>" if config.MOD_ROLE_ID else "Staff"
            if not config.BOOSTER_ROLE_ID:
                log.tree("Config Fallback", [
                    ("Field", "BOOSTER_ROLE_ID"),
                    ("Using", "Booster (text)"),
                ], emoji="ℹ️")
            if not config.MOD_ROLE_ID:
                log.tree("Config Fallback", [
                    ("Field", "MOD_ROLE_ID"),
                    ("Using", "Staff (text)"),
                ], emoji="ℹ️")
            return (
                f"**{booster}**\n"
                "• 2x XP multiplier on all activities\n"
                "• Unlimited downloads and conversions\n"
                "• Special booster badge\n"
                "• Access to exclusive channels\n\n"
                f"**{mod}**\n"
                "• Admin assigned only\n"
                "• Apply when applications open\n"
                "• Must be active and trusted"
            )

        elif category == "level_perks":
            return (
                "Unlock permissions as you level up:\n\n"
                "**Level 1**\n"
                "• Connect to voice channels\n\n"
                "**Level 5**\n"
                "• Attach files and images\n"
                "• Embed links in messages\n\n"
                "**Level 10**\n"
                "• Use external emojis\n\n"
                "**Level 20**\n"
                "• Use external stickers\n\n"
                "**Level 30**\n"
                "• Change your nickname"
            )

        log.tree("Unknown Role Category", [
            ("Category", category),
        ], emoji="⚠️")
        return "Information not available for this category."

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle category selection."""
        category: str = self.values[0]

        log.tree("Roles Select Callback", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Category", category),
        ], emoji="🎭")

        if category == "none":
            try:
                await interaction.response.send_message(
                    "No role categories are configured.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                log.error_tree("Roles Select Response Failed", e, [
                    ("User", str(interaction.user.id)),
                ])
            return

        data: Optional[Dict[str, str]] = ROLES_CATEGORIES.get(category)

        if not data:
            log.tree("Roles Category Not Found", [
                ("User", str(interaction.user.id)),
                ("Category", category),
                ("Available", ", ".join(ROLES_CATEGORIES.keys())),
            ], emoji="❌")
            try:
                await interaction.response.send_message(
                    "Category not found.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                log.error_tree("Roles Error Response Failed", e, [
                    ("User", str(interaction.user.id)),
                ])
            return

        try:
            label: str = data.get("label", category)
            emoji: str = data.get("emoji", "🎭")

            embed = discord.Embed(
                title=f"{emoji} {label}",
                color=COLOR_SYRIA_GREEN,
            )

            embed.description = self._build_role_content(category)
            set_footer(embed)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            log.tree("Guide Roles Selected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Category", label),
            ], emoji="🎭")

        except discord.HTTPException as e:
            log.error_tree("Roles Response Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Category", category),
            ])
        except Exception as e:
            log.error_tree("Roles Callback Error", e, [
                ("User", str(interaction.user.id)),
                ("Category", category),
            ])
            try:
                await interaction.response.send_message(
                    "An error occurred while loading role information.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass


class RolesSelectView(ui.View):
    """View with roles category dropdown."""

    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_item(RolesTopicSelect())


# =============================================================================
# Commands Section (Nested)
# =============================================================================

COMMANDS_CATEGORIES: Dict[str, Dict[str, str]] = {
    "fun": {
        "label": "Fun Commands",
        "emoji": "🎉",
    },
    "actions": {
        "label": "Action Commands",
        "emoji": "💫",
    },
    "utility": {
        "label": "Utility Commands",
        "emoji": "🔧",
    },
    "social": {
        "label": "Social Commands",
        "emoji": "💬",
    },
}


class CommandsTopicSelect(ui.Select["CommandsSelectView"]):
    """Dropdown for selecting command categories."""

    def __init__(self) -> None:
        options: List[discord.SelectOption] = []

        for key, data in COMMANDS_CATEGORIES.items():
            options.append(discord.SelectOption(
                label=data.get("label", key),
                value=key,
                emoji=data.get("emoji", "🤖"),
            ))

        if not options:
            log.tree("Commands Select Init", [
                ("Status", "No categories available"),
            ], emoji="⚠️")
            options.append(discord.SelectOption(
                label="No categories available",
                value="none",
            ))

        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="guide:commands:select",
        )

        log.tree("Commands Select Initialized", [
            ("Options", str(len(options))),
        ], emoji="🤖")

    def _build_command_content(self, category: str) -> str:
        """Build command content for a category with config fallbacks."""
        fun_ch: str = f"<#{config.FUN_COMMANDS_CHANNEL_ID}>" if config.FUN_COMMANDS_CHANNEL_ID else "the fun channel"

        if not config.FUN_COMMANDS_CHANNEL_ID and category == "fun":
            log.tree("Config Fallback", [
                ("Field", "FUN_COMMANDS_CHANNEL_ID"),
                ("Using", "the fun channel (text)"),
            ], emoji="ℹ️")

        if category == "fun":
            return (
                f"*Use these in {fun_ch}*\n\n"
                "**Compatibility**\n"
                "`ship @user @user` - Check love compatibility\n\n"
                "**Meter Cards**\n"
                "`howgay` - Rainbow meter\n"
                "`simp` - Simp-o-meter\n"
                "`howsmart` - IQ meter\n"
                "`bodyfat` - Body fat percentage\n\n"
                "*All meters are random and just for fun!*"
            )

        elif category == "actions":
            return (
                "**Target Actions** *(mention someone)*\n"
                "`hug @user` - Give someone a hug\n"
                "`kiss @user` - Kiss someone\n"
                "`slap @user` - Slap someone\n"
                "`pat @user` - Pat someone's head\n"
                "`poke @user` - Poke someone\n"
                "`cuddle @user` - Cuddle with someone\n"
                "`bite @user` - Bite someone\n\n"
                "**Self Actions** *(no target needed)*\n"
                "`cry` `dance` `laugh` `sleep` `blush`\n"
                "`smile` `wave` `shrug` `facepalm`\n\n"
                "*40+ actions available! All use anime GIFs.*"
            )

        elif category == "utility":
            return (
                "**XP & Profile**\n"
                "`/rank` - View your level and XP\n"
                "`/rank @user` - View someone else's rank\n\n"
                "**Media Tools**\n"
                "`/get avatar @user` - Get someone's avatar\n"
                "`/get banner @user` - Get someone's banner\n"
                "`/download [url]` - Download social media videos\n"
                "`/convert` - Convert video to GIF\n"
                "`/image [query]` - Search for images\n\n"
                "**Other**\n"
                "`/weather [city]` - Check weather anywhere\n"
                "`/translate [text]` - Translate text"
            )

        elif category == "social":
            return (
                "**Confessions**\n"
                "`/confess` - Send an anonymous confession\n"
                "Your identity is hidden from everyone.\n\n"
                "**Suggestions**\n"
                "`/suggest` - Submit a server suggestion\n"
                "Members can vote on suggestions.\n\n"
                "**AFK System**\n"
                "`/afk [reason]` - Set yourself as AFK\n"
                "Others will be notified when they ping you.\n\n"
                "**Birthdays**\n"
                "`/birthday set` - Set your birthday\n"
                "Get announced and a special role on your day!"
            )

        log.tree("Unknown Command Category", [
            ("Category", category),
        ], emoji="⚠️")
        return "Information not available for this category."

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle category selection."""
        category: str = self.values[0]

        log.tree("Commands Select Callback", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Category", category),
        ], emoji="🤖")

        if category == "none":
            try:
                await interaction.response.send_message(
                    "No command categories are configured.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                log.error_tree("Commands Select Response Failed", e, [
                    ("User", str(interaction.user.id)),
                ])
            return

        data: Optional[Dict[str, str]] = COMMANDS_CATEGORIES.get(category)

        if not data:
            log.tree("Commands Category Not Found", [
                ("User", str(interaction.user.id)),
                ("Category", category),
                ("Available", ", ".join(COMMANDS_CATEGORIES.keys())),
            ], emoji="❌")
            try:
                await interaction.response.send_message(
                    "Category not found.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                log.error_tree("Commands Error Response Failed", e, [
                    ("User", str(interaction.user.id)),
                ])
            return

        try:
            label: str = data.get("label", category)
            emoji: str = data.get("emoji", "🤖")

            embed = discord.Embed(
                title=f"{emoji} {label}",
                color=COLOR_SYRIA_GREEN,
            )

            embed.description = self._build_command_content(category)
            set_footer(embed)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            log.tree("Guide Commands Selected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Category", label),
            ], emoji="🤖")

        except discord.HTTPException as e:
            log.error_tree("Commands Response Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Category", category),
            ])
        except Exception as e:
            log.error_tree("Commands Callback Error", e, [
                ("User", str(interaction.user.id)),
                ("Category", category),
            ])
            try:
                await interaction.response.send_message(
                    "An error occurred while loading command information.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass


class CommandsSelectView(ui.View):
    """View with commands category dropdown."""

    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_item(CommandsTopicSelect())


# =============================================================================
# FAQ Section (Nested)
# =============================================================================

FAQ_OPTIONS: Dict[str, Tuple[str, str]] = {
    "xp": ("XP & Leveling", "📊"),
    "roles": ("How to Get Roles", "🎭"),
    "tempvoice": ("TempVoice Channels", "🎤"),
    "report": ("How to Report", "📥"),
    "confess": ("Confessions", "🤫"),
    "language": ("Language Rules", "🌍"),
    "staff": ("Becoming Staff", "👮"),
    "invite": ("Server Invite", "🔗"),
    "download": ("Download Command", "📥"),
    "convert": ("Convert to GIF", "🔄"),
    "economy": ("Economy System", "💰"),
    "casino": ("Casino Games", "🎰"),
    "games": ("Minigames", "🎮"),
    "giveaway": ("Giveaways", "🎉"),
    "partnership": ("Partnerships", "🤝"),
}


class FAQTopicSelect(ui.Select["FAQSelectView"]):
    """Dropdown for selecting FAQ topics."""

    def __init__(self) -> None:
        options: List[discord.SelectOption] = []
        available_topics: List[str] = []

        for key, (label, emoji) in FAQ_OPTIONS.items():
            if key in FAQ_DATA:
                options.append(discord.SelectOption(
                    label=label,
                    value=key,
                    emoji=emoji,
                ))
                available_topics.append(key)

        if not options:
            log.tree("FAQ Select Init", [
                ("Status", "No topics available"),
                ("FAQ_DATA Keys", ", ".join(FAQ_DATA.keys()) if FAQ_DATA else "Empty"),
            ], emoji="⚠️")
            options.append(discord.SelectOption(
                label="No topics available",
                value="none",
            ))

        super().__init__(
            placeholder="Select a topic...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="guide:faq:select",
        )

        log.tree("FAQ Select Initialized", [
            ("Options", str(len(options))),
            ("Topics", ", ".join(available_topics) if available_topics else "None"),
        ], emoji="❓")

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle topic selection."""
        topic: str = self.values[0]

        log.tree("FAQ Select Callback", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Topic", topic),
        ], emoji="❓")

        if topic == "none":
            try:
                await interaction.response.send_message(
                    "No FAQ topics are configured.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                log.error_tree("FAQ Select Response Failed", e, [
                    ("User", str(interaction.user.id)),
                ])
            return

        faq: Optional[Dict] = FAQ_DATA.get(topic)

        if not faq:
            log.tree("FAQ Topic Not Found", [
                ("User", str(interaction.user.id)),
                ("Topic", topic),
                ("Available", ", ".join(FAQ_DATA.keys())),
            ], emoji="❌")
            try:
                await interaction.response.send_message(
                    "FAQ topic not found.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                log.error_tree("FAQ Error Response Failed", e, [
                    ("User", str(interaction.user.id)),
                ])
            return

        try:
            title_data: Dict[str, str] = faq.get("title", {})
            desc_data: Dict[str, str] = faq.get("description", {})

            title: str = title_data.get("en", "FAQ")
            description: str = desc_data.get("en", "No content available.")

            embed = discord.Embed(
                title=title,
                description=description,
                color=COLOR_SYRIA_GREEN,
            )
            set_footer(embed)

            view = FAQResponseView(topic)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            log.tree("Guide FAQ Selected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Topic", topic),
                ("Title", title[:30]),
            ], emoji="❓")

        except discord.HTTPException as e:
            log.error_tree("FAQ Response Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Topic", topic),
            ])
        except Exception as e:
            log.error_tree("FAQ Callback Error", e, [
                ("User", str(interaction.user.id)),
                ("Topic", topic),
            ])
            try:
                await interaction.response.send_message(
                    "An error occurred while loading the FAQ.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass


class FAQResponseView(ui.View):
    """View for FAQ response with language toggle."""

    def __init__(self, topic: str, lang: str = "en") -> None:
        super().__init__(timeout=300)
        self.topic: str = topic
        self.lang: str = lang

        log.tree("FAQ Response View Created", [
            ("Topic", topic),
            ("Language", lang),
        ], emoji="🌐")

    @ui.button(label="العربية", emoji="🇸🇦", style=discord.ButtonStyle.secondary)
    async def toggle_language(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        """Toggle between English and Arabic."""
        old_lang: str = self.lang
        self.lang = "ar" if self.lang == "en" else "en"
        button.label = "English" if self.lang == "ar" else "العربية"

        log.tree("FAQ Language Toggle", [
            ("User", f"{interaction.user.name}"),
            ("ID", str(interaction.user.id)),
            ("Topic", self.topic),
            ("From", old_lang.upper()),
            ("To", self.lang.upper()),
        ], emoji="🌐")

        faq: Optional[Dict] = FAQ_DATA.get(self.topic)

        if not faq:
            log.tree("FAQ Data Missing on Toggle", [
                ("Topic", self.topic),
            ], emoji="❌")
            try:
                await interaction.response.send_message(
                    "FAQ data not found.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass
            return

        try:
            title_data: Dict[str, str] = faq.get("title", {})
            desc_data: Dict[str, str] = faq.get("description", {})

            title: str = title_data.get(self.lang, title_data.get("en", "FAQ"))
            description: str = desc_data.get(self.lang, desc_data.get("en", "No content."))

            embed = discord.Embed(
                title=title,
                description=description,
                color=COLOR_SYRIA_GREEN,
            )
            set_footer(embed)

            await interaction.response.edit_message(embed=embed, view=self)

            log.tree("FAQ Language Toggled", [
                ("User", f"{interaction.user.name}"),
                ("Topic", self.topic),
                ("Language", self.lang.upper()),
            ], emoji="✅")

        except discord.HTTPException as e:
            log.error_tree("FAQ Toggle Response Failed", e, [
                ("User", str(interaction.user.id)),
                ("Topic", self.topic),
                ("Language", self.lang),
            ])
        except Exception as e:
            log.error_tree("FAQ Toggle Error", e, [
                ("User", str(interaction.user.id)),
                ("Topic", self.topic),
            ])


class FAQSelectView(ui.View):
    """View with FAQ topic dropdown."""

    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_item(FAQTopicSelect())


# =============================================================================
# Guide View (Persistent) - Main Panel
# =============================================================================

class GuideView(ui.View):
    """
    Persistent view with buttons for server guide sections.
    Survives bot restarts via custom_id registration.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    def _build_rules_content(self) -> str:
        """Build all rules content with config channel/role mentions."""
        inbox_ch: str = f"<#{config.INBOX_CHANNEL_ID}>" if config.INBOX_CHANNEL_ID else "the inbox channel"
        mod_role: str = f"<@&{config.MOD_ROLE_ID}>" if config.MOD_ROLE_ID else "staff"

        return (
            "**🚫 Zero Tolerance**\n"
            "• No terrorism, extremism, or support for terrorist groups\n"
            "• No glorifying violence, war crimes, or armed militias\n"
            "• No sectarian hate or religious extremism\n"
            "• No political propaganda or recruitment\n"
            "• No racism, sexism, homophobia, or discrimination\n\n"
            "**🤝 General Conduct**\n"
            "• Be respectful to everyone regardless of background\n"
            "• No harassment, bullying, threats, or doxxing\n"
            "• No impersonating staff or other members\n"
            "• No begging for roles, permissions, or currency\n"
            f"• Keep drama private - use {mod_role} for disputes\n"
            "• English & Arabic only in main chat\n\n"
            "**📝 Content Rules**\n"
            "• No NSFW, gore, or disturbing imagery\n"
            "• No illegal content, piracy, or hacking services\n"
            "• No scamming, phishing, or malicious links\n"
            "• No spam, flooding, or excessive caps/emojis\n"
            "• No self-promotion or server advertising\n"
            "• No DM advertising - instant ban\n\n"
            "**👤 Profile Rules**\n"
            "• No offensive usernames, avatars, or banners\n"
            "• No impersonating celebrities or public figures\n"
            "• No inappropriate custom statuses\n\n"
            "**🔒 Privacy & Safety**\n"
            "• Don't share others' personal information\n"
            "• Don't ask members for personal details\n"
            "• No unsolicited DMs to members\n"
            "• You must be 13+ to use Discord (TOS)\n\n"
            "**🎤 Voice & Chat Rules**\n"
            "• No mic spam, soundboards, or loud noises\n"
            "• No channel hopping to annoy others\n"
            "• Respect TempVoice channel owners\n"
            "• No recording without consent\n"
            "• Use channels for their intended purpose\n\n"
            "**🛡️ Moderation**\n"
            f"• {mod_role} decisions are final - appeal in tickets\n"
            "• No mini-modding - report instead of calling out\n"
            "• No alt accounts - ban evasion = IP ban\n"
            f"• Use {inbox_ch} to report with evidence"
        )

    @ui.button(
        label="Rules",
        style=discord.ButtonStyle.secondary,
        custom_id="guide:rules",
        emoji=GUIDE_EMOJI_RULES,
        row=0,
    )
    async def rules_button(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        """Show server rules."""
        log.tree("Guide Rules Button", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Guild", interaction.guild.name if interaction.guild else "DM"),
        ], emoji="📜")

        try:
            embed = discord.Embed(
                title="Server Rules",
                description=self._build_rules_content(),
                color=COLOR_GOLD,
            )
            set_footer(embed)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            log.tree("Guide Button Response Sent", [
                ("Section", "Rules"),
                ("User", str(interaction.user.id)),
            ], emoji="✅")

        except discord.HTTPException as e:
            log.error_tree("Guide Rules Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
        except Exception as e:
            log.error_tree("Guide Rules Button Error", e, [
                ("User", str(interaction.user.id)),
            ])
            try:
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass

    def _build_roles_content(self) -> str:
        """Build all roles content with config mentions."""
        citizen: str = f"<@&{config.AUTO_ROLE_ID}>" if config.AUTO_ROLE_ID else "Citizens"
        booster: str = f"<@&{config.BOOSTER_ROLE_ID}>" if config.BOOSTER_ROLE_ID else "Booster"
        roles_ch: str = f"<#{config.ROLES_CHANNEL_ID}>" if config.ROLES_CHANNEL_ID else "the roles channel"

        return (
            f"**🤖 Auto Roles**\n"
            f"• {citizen} - Given when you join\n"
            "• Level roles - Earned through activity\n\n"
            "**✋ Self-Assign Roles**\n"
            "Go to **Browse Channels** → **Channels & Roles**\n"
            "• Gender, Age, Ethnicity, Religion\n"
            "• Notification pings\n\n"
            f"**💰 Purchasable Roles**\n"
            f"Visit {roles_ch} to rent cosmetic roles with coins.\n"
            "Earn coins through chat, minigames, and giveaways.\n\n"
            f"**⭐ Special Roles**\n"
            f"• {booster} - 2x XP, unlimited downloads, exclusive channels\n"
            "• Staff - Admin assigned, apply when apps open\n\n"
            "**📈 Level Permissions**\n"
            "• Lv1: Voice channels\n"
            "• Lv5: Files & embeds\n"
            "• Lv10: External emojis\n"
            "• Lv20: External stickers\n"
            "• Lv30: Change nickname"
        )

    @ui.button(
        label="Roles",
        style=discord.ButtonStyle.secondary,
        custom_id="guide:roles",
        emoji=GUIDE_EMOJI_ROLES,
        row=0,
    )
    async def roles_button(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        """Show server roles info."""
        log.tree("Guide Roles Button", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Guild", interaction.guild.name if interaction.guild else "DM"),
        ], emoji="🎭")

        try:
            embed = discord.Embed(
                title="Server Roles",
                description=self._build_roles_content(),
                color=COLOR_SYRIA_GREEN,
            )
            set_footer(embed)

            await interaction.response.send_message(embed=embed, ephemeral=True)

            log.tree("Guide Button Response Sent", [
                ("Section", "Roles"),
                ("User", str(interaction.user.id)),
            ], emoji="✅")

        except discord.HTTPException as e:
            log.error_tree("Guide Roles Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
        except Exception as e:
            log.error_tree("Guide Roles Button Error", e, [
                ("User", str(interaction.user.id)),
            ])
            try:
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass

    @ui.button(
        label="FAQ",
        style=discord.ButtonStyle.secondary,
        custom_id="guide:faq",
        emoji=GUIDE_EMOJI_FAQ,
        row=0,
    )
    async def faq_button(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        """Show FAQ dropdown."""
        log.tree("Guide FAQ Button", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Guild", interaction.guild.name if interaction.guild else "DM"),
        ], emoji="❓")

        try:
            embed = discord.Embed(
                title="Frequently Asked Questions",
                description=(
                    "Select a topic from the dropdown below.\n\n"
                    "**Popular Topics:**\n"
                    "📊 XP & Leveling\n"
                    "🎭 How to Get Roles\n"
                    "🎤 TempVoice Channels\n"
                    "💰 Economy System\n"
                    "🎰 Casino Games\n"
                    "*...and more!*"
                ),
                color=COLOR_SYRIA_GREEN,
            )
            set_footer(embed)

            view = FAQSelectView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            log.tree("Guide Button Response Sent", [
                ("Section", "FAQ"),
                ("User", str(interaction.user.id)),
            ], emoji="✅")

        except discord.HTTPException as e:
            log.error_tree("Guide FAQ Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
        except Exception as e:
            log.error_tree("Guide FAQ Button Error", e, [
                ("User", str(interaction.user.id)),
            ])
            try:
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass

    @ui.button(
        label="Commands",
        style=discord.ButtonStyle.secondary,
        custom_id="guide:commands",
        emoji=GUIDE_EMOJI_COMMANDS,
        row=0,
    )
    async def commands_button(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        """Show commands category dropdown."""
        log.tree("Guide Commands Button", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Guild", interaction.guild.name if interaction.guild else "DM"),
        ], emoji="🤖")

        try:
            embed = discord.Embed(
                title="Bot Commands",
                description=(
                    "Select a category from the dropdown below.\n\n"
                    "**Categories:**\n"
                    "🎉 Fun Commands\n"
                    "💫 Action Commands\n"
                    "🔧 Utility Commands\n"
                    "💬 Social Commands"
                ),
                color=COLOR_SYRIA_GREEN,
            )
            set_footer(embed)

            view = CommandsSelectView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            log.tree("Guide Button Response Sent", [
                ("Section", "Commands"),
                ("User", str(interaction.user.id)),
            ], emoji="✅")

        except discord.HTTPException as e:
            log.error_tree("Guide Commands Button Failed", e, [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
            ])
        except Exception as e:
            log.error_tree("Guide Commands Button Error", e, [
                ("User", str(interaction.user.id)),
            ])
            try:
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass


# =============================================================================
# Persistent View Registration
# =============================================================================

def setup_guide_views(bot: Client) -> None:
    """
    Register persistent guide views with the bot.
    Call this in bot.setup_hook() to enable buttons after restart.

    Args:
        bot: The Discord bot client instance.
    """
    try:
        bot.add_view(GuideView())
        log.tree("Guide Views Registered", [
            ("View", "GuideView"),
            ("Buttons", "4 (Rules, Roles, FAQ, Commands)"),
            ("Nested", "FAQ and Commands have dropdowns"),
            ("Persistent", "Yes (timeout=None)"),
        ], emoji="✅")
    except Exception as e:
        log.error_tree("Guide Views Registration Failed", e, [
            ("View", "GuideView"),
        ])
        raise
