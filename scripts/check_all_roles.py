"""
Check all XP roles from Citizen to LVL 100 and their permissions.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import discord

GUILD_ID = int(os.getenv("SYRIA_GUILD_ID", 0))

# Expected permissions for each level
# Perms are CUMULATIVE - higher levels should have all perms from lower levels
EXPECTED_PERMS = {
    "Citizen": {
        "connect": False,  # Cannot connect to voice
        "attach_files": False,
        "embed_links": False,
        "use_external_emojis": False,
        "use_external_stickers": False,
        "change_nickname": False,
    },
    "LVL 1": {
        "connect": True,  # Can connect to voice
        "attach_files": False,
        "embed_links": False,
        "use_external_emojis": False,
        "use_external_stickers": False,
        "change_nickname": False,
    },
    "LVL 5": {
        "connect": True,
        "attach_files": True,  # Unlocked
        "embed_links": True,   # Unlocked
        "use_external_emojis": False,
        "use_external_stickers": False,
        "change_nickname": False,
    },
    "LVL 10": {
        "connect": True,
        "attach_files": True,
        "embed_links": True,
        "use_external_emojis": True,  # Unlocked
        "use_external_stickers": False,
        "change_nickname": False,
    },
    "LVL 20": {
        "connect": True,
        "attach_files": True,
        "embed_links": True,
        "use_external_emojis": True,
        "use_external_stickers": True,  # Unlocked
        "change_nickname": False,
    },
    "LVL 30": {
        "connect": True,
        "attach_files": True,
        "embed_links": True,
        "use_external_emojis": True,
        "use_external_stickers": True,
        "change_nickname": True,  # Unlocked
    },
}

# LVL 40-100 should have same perms as LVL 30 (all unlocked)
for lvl in [40, 50, 60, 70, 80, 90, 100]:
    EXPECTED_PERMS[f"LVL {lvl}"] = EXPECTED_PERMS["LVL 30"].copy()


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

        print("=" * 70)
        print("ROLE PERMISSIONS AUDIT")
        print("=" * 70)

        all_good = True

        for role_name, expected in EXPECTED_PERMS.items():
            # Find role by name
            role = discord.utils.get(guild.roles, name=role_name)

            if not role:
                print(f"\n❌ {role_name}: NOT FOUND")
                all_good = False
                continue

            # Check permissions
            issues = []
            for perm_name, should_have in expected.items():
                actual = getattr(role.permissions, perm_name, None)
                if actual != should_have:
                    issues.append(f"{perm_name}: has={actual}, expected={should_have}")

            if issues:
                print(f"\n❌ {role_name} (ID: {role.id})")
                for issue in issues:
                    print(f"   ⚠️  {issue}")
                all_good = False
            else:
                # Show what perms they have
                has_perms = [p for p, v in expected.items() if v]
                if has_perms:
                    print(f"\n✅ {role_name} (ID: {role.id})")
                    print(f"   Perms: {', '.join(has_perms)}")
                else:
                    print(f"\n✅ {role_name} (ID: {role.id})")
                    print(f"   Perms: None (restricted)")

        print("\n" + "=" * 70)
        if all_good:
            print("✅ ALL ROLES CONFIGURED CORRECTLY")
        else:
            print("❌ SOME ROLES NEED FIXING")
        print("=" * 70)

        await client.close()

    token = os.getenv("SYRIA_BOT_TOKEN")
    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
