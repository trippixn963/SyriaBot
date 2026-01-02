"""
Update role permissions for XP system.

LVL 5: Attach files, embed links (remove external emojis if present)
LVL 10: Add external emojis
LVL 20: Add external stickers
"""

import asyncio
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import discord
from discord import Permissions

# Role IDs
ROLE_UPDATES = {
    # LVL 5 - ensure it has attach_files, embed_links but NOT external emojis
    1402310963989975170: {
        "name": "LVL 5",
        "add": ["attach_files", "embed_links"],
        "remove": ["use_external_emojis", "use_external_stickers"],
    },
    # LVL 10 - add external emojis
    1402311203413295124: {
        "name": "LVL 10",
        "add": ["use_external_emojis"],
        "remove": [],
    },
    # LVL 20 - add external stickers
    1402311311907356682: {
        "name": "LVL 20",
        "add": ["use_external_stickers"],
        "remove": [],
    },
}

GUILD_ID = int(os.getenv("SYRIA_GUILD_ID", 0))


async def main():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}")

        guild = client.get_guild(GUILD_ID)
        if not guild:
            print(f"Guild {GUILD_ID} not found")
            await client.close()
            return

        for role_id, config in ROLE_UPDATES.items():
            role = guild.get_role(role_id)
            if not role:
                print(f"❌ Role {config['name']} ({role_id}) not found")
                continue

            # Get current permissions
            perms = role.permissions

            # Build new permissions
            new_perms_dict = dict(perms)

            # Add permissions
            for perm in config["add"]:
                new_perms_dict[perm] = True

            # Remove permissions
            for perm in config["remove"]:
                new_perms_dict[perm] = False

            new_perms = Permissions(**new_perms_dict)

            # Update if changed
            if perms != new_perms:
                try:
                    await role.edit(permissions=new_perms, reason="XP system permission update")
                    print(f"✅ Updated {config['name']}")
                    print(f"   Added: {config['add']}")
                    if config['remove']:
                        print(f"   Removed: {config['remove']}")
                except Exception as e:
                    print(f"❌ Failed to update {config['name']}: {e}")
            else:
                print(f"⏭️  {config['name']} already has correct permissions")

        print("\nDone!")
        await client.close()

    token = os.getenv("SYRIA_BOT_TOKEN")
    if not token:
        print("No token found")
        return

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
