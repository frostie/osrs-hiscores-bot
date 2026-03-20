import discord
from discord.ext import commands
import aiohttp
import json
import os
from datetime import datetime, timedelta
import asyncio

# Constants
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
PLAYER_DATA_FILE = os.path.join(os.path.dirname(__file__), 'player_data.json')
HISCORES_URL = 'https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player='
WISE_OLD_MAN_URL = 'https://api.wiseoldman.net/v2/players/'

# Configuration and bot setup
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

TOKEN = config.get("DISCORD_TOKEN")
PLAYERS = config.get("players", [])

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Helper functions
def load_player_data():
    """Loads the player data file."""
    try:
        with open(PLAYER_DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_player_data(data):
    """Saves data to the player data file."""
    with open(PLAYER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

async def fetch_all_stats(session, player_name):
    """Fetches and parses all player stats from the hiscores API."""
    url = f"{HISCORES_URL}{player_name}"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.text()
                return parse_stats(data)
            return None
    except Exception:
        return None

def parse_stats(data):
    """Parses the CSV data from the hiscores API."""
    skills = [
        'Overall', 'Attack', 'Defence', 'Strength', 'Hitpoints', 'Ranged', 'Prayer',
        'Magic', 'Cooking', 'Woodcutting', 'Fletching', 'Fishing', 'Firemaking',
        'Crafting', 'Smithing', 'Mining', 'Herblore', 'Agility', 'Thieving',
        'Slayer', 'Farming', 'Runecraft', 'Hunter', 'Construction'
    ]
    stats = {}
    lines = data.strip().split('\n')
    for i, line in enumerate(lines[:len(skills)]):
        parts = line.split(',')
        if len(parts) == 3:
            rank, level, xp = parts
            stats[skills[i]] = {'rank': int(rank), 'level': int(level), 'xp': int(xp)}
    return stats

async def fetch_collection_log(session, username):
    """Fetches collection log data from the Wise Old Man API."""
    url = f"{WISE_OLD_MAN_URL}{username}/collection-log"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('collectionLog', {}).get('items', [])
            return []
    except Exception:
        return []

# Bot events
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    # Create player data file if it doesn't exist
    if not os.path.exists(PLAYER_DATA_FILE):
        save_player_data({})
    print('------')

# Bot commands
@bot.command(name='hiscores')
async def hiscores_command(ctx):
    """Displays the overall hiscores for tracked players."""
    if not PLAYERS:
        await ctx.send("No players are currently configured to be tracked.")
        return

    m = await ctx.send(f"Fetching hiscores for {len(PLAYERS)} players...")

    results = []
    async with aiohttp.ClientSession() as session:
        for player in PLAYERS:
            url = f"{HISCORES_URL}{player}"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.text()
                        first_line = data.split('\n')[0]
                        rank, level, xp = first_line.split(',')
                        results.append({
                            "player": player, "rank": int(rank),
                            "level": int(level), "xp": int(xp)
                        })
                    elif response.status == 404:
                        results.append({"player": player, "error": "Player not found."})
                    else:
                        results.append({"player": player, "error": f"API Error: {response.status}"})
            except Exception as e:
                results.append({"player": player, "error": str(e)})

    results.sort(key=lambda x: (0 if "error" not in x else 1, -x.get("xp", 0)))

    embed = discord.Embed(title="OSRS Overall Hiscores", color=discord.Color.green())
    for i, stat in enumerate(results, start=1):
        if "error" in stat:
            embed.add_field(name=f"{i}. {stat['player']}", value=f"Error: {stat['error']}", inline=False)
        else:
            value = f"**Level:** {stat['level']}\n**Rank:** {stat['rank']:,}\n**XP:** {stat['xp']:,}"
            embed.add_field(name=f"{i}. {stat['player']}", value=value, inline=False)

    await m.edit(content=None, embed=embed)

@bot.command(name='updates')
async def updates_command(ctx):
    """Checks for player updates in the last 24 hours."""
    m = await ctx.send("Checking for recent player updates...")
    player_data = load_player_data()
    now = datetime.utcnow()
    updates_found = False

    async with aiohttp.ClientSession() as session:
        for username in PLAYERS:
            # Check Hiscores for level ups
            new_stats = await fetch_all_stats(session, username)
            if new_stats:
                old_player_stats = player_data.get(username, {}).get('stats', {})
                if old_player_stats:
                    for skill, new_values in new_stats.items():
                        old_values = old_player_stats.get(skill)
                        if old_values and new_values['level'] > old_values['level']:
                            updates_found = True
                            await ctx.send(f"🎉 **{username}** reached level **{new_values['level']}** in **{skill}**!")
                
                if username not in player_data: player_data[username] = {}
                player_data[username]['stats'] = new_stats
                player_data[username]['last_updated_stats'] = now.isoformat()

            # Check Collection Log for new items
            new_collection_log = await fetch_collection_log(session, username)
            if new_collection_log:
                old_collection_log = player_data.get(username, {}).get('collection_log', [])
                old_item_ids = {item['id'] for item in old_collection_log}
                
                for item in new_collection_log:
                    if item['id'] not in old_item_ids and item['obtainedAt']:
                        obtained_at = datetime.fromisoformat(item['obtainedAt'].replace('Z', '+00:00'))
                        if now - obtained_at <= timedelta(hours=24):
                            updates_found = True
                            await ctx.send(f"🎁 **{username}** received a new collection log item: **{item['name']}**!")

                if username not in player_data: player_data[username] = {}
                player_data[username]['collection_log'] = new_collection_log
                player_data[username]['last_updated_collection'] = now.isoformat()
            
            await asyncio.sleep(1) # Avoid hitting APIs too quickly

    save_player_data(player_data)
    
    if updates_found:
        await m.edit(content="Update check complete.")
    else:
        await m.edit(content="No new updates in the last 24 hours.")

# Main execution
if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE" or not TOKEN:
        print("Please configure your DISCORD_TOKEN in config.json")
    else:
        bot.run(TOKEN)
