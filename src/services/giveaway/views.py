"""
SyriaBot - Giveaway Views
=========================

Interactive views for giveaway setup and entry.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import ui
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from src.core.logger import log
from src.core.config import config
from src.core.colors import COLOR_SYRIA_GREEN, COLOR_GOLD, COLOR_ERROR
from src.utils.footer import set_footer

if TYPE_CHECKING:
    from src.services.giveaway.service import GiveawayService


# =============================================================================
# Constants
# =============================================================================

PRIZE_TYPE_OPTIONS = [
    ("xp", "XP", "⭐", "Award XP to winners"),
    ("coins", "Casino Coins", "💰", "Award casino coins to winners"),
    ("combo", "XP + Coins", "✨", "Award both XP and coins"),
    ("nitro", "Discord Nitro", "🎁", "Nitro giveaway (manual delivery)"),
    ("role", "Role", "🏷️", "Award a role to winners"),
    ("custom", "Custom Prize", "🎉", "Custom prize (manual delivery)"),
]

DURATION_OPTIONS = [
    ("1h", "1 Hour", timedelta(hours=1)),
    ("6h", "6 Hours", timedelta(hours=6)),
    ("12h", "12 Hours", timedelta(hours=12)),
    ("24h", "24 Hours", timedelta(hours=24)),
    ("48h", "48 Hours", timedelta(hours=48)),
    ("7d", "7 Days", timedelta(days=7)),
]

WINNER_OPTIONS = [1, 2, 3, 5, 10]


# =============================================================================
# Setup View - Main Builder
# =============================================================================

class GiveawaySetupView(ui.View):
    """Interactive builder for creating giveaways."""

    def __init__(self, service: "GiveawayService", host: discord.Member):
        super().__init__(timeout=300)  # 5 minute timeout

        self.service = service
        self.host = host
        self.guild = host.guild
        self._original_interaction: Optional[discord.Interaction] = None

        # Giveaway settings (sensible defaults)
        self.prize_type: Optional[str] = None
        self.prize_description: str = ""
        self.prize_amount: int = 0  # XP amount (or coins for coins-only)
        self.prize_coins: int = 0   # Coins amount (for combo prizes)
        self.prize_role_id: Optional[int] = None
        self.duration: timedelta = timedelta(hours=24)  # Default: 24 hours
        self.duration_key: str = "24h"
        self.winner_count: int = 1  # Default: 1 winner
        self.required_role_id: Optional[int] = None
        self.min_level: int = 0
        self.ping_role: bool = False  # Whether to ping giveaway role

    def set_original_interaction(self, interaction: discord.Interaction) -> None:
        """Store the original interaction for later updates."""
        self._original_interaction = interaction

    def build_preview_embed(self) -> discord.Embed:
        """Build preview embed showing current settings."""
        embed = discord.Embed(
            title="🎉 Giveaway Builder",
            description="Use the buttons below to configure your giveaway.",
            color=COLOR_GOLD,
        )

        # Prize
        if self.prize_type:
            prize_emoji = next(
                (emoji for key, _, emoji, _ in PRIZE_TYPE_OPTIONS if key == self.prize_type),
                "🎁"
            )
            prize_text = f"{prize_emoji} `{self.prize_description or 'Not set'}`"
            if self.prize_type == "role" and self.prize_role_id:
                role = self.guild.get_role(self.prize_role_id)
                if role:
                    prize_text += f"\n{role.mention}"
        else:
            prize_text = "❓ Not selected"
        embed.add_field(name="Prize", value=prize_text, inline=True)

        # Duration - show as timestamp
        ends_at = datetime.now(ZoneInfo("America/New_York")) + self.duration
        timestamp = int(ends_at.timestamp())
        embed.add_field(name="Ends", value=f"<t:{timestamp}:R>", inline=True)

        # Winners
        embed.add_field(name="Winners", value=f"`{self.winner_count}`", inline=True)

        # Requirements
        req_parts = []
        if self.required_role_id:
            role = self.guild.get_role(self.required_role_id)
            req_parts.append(f"{role.mention if role else 'Unknown'}")
        if self.min_level > 0:
            req_parts.append(f"Level `{self.min_level}+`")
        req_text = " • ".join(req_parts) if req_parts else "`None`"
        embed.add_field(name="Requirements", value=req_text, inline=True)

        # Ping status
        ping_text = "`Yes`" if self.ping_role else "`No`"
        embed.add_field(name="Ping", value=ping_text, inline=True)

        # Ready status (only prize is required, duration has default)
        ready = all([self.prize_type, self.prize_description])
        status = "✅ Ready!" if ready else "⚠️ Set a prize"
        embed.add_field(name="Status", value=status, inline=True)

        set_footer(embed)
        return embed

    async def update_embed(self, interaction: discord.Interaction) -> None:
        """Update the setup message with current settings (for direct button interactions)."""
        embed = self.build_preview_embed()
        await interaction.message.edit(embed=embed, view=self)

    async def refresh_original(self) -> None:
        """Refresh the original builder message (for child view callbacks)."""
        if self._original_interaction:
            embed = self.build_preview_embed()
            try:
                await self._original_interaction.edit_original_response(embed=embed, view=self)
            except Exception:
                pass  # Original message may have been deleted

    # -------------------------------------------------------------------------
    # Row 0: Prize Type
    # -------------------------------------------------------------------------

    @ui.button(label="Set Prize", style=discord.ButtonStyle.primary, emoji="🎁", row=0)
    async def prize_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Open prize type selection."""
        view = PrizeTypeView(self)
        await interaction.response.send_message(
            "**Select prize type:**",
            view=view,
            ephemeral=True
        )

    @ui.button(label="Set Duration", style=discord.ButtonStyle.primary, emoji="⏱️", row=0)
    async def duration_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Open duration selection."""
        view = DurationView(self)
        await interaction.response.send_message(
            "**Select giveaway duration:**",
            view=view,
            ephemeral=True
        )

    @ui.button(label="Set Winners", style=discord.ButtonStyle.primary, emoji="🏆", row=0)
    async def winners_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Open winner count selection."""
        view = WinnerCountView(self)
        await interaction.response.send_message(
            "**Select number of winners:**",
            view=view,
            ephemeral=True
        )

    # -------------------------------------------------------------------------
    # Row 1: Requirements (Optional)
    # -------------------------------------------------------------------------

    @ui.button(label="Add Role Requirement", style=discord.ButtonStyle.secondary, emoji="🏷️", row=1)
    async def role_req_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Add a role requirement."""
        view = RoleRequirementView(self)
        await interaction.response.send_message(
            "**Select required role to enter:**",
            view=view,
            ephemeral=True
        )

    @ui.button(label="Add Level Requirement", style=discord.ButtonStyle.secondary, emoji="⭐", row=1)
    async def level_req_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Add a level requirement."""
        await interaction.response.send_modal(LevelRequirementModal(self))

    @ui.button(label="Clear Requirements", style=discord.ButtonStyle.secondary, emoji="🗑️", row=1)
    async def clear_req_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Clear all requirements."""
        self.required_role_id = None
        self.min_level = 0

        log.tree("Giveaway Setup - Requirements Cleared", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ], emoji="🗑️")

        await interaction.response.defer()
        await self.update_embed(interaction)

    @ui.button(label="Toggle Ping", style=discord.ButtonStyle.secondary, emoji="🔔", row=1)
    async def ping_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Toggle whether to ping giveaway role."""
        self.ping_role = not self.ping_role

        log.tree("Giveaway Setup - Ping Toggled", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Ping", "Yes" if self.ping_role else "No"),
        ], emoji="🔔" if self.ping_role else "🔕")

        await interaction.response.defer()
        await self.update_embed(interaction)

    # -------------------------------------------------------------------------
    # Row 2: Actions
    # -------------------------------------------------------------------------

    @ui.button(label="Start Giveaway", style=discord.ButtonStyle.success, emoji="🚀", row=2)
    async def start_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Start the giveaway with current settings."""
        # Validate settings (only prize required, others have defaults)
        if not self.prize_type or not self.prize_description:
            await interaction.response.send_message(
                "Please set a prize first!", ephemeral=True
            )
            return

        log.tree("Giveaway Setup - Starting", [
            ("Host", f"{self.host.name} ({self.host.display_name})"),
            ("ID", str(self.host.id)),
            ("Prize", self.prize_description[:30]),
            ("Type", self.prize_type),
            ("Duration", self.duration_key),
            ("Winners", str(self.winner_count)),
        ], emoji="🚀")

        # Create giveaway
        success, message, giveaway_id = await self.service.create_giveaway(
            host=self.host,
            prize_type=self.prize_type,
            prize_description=self.prize_description,
            prize_amount=self.prize_amount,
            prize_coins=self.prize_coins,
            prize_role_id=self.prize_role_id,
            required_role_id=self.required_role_id,
            min_level=self.min_level,
            winner_count=self.winner_count,
            duration=self.duration,
            ping_role=self.ping_role,
        )

        if success:
            embed = discord.Embed(
                title="Giveaway Started!",
                description=f"Your giveaway for **{self.prize_description}** has been created!\n\n"
                           f"Check <#{config.GIVEAWAY_CHANNEL_ID}> to see it.",
                color=COLOR_SYRIA_GREEN,
            )
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
        else:
            await interaction.response.send_message(
                f"Failed to start giveaway: {message}", ephemeral=True
            )

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️", row=2)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Cancel giveaway setup."""
        log.tree("Giveaway Setup - Cancelled", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ], emoji="❌")

        embed = discord.Embed(
            title="Setup Cancelled",
            description="Giveaway setup has been cancelled.",
            color=COLOR_ERROR,
        )
        set_footer(embed)
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    async def on_timeout(self) -> None:
        """Handle view timeout."""
        log.tree("Giveaway Setup - Timeout", [
            ("Host", f"{self.host.name} ({self.host.id})"),
        ], emoji="⏰")


