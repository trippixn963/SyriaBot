"""
One-time script to remove all members from custom roles.

Run with: python scripts/clear_custom_roles.py
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env BEFORE importing config
from dotenv import load_dotenv
load_dotenv()

import discord

# Now import config (after dotenv loaded)
from src.core.config import Config
config = Config()

# Role IDs to clear
ROLE_IDS_TO_CLEAR = [
    1402310963989975170,
    1402311203413295124,
    1402311311907356682,
    1258088149524156497,
    1258088492261576815,
    1402354179405779014,
    1402353635521990686,
]


async def main():
    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}")

        guild = client.get_guild(config.GUILD_ID)
        if not guild:
            print(f"Could not find guild {config.GUILD_ID}")
            await client.close()
            return

        print(f"Found guild: {guild.name}")

        total_removed = 0

        for role_id in ROLE_IDS_TO_CLEAR:
            role = guild.get_role(role_id)
            if not role:
                print(f"Role {role_id} not found, skipping...")
                continue

            members_with_role = [m for m in guild.members if role in m.roles]
            print(f"\nRole: {role.name} ({role_id})")
            print(f"  Members: {len(members_with_role)}")

            for member in members_with_role:
                try:
                    await member.remove_roles(role, reason="Clearing custom roles")
                    print(f"  Removed from: {member.display_name}")
                    total_removed += 1
                except discord.Forbidden:
                    print(f"  FAILED (forbidden): {member.display_name}")
                except discord.HTTPException as e:
                    print(f"  FAILED (HTTP error): {member.display_name} - {e}")

                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)

        print(f"\nDone! Removed {total_removed} role assignments.")
        await client.close()

    await client.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
