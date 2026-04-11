import aiohttp
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
import sys
import discord

# Add current directory to path to import bot
sys.path.append(os.getcwd())
import bot

async def verify():
    print(f"Testing get_updates_data with {len(bot.PLAYERS)} players...")
    async with aiohttp.ClientSession() as session:
        updates = await bot.get_updates_data(session, bot.PLAYERS)
    
    print(f"\nFound {len(updates)} updates.")
    
    for i, up in enumerate(updates, start=1):
        print(f"\n--- Update {i} ---")
        print(f"Type: {up['type']}")
        print(f"Player: {up['player']}")
        embed = bot.create_update_embed(up)
        print(f"Embed Title: {embed.title}")
        print(f"Embed Description: {embed.description}")
        print(f"Embed Color: {embed.color}")
        print(f"Embed Footer: {embed.footer.text}")
    
    if updates:
        print("\nVerification Successful: Styled updates generated.")
    else:
        print("\nVerification: No updates found (this is normal if no recent activity).")

if __name__ == "__main__":
    asyncio.run(verify())