# =============================================================================
# Prize Type Selection
# =============================================================================

class PrizeTypeSelect(ui.Select):
    """Dropdown to select prize type."""

    def __init__(self, parent_view: GiveawaySetupView):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label=label,
                value=key,
                emoji=emoji,
                description=desc,
            )
            for key, label, emoji, desc in PRIZE_TYPE_OPTIONS
        ]

        super().__init__(
            placeholder="Select prize type...",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        prize_type = self.values[0]
        self.parent_view.prize_type = prize_type

        prize_name = next(
            (label for key, label, _, _ in PRIZE_TYPE_OPTIONS if key == prize_type),
            prize_type
        )

        log.tree("Giveaway Setup - Prize Type", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Type", prize_name),
        ], emoji="🎁")

        # Different flows based on prize type
        if prize_type in ("xp", "coins"):
            # Need amount only (description auto-generated)
            await interaction.response.send_modal(PrizeAmountModal(self.parent_view))
        elif prize_type == "combo":
            # Need both XP and coins amounts
            await interaction.response.send_modal(ComboAmountModal(self.parent_view))
        elif prize_type == "role":
            # Need role selection (description auto-generated from role name)
            view = PrizeRoleView(self.parent_view)
            await interaction.response.edit_message(
                content="**Select the role to award:**",
                view=view
            )
        elif prize_type == "nitro":
            # Auto-set description for Nitro
            self.parent_view.prize_description = "Discord Nitro"
            await interaction.response.defer()
            await self.parent_view.refresh_original()
            await interaction.delete_original_response()
        else:
            # Custom prize - need manual description
            await interaction.response.send_modal(PrizeDescriptionModal(self.parent_view))


