"""
Fix all XP roles to have correct cumulative permissions.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import discord

GUILD_ID = int(os.getenv("SYRIA_GUILD_ID", 0))

# Role configs - cumulative permissions
ROLE_CONFIGS = {
    "Citizen": {
        "connect": False,
        "attach_files": False,
        "embed_links": False,
        "use_external_emojis": False,
        "use_external_stickers": False,
        "change_nickname": False,
    },
    "LVL 1": {
        "connect": True,
    },
    "LVL 5": {
        "connect": True,
        "attach_files": True,
        "embed_links": True,
    },
    "LVL 10": {
        "connect": True,
        "attach_files": True,
        "embed_links": True,
        "use_external_emojis": True,
    },
    "LVL 20": {
        "connect": True,
        "attach_files": True,
        "embed_links": True,
        "use_external_emojis": True,
        "use_external_stickers": True,
    },
    "LVL 30": {
        "connect": True,
        "attach_files": True,
        "embed_links": True,
        "use_external_emojis": True,
        "use_external_stickers": True,
        "change_nickname": True,
    },
}

# LVL 40-100 same as LVL 30
for lvl in [40, 50, 60, 70, 80, 90, 100]:
    ROLE_CONFIGS[f"LVL {lvl}"] = ROLE_CONFIGS["LVL 30"].copy()


async def main():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}\n")

        guild = client.get_guild(GUILD_ID)
        if not guild:
            print(f"Guild {GUILD_ID} not found")
            await client.close()
            return

        print("=" * 60)
        print("FIXING ROLE PERMISSIONS")
        print("=" * 60)

        for role_name, perms_to_set in ROLE_CONFIGS.items():
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                print(f"\n❌ {role_name}: NOT FOUND")
                continue

            # Get current permissions as dict
            current = {p: getattr(role.permissions, p) for p in perms_to_set.keys()}

            # Check if update needed
            needs_update = any(current.get(p) != v for p, v in perms_to_set.items())

            if needs_update:
                # Build new permissions - start with current, update specific ones
                new_perms_dict = dict(role.permissions)
                for perm, value in perms_to_set.items():
                    new_perms_dict[perm] = value

                new_perms = discord.Permissions(**new_perms_dict)

                try:
                    await role.edit(permissions=new_perms, reason="XP system permission fix")
                    print(f"\n✅ Fixed {role_name}")
                    for p, v in perms_to_set.items():
                        if current.get(p) != v:
                            print(f"   {p}: {current.get(p)} → {v}")
                except Exception as e:
                    print(f"\n❌ Failed {role_name}: {e}")
            else:
                print(f"\n✓ {role_name} - OK")

        print("\n" + "=" * 60)
        print("DONE")
        print("=" * 60)

        await client.close()

    token = os.getenv("SYRIA_BOT_TOKEN")
    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
