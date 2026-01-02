"""
SyriaBot - Get Command
======================

Get user avatars/banners and server icon/banner.

Author: حَـــــنَّـــــا
"""

import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Optional

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING, COLOR_GOLD
from src.utils.footer import set_footer


def get_cooldown(interaction: discord.Interaction) -> app_commands.Cooldown | None:
    """Dynamic cooldown - None for mods/owners, 5 min for everyone else."""
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


class DownloadView(ui.View):
    """View with download button."""

    def __init__(self, url: str, label: str = "Download"):
        super().__init__(timeout=300)
        self.url = url
        self.label = label

    async def on_timeout(self):
        """Disable button on timeout."""
        for item in self.children:
            item.disabled = True

    @ui.button(label="Save", style=discord.ButtonStyle.secondary, emoji="<:save:1455776703468273825>")
    async def save(self, interaction: discord.Interaction, button: ui.Button):
        """Send download link."""
        await interaction.response.send_message(self.url, ephemeral=True)
        log.tree("Save Link Sent", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Type", self.label),
        ], emoji="💾")


class AvatarToggleView(ui.View):
    """View with save button and optional toggle between server/global avatar."""

    def __init__(self, target: discord.Member, server_url: str, global_url: str, showing_server: bool = True):
        super().__init__(timeout=300)
        self.target = target
        self.server_url = server_url
        self.global_url = global_url
        self.showing_server = showing_server
        self._update_toggle_button()

    def _update_toggle_button(self):
        """Update toggle button label based on current state."""
        if self.showing_server:
            self.toggle_btn.label = "View Global"
        else:
            self.toggle_btn.label = "View Server"

    def _get_current_url(self) -> str:
        return self.server_url if self.showing_server else self.global_url

    async def on_timeout(self):
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True

    @ui.button(label="Save", style=discord.ButtonStyle.secondary, emoji="<:save:1455776703468273825>", row=0)
    async def save(self, interaction: discord.Interaction, button: ui.Button):
        """Send download link."""
        await interaction.response.send_message(self._get_current_url(), ephemeral=True)
        log.tree("Save Link Sent", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Type", "Avatar"),
        ], emoji="💾")

    @ui.button(label="View Global", style=discord.ButtonStyle.secondary, emoji="<:transfer:1455710226429902858>", row=0)
    async def toggle_btn(self, interaction: discord.Interaction, button: ui.Button):
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


class GetCog(commands.Cog):
    """Get avatar/banner command."""

    def __init__(self, bot: commands.Bot):
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
    ):
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
                await self._handle_banner(interaction, target)
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
            view = AvatarToggleView(target, server_url, global_url, showing_server=True)
        else:
            view = DownloadView(avatar_url, "Avatar")

        await interaction.followup.send(embed=embed, view=view)

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
        target: discord.Member
    ) -> None:
        """Handle banner request."""
        # Need to fetch user to get banner (not cached by default)
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

        if not fetched_user.banner:
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

        banner_url = fetched_user.banner.url

        # Get high quality URL
        if "?" in banner_url:
            banner_url = banner_url.split("?")[0] + "?size=4096"
        else:
            banner_url = banner_url + "?size=4096"

        embed = discord.Embed(
            title=f"{target.name}'s Banner",
            description=f"Account created <t:{int(target.created_at.timestamp())}:R>",
            color=COLOR_GET
        )
        embed.set_image(url=banner_url)
        embed.add_field(name="User", value=target.mention, inline=True)
        set_footer(embed)

        view = DownloadView(banner_url, "Banner")
        await interaction.followup.send(embed=embed, view=view)

        log.tree("Get Banner Complete", [
            ("Target", f"{target.name} ({target.display_name})"),
            ("Target ID", str(target.id)),
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

        view = DownloadView(icon_url, "Server Icon")
        await interaction.followup.send(embed=embed, view=view)

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

        view = DownloadView(banner_url, "Server Banner")
        await interaction.followup.send(embed=embed, view=view)

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
            except discord.HTTPException:
                pass

            log.tree("Get Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("User ID", str(interaction.user.id)),
                ("Remaining", time_str),
            ], emoji="⏳")
            return

        log.tree("Get Command Error", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
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
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(GetCog(bot))
    log.success("Loaded get command")