class PrizeTypeView(ui.View):
    """View containing prize type select."""

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__(timeout=60)
        self.add_item(PrizeTypeSelect(parent_view))


# =============================================================================
# Prize Role Selection (for role prizes)
# =============================================================================

class PrizeRoleSelect(ui.RoleSelect):
    """Role select for prize role."""

    def __init__(self, parent_view: GiveawaySetupView):
        self.parent_view = parent_view
        super().__init__(placeholder="Select role to award...")

    async def callback(self, interaction: discord.Interaction) -> None:
        role = self.values[0]
        self.parent_view.prize_role_id = role.id
        self.parent_view.prize_description = f"{role.name} Role"

        log.tree("Giveaway Setup - Prize Role", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Role", f"{role.name} ({role.id})"),
        ], emoji="🏷️")

        await interaction.response.defer()
        await self.parent_view.refresh_original()
        await interaction.delete_original_response()


class PrizeRoleView(ui.View):
    """View for selecting prize role."""

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__(timeout=60)
        self.add_item(PrizeRoleSelect(parent_view))


# =============================================================================
# Duration Selection
# =============================================================================

class DurationSelect(ui.Select):
    """Dropdown to select giveaway duration."""

    def __init__(self, parent_view: GiveawaySetupView):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label=label, value=key)
            for key, label, _ in DURATION_OPTIONS
        ]

        super().__init__(
            placeholder="Select duration...",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.duration_key = self.values[0]
        self.parent_view.duration = next(
            (td for key, _, td in DURATION_OPTIONS if key == self.values[0]),
            timedelta(hours=24)
        )

        log.tree("Giveaway Setup - Duration", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Duration", self.values[0]),
        ], emoji="⏱️")

        await interaction.response.defer()
        await self.parent_view.refresh_original()
        await interaction.delete_original_response()


