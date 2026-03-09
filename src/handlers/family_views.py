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

from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_NEUTRAL, COLOR_WARNING, COLOR_GOLD, EMOJI_ALLOW, EMOJI_BLOCK
from src.core.constants import (
    MAX_CHILDREN, ANCESTOR_MAX_DEPTH,
    FAMILY_VIEW_TIMEOUT, FAMILY_CONFIRM_TIMEOUT,
)
from src.core.logger import logger
from src.services.database import db
from src.services.actions import action_service


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
        super().__init__(timeout=FAMILY_VIEW_TIMEOUT)
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
            if self.message:
                await self.message.edit(content=None, embed=embed, view=None)
            logger.tree("Marriage Proposal Expired", [
                ("Proposer", f"{self.proposer.name} ({self.proposer.display_name})"),
                ("Target", f"{self.target.name} ({self.target.display_name})"),
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
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return

            if db.get_spouse(self.target.id, interaction.guild.id):
                embed = discord.Embed(
                    description=f"❌ {self.target.mention} is already married to someone else.",
                    color=COLOR_ERROR,
                )
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
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Marriage Accepted", [
                ("Proposer", f"{self.proposer.name} ({self.proposer.display_name})"),
                ("Target", f"{self.target.name} ({self.target.display_name})"),
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
            await interaction.response.edit_message(embed=embed, view=None)

            logger.tree("Marriage Rejected", [
                ("Proposer", f"{self.proposer.name} ({self.proposer.display_name})"),
                ("Target", f"{self.target.name} ({self.target.display_name})"),
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
# Adopt Approval View (combined target + spouse)
# =============================================================================

class AdoptApprovalView(ui.View):
    """Combined Accept/Reject for adoption. Both target AND spouse must accept on the same embed."""

    def __init__(
        self,
        requester: discord.Member,
        target: discord.Member,
        spouse_id: int,
        gif_url: Optional[str] = None,
    ) -> None:
        super().__init__(timeout=FAMILY_VIEW_TIMEOUT)
        self.requester = requester
        self.target = target
        self.spouse_id = spouse_id
        self.gif_url = gif_url
        self.target_accepted = False
        self.spouse_accepted = False

    def _status_line(self) -> str:
        """Build status line showing who has accepted."""
        t = "✅" if self.target_accepted else "⏳"
        s = "✅" if self.spouse_accepted else "⏳"
        return f"{t} {self.target.mention}  ·  {s} <@{self.spouse_id}>"

    async def _build_pending_embed(self) -> discord.Embed:
        """Build the pending adoption embed with current status."""
        embed = discord.Embed(
            description=f"👨‍👧 {self.requester.mention} wants to adopt {self.target.mention}!\n\n{self._status_line()}",
            color=COLOR_GOLD,
        )
        if self.gif_url:
            embed.set_image(url=self.gif_url)
        return embed

    async def _try_complete(self, interaction: discord.Interaction) -> None:
        """If both accepted, re-validate and complete the adoption."""
        if not (self.target_accepted and self.spouse_accepted):
            # Only one accepted so far — update embed in-place
            embed = await self._build_pending_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            return

        guild_id = interaction.guild.id

        # Re-validate before completing
        if db.get_parent(self.target.id, guild_id):
            embed = discord.Embed(
                description=f"❌ {self.target.mention} already has a parent.",
                color=COLOR_ERROR,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None)
            self.stop()
            return

        if db.get_household_children_count(self.requester.id, guild_id) >= MAX_CHILDREN:
            embed = discord.Embed(
                description=f"❌ {self.requester.mention}'s household already has {MAX_CHILDREN} children (max).",
                color=COLOR_ERROR,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None)
            self.stop()
            return

        if db.get_spouse(self.requester.id, guild_id) != self.spouse_id:
            embed = discord.Embed(
                description="❌ You are no longer married — adoption cancelled.",
                color=COLOR_ERROR,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None)
            self.stop()
            return

        if db.is_ancestor(self.target.id, self.requester.id, guild_id, ANCESTOR_MAX_DEPTH):
            embed = discord.Embed(
                description="❌ Can't adopt — circular family relationship detected.",
                color=COLOR_ERROR,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None)
            self.stop()
            return

        if db.is_ancestor(self.target.id, self.spouse_id, guild_id, ANCESTOR_MAX_DEPTH):
            embed = discord.Embed(
                description="❌ Can't adopt — circular family relationship detected.",
                color=COLOR_ERROR,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None)
            self.stop()
            return

        db.adopt(self.requester.id, self.target.id, guild_id)

        embed = discord.Embed(
            title="👨‍👧 Adopted!",
            description=f"🎉 {self.requester.mention} & <@{self.spouse_id}> adopted {self.target.mention}!",
            color=COLOR_SUCCESS,
        )
        gif_url = await fetch_family_gif("pat")
        if gif_url:
            embed.set_image(url=gif_url)
        await interaction.response.edit_message(content=None, embed=embed, view=None)

        logger.tree("Adoption Completed", [
            ("Parent", f"{self.requester.name} ({self.requester.display_name})"),
            ("Spouse", str(self.spouse_id)),
            ("Child", f"{self.target.name} ({self.target.display_name})"),
            ("Guild", str(guild_id)),
        ], emoji="👨‍👧")

        self.stop()

    async def on_timeout(self) -> None:
        try:
            embed = discord.Embed(
                title="👨‍👧 Adoption Request — Expired",
                description=f"{self.requester.mention} wanted to adopt {self.target.mention}, but not everyone responded in time.",
                color=COLOR_NEUTRAL,
            )
            if self.message:
                await self.message.edit(content=None, embed=embed, view=None)
            logger.tree("Adoption Request Expired", [
                ("Requester", f"{self.requester.name} ({self.requester.display_name})"),
                ("Target", f"{self.target.name} ({self.target.display_name})"),
                ("Spouse", str(self.spouse_id)),
            ], emoji="⏳")
        except discord.HTTPException as e:
            logger.error_tree("Adopt Timeout Update Failed", e, [
                ("Requester", str(self.requester.id)),
                ("Target", str(self.target.id)),
            ])

    @ui.button(label="Accept", style=discord.ButtonStyle.secondary, emoji=EMOJI_ALLOW)
    async def accept(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            uid = interaction.user.id

            if uid == self.target.id:
                self.target_accepted = True
            elif uid == self.spouse_id:
                self.spouse_accepted = True
            else:
                await interaction.response.send_message("❌ Only the target and spouse can accept.", ephemeral=True)
                return

            await self._try_complete(interaction)

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

    @ui.button(label="Reject", style=discord.ButtonStyle.secondary, emoji=EMOJI_BLOCK)
    async def reject(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            uid = interaction.user.id

            if uid != self.target.id and uid != self.spouse_id:
                await interaction.response.send_message("❌ Only the target and spouse can reject.", ephemeral=True)
                return

            embed = discord.Embed(
                title="👨‍👧 Adoption Declined",
                description=f"{interaction.user.mention} declined {self.requester.mention}'s adoption request.",
                color=COLOR_NEUTRAL,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None)

            logger.tree("Adoption Rejected", [
                ("Requester", f"{self.requester.name} ({self.requester.display_name})"),
                ("Rejected By", f"{interaction.user.name} ({interaction.user.display_name})"),
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
        super().__init__(timeout=FAMILY_CONFIRM_TIMEOUT)
        self.user = user
        self.spouse_id = spouse_id

    async def on_timeout(self) -> None:
        try:
            embed = discord.Embed(
                description="⏳ Divorce confirmation expired.",
                color=COLOR_NEUTRAL,
            )
            if self.message:
                await self.message.edit(content=None, embed=embed, view=None)
            logger.tree("Divorce Confirmation Expired", [
                ("User", f"{self.user.name} ({self.user.display_name})"),
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

            guild_id = interaction.guild.id

            # Gather all household children BEFORE divorce (need spouse link)
            all_children = db.get_household_children(self.user.id, guild_id)

            ex_spouse_id = db.divorce(self.user.id, guild_id)

            if not ex_spouse_id:
                embed = discord.Embed(
                    description="❌ You're not married anymore.",
                    color=COLOR_ERROR,
                )
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return

            # Remove all children from both parents
            for child_id in all_children:
                parent_of_child = db.get_parent(child_id, guild_id)
                if parent_of_child:
                    db.disown(parent_of_child, child_id, guild_id)

            # Build description
            desc = f"{self.user.mention} and <@{ex_spouse_id}> are no longer married.\n\n⏳ Both must wait **24 hours** before remarrying."
            if all_children:
                children_str = ", ".join(f"<@{c}>" for c in all_children)
                desc += f"\n\n👶 {children_str} — put up for adoption."

            embed = discord.Embed(
                title="💔 Divorced",
                description=desc,
                color=COLOR_ERROR,
            )
            gif_url = await fetch_family_gif("cry")
            if gif_url:
                embed.set_image(url=gif_url)

            # Ping ex-spouse and children via content (same message as embed)
            pings = [f"<@{ex_spouse_id}>"]
            pings.extend(f"<@{c}>" for c in all_children)
            await interaction.response.edit_message(content=" ".join(pings), embed=embed, view=None)

            logger.tree("Divorce Confirmed", [
                ("User", f"{self.user.name} ({self.user.display_name})"),
                ("Ex-Spouse", str(ex_spouse_id)),
                ("Children Removed", str(len(all_children))),
                ("Guild", str(guild_id)),
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
            await interaction.response.edit_message(content=None, embed=embed, view=None)

            logger.tree("Divorce Cancelled", [
                ("User", f"{self.user.name} ({self.user.display_name})"),
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

    def __init__(self, parent: discord.Member, child: discord.Member, actual_parent_id: int = 0) -> None:
        super().__init__(timeout=FAMILY_CONFIRM_TIMEOUT)
        self.parent = parent
        self.child = child
        self.actual_parent_id = actual_parent_id or parent.id

    async def on_timeout(self) -> None:
        try:
            embed = discord.Embed(
                description="⏳ Disown confirmation expired.",
                color=COLOR_NEUTRAL,
            )
            if self.message:
                await self.message.edit(content=None, embed=embed, view=None)
            logger.tree("Disown Confirmation Expired", [
                ("Parent", f"{self.parent.name} ({self.parent.display_name})"),
                ("Child", f"{self.child.name} ({self.child.display_name})"),
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

            guild_id = interaction.guild.id

            # Check if parent has a spouse — need spouse approval
            spouse_id = db.get_spouse(self.parent.id, guild_id)
            if spouse_id:
                embed = discord.Embed(
                    description=f"⚠️ {self.parent.mention} wants to disown {self.child.mention}. Waiting for <@{spouse_id}> to approve.",
                    color=COLOR_WARNING,
                )
                view = SpouseApprovalView(
                    action="disown",
                    initiator=self.parent,
                    spouse_id=spouse_id,
                    target=self.child,
                    guild_id=guild_id,
                    actual_parent_id=self.actual_parent_id,
                )
                await interaction.response.edit_message(content=f"<@{spouse_id}>", embed=embed, view=view)
                view.message = self.message

                logger.tree("Disown Awaiting Spouse", [
                    ("Parent", f"{self.parent.name} ({self.parent.display_name})"),
                    ("Spouse", str(spouse_id)),
                    ("Child", f"{self.child.name} ({self.child.display_name})"),
                    ("Guild", str(guild_id)),
                ], emoji="⏳")
            else:
                deleted = db.disown(self.actual_parent_id, self.child.id, guild_id)

                if not deleted:
                    embed = discord.Embed(
                        description=f"❌ {self.child.mention} is no longer your child.",
                        color=COLOR_ERROR,
                    )
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
                await interaction.response.edit_message(embed=embed, view=None)

                logger.tree("Disown Confirmed", [
                    ("Parent", f"{self.parent.name} ({self.parent.display_name})"),
                    ("Child", f"{self.child.name} ({self.child.display_name})"),
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
            await interaction.response.edit_message(content=None, embed=embed, view=None)

            logger.tree("Disown Cancelled", [
                ("Parent", f"{self.parent.name} ({self.parent.display_name})"),
                ("Child", f"{self.child.name} ({self.child.display_name})"),
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


# =============================================================================
# Spouse Approval View (Adopt / Disown)
# =============================================================================

class SpouseApprovalView(ui.View):
    """Approve/Reject buttons for a spouse to confirm adopt or disown. Only the spouse can respond."""

    def __init__(
        self,
        action: str,  # "adopt" or "disown"
        initiator: discord.Member,
        spouse_id: int,
        target: discord.Member,
        guild_id: int,
        actual_parent_id: int = 0,  # for disown
    ) -> None:
        super().__init__(timeout=FAMILY_VIEW_TIMEOUT)
        self.action = action
        self.initiator = initiator
        self.spouse_id = spouse_id
        self.target = target
        self.guild_id = guild_id
        self.actual_parent_id = actual_parent_id or initiator.id

    async def on_timeout(self) -> None:
        try:
            action_name = "Adoption" if self.action == "adopt" else "Disown"
            embed = discord.Embed(
                description=f"⏳ {action_name} cancelled — <@{self.spouse_id}> didn't respond in time.",
                color=COLOR_NEUTRAL,
            )
            if self.message:
                await self.message.edit(content=None, embed=embed, view=None)
            logger.tree(f"Spouse Approval Expired ({self.action})", [
                ("Initiator", f"{self.initiator.name} ({self.initiator.display_name})"),
                ("Spouse", str(self.spouse_id)),
                ("Target", f"{self.target.name} ({self.target.display_name})"),
            ], emoji="⏳")
        except discord.HTTPException as e:
            logger.error_tree("Spouse Approval Timeout Failed", e, [
                ("Initiator", str(self.initiator.id)),
                ("Spouse", str(self.spouse_id)),
            ])

    @ui.button(label="Approve", style=discord.ButtonStyle.secondary, emoji=EMOJI_ALLOW)
    async def approve(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.spouse_id:
                await interaction.response.send_message("❌ Only the spouse can approve.", ephemeral=True)
                return

            # Re-validate: still married?
            if db.get_spouse(self.initiator.id, self.guild_id) != self.spouse_id:
                embed = discord.Embed(
                    description="❌ You are no longer married — action cancelled.",
                    color=COLOR_ERROR,
                )
                await interaction.response.edit_message(content=None, embed=embed, view=None)
                self.stop()
                return

            if self.action == "adopt":
                # Re-validate before completing
                if db.get_parent(self.target.id, self.guild_id):
                    embed = discord.Embed(
                        description=f"❌ {self.target.mention} already has a parent.",
                        color=COLOR_ERROR,
                    )
                    await interaction.response.edit_message(content=None, embed=embed, view=None)
                    self.stop()
                    return

                if db.get_household_children_count(self.initiator.id, self.guild_id) >= MAX_CHILDREN:
                    embed = discord.Embed(
                        description=f"❌ Your household already has {MAX_CHILDREN} children (max).",
                        color=COLOR_ERROR,
                    )
                    await interaction.response.edit_message(content=None, embed=embed, view=None)
                    self.stop()
                    return

                db.adopt(self.initiator.id, self.target.id, self.guild_id)

                embed = discord.Embed(
                    title="👨‍👧 Adopted!",
                    description=f"🎉 {self.initiator.mention} & <@{self.spouse_id}> adopted {self.target.mention}!",
                    color=COLOR_SUCCESS,
                )
                gif_url = await fetch_family_gif("pat")
                if gif_url:
                    embed.set_image(url=gif_url)
                await interaction.response.edit_message(content=None, embed=embed, view=None)

                logger.tree("Adoption Spouse Approved", [
                    ("Parent", f"{self.initiator.name} ({self.initiator.display_name})"),
                    ("Spouse", str(self.spouse_id)),
                    ("Child", f"{self.target.name} ({self.target.display_name})"),
                    ("Guild", str(self.guild_id)),
                ], emoji="👨‍👧")

            elif self.action == "disown":
                deleted = db.disown(self.actual_parent_id, self.target.id, self.guild_id)

                if not deleted:
                    embed = discord.Embed(
                        description=f"❌ {self.target.mention} is no longer your child.",
                        color=COLOR_ERROR,
                    )
                    await interaction.response.edit_message(content=None, embed=embed, view=None)
                    self.stop()
                    return

                embed = discord.Embed(
                    title="👋 Disowned",
                    description=f"{self.initiator.mention} & <@{self.spouse_id}> disowned {self.target.mention}.",
                    color=COLOR_ERROR,
                )
                gif_url = await fetch_family_gif("wave")
                if gif_url:
                    embed.set_image(url=gif_url)
                await interaction.response.edit_message(content=None, embed=embed, view=None)

                logger.tree("Disown Spouse Approved", [
                    ("Parent", f"{self.initiator.name} ({self.initiator.display_name})"),
                    ("Spouse", str(self.spouse_id)),
                    ("Child", f"{self.target.name} ({self.target.display_name})"),
                    ("Guild", str(self.guild_id)),
                ], emoji="👋")

        except discord.HTTPException as e:
            logger.error_tree("Spouse Approval Failed", e, [
                ("Initiator", str(self.initiator.id)),
                ("Spouse", str(self.spouse_id)),
                ("Action", self.action),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Something went wrong.", ephemeral=True)
        except Exception as e:
            logger.error_tree("Spouse Approval Error", e, [
                ("Initiator", str(self.initiator.id)),
                ("Spouse", str(self.spouse_id)),
                ("Action", self.action),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        self.stop()

    @ui.button(label="Reject", style=discord.ButtonStyle.secondary, emoji=EMOJI_BLOCK)
    async def reject(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.spouse_id:
                await interaction.response.send_message("❌ Only the spouse can reject.", ephemeral=True)
                return

            action_name = "adoption" if self.action == "adopt" else "disown"
            embed = discord.Embed(
                description=f"❌ <@{self.spouse_id}> rejected the {action_name} of {self.target.mention}.",
                color=COLOR_NEUTRAL,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None)

            logger.tree(f"Spouse Rejected ({self.action})", [
                ("Initiator", f"{self.initiator.name} ({self.initiator.display_name})"),
                ("Spouse", str(self.spouse_id)),
                ("Target", f"{self.target.name} ({self.target.display_name})"),
            ], emoji="✋")

        except discord.HTTPException as e:
            logger.error_tree("Spouse Reject Failed", e, [
                ("Initiator", str(self.initiator.id)),
                ("Spouse", str(self.spouse_id)),
            ])
        except Exception as e:
            logger.error_tree("Spouse Reject Error", e, [
                ("Initiator", str(self.initiator.id)),
                ("Spouse", str(self.spouse_id)),
            ])

        self.stop()


# =============================================================================
# Runaway Confirmation View
# =============================================================================

class RunawayView(ui.View):
    """Confirm/Cancel buttons for running away. Only the child can click."""

    def __init__(self, child: discord.Member, parent_id: int) -> None:
        super().__init__(timeout=FAMILY_CONFIRM_TIMEOUT)
        self.child = child
        self.parent_id = parent_id

    async def on_timeout(self) -> None:
        try:
            embed = discord.Embed(
                description="⏳ Runaway confirmation expired.",
                color=COLOR_NEUTRAL,
            )
            if self.message:
                await self.message.edit(content=None, embed=embed, view=None)
            logger.tree("Runaway Confirmation Expired", [
                ("Child", f"{self.child.name} ({self.child.display_name})"),
                ("Parent", str(self.parent_id)),
            ], emoji="⏳")
        except discord.HTTPException as e:
            logger.error_tree("Runaway Timeout Update Failed", e, [
                ("Child", str(self.child.id)),
            ])

    @ui.button(label="Confirm Runaway", style=discord.ButtonStyle.secondary, emoji=EMOJI_ALLOW)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.child.id:
                await interaction.response.send_message("❌ Only the child can confirm.", ephemeral=True)
                return

            guild_id = interaction.guild.id

            # Fetch parent's spouse BEFORE runaway deletes the child link
            parent_spouse_id = db.get_spouse(self.parent_id, guild_id)

            parent_id = db.runaway(self.child.id, guild_id)

            if not parent_id:
                embed = discord.Embed(
                    description="❌ You no longer have a parent.",
                    color=COLOR_ERROR,
                )
                await interaction.response.edit_message(embed=embed, view=None)
                self.stop()
                return
            if parent_spouse_id:
                description = f"🏃 {self.child.mention} ran away from <@{parent_id}> & <@{parent_spouse_id}>!"
            else:
                description = f"🏃 {self.child.mention} ran away from <@{parent_id}>!"

            embed = discord.Embed(description=description, color=COLOR_WARNING)
            gif_url = await fetch_family_gif("run")
            if gif_url:
                embed.set_image(url=gif_url)

            # Ping parents via content (same message as embed)
            ping = f"<@{parent_id}>"
            if parent_spouse_id:
                ping += f" <@{parent_spouse_id}>"
            await interaction.response.edit_message(content=ping, embed=embed, view=None)

            logger.tree("Runaway Confirmed", [
                ("Child", f"{self.child.name} ({self.child.display_name})"),
                ("Parent", str(parent_id)),
                ("Parent Spouse", str(parent_spouse_id) if parent_spouse_id else "None"),
                ("Guild", str(interaction.guild.id)),
            ], emoji="🏃")

        except discord.HTTPException as e:
            logger.error_tree("Runaway Confirm Failed", e, [
                ("Child", str(self.child.id)),
                ("Parent", str(self.parent_id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Something went wrong.", ephemeral=True)
        except Exception as e:
            logger.error_tree("Runaway Confirm Error", e, [
                ("Child", str(self.child.id)),
                ("Parent", str(self.parent_id)),
            ])
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji=EMOJI_BLOCK)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        try:
            if interaction.user.id != self.child.id:
                await interaction.response.send_message("❌ Only the child can cancel.", ephemeral=True)
                return

            embed = discord.Embed(
                description="↩️ Runaway cancelled.",
                color=COLOR_NEUTRAL,
            )
            await interaction.response.edit_message(content=None, embed=embed, view=None)

            logger.tree("Runaway Cancelled", [
                ("Child", f"{self.child.name} ({self.child.display_name})"),
                ("Parent", str(self.parent_id)),
            ], emoji="↩️")

        except discord.HTTPException as e:
            logger.error_tree("Runaway Cancel Failed", e, [
                ("Child", str(self.child.id)),
            ])
        except Exception as e:
            logger.error_tree("Runaway Cancel Error", e, [
                ("Child", str(self.child.id)),
            ])

        self.stop()
