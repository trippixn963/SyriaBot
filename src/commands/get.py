"""
SyriaBot - Get Command
======================

Get user avatars/banners and server icon/banner.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import io
import aiohttp
import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Optional

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_ERROR, COLOR_WARNING, COLOR_GOLD
from src.utils.footer import set_footer
from src.utils.http import http_session


def get_cooldown(interaction: discord.Interaction) -> Optional[app_commands.Cooldown]:
    """
    Dynamic cooldown - None for mods/owners, 5 min for everyone else.

    Args:
        interaction: The Discord interaction

    Returns:
        Cooldown object or None if user is exempt
    """
    if interaction.user.id == config.OWNER_ID:
        return None

    if isinstance(interaction.user, discord.Member):
        if config.MOD_ROLE_ID:
            mod_role = interaction.user.get_role(config.MOD_ROLE_ID)
            if mod_role:
                return None

    return app_commands.Cooldown(1, 300.0)

# Main embed color (alias for backwards compatibility)
COLOR_GET = COLOR_GOLD


async def _download_and_save_image(
    interaction: discord.Interaction,
    url: str,
    label: str,
    message: Optional[discord.Message] = None,
    target_name: Optional[str] = None,
) -> None:
    """
    Shared helper to download an image, send as .gif file, and delete original.

    Args:
        interaction: The Discord interaction (must be deferred)
        url: URL to download from
        label: Label for logging (e.g., "Avatar", "Banner", "Server Icon")
        message: Original message to delete after save
        target_name: Target user/server name for logging
    """
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with http_session.session.get(url, timeout=timeout) as response:
            if response.status != 200:
                await interaction.followup.send(f"Failed to download {label.lower()}.", ephemeral=True)
                log.tree(f"{label} Save Failed", [
                    ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                    ("ID", str(interaction.user.id)),
                    ("Status", str(response.status)),
                ], emoji="❌")
                return
            image_bytes = await response.read()

        # Send as public .gif
        file = discord.File(
            fp=io.BytesIO(image_bytes),
            filename="discord.gg-syria.gif"
        )
        await interaction.followup.send(file=file)

        # Delete original message
        if message:
            try:
                await message.delete()
            except discord.NotFound:
                log.tree(f"{label} Delete Skipped", [
                    ("User", f"{interaction.user.name}"),
                    ("Reason", "Message already deleted"),
                ], emoji="⚠️")

        log_entries = [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
        ]
        if target_name:
            log_entries.append(("Target", target_name))
        log_entries.extend([
            ("Size", f"{len(image_bytes) // 1024}KB"),
            ("Original", "Deleted"),
        ])
        log.tree(f"{label} Saved", log_entries, emoji="✅")

    except Exception as e:
        log.tree(f"{label} Save Failed", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Error", str(e)[:50]),
        ], emoji="❌")
        await interaction.followup.send(f"Failed to save {label.lower()}.", ephemeral=True)


class DownloadView(ui.View):
    """View with download button."""

    def __init__(self, url: str, label: str = "Download", requester_id: int = 0) -> None:
        """
        Initialize the download view.

        Args:
            url: URL to provide for download
            label: Label for logging purposes
            requester_id: ID of user who can save
        """
        super().__init__(timeout=300)
        self.url = url
        self.label = label
        self.requester_id = requester_id
        self.message: Optional[discord.Message] = None

    async def on_timeout(self) -> None:
        """Disable button on timeout."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                log.tree("View Timeout Edit Failed", [
                    ("Type", self.label),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

    @ui.button(label="Save", style=discord.ButtonStyle.secondary, emoji="<:save:1455776703468273825>")
    async def save(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Download, send as public .gif, delete original."""
        if self.requester_id and interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who used this command can save it.",
                ephemeral=True
            )
            log.tree("Save Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Owner ID", str(self.requester_id)),
                ("Type", self.label),
            ], emoji="🚫")
            return

        await interaction.response.defer()
        log.tree("Save Started", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Type", self.label),
        ], emoji="💾")

        await _download_and_save_image(interaction, self.url, self.label, self.message)


class AvatarToggleView(ui.View):
    """View with save button and optional toggle between server/global avatar."""

    def __init__(
        self, target: discord.Member, server_url: str, global_url: str, showing_server: bool = True, requester_id: int = 0
    ) -> None:
        """
        Initialize the avatar toggle view.

        Args:
            target: The member whose avatar is shown
            server_url: URL to server avatar
            global_url: URL to global avatar
            showing_server: Whether to show server avatar first
            requester_id: ID of user who can save
        """
        super().__init__(timeout=300)
        self.target = target
        self.server_url = server_url
        self.global_url = global_url
        self.showing_server = showing_server
        self.requester_id = requester_id
        self.message: Optional[discord.Message] = None
        self._update_toggle_button()

    def _update_toggle_button(self) -> None:
        """Update toggle button label based on current state."""
        if self.showing_server:
            self.toggle_btn.label = "View Global"
        else:
            self.toggle_btn.label = "View Server"

    def _get_current_url(self) -> str:
        """Get the currently displayed avatar URL."""
        return self.server_url if self.showing_server else self.global_url

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                log.tree("Avatar View Timeout Edit Failed", [
                    ("Target", f"{self.target.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

    @ui.button(label="Save", style=discord.ButtonStyle.secondary, emoji="<:save:1455776703468273825>", row=0)
    async def save(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Download, send as public .gif, delete original."""
        if self.requester_id and interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who used this command can save it.",
                ephemeral=True
            )
            log.tree("Avatar Save Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Owner ID", str(self.requester_id)),
            ], emoji="🚫")
            return

        await interaction.response.defer()
        avatar_type = "Server" if self.showing_server else "Global"
        log.tree("Avatar Save Started", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Target", f"{self.target.name}"),
            ("Type", avatar_type),
        ], emoji="💾")

        await _download_and_save_image(
            interaction, self._get_current_url(), f"Avatar ({avatar_type})",
            self.message, self.target.name
        )

    @ui.button(label="View Global", style=discord.ButtonStyle.secondary, emoji="<:transfer:1455710226429902858>", row=0)
    async def toggle_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Toggle between server and global avatar."""
        self.showing_server = not self.showing_server
        self._update_toggle_button()

        # Build new embed
        current_url = self._get_current_url()
        avatar_type = "Server" if self.showing_server else "Global"

        embed = discord.Embed(
            title=f"{self.target.name}'s Avatar",
            description=f"Account created <t:{int(self.target.created_at.timestamp())}:R>",
            color=COLOR_GET
        )
        embed.set_image(url=current_url)
        embed.add_field(name="Type", value=avatar_type, inline=True)
        embed.add_field(name="User", value=self.target.mention, inline=True)
        set_footer(embed)

        await interaction.response.edit_message(embed=embed, view=self)

        log.tree("Avatar Toggled", [
            ("Target", f"{self.target.name} ({self.target.display_name})"),
            ("Target ID", str(self.target.id)),
            ("Now Showing", avatar_type),
            ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("By ID", str(interaction.user.id)),
        ], emoji="🔄")


class BannerToggleView(ui.View):
    """View with save button and optional toggle between server/global banner."""

    def __init__(
        self, target: discord.Member, server_url: str, global_url: str, showing_server: bool = True, requester_id: int = 0
    ) -> None:
        """
        Initialize the banner toggle view.

        Args:
            target: The member whose banner is shown
            server_url: URL to server banner
            global_url: URL to global banner
            showing_server: Whether to show server banner first
            requester_id: ID of user who can save
        """
        super().__init__(timeout=300)
        self.target = target
        self.server_url = server_url
        self.global_url = global_url
        self.showing_server = showing_server
        self.requester_id = requester_id
        self.message: Optional[discord.Message] = None
        self._update_toggle_button()

    def _update_toggle_button(self) -> None:
        """Update toggle button label based on current state."""
        if self.showing_server:
            self.toggle_btn.label = "View Global"
        else:
            self.toggle_btn.label = "View Server"

    def _get_current_url(self) -> str:
        """Get the currently displayed banner URL."""
        return self.server_url if self.showing_server else self.global_url

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                log.tree("Banner View Timeout Edit Failed", [
                    ("Target", f"{self.target.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

    @ui.button(label="Save", style=discord.ButtonStyle.secondary, emoji="<:save:1455776703468273825>", row=0)
    async def save(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Download, send as public .gif, delete original."""
        if self.requester_id and interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who used this command can save it.",
                ephemeral=True
            )
            log.tree("Banner Save Rejected", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Owner ID", str(self.requester_id)),
            ], emoji="🚫")
            return

        await interaction.response.defer()
        banner_type = "Server" if self.showing_server else "Global"
        log.tree("Banner Save Started", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Target", f"{self.target.name}"),
            ("Type", banner_type),
        ], emoji="💾")

        await _download_and_save_image(
            interaction, self._get_current_url(), f"Banner ({banner_type})",
            self.message, self.target.name
        )

    @ui.button(label="View Global", style=discord.ButtonStyle.secondary, emoji="<:transfer:1455710226429902858>", row=0)
    async def toggle_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Toggle between server and global banner."""
        self.showing_server = not self.showing_server
        self._update_toggle_button()

        # Build new embed
        current_url = self._get_current_url()
        banner_type = "Server" if self.showing_server else "Global"

        embed = discord.Embed(
            title=f"{self.target.name}'s Banner",
            description=f"Account created <t:{int(self.target.created_at.timestamp())}:R>",
            color=COLOR_GET
        )
        embed.set_image(url=current_url)
        embed.add_field(name="Type", value=banner_type, inline=True)
        embed.add_field(name="User", value=self.target.mention, inline=True)
        set_footer(embed)

        await interaction.response.edit_message(embed=embed, view=self)

        log.tree("Banner Toggled", [
            ("Target", f"{self.target.name} ({self.target.display_name})"),
            ("Target ID", str(self.target.id)),
            ("Now Showing", banner_type),
            ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("By ID", str(interaction.user.id)),
        ], emoji="🔄")


class GetCog(commands.Cog):
    """Get avatar/banner command."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the get cog."""
        self.bot = bot

    @app_commands.command(name="get", description="Get avatars, banners, or server assets")
    @app_commands.describe(
        option="Avatar, banner, server icon, or server banner",
        user="Target user (leave empty for yourself, ignored for server options)"
    )
    @app_commands.choices(option=[
        app_commands.Choice(name="Avatar", value="avatar"),
        app_commands.Choice(name="Banner", value="banner"),
        app_commands.Choice(name="Server Icon", value="server_icon"),
        app_commands.Choice(name="Server Banner", value="server_banner"),
    ])
    @app_commands.checks.dynamic_cooldown(get_cooldown)
    async def get(
        self,
        interaction: discord.Interaction,
        option: app_commands.Choice[str],
        user: Optional[discord.Member] = None
    ) -> None:
        """Get a user's avatar/banner or server icon/banner."""
        await interaction.response.defer()

        # Server options don't need a target user
        is_server_option = option.value in ("server_icon", "server_banner")

        if is_server_option:
            log.tree("Get Command", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Option", option.value),
                ("Guild", interaction.guild.name if interaction.guild else "DM"),
            ], emoji="🔍")
        else:
            target = user or interaction.user
            target_member = interaction.guild.get_member(target.id) if interaction.guild else None
            log.tree("Get Command", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Option", option.value),
                ("Target", f"{target.name} ({target.display_name})"),
                ("Target ID", str(target.id)),
            ], emoji="🔍")

        try:
            if option.value == "avatar":
                target = user or interaction.user
                target_member = interaction.guild.get_member(target.id) if interaction.guild else None
                await self._handle_avatar(interaction, target, target_member)
            elif option.value == "banner":
                target = user or interaction.user
                target_member = interaction.guild.get_member(target.id) if interaction.guild else None
                await self._handle_banner(interaction, target, target_member)
            elif option.value == "server_icon":
                await self._handle_server_icon(interaction)
            elif option.value == "server_banner":
                await self._handle_server_banner(interaction)

        except discord.HTTPException as e:
            log.tree("Get Command Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Option", option.value),
                ("Error", str(e)[:100]),
            ], emoji="❌")
            embed = discord.Embed(
                description="❌ Failed to fetch data.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            log.tree("Get Command Error", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Option", option.value),
                ("Error", str(e)[:100]),
            ], emoji="❌")
            embed = discord.Embed(
                description="❌ An error occurred.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def _handle_avatar(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        target_member: Optional[discord.Member]
    ) -> None:
        """Handle avatar request - shows toggle if user has both server and global avatar."""
        # Check if user has both server and global avatar
        has_server_avatar = target_member and target_member.guild_avatar
        has_global_avatar = target.avatar is not None

        # Get URLs
        if has_server_avatar:
            server_url = target_member.guild_avatar.url
            if "?" in server_url:
                server_url = server_url.split("?")[0] + "?size=4096"
            else:
                server_url = server_url + "?size=4096"
        else:
            server_url = None

        if has_global_avatar:
            global_url = target.avatar.url
        else:
            global_url = target.default_avatar.url
        if "?" in global_url:
            global_url = global_url.split("?")[0] + "?size=4096"
        else:
            global_url = global_url + "?size=4096"

        # Determine what to show first and if toggle is needed
        has_both = has_server_avatar and has_global_avatar
        if has_server_avatar:
            avatar_url = server_url
            avatar_type = "Server"
        else:
            avatar_url = global_url
            avatar_type = "Global"

        embed = discord.Embed(
            title=f"{target.name}'s Avatar",
            description=f"Account created <t:{int(target.created_at.timestamp())}:R>",
            color=COLOR_GET
        )
        embed.set_image(url=avatar_url)
        embed.add_field(name="Type", value=avatar_type, inline=True)
        embed.add_field(name="User", value=target.mention, inline=True)
        set_footer(embed)

        # Use toggle view if both avatars exist, otherwise just download view
        if has_both:
            view = AvatarToggleView(target, server_url, global_url, showing_server=True, requester_id=interaction.user.id)
        else:
            view = DownloadView(avatar_url, "Avatar", requester_id=interaction.user.id)

        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg

        log.tree("Get Avatar Complete", [
            ("Target", f"{target.name} ({target.display_name})"),
            ("Target ID", str(target.id)),
            ("Type", avatar_type),
            ("Has Both", "Yes" if has_both else "No"),
            ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("By ID", str(interaction.user.id)),
        ], emoji="✅")

    async def _handle_banner(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        target_member: Optional[discord.Member]
    ) -> None:
        """Handle banner request - shows toggle if user has both server and global banner."""
        # Need to fetch user to get global banner (not cached by default)
        try:
            fetched_user = await self.bot.fetch_user(target.id)
        except discord.NotFound:
            log.tree("Get Banner Failed", [
                ("Target", f"{target.name} ({target.display_name})"),
                ("Target ID", str(target.id)),
                ("Reason", "User not found"),
            ], emoji="❌")
            embed = discord.Embed(
                description="❌ Could not find that user.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Check if user has both server and global banner
        has_server_banner = target_member and target_member.guild_banner
        has_global_banner = fetched_user.banner is not None

        # If no banners at all
        if not has_server_banner and not has_global_banner:
            log.tree("Get Banner No Banner", [
                ("Target", f"{target.name} ({target.display_name})"),
                ("Target ID", str(target.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
            ], emoji="⚠️")
            embed = discord.Embed(
                description=f"⚠️ **{target.name}** doesn't have a banner.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get URLs
        if has_server_banner:
            server_url = target_member.guild_banner.url
            if "?" in server_url:
                server_url = server_url.split("?")[0] + "?size=4096"
            else:
                server_url = server_url + "?size=4096"
        else:
            server_url = None

        if has_global_banner:
            global_url = fetched_user.banner.url
            if "?" in global_url:
                global_url = global_url.split("?")[0] + "?size=4096"
            else:
                global_url = global_url + "?size=4096"
        else:
            global_url = None

        # Determine what to show first and if toggle is needed
        has_both = has_server_banner and has_global_banner
        if has_server_banner:
            banner_url = server_url
            banner_type = "Server"
        else:
            banner_url = global_url
            banner_type = "Global"

        embed = discord.Embed(
            title=f"{target.name}'s Banner",
            description=f"Account created <t:{int(target.created_at.timestamp())}:R>",
            color=COLOR_GET
        )
        embed.set_image(url=banner_url)
        embed.add_field(name="Type", value=banner_type, inline=True)
        embed.add_field(name="User", value=target.mention, inline=True)
        set_footer(embed)

        # Use toggle view if both banners exist, otherwise just download view
        if has_both:
            view = BannerToggleView(target, server_url, global_url, showing_server=True, requester_id=interaction.user.id)
        else:
            view = DownloadView(banner_url, "Banner", requester_id=interaction.user.id)

        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg

        log.tree("Get Banner Complete", [
            ("Target", f"{target.name} ({target.display_name})"),
            ("Target ID", str(target.id)),
            ("Type", banner_type),
            ("Has Both", "Yes" if has_both else "No"),
            ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("By ID", str(interaction.user.id)),
        ], emoji="✅")

    async def _handle_server_icon(self, interaction: discord.Interaction) -> None:
        """Handle server icon request."""
        if not interaction.guild:
            embed = discord.Embed(
                description="⚠️ This command can only be used in a server.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if not interaction.guild.icon:
            log.tree("Get Server Icon No Icon", [
                ("Guild", interaction.guild.name),
                ("Guild ID", str(interaction.guild.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="⚠️ This server doesn't have an icon.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        icon_url = interaction.guild.icon.url

        # Get high quality URL
        if "?" in icon_url:
            icon_url = icon_url.split("?")[0] + "?size=4096"
        else:
            icon_url = icon_url + "?size=4096"

        # Build server info description
        guild = interaction.guild
        boost_level = f"Level {guild.premium_tier}" if guild.premium_tier > 0 else "No boosts"
        description = (
            f"**{guild.member_count:,}** members · {boost_level}\n"
            f"Created <t:{int(guild.created_at.timestamp())}:R>"
        )

        embed = discord.Embed(
            title=f"{guild.name}'s Icon",
            description=description,
            color=COLOR_GET
        )
        embed.set_image(url=icon_url)
        set_footer(embed)

        view = DownloadView(icon_url, "Server Icon", requester_id=interaction.user.id)
        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg

        log.tree("Get Server Icon Complete", [
            ("Guild", interaction.guild.name),
            ("Guild ID", str(interaction.guild.id)),
            ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("By ID", str(interaction.user.id)),
        ], emoji="✅")

    async def _handle_server_banner(self, interaction: discord.Interaction) -> None:
        """Handle server banner request."""
        if not interaction.guild:
            embed = discord.Embed(
                description="⚠️ This command can only be used in a server.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if not interaction.guild.banner:
            log.tree("Get Server Banner No Banner", [
                ("Guild", interaction.guild.name),
                ("Guild ID", str(interaction.guild.id)),
                ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("By ID", str(interaction.user.id)),
            ], emoji="⚠️")
            embed = discord.Embed(
                description="⚠️ This server doesn't have a banner.",
                color=COLOR_WARNING
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        banner_url = interaction.guild.banner.url

        # Get high quality URL
        if "?" in banner_url:
            banner_url = banner_url.split("?")[0] + "?size=4096"
        else:
            banner_url = banner_url + "?size=4096"

        # Build server info description
        guild = interaction.guild
        boost_level = f"Level {guild.premium_tier}" if guild.premium_tier > 0 else "No boosts"
        description = (
            f"**{guild.member_count:,}** members · {boost_level}\n"
            f"Created <t:{int(guild.created_at.timestamp())}:R>"
        )

        embed = discord.Embed(
            title=f"{guild.name}'s Banner",
            description=description,
            color=COLOR_GET
        )
        embed.set_image(url=banner_url)
        set_footer(embed)

        view = DownloadView(banner_url, "Server Banner", requester_id=interaction.user.id)
        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg

        log.tree("Get Server Banner Complete", [
            ("Guild", interaction.guild.name),
            ("Guild ID", str(interaction.guild.id)),
            ("By", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("By ID", str(interaction.user.id)),
        ], emoji="✅")

    @get.error
    async def get_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """Handle get command errors."""
        if isinstance(error, app_commands.CommandOnCooldown):
            minutes = int(error.retry_after // 60)
            seconds = int(error.retry_after % 60)
            if minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"

            try:
                await interaction.response.send_message(
                    f"⏳ Slow down! You can use `/get` again in **{time_str}**",
                    ephemeral=True,
                )
            except discord.HTTPException as e:
                log.tree("Get Cooldown Response Failed", [
                    ("User", f"{interaction.user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

            log.tree("Get Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Remaining", time_str),
            ], emoji="⏳")
            return

        log.tree("Get Command Error", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Error", str(error)[:100]),
        ], emoji="❌")

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred",
                    ephemeral=True,
                )
        except discord.HTTPException as e:
            log.tree("Get Error Response Failed", [
                ("User", f"{interaction.user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")


async def setup(bot: commands.Bot) -> None:
    """Load the get cog."""
    await bot.add_cog(GetCog(bot))
    log.tree("Command Loaded", [("Name", "get")], emoji="✅")