class DurationView(ui.View):
    """View containing duration select."""

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__(timeout=60)
        self.add_item(DurationSelect(parent_view))


# =============================================================================
# Winner Count Selection
# =============================================================================

class WinnerCountSelect(ui.Select):
    """Dropdown to select number of winners."""

    def __init__(self, parent_view: GiveawaySetupView):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label=f"{n} Winner{'s' if n > 1 else ''}",
                value=str(n),
            )
            for n in WINNER_OPTIONS
        ]

        super().__init__(
            placeholder="Select winners...",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.winner_count = int(self.values[0])

        log.tree("Giveaway Setup - Winners", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Winners", self.values[0]),
        ], emoji="🏆")

        await interaction.response.defer()
        await self.parent_view.refresh_original()
        await interaction.delete_original_response()


class WinnerCountView(ui.View):
    """View containing winner count select."""

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__(timeout=60)
        self.add_item(WinnerCountSelect(parent_view))


# =============================================================================
# Role Requirement Selection
# =============================================================================

class RoleRequirementSelect(ui.RoleSelect):
    """Role select for entry requirement."""

    def __init__(self, parent_view: GiveawaySetupView):
        self.parent_view = parent_view
        super().__init__(placeholder="Select required role...")

    async def callback(self, interaction: discord.Interaction) -> None:
        role = self.values[0]
        self.parent_view.required_role_id = role.id

        log.tree("Giveaway Setup - Role Requirement", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Role", f"{role.name} ({role.id})"),
        ], emoji="🏷️")

        await interaction.response.defer()
        await self.parent_view.refresh_original()
        await interaction.delete_original_response()


class RoleRequirementView(ui.View):
    """View for selecting required role."""

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__(timeout=60)
        self.add_item(RoleRequirementSelect(parent_view))


# =============================================================================
# Modals
# =============================================================================

class PrizeAmountModal(ui.Modal, title="Prize Amount"):
    """Modal for entering XP/coins amount."""

    amount = ui.TextInput(
        label="Amount",
        placeholder="Enter amount (e.g., 5000)",
        min_length=1,
        max_length=10,
    )

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            amount = int(self.amount.value.replace(",", "").replace(" ", ""))
            if amount <= 0:
                raise ValueError("Amount must be positive")

            self.parent_view.prize_amount = amount

            # Auto-generate description
            prize_label = "XP" if self.parent_view.prize_type == "xp" else "Casino Coins"
            self.parent_view.prize_description = f"{amount:,} {prize_label}"

            log.tree("Giveaway Setup - Prize Amount", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Amount", f"{amount:,}"),
                ("Type", self.parent_view.prize_type),
            ], emoji="💰")

            await interaction.response.defer()
            await self.parent_view.refresh_original()

        except ValueError:
            log.tree("Giveaway Setup - Invalid Amount", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Input", self.amount.value[:20]),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Invalid amount. Please enter a positive number.", ephemeral=True
            )


