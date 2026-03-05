"""
SyriaBot - Family System Views
===============================

Button views for marriage proposals, adoption requests,
divorce/disown confirmations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Optional

import discord
from discord import ui

from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_NEUTRAL, EMOJI_ALLOW, EMOJI_BLOCK
from src.core.logger import logger
from src.services.database import db
from src.services.actions import action_service
from src.utils.footer import set_footer


# =============================================================================
# Shared GIF Helper
# =============================================================================

async def fetch_family_gif(endpoint: str) -> Optional[str]:
    """Fetch an anime GIF for family embeds. Returns URL or None."""
    try:
        return await action_service.get_action_gif(endpoint)
    except Exception as e:
        logger.error_tree("Family GIF Fetch Failed", e, [
            ("Endpoint", endpoint),
        ])
        return None


# =============================================================================
# Proposal View (Marry)
# =============================================================================

class ProposalView(ui.View):
    """Accept/Reject buttons for a marriage proposal. Only the target can respond."""

    def __init__(self, proposer: discord.Member, target: discord.Member) -> None:
        super().__init__(timeout=60)
        self.proposer = proposer
        self.target = target

    async def on_timeout(self) -> None:
        """Edit embed to show expired."""
        try:
            embed = discord.Embed(
                title="💍 Marriage Proposal — Expired",
                description=f"{self.proposer.mention} proposed to {self.target.mention}, but they didn't respond in time.",
                color=COLOR_NEUTRAL,
            )
            set_footer(embed)
            if self.message:
                await self.message.edit(embed=embed, view=None)
            logger.tree("Marriage Proposal Expired", [
                ("Proposer", f"{self.proposer.name} ({self.proposer.id})"),
                ("Target", f"{self.target.name} ({self.target.id})"),
            ], emoji="⏳")
        except discord.HTTPException as e:
            logger.error_tree("Proposal Timeout Update Failed", e, [
                ("Proposer", str(self.proposer.id)),
                ("Target", str(self.target.id)),
            ])

    @ui.button(label="Accept", style=discord.ButtonStyle.secondary, emoji=EMOJI_ALLOW)
    async def accept(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.target.id:
                await interaction.response.send_message("❌ Only the person being proposed to can accept.", ephemeral=True)
                return

            # Re-validate: neither married in the meantime
            if db.get_spouse(self.proposer.id, interaction.guild.id):
                embed = discord.Embed(
                    description=f"❌ {self.proposer.mention} is already married to someone else.",
                    color=COLOR_ERROR,
                )
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return

            if db.get_spouse(self.target.id, interaction.guild.id):
                embed = discord.Embed(
                    description=f"❌ {self.target.mention} is already married to someone else.",
                    color=COLOR_ERROR,
                )
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return

            db.marry(self.proposer.id, self.target.id, interaction.guild.id)

            embed = discord.Embed(
                title="💍 Married!",
                description=f"🎉 {self.proposer.mention} and {self.target.mention} are now married!",
                color=COLOR_SUCCESS,
            )
            gif_url = await fetch_family_gif("hug")
            if gif_url:
                embed.set_image(url=gif_url)
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Marriage Accepted", [
                ("Proposer", f"{self.proposer.name} ({self.proposer.id})"),
                ("Target", f"{self.target.name} ({self.target.id})"),
                ("Guild", str(interaction.guild.id)),
            ], emoji="💍")

        except discord.HTTPException as e:
            logger.error_tree("Marriage Accept Failed", e, [
                ("Proposer", str(self.proposer.id)),
                ("Target", str(self.target.id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Something went wrong.", ephemeral=True)
        except Exception as e:
            logger.error_tree("Marriage Accept Error", e, [
                ("Proposer", str(self.proposer.id)),
                ("Target", str(self.target.id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        self.stop()

    @ui.button(label="Reject", style=discord.ButtonStyle.secondary, emoji=EMOJI_BLOCK)
    async def reject(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.target.id:
                await interaction.response.send_message("❌ Only the person being proposed to can reject.", ephemeral=True)
                return

            embed = discord.Embed(
                title="💍 Proposal Declined",
                description=f"{self.target.mention} declined {self.proposer.mention}'s proposal.",
                color=COLOR_NEUTRAL,
            )
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Marriage Rejected", [
                ("Proposer", f"{self.proposer.name} ({self.proposer.id})"),
                ("Target", f"{self.target.name} ({self.target.id})"),
                ("Guild", str(interaction.guild.id)),
            ], emoji="💔")

        except discord.HTTPException as e:
            logger.error_tree("Marriage Reject Failed", e, [
                ("Proposer", str(self.proposer.id)),
                ("Target", str(self.target.id)),
            ])
        except Exception as e:
            logger.error_tree("Marriage Reject Error", e, [
                ("Proposer", str(self.proposer.id)),
                ("Target", str(self.target.id)),
            ])

        self.stop()


# =============================================================================
# Adopt View
# =============================================================================

class AdoptView(ui.View):
    """Accept/Reject buttons for an adoption request. Only the target can respond."""

    def __init__(self, requester: discord.Member, target: discord.Member) -> None:
        super().__init__(timeout=60)
        self.requester = requester
        self.target = target

    async def on_timeout(self) -> None:
        try:
            embed = discord.Embed(
                title="👨‍👧 Adoption Request — Expired",
                description=f"{self.requester.mention} wanted to adopt {self.target.mention}, but they didn't respond in time.",
                color=COLOR_NEUTRAL,
            )
            set_footer(embed)
            if self.message:
                await self.message.edit(embed=embed, view=None)
            logger.tree("Adoption Request Expired", [
                ("Requester", f"{self.requester.name} ({self.requester.id})"),
                ("Target", f"{self.target.name} ({self.target.id})"),
            ], emoji="⏳")
        except discord.HTTPException as e:
            logger.error_tree("Adopt Timeout Update Failed", e, [
                ("Requester", str(self.requester.id)),
                ("Target", str(self.target.id)),
            ])

    @ui.button(label="Accept", style=discord.ButtonStyle.secondary, emoji=EMOJI_ALLOW)
    async def accept(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.target.id:
                await interaction.response.send_message("❌ Only the person being adopted can accept.", ephemeral=True)
                return

            # Re-validate
            if db.get_parent(self.target.id, interaction.guild.id):
                embed = discord.Embed(
                    description=f"❌ {self.target.mention} already has a parent.",
                    color=COLOR_ERROR,
                )
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return

            if db.get_children_count(self.requester.id, interaction.guild.id) >= 10:
                embed = discord.Embed(
                    description=f"❌ {self.requester.mention} already has 10 children (max).",
                    color=COLOR_ERROR,
                )
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return

            db.adopt(self.requester.id, self.target.id, interaction.guild.id)

            embed = discord.Embed(
                title="👨‍👧 Adopted!",
                description=f"🎉 {self.requester.mention} adopted {self.target.mention}!",
                color=COLOR_SUCCESS,
            )
            gif_url = await fetch_family_gif("pat")
            if gif_url:
                embed.set_image(url=gif_url)
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Adoption Accepted", [
                ("Parent", f"{self.requester.name} ({self.requester.id})"),
                ("Child", f"{self.target.name} ({self.target.id})"),
                ("Guild", str(interaction.guild.id)),
            ], emoji="👨‍👧")

        except discord.HTTPException as e:
            logger.error_tree("Adoption Accept Failed", e, [
                ("Requester", str(self.requester.id)),
                ("Target", str(self.target.id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Something went wrong.", ephemeral=True)
        except Exception as e:
            logger.error_tree("Adoption Accept Error", e, [
                ("Requester", str(self.requester.id)),
                ("Target", str(self.target.id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        self.stop()

    @ui.button(label="Reject", style=discord.ButtonStyle.secondary, emoji=EMOJI_BLOCK)
    async def reject(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.target.id:
                await interaction.response.send_message("❌ Only the person being adopted can reject.", ephemeral=True)
                return

            embed = discord.Embed(
                title="👨‍👧 Adoption Declined",
                description=f"{self.target.mention} declined {self.requester.mention}'s adoption request.",
                color=COLOR_NEUTRAL,
            )
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Adoption Rejected", [
                ("Requester", f"{self.requester.name} ({self.requester.id})"),
                ("Target", f"{self.target.name} ({self.target.id})"),
                ("Guild", str(interaction.guild.id)),
            ], emoji="✋")

        except discord.HTTPException as e:
            logger.error_tree("Adoption Reject Failed", e, [
                ("Requester", str(self.requester.id)),
                ("Target", str(self.target.id)),
            ])
        except Exception as e:
            logger.error_tree("Adoption Reject Error", e, [
                ("Requester", str(self.requester.id)),
                ("Target", str(self.target.id)),
            ])

        self.stop()


# =============================================================================
# Divorce Confirmation View
# =============================================================================

class DivorceView(ui.View):
    """Confirm/Cancel buttons for divorce. Only the initiator can click."""

    def __init__(self, user: discord.Member, spouse_id: int) -> None:
        super().__init__(timeout=30)
        self.user = user
        self.spouse_id = spouse_id

    async def on_timeout(self) -> None:
        try:
            embed = discord.Embed(
                description="⏳ Divorce confirmation expired.",
                color=COLOR_NEUTRAL,
            )
            set_footer(embed)
            if self.message:
                await self.message.edit(embed=embed, view=None)
            logger.tree("Divorce Confirmation Expired", [
                ("User", f"{self.user.name} ({self.user.id})"),
                ("Spouse", str(self.spouse_id)),
            ], emoji="⏳")
        except discord.HTTPException as e:
            logger.error_tree("Divorce Timeout Update Failed", e, [
                ("User", str(self.user.id)),
            ])

    @ui.button(label="Confirm Divorce", style=discord.ButtonStyle.secondary, emoji=EMOJI_ALLOW)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("❌ Only the person who initiated can confirm.", ephemeral=True)
                return

            ex_spouse_id = db.divorce(self.user.id, interaction.guild.id)

            if not ex_spouse_id:
                embed = discord.Embed(
                    description="❌ You're not married anymore.",
                    color=COLOR_ERROR,
                )
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return

            embed = discord.Embed(
                title="💔 Divorced",
                description=f"{self.user.mention} and <@{ex_spouse_id}> are no longer married.\n\n⏳ Both must wait **24 hours** before remarrying.",
                color=COLOR_ERROR,
            )
            gif_url = await fetch_family_gif("cry")
            if gif_url:
                embed.set_image(url=gif_url)
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Divorce Confirmed", [
                ("User", f"{self.user.name} ({self.user.id})"),
                ("Ex-Spouse", str(ex_spouse_id)),
                ("Guild", str(interaction.guild.id)),
            ], emoji="💔")

        except discord.HTTPException as e:
            logger.error_tree("Divorce Confirm Failed", e, [
                ("User", str(self.user.id)),
                ("Spouse", str(self.spouse_id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Something went wrong.", ephemeral=True)
        except Exception as e:
            logger.error_tree("Divorce Confirm Error", e, [
                ("User", str(self.user.id)),
                ("Spouse", str(self.spouse_id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji=EMOJI_BLOCK)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("❌ Only the person who initiated can cancel.", ephemeral=True)
                return

            embed = discord.Embed(
                description="↩️ Divorce cancelled.",
                color=COLOR_NEUTRAL,
            )
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Divorce Cancelled", [
                ("User", f"{self.user.name} ({self.user.id})"),
                ("Spouse", str(self.spouse_id)),
            ], emoji="↩️")

        except discord.HTTPException as e:
            logger.error_tree("Divorce Cancel Failed", e, [
                ("User", str(self.user.id)),
            ])
        except Exception as e:
            logger.error_tree("Divorce Cancel Error", e, [
                ("User", str(self.user.id)),
            ])

        self.stop()


# =============================================================================
# Disown Confirmation View
# =============================================================================

class DisownView(ui.View):
    """Confirm/Cancel buttons for disowning a child. Only the parent can click."""

    def __init__(self, parent: discord.Member, child: discord.Member) -> None:
        super().__init__(timeout=30)
        self.parent = parent
        self.child = child

    async def on_timeout(self) -> None:
        try:
            embed = discord.Embed(
                description="⏳ Disown confirmation expired.",
                color=COLOR_NEUTRAL,
            )
            set_footer(embed)
            if self.message:
                await self.message.edit(embed=embed, view=None)
            logger.tree("Disown Confirmation Expired", [
                ("Parent", f"{self.parent.name} ({self.parent.id})"),
                ("Child", f"{self.child.name} ({self.child.id})"),
            ], emoji="⏳")
        except discord.HTTPException as e:
            logger.error_tree("Disown Timeout Update Failed", e, [
                ("Parent", str(self.parent.id)),
                ("Child", str(self.child.id)),
            ])

    @ui.button(label="Confirm Disown", style=discord.ButtonStyle.secondary, emoji=EMOJI_ALLOW)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.parent.id:
                await interaction.response.send_message("❌ Only the parent can confirm.", ephemeral=True)
                return

            deleted = db.disown(self.parent.id, self.child.id, interaction.guild.id)

            if not deleted:
                embed = discord.Embed(
                    description=f"❌ {self.child.mention} is no longer your child.",
                    color=COLOR_ERROR,
                )
                set_footer(embed)
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return

            embed = discord.Embed(
                title="👋 Disowned",
                description=f"{self.parent.mention} disowned {self.child.mention}.",
                color=COLOR_ERROR,
            )
            gif_url = await fetch_family_gif("wave")
            if gif_url:
                embed.set_image(url=gif_url)
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Disown Confirmed", [
                ("Parent", f"{self.parent.name} ({self.parent.id})"),
                ("Child", f"{self.child.name} ({self.child.id})"),
                ("Guild", str(interaction.guild.id)),
            ], emoji="👋")

        except discord.HTTPException as e:
            logger.error_tree("Disown Confirm Failed", e, [
                ("Parent", str(self.parent.id)),
                ("Child", str(self.child.id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Something went wrong.", ephemeral=True)
        except Exception as e:
            logger.error_tree("Disown Confirm Error", e, [
                ("Parent", str(self.parent.id)),
                ("Child", str(self.child.id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji=EMOJI_BLOCK)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.parent.id:
                await interaction.response.send_message("❌ Only the parent can cancel.", ephemeral=True)
                return

            embed = discord.Embed(
                description="↩️ Disown cancelled.",
                color=COLOR_NEUTRAL,
            )
            set_footer(embed)
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Disown Cancelled", [
                ("Parent", f"{self.parent.name} ({self.parent.id})"),
                ("Child", f"{self.child.name} ({self.child.id})"),
            ], emoji="↩️")

        except discord.HTTPException as e:
            logger.error_tree("Disown Cancel Failed", e, [
                ("Parent", str(self.parent.id)),
                ("Child", str(self.child.id)),
            ])
        except Exception as e:
            logger.error_tree("Disown Cancel Error", e, [
                ("Parent", str(self.parent.id)),
                ("Child", str(self.child.id)),
            ])

        self.stop()
