"""
SyriaBot - Family Commands Handler
===================================

Text-based family commands: marry, divorce, adopt, disown, runaway, family.
Triggered by typing the command word + optional @mention in chat.
Uses GIF embeds like action commands.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import asyncio
import io
import time
from collections import OrderedDict
from typing import Optional

import discord

from src.core.logger import logger
from src.core.config import config
from src.core.colors import COLOR_GOLD, COLOR_ERROR, COLOR_WARNING
from src.core.constants import (
    DELETE_DELAY_SHORT, MAX_CHILDREN, ANCESTOR_MAX_DEPTH,
    FAMILY_VIEW_TIMEOUT, FAMILY_CONFIRM_TIMEOUT,
)
from src.services.database import db
from src.utils.footer import set_footer
from src.utils.permissions import is_cooldown_exempt
from src.handlers.family_views import (
    ProposalView, AdoptView, DivorceView, DisownView, RunawayView, fetch_family_gif,
)
from src.services.family_card import (
    generate_family_card, resolve_family_member, FamilyData,
)


# =============================================================================
# Constants
# =============================================================================

FAMILY_COMMANDS = {"marry", "divorce", "adopt", "disown", "runaway", "family"}
COOLDOWN_24H: int = 86400
FAMILY_COOLDOWN: int = 10  # seconds between family commands per user
MAX_COOLDOWN_CACHE_SIZE: int = 100

# GIF endpoints for each family action
FAMILY_GIFS = {
    "marry_proposal": "kiss",
    "adopt_request": "handhold",
    "runaway": "run",
}


# =============================================================================
# Handler
# =============================================================================

class FamilyHandler:
    """
    Handler for text-based family commands with GIF responses.

    DESIGN:
        Processes message-based family commands (marry, divorce, adopt, etc.)
        Uses strict matching like ActionHandler to prevent false triggers.
        Fetches GIFs from nekos.best/waifu.pics via ActionService.
        Uses button views for interactive proposals/confirmations.
        Supports reply-based targeting (reply to someone + type "marry").
    """

    def __init__(self) -> None:
        self._cooldowns: OrderedDict[int, float] = OrderedDict()
        self._cooldown_lock = asyncio.Lock()
        # Track active outgoing proposals/adopt requests per user
        self._active_proposals: dict[int, float] = {}

    async def _cleanup_cooldowns(self) -> None:
        """Remove expired cooldowns and stale proposals to prevent unbounded growth."""
        now = time.time()

        # Clean expired proposals (60s lifetime)
        expired_proposals = [
            uid for uid, ts in list(self._active_proposals.items())
            if now - ts > 120  # 2x timeout for safety margin
        ]
        for uid in expired_proposals:
            self._active_proposals.pop(uid, None)

        if len(self._cooldowns) <= MAX_COOLDOWN_CACHE_SIZE:
            return

        async with self._cooldown_lock:
            expired = [
                uid for uid, ts in list(self._cooldowns.items())
                if now - ts > FAMILY_COOLDOWN
            ]
            for uid in expired:
                self._cooldowns.pop(uid, None)

            while len(self._cooldowns) > MAX_COOLDOWN_CACHE_SIZE:
                try:
                    self._cooldowns.popitem(last=False)
                except KeyError:
                    break

    async def _check_cooldown(self, message: discord.Message) -> bool:
        """Check and apply cooldown. Returns True if on cooldown."""
        user_id = message.author.id

        if is_cooldown_exempt(message.author):
            return False

        # Check cooldown under lock, but release before Discord API calls
        on_cooldown = False
        cooldown_ends = 0

        async with self._cooldown_lock:
            last_use = self._cooldowns.get(user_id, 0)
            time_since = time.time() - last_use
            if time_since < FAMILY_COOLDOWN:
                remaining = FAMILY_COOLDOWN - time_since
                cooldown_ends = int(time.time() + remaining)
                on_cooldown = True
            else:
                self._cooldowns[user_id] = time.time()

        if on_cooldown:
            cooldown_msg = await message.reply(
                f"You're on cooldown. Try again <t:{cooldown_ends}:R>",
                mention_author=False,
            )
            await asyncio.gather(
                message.delete(delay=DELETE_DELAY_SHORT),
                cooldown_msg.delete(delay=DELETE_DELAY_SHORT),
                return_exceptions=True,
            )
            logger.tree("Family Cooldown", [
                ("User", f"{message.author.name}"),
                ("ID", str(user_id)),
                ("Ends", f"<t:{cooldown_ends}:R>"),
            ], emoji="⏳")
            return True

        return False

    async def _remove_cooldown(self, user_id: int) -> None:
        """Remove cooldown for a user (when command didn't actually execute)."""
        async with self._cooldown_lock:
            self._cooldowns.pop(user_id, None)

    async def _fetch_gif(self, key: str) -> Optional[str]:
        """Fetch a GIF for a family event. Returns URL or None."""
        endpoint = FAMILY_GIFS.get(key)
        if not endpoint:
            return None
        return await fetch_family_gif(endpoint)

    async def _send_error(self, message: discord.Message, description: str) -> None:
        """Send an error embed and auto-delete both it and the original message."""
        embed = discord.Embed(description=description, color=COLOR_ERROR)
        set_footer(embed)
        error_msg = await message.channel.send(embed=embed)
        await asyncio.gather(
            message.delete(delay=DELETE_DELAY_SHORT),
            error_msg.delete(delay=DELETE_DELAY_SHORT),
            return_exceptions=True,
        )

    async def _send_warning(self, message: discord.Message, description: str) -> None:
        """Send a warning embed and auto-delete both it and the original message."""
        embed = discord.Embed(description=description, color=COLOR_WARNING)
        set_footer(embed)
        warn_msg = await message.channel.send(embed=embed)
        await asyncio.gather(
            message.delete(delay=DELETE_DELAY_SHORT),
            warn_msg.delete(delay=DELETE_DELAY_SHORT),
            return_exceptions=True,
        )

    # =========================================================================
    # Main Handler
    # =========================================================================

    async def handle(self, message: discord.Message) -> bool:
        """
        Handle family commands. Returns True if a command was processed.

        Supported:
            marry @user, divorce, adopt @user, disown @user, runaway, family [@user]
        """
        if not message.guild or message.guild.id != config.GUILD_ID:
            return False

        if message.channel.id != config.CMDS_CHANNEL_ID:
            return False

        content = message.content.strip().lower()
        words = content.split()
        if not words:
            return False

        command = words[0]
        if command not in FAMILY_COMMANDS:
            return False

        # Strict matching: only allow command + mentions, no extra text
        for word in words[1:]:
            if not word.startswith("<@"):
                return False

        # Cooldown check
        if await self._check_cooldown(message):
            return True

        await self._cleanup_cooldowns()

        try:
            if command == "marry":
                await self._handle_marry(message)
            elif command == "divorce":
                await self._handle_divorce(message)
            elif command == "adopt":
                await self._handle_adopt(message)
            elif command == "disown":
                await self._handle_disown(message)
            elif command == "runaway":
                await self._handle_runaway(message)
            elif command == "family":
                await self._handle_family(message)
        except Exception as e:
            logger.error_tree("Family Command Error", e, [
                ("User", f"{message.author.name} ({message.author.display_name})"),
                ("ID", str(message.author.id)),
                ("Command", command),
            ])
            try:
                error_msg = await message.reply("❌ Something went wrong.", mention_author=False)
                await error_msg.delete(delay=DELETE_DELAY_SHORT)
            except discord.HTTPException:
                pass

        return True

    # =========================================================================
    # marry @user
    # =========================================================================

    async def _handle_marry(self, message: discord.Message) -> None:
        """Handle the marry command."""
        user = message.author
        guild_id = message.guild.id

        # Need exactly one target (mention or reply)
        target = self._get_target(message)
        if not target:
            await self._remove_cooldown(user.id)
            msg = await message.reply("Mention someone to propose to! e.g. `marry @user`", mention_author=False)
            await asyncio.gather(
                message.delete(delay=DELETE_DELAY_SHORT),
                msg.delete(delay=DELETE_DELAY_SHORT),
                return_exceptions=True,
            )
            return

        # Validation: self
        if target.id == user.id:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You can't marry yourself.")
            logger.tree("Marry Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Reason", "Self-marriage"),
            ], emoji="⚠️")
            return

        # Validation: bot
        if target.bot:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You can't marry a bot.")
            logger.tree("Marry Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Target is bot"),
            ], emoji="⚠️")
            return

        # Validation: proposer already married
        if db.get_spouse(user.id, guild_id):
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You're already married. Divorce first.")
            logger.tree("Marry Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Reason", "Already married"),
            ], emoji="⚠️")
            return

        # Validation: target already married
        if db.get_spouse(target.id, guild_id):
            await self._remove_cooldown(user.id)
            await self._send_error(message, f"❌ {target.mention} is already married.")
            logger.tree("Marry Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Target already married"),
            ], emoji="⚠️")
            return

        # Validation: divorce cooldown (proposer)
        remaining = self._check_divorce_cooldown(user.id, guild_id)
        if remaining:
            await self._remove_cooldown(user.id)
            hours, minutes = remaining
            await self._send_warning(message, f"❌ You must wait **{hours}h {minutes}m** after your divorce before remarrying.")
            logger.tree("Marry Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Reason", "Divorce cooldown"),
                ("Remaining", f"{hours}h {minutes}m"),
            ], emoji="⏳")
            return

        # Validation: divorce cooldown (target)
        remaining = self._check_divorce_cooldown(target.id, guild_id)
        if remaining:
            await self._remove_cooldown(user.id)
            hours, minutes = remaining
            await self._send_warning(message, f"❌ {target.mention} must wait **{hours}h {minutes}m** after their divorce before remarrying.")
            logger.tree("Marry Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Target divorce cooldown"),
                ("Remaining", f"{hours}h {minutes}m"),
            ], emoji="⏳")
            return

        # Send proposal embed with GIF
        embed = discord.Embed(
            description=f"💍 {user.mention} is proposing to {target.mention}!",
            color=COLOR_GOLD,
        )
        gif_url = await self._fetch_gif("marry_proposal")
        if gif_url:
            embed.set_image(url=gif_url)
        set_footer(embed)

        # Check for active outgoing proposal
        last_proposal = self._active_proposals.get(user.id, 0)
        if time.time() - last_proposal < 60:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You already have a pending proposal. Wait for it to expire.")
            return

        self._active_proposals[user.id] = time.time()

        view = ProposalView(user, target)
        msg = await message.channel.send(embed=embed, view=view)
        view.message = msg

        logger.tree("Marriage Proposal Sent", [
            ("Proposer", f"{user.name} ({user.display_name})"),
            ("Target", f"{target.name} ({target.display_name})"),
            ("Guild", str(guild_id)),
        ], emoji="💍")

    # =========================================================================
    # divorce
    # =========================================================================

    async def _handle_divorce(self, message: discord.Message) -> None:
        """Handle the divorce command."""
        user = message.author
        guild_id = message.guild.id

        spouse_id: Optional[int] = db.get_spouse(user.id, guild_id)
        if not spouse_id:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You're not married.")
            logger.tree("Divorce Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Reason", "Not married"),
            ], emoji="⚠️")
            return

        embed = discord.Embed(
            description=f"⚠️ {user.mention}, are you sure you want to divorce <@{spouse_id}>?\n\nBoth of you will have a **24-hour cooldown** before remarrying.",
            color=COLOR_WARNING,
        )
        set_footer(embed)

        view = DivorceView(user, spouse_id)
        msg = await message.channel.send(embed=embed, view=view)
        view.message = msg

        logger.tree("Divorce Initiated", [
            ("User", f"{user.name} ({user.display_name})"),
            ("Spouse", str(spouse_id)),
            ("Guild", str(guild_id)),
        ], emoji="⚠️")

    # =========================================================================
    # adopt @user
    # =========================================================================

    async def _handle_adopt(self, message: discord.Message) -> None:
        """Handle the adopt command."""
        user = message.author
        guild_id = message.guild.id

        target = self._get_target(message)
        if not target:
            await self._remove_cooldown(user.id)
            msg = await message.reply("Mention someone to adopt! e.g. `adopt @user`", mention_author=False)
            await asyncio.gather(
                message.delete(delay=DELETE_DELAY_SHORT),
                msg.delete(delay=DELETE_DELAY_SHORT),
                return_exceptions=True,
            )
            return

        # Validation: self
        if target.id == user.id:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You can't adopt yourself.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Reason", "Self-adoption"),
            ], emoji="⚠️")
            return

        # Validation: bot
        if target.bot:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You can't adopt a bot.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Target is bot"),
            ], emoji="⚠️")
            return

        # Validation: must be married to adopt
        spouse_id: Optional[int] = db.get_spouse(user.id, guild_id)
        if not spouse_id:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You must be married before you can adopt.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Reason", "Not married"),
            ], emoji="⚠️")
            return

        # Validation: can't adopt your spouse
        if spouse_id == target.id:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You can't adopt your spouse.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Target is spouse"),
            ], emoji="⚠️")
            return

        # Validation: already your child through marriage (spouse_id always set — marriage required)
        spouse_children = db.get_children(spouse_id, guild_id)
        if target.id in spouse_children:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ This user is already your child through marriage.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Already child through spouse"),
            ], emoji="⚠️")
            return

        # Validation: can't adopt your parent
        if db.get_parent(user.id, guild_id) == target.id:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You can't adopt your own parent.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Target is parent"),
            ], emoji="⚠️")
            return

        # Validation: max household children
        household_count: int = db.get_household_children_count(user.id, guild_id)
        if household_count >= MAX_CHILDREN:
            await self._remove_cooldown(user.id)
            await self._send_error(message, f"❌ Your household already has {MAX_CHILDREN} children (max).")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Children", str(household_count)),
                ("Reason", "Max household children reached"),
            ], emoji="⚠️")
            return

        # Validation: target already has a parent
        if db.get_parent(target.id, guild_id):
            await self._remove_cooldown(user.id)
            await self._send_error(message, f"❌ {target.mention} already has a parent.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Target has parent"),
            ], emoji="⚠️")
            return

        # Validation: circular — can't adopt your ancestor (check both user and spouse)
        if db.is_ancestor(target.id, user.id, guild_id, ANCESTOR_MAX_DEPTH):
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You can't adopt your ancestor.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Circular adoption"),
            ], emoji="⚠️")
            return

        if db.is_ancestor(target.id, spouse_id, guild_id, ANCESTOR_MAX_DEPTH):
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You can't adopt your ancestor.")
            logger.tree("Adopt Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Reason", "Circular adoption via spouse"),
            ], emoji="⚠️")
            return

        # Send adoption request with GIF
        embed = discord.Embed(
            description=f"👨‍👧 {user.mention} wants to adopt {target.mention}!",
            color=COLOR_GOLD,
        )
        gif_url = await self._fetch_gif("adopt_request")
        if gif_url:
            embed.set_image(url=gif_url)
        set_footer(embed)

        # Check for active outgoing proposal/adopt
        last_proposal = self._active_proposals.get(user.id, 0)
        if time.time() - last_proposal < 60:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You already have a pending request. Wait for it to expire.")
            return

        self._active_proposals[user.id] = time.time()

        view = AdoptView(user, target)
        msg = await message.channel.send(embed=embed, view=view)
        view.message = msg

        logger.tree("Adoption Request Sent", [
            ("Requester", f"{user.name} ({user.display_name})"),
            ("Target", f"{target.name} ({target.display_name})"),
            ("Guild", str(guild_id)),
        ], emoji="👨‍👧")

    # =========================================================================
    # disown @user
    # =========================================================================

    async def _handle_disown(self, message: discord.Message) -> None:
        """Handle the disown command."""
        user = message.author
        guild_id = message.guild.id

        target = self._get_target(message)
        if not target:
            await self._remove_cooldown(user.id)
            msg = await message.reply("Mention someone to disown! e.g. `disown @user`", mention_author=False)
            await asyncio.gather(
                message.delete(delay=DELETE_DELAY_SHORT),
                msg.delete(delay=DELETE_DELAY_SHORT),
                return_exceptions=True,
            )
            return

        # Check user's own children first, then spouse's
        children = db.get_children(user.id, guild_id)
        actual_parent_id = user.id

        if target.id not in children:
            spouse_id = db.get_spouse(user.id, guild_id)
            if spouse_id:
                spouse_children = db.get_children(spouse_id, guild_id)
                if target.id in spouse_children:
                    actual_parent_id = spouse_id
                else:
                    await self._remove_cooldown(user.id)
                    await self._send_error(message, f"❌ {target.mention} is not your child.")
                    logger.tree("Disown Rejected", [
                        ("User", f"{user.name} ({user.display_name})"),
                        ("Target", f"{target.name} ({target.display_name})"),
                        ("Reason", "Not a child"),
                    ], emoji="⚠️")
                    return
            else:
                await self._remove_cooldown(user.id)
                await self._send_error(message, f"❌ {target.mention} is not your child.")
                logger.tree("Disown Rejected", [
                    ("User", f"{user.name} ({user.display_name})"),
                    ("Target", f"{target.name} ({target.display_name})"),
                    ("Reason", "Not a child"),
                ], emoji="⚠️")
                return

        embed = discord.Embed(
            description=f"⚠️ {user.mention}, are you sure you want to disown {target.mention}?",
            color=COLOR_WARNING,
        )
        set_footer(embed)

        view = DisownView(user, target, actual_parent_id)
        msg = await message.channel.send(embed=embed, view=view)
        view.message = msg

        logger.tree("Disown Initiated", [
            ("Parent", f"{user.name} ({user.display_name})"),
            ("Child", f"{target.name} ({target.display_name})"),
            ("Guild", str(guild_id)),
        ], emoji="⚠️")

    # =========================================================================
    # runaway
    # =========================================================================

    async def _handle_runaway(self, message: discord.Message) -> None:
        """Handle the runaway command."""
        user = message.author
        guild_id = message.guild.id

        parent_id: Optional[int] = db.get_parent(user.id, guild_id)
        if not parent_id:
            await self._remove_cooldown(user.id)
            await self._send_error(message, "❌ You don't have a parent.")
            logger.tree("Runaway Rejected", [
                ("User", f"{user.name} ({user.display_name})"),
                ("Reason", "No parent"),
            ], emoji="⚠️")
            return

        # Show confirmation with both parents
        parent_spouse_id: Optional[int] = db.get_spouse(parent_id, guild_id)
        if parent_spouse_id:
            description = f"⚠️ {user.mention}, are you sure you want to run away from <@{parent_id}> & <@{parent_spouse_id}>?"
        else:
            description = f"⚠️ {user.mention}, are you sure you want to run away from <@{parent_id}>?"

        embed = discord.Embed(description=description, color=COLOR_WARNING)
        set_footer(embed)

        view = RunawayView(user, parent_id)
        msg = await message.channel.send(embed=embed, view=view)
        view.message = msg

        logger.tree("Runaway Initiated", [
            ("Child", f"{user.name} ({user.display_name})"),
            ("Parent", str(parent_id)),
            ("Guild", str(guild_id)),
        ], emoji="🏃")

    # =========================================================================
    # family [@user]
    # =========================================================================

    async def _handle_family(self, message: discord.Message) -> None:
        """Handle the family command — generates a graphical family tree card."""
        user = message.author
        guild = message.guild
        guild_id = guild.id

        # Optional target — mention, reply, or default to self
        target = self._get_target_or_self(message)

        # Gather family data from DB
        spouse_id: Optional[int] = db.get_spouse(target.id, guild_id)
        parent_id: Optional[int] = db.get_parent(target.id, guild_id)
        children: list[int] = db.get_household_children(target.id, guild_id)
        siblings: list[int] = db.get_siblings(target.id, guild_id)

        # Build FamilyData with resolved members
        data = FamilyData(
            display_name=target.display_name,
            username=target.name,
            avatar_url=str(target.display_avatar.replace(size=128, format="png")),
            max_children=MAX_CHILDREN,
        )

        # Resolve spouse
        if spouse_id:
            data.spouse = await resolve_family_member(guild, spouse_id)
            data.married_at = db.get_marriage_timestamp(target.id, guild_id)

        # Resolve parents
        if parent_id:
            data.adopted_at = db.get_adoption_timestamp(target.id, guild_id)
            parent_member = await resolve_family_member(guild, parent_id)
            data.parents.append(parent_member)
            # Check if parent has a spouse (second parent)
            parent_spouse_id: Optional[int] = db.get_spouse(parent_id, guild_id)
            if parent_spouse_id:
                parent_spouse_member = await resolve_family_member(guild, parent_spouse_id)
                data.parents.append(parent_spouse_member)

        # Resolve children
        for child_id in children[:5]:
            child_member = await resolve_family_member(guild, child_id)
            data.children.append(child_member)

        # Resolve siblings
        for sib_id in siblings[:8]:
            sib_member = await resolve_family_member(guild, sib_id)
            data.siblings.append(sib_member)

        # Generate the card image
        try:
            card_bytes = await generate_family_card(data)
            file = discord.File(io.BytesIO(card_bytes), filename="family.png")
            await message.channel.send(file=file)
        except Exception as e:
            logger.error_tree("Family Card Failed", e, [
                ("Target", f"{target.name} ({target.display_name})"),
            ])
            await self._send_error(message, "❌ Failed to generate family card.")

        logger.tree("Family Viewed", [
            ("Target", f"{target.name} ({target.display_name})"),
            ("Viewer", f"{user.name} ({user.display_name})"),
            ("Guild", str(guild_id)),
            ("Spouse", str(spouse_id) if spouse_id else "None"),
            ("Parent", str(parent_id) if parent_id else "None"),
            ("Children", str(len(children))),
            ("Siblings", str(len(siblings))),
        ], emoji="👪")

    # =========================================================================
    # Targeting Helpers
    # =========================================================================

    def _get_target(self, message: discord.Message) -> Optional[discord.Member]:
        """
        Get a target member from mentions or reply.
        Returns None if no valid target found.
        Excludes bots. Does NOT return self (use _get_target_or_self for that).
        """
        # Check reply first (like action handler)
        if message.reference and message.reference.message_id:
            try:
                replied_msg = message.reference.resolved
                if replied_msg and isinstance(replied_msg, discord.Message):
                    reply_author = replied_msg.author
                    if not reply_author.bot and reply_author.id != message.author.id:
                        return reply_author
            except Exception:
                pass

        # Check explicit mentions
        for mention in message.mentions:
            if not mention.bot and mention.id != message.author.id:
                return mention

        return None

    def _get_target_or_self(self, message: discord.Message) -> discord.Member:
        """
        Get a target member from mentions/reply, or fall back to the author.
        Used for /family where looking up yourself is valid.
        """
        # Check reply
        if message.reference and message.reference.message_id:
            try:
                replied_msg = message.reference.resolved
                if replied_msg and isinstance(replied_msg, discord.Message):
                    reply_author = replied_msg.author
                    if not reply_author.bot:
                        return reply_author
            except Exception:
                pass

        # Check mentions (allow self-mention for family lookup)
        for mention in message.mentions:
            if not mention.bot:
                return mention

        return message.author

    def _check_divorce_cooldown(self, user_id: int, guild_id: int) -> Optional[tuple[int, int]]:
        """Check divorce cooldown. Returns (hours, minutes) remaining or None."""
        cooldown_ts: Optional[int] = db.get_divorce_cooldown(user_id, guild_id)
        if not cooldown_ts:
            return None
        elapsed = int(time.time()) - cooldown_ts
        if elapsed >= COOLDOWN_24H:
            # Clean up expired cooldown
            db.delete_divorce_cooldown(user_id, guild_id)
            return None
        remaining = COOLDOWN_24H - elapsed
        return (remaining // 3600, (remaining % 3600) // 60)


# Singleton instance
family = FamilyHandler()