class ComboAmountModal(ui.Modal, title="XP + Coins Prize"):
    """Modal for entering both XP and coins amounts."""

    xp_amount = ui.TextInput(
        label="XP Amount",
        placeholder="Enter XP amount (e.g., 1000)",
        min_length=1,
        max_length=10,
    )

    coins_amount = ui.TextInput(
        label="Coins Amount",
        placeholder="Enter coins amount (e.g., 500)",
        min_length=1,
        max_length=10,
    )

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            xp = int(self.xp_amount.value.replace(",", "").replace(" ", ""))
            coins = int(self.coins_amount.value.replace(",", "").replace(" ", ""))

            if xp <= 0 or coins <= 0:
                raise ValueError("Amounts must be positive")

            self.parent_view.prize_amount = xp
            self.parent_view.prize_coins = coins

            # Auto-generate description
            self.parent_view.prize_description = f"{xp:,} XP + {coins:,} Coins"

            log.tree("Giveaway Setup - Combo Prize", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("XP", f"{xp:,}"),
                ("Coins", f"{coins:,}"),
            ], emoji="✨")

            await interaction.response.defer()
            await self.parent_view.refresh_original()

        except ValueError:
            log.tree("Giveaway Setup - Invalid Combo Amount", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("XP Input", self.xp_amount.value[:20]),
                ("Coins Input", self.coins_amount.value[:20]),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Invalid amounts. Please enter positive numbers.", ephemeral=True
            )


class PrizeDescriptionModal(ui.Modal, title="Prize Description"):
    """Modal for entering prize description."""

    description = ui.TextInput(
        label="Prize Description",
        placeholder="e.g., Discord Nitro (1 Month)",
        max_length=100,
    )

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.parent_view.prize_description = self.description.value

        log.tree("Giveaway Setup - Description", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Description", self.description.value),
        ], emoji="📝")

        await interaction.response.defer()
        await self.parent_view.refresh_original()


class LevelRequirementModal(ui.Modal, title="Level Requirement"):
    """Modal for entering minimum level requirement."""

    level = ui.TextInput(
        label="Minimum Level",
        placeholder="Enter minimum level (e.g., 10)",
        min_length=1,
        max_length=3,
    )

    def __init__(self, parent_view: GiveawaySetupView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            level = int(self.level.value)
            if level <= 0:
                raise ValueError("Level must be positive")

            self.parent_view.min_level = level

            log.tree("Giveaway Setup - Level Requirement", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Level", str(level)),
            ], emoji="⭐")

            await interaction.response.defer()
            await self.parent_view.refresh_original()

        except ValueError:
            log.tree("Giveaway Setup - Invalid Level", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Input", self.level.value),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Invalid level. Please enter a positive number.", ephemeral=True
            )


# =============================================================================
# Entry View (for active giveaways)
# =============================================================================

class GiveawayEntryView(ui.View):
    """View with entry button for active giveaways."""

    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.giveaway_id = giveaway_id

    @ui.button(label="Enter", style=discord.ButtonStyle.secondary, emoji="<:join:1459322239311937606>", custom_id="giveaway:enter")
    async def enter_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Enter the giveaway."""
        bot = interaction.client

        if not hasattr(bot, "giveaway_service") or not bot.giveaway_service:
            log.tree("Giveaway Entry - Service Unavailable", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Message ID", str(interaction.message.id)),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Giveaway system is not available.", ephemeral=True
            )
            return

        from src.services.database import db
        giveaway = db.get_giveaway_by_message(interaction.message.id)

        if not giveaway:
            log.tree("Giveaway Entry - Not Found", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Message ID", str(interaction.message.id)),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Could not find this giveaway.", ephemeral=True
            )
            return

        success, message = await bot.giveaway_service.enter_giveaway(
            giveaway["id"], interaction.user
        )

        await interaction.response.send_message(message, ephemeral=True)

    @ui.button(label="Leave", style=discord.ButtonStyle.secondary, emoji="<:transfer:1455710226429902858>", custom_id="giveaway:leave")
    async def leave_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Leave the giveaway."""
        bot = interaction.client

        if not hasattr(bot, "giveaway_service") or not bot.giveaway_service:
            log.tree("Giveaway Leave - Service Unavailable", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Message ID", str(interaction.message.id)),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Giveaway system is not available.", ephemeral=True
            )
            return

        from src.services.database import db
        giveaway = db.get_giveaway_by_message(interaction.message.id)

        if not giveaway:
            log.tree("Giveaway Leave - Not Found", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Message ID", str(interaction.message.id)),
            ], emoji="⚠️")
            await interaction.response.send_message(
                "Could not find this giveaway.", ephemeral=True
            )
            return

        success, message = await bot.giveaway_service.leave_giveaway(
            giveaway["id"], interaction.user
        )

        await interaction.response.send_message(message, ephemeral=True)
