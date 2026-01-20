"""
6K Members Nitro Giveaway
Run: python3 giveaway_6k.py start
Pick winner: python3 giveaway_6k.py pick <message_id>
"""

import asyncio
import discord
import os
import random
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

TOKEN = os.getenv("SYRIA_TOKEN")
GIVEAWAY_CHANNEL_ID = 1429448081354522704
GIVEAWAY_ROLE_ID = 1403196818992402452
JOIN_EMOJI_ID = 1459322239311937606
OWNER_ID = int(os.getenv("SYRIA_OWNER", 0))
GIVEAWAY_ID_FILE = Path(__file__).parent / "data" / "giveaway_message.txt"
FOOTER_TEXT = "trippixn.com/Syria"

# Embed colors
GOLD = 0xFFD700
GREEN = 0x00A859

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)


async def start_giveaway():
    """Post the giveaway embed."""
    await client.wait_until_ready()

    channel = client.get_channel(GIVEAWAY_CHANNEL_ID)
    if not channel:
        print(f"❌ Channel {GIVEAWAY_CHANNEL_ID} not found")
        await client.close()
        return

    # Use PartialEmoji for the reaction
    join_emoji = discord.PartialEmoji(name="join", id=JOIN_EMOJI_ID)

    # Calculate end time (3 days from now)
    end_time = datetime.now() + timedelta(days=3)
    end_timestamp = int(end_time.timestamp())

    # Get owner avatar for footer
    owner_avatar = None
    if OWNER_ID:
        guild = channel.guild
        try:
            owner = guild.get_member(OWNER_ID) or await guild.fetch_member(OWNER_ID)
            if owner:
                owner_avatar = owner.display_avatar.url
        except Exception:
            pass

    embed = discord.Embed(
        title="🎉  6,000 MEMBERS CELEBRATION  🎉",
        description=(
            "**Thank you for helping us reach this milestone!**\n\n"
            "To celebrate, we're giving away:\n\n"
            "# 💎 Discord Nitro 💎\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**How to Enter:**\n"
            f"React with <:join:{JOIN_EMOJI_ID}> below!\n\n"
            f"**Requirement:** Level 10+\n\n"
            f"**Ends:** <t:{end_timestamp}:R> (<t:{end_timestamp}:F>)\n"
            f"**Winner:** 1\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=GOLD,
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1071216124747849838.gif")
    embed.set_footer(text=FOOTER_TEXT, icon_url=owner_avatar)
    embed.timestamp = end_time

    # Send with role ping outside embed
    msg = await channel.send(content=f"<@&{GIVEAWAY_ROLE_ID}>", embed=embed)
    await msg.add_reaction(join_emoji)

    # Save message ID for the reaction handler
    GIVEAWAY_ID_FILE.write_text(str(msg.id))

    print(f"✅ Giveaway posted!")
    print(f"📝 Message ID: {msg.id}")
    print(f"📁 Saved to: {GIVEAWAY_ID_FILE}")
    print(f"⏰ Ends: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n💡 To pick winner, run:")
    print(f"   python3 giveaway_6k.py pick {msg.id}")

    await client.close()


async def pick_winner(message_id: int):
    """Pick a random winner from reactions."""
    await client.wait_until_ready()

    channel = client.get_channel(GIVEAWAY_CHANNEL_ID)
    if not channel:
        print(f"❌ Channel {GIVEAWAY_CHANNEL_ID} not found")
        await client.close()
        return

    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        print(f"❌ Message {message_id} not found")
        await client.close()
        return

    # Find join emoji reaction
    reaction = None
    for r in message.reactions:
        if hasattr(r.emoji, 'id') and r.emoji.id == JOIN_EMOJI_ID:
            reaction = r
            break

    if not reaction:
        print("❌ No join reaction found")
        await client.close()
        return

    # Get users who reacted (excluding bots)
    users = []
    async for user in reaction.users():
        if not user.bot:
            users.append(user)

    if not users:
        print("❌ No valid entries")
        await client.close()
        return

    print(f"📊 Total entries: {len(users)}")

    # Pick random winner
    winner = random.choice(users)
    print(f"🎉 Winner: {winner.name} ({winner.id})")

    # Get owner avatar for footer
    owner_avatar = None
    if OWNER_ID:
        guild = channel.guild
        try:
            owner = guild.get_member(OWNER_ID) or await guild.fetch_member(OWNER_ID)
            if owner:
                owner_avatar = owner.display_avatar.url
        except Exception:
            pass

    # Update original embed to show ended
    ended_embed = discord.Embed(
        title="🎉  6,000 MEMBERS CELEBRATION  🎉",
        description=(
            "**This giveaway has ended!**\n\n"
            "Prize:\n"
            "# 💎 Discord Nitro 💎\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Winner:** {winner.mention}\n"
            f"**Entries:** {len(users)}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=GREEN,
    )
    ended_embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1071216124747849838.gif")
    ended_embed.set_footer(text=FOOTER_TEXT, icon_url=owner_avatar)
    ended_embed.timestamp = datetime.now()

    await message.edit(embed=ended_embed)

    # Send winner announcement
    winner_embed = discord.Embed(
        title="🏆 GIVEAWAY WINNER 🏆",
        description=(
            f"Congratulations {winner.mention}!\n\n"
            "You won **Discord Nitro** in our 6K celebration giveaway!\n\n"
            "Please DM a staff member to claim your prize! 🎁"
        ),
        color=GOLD,
    )
    winner_embed.set_thumbnail(url=winner.display_avatar.url)
    winner_embed.set_footer(text=FOOTER_TEXT, icon_url=owner_avatar)

    await channel.send(
        content=f"🎉 {winner.mention}",
        embed=winner_embed
    )

    # Clear the giveaway message ID file
    if GIVEAWAY_ID_FILE.exists():
        GIVEAWAY_ID_FILE.unlink()
        print("📁 Cleared giveaway_message.txt")

    print("✅ Winner announced!")
    await client.close()


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 giveaway_6k.py start")
        print("  python3 giveaway_6k.py pick <message_id>")
        await client.close()
        return

    action = sys.argv[1].lower()

    if action == "start":
        await start_giveaway()
    elif action == "pick" and len(sys.argv) >= 3:
        try:
            message_id = int(sys.argv[2])
            await pick_winner(message_id)
        except ValueError:
            print("❌ Invalid message ID")
            await client.close()
    else:
        print("❌ Unknown action")
        await client.close()


if __name__ == "__main__":
    client.run(TOKEN)
