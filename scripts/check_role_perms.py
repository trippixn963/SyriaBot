"""
Script to find LVL roles and check their permissions.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import discord
from src.core.config import Config
config = Config()

# Role names to find
ROLE_NAMES = [
    "Citizen",
    "LVL 5",
    "LVL 10",
    "LVL 20",
    "LVL 30",
    "LVL 40",
    "LVL 50",
    "LVL 60",
    "LVL 70",
    "LVL 80",
    "LVL 90",
    "LVL 100",
]

# Key permissions to check
PERMS_TO_CHECK = [
    "send_messages",
    "add_reactions",
    "connect",  # Voice
    "attach_files",
    "embed_links",
    "use_external_emojis",
    "use_external_stickers",
]


async def main():
    intents = discord.Intents.default()
    intents.guilds = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}\n")

        guild = client.get_guild(config.GUILD_ID)
        if not guild:
            print(f"Could not find guild {config.GUILD_ID}")
            await client.close()
            return

        print(f"Guild: {guild.name}\n")
        print("=" * 80)

        for role_name in ROLE_NAMES:
            # Find role by name
            role = discord.utils.get(guild.roles, name=role_name)

            if not role:
                print(f"{role_name}: NOT FOUND")
                print("-" * 80)
                continue

            print(f"{role_name}")
            print(f"  ID: {role.id}")
            print(f"  Members: {len(role.members)}")
            print(f"  Position: {role.position}")
            print(f"  Color: #{role.color.value:06x}")
            print(f"  Permissions:")

            perms = role.permissions
            for perm_name in PERMS_TO_CHECK:
                has_perm = getattr(perms, perm_name, False)
                status = "✓" if has_perm else "✗"
                print(f"    {status} {perm_name}")

            print("-" * 80)

        # Print env format for role rewards
        print("\n\nENV FORMAT FOR XP_ROLE_REWARDS:")
        print("SYRIA_XP_ROLE_REWARDS=", end="")
        pairs = []
        for role_name in ROLE_NAMES:
            role = discord.utils.get(guild.roles, name=role_name)
            if role and role_name.startswith("LVL "):
                level = role_name.replace("LVL ", "")
                pairs.append(f"{level}:{role.id}")
        print(",".join(pairs))

        await client.close()

    await client.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
