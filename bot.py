import discord
from discord.ext import commands
import aiohttp
import json
import os
from datetime import datetime, timedelta, timezone

# Load Configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

TOKEN = config.get("DISCORD_TOKEN")
PLAYERS = config.get("players", [])

# Setup Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def fetch_hiscores(session, player_name):
    """Fetches the overall hiscores for a single player."""
    url = f"https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={player_name}"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.text()
                # The first line is the Overall stats: Rank, Level, XP
                first_line = data.split('\n')[0]
                rank, level, xp = first_line.split(',')
                return {
                    "player": player_name,
                    "rank": int(rank),
                    "level": int(level),
                    "xp": int(xp)
                }
            elif response.status == 404:
                return {"player": player_name, "error": "Player not found."}
            else:
                return {"player": player_name, "error": f"API Error: {response.status}"}
    except Exception as e:
        return {"player": player_name, "error": str(e)}

async def fetch_wom_gains(session, player_name):
    """Fetches skill gains from Wise Old Man for the last 24 hours."""
    url = f"https://api.wiseoldman.net/v2/players/{player_name}/gained?period=day"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
    except Exception:
        pass
    return None

async def fetch_cl_recent_items(session, player_name):
    """Fetches recent collection log items from templeosrs.com."""
    # TempleOSRS is more reliable for recent items with timestamps
    url = f"https://templeosrs.com/api/collection-log/player_recent_items.php?player={player_name}&count=25"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
    except Exception:
        pass
    return None

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

@bot.command(name='hiscores')
async def hiscores_command(ctx):
    if not PLAYERS:
        await ctx.send("No players are currently configured to be tracked.")
        return

    m = await ctx.send(f"Fetching hiscores for {len(PLAYERS)} players...")

    results = []
    async with aiohttp.ClientSession() as session:
        for player in PLAYERS:
            stats = await fetch_hiscores(session, player)
            results.append(stats)

    # Sort results: valid entries first (sorted by Level descending), then errors
    results.sort(key=lambda x: (
        0 if "error" not in x else 1,
        -x.get("level", 0)
    ))

    embed = discord.Embed(title="OSRS Googlers Overall Hiscores", color=discord.Color.green())
    
    for i, stat in enumerate(results, start=1):
        if "error" in stat:
            embed.add_field(name=f"{i}. {stat['player']}", value=f"Error: {stat['error']}", inline=False)
        else:
            rank_str = f"{stat['rank']:,}"
            xp_str = f"{stat['xp']:,}"
            value = f"**Level:** {stat['level']}\n**Rank:** {rank_str}\n**XP:** {xp_str}"
            embed.add_field(name=f"{i}. {stat['player']}", value=value, inline=False)

    await m.edit(content=None, embed=embed)

@bot.command(name='updates')
async def updates_command(ctx):
    if not PLAYERS:
        await ctx.send("No players are currently configured to be tracked.")
        return

    m = await ctx.send(f"Checking for updates for {len(PLAYERS)} players from the last 24 hours...")
    
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    all_updates = []

    async with aiohttp.ClientSession() as session:
        for player in PLAYERS:
            # 1. Level ups from WOM
            wom_data = await fetch_wom_gains(session, player)
            if wom_data and 'data' in wom_data:
                data_obj = wom_data['data']
                if 'skills' in data_obj:
                    for skill, skill_data in data_obj['skills'].items():
                        if skill_data.get('level', {}).get('gained', 0) > 0:
                            level = skill_data['level']['end']
                            # WOM '/gained' response includes startsAt/endsAt
                            timestamp_str = wom_data.get('endsAt')
                            if timestamp_str:
                                ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            else:
                                ts = now
                            
                            all_updates.append({
                                "type": "level",
                                "player": player,
                                "skill": skill,
                                "level": level,
                                "timestamp": ts
                            })

            # 2. Collection Log items from TempleOSRS
            cl_data = await fetch_cl_recent_items(session, player)
            # Temple response is usually a list under 'data' or directly a list
            items_list = []
            if isinstance(cl_data, list):
                items_list = cl_data
            elif isinstance(cl_data, dict) and 'data' in cl_data:
                items_list = cl_data['data']
            
            for item in items_list:
                # Temple returns 'date_unix'
                date_unix = item.get('date_unix')
                if date_unix:
                    ts = datetime.fromtimestamp(int(date_unix), tz=timezone.utc)
                    if ts >= cutoff:
                        all_updates.append({
                            "type": "cl",
                            "player": player,
                            "item": item.get('item_name', item.get('name', 'Unknown Item')),
                            "timestamp": ts
                        })

    if not all_updates:
        await m.edit(content="No updates found for the last 24 hours.")
        return

    # Sort all updates by timestamp
    all_updates.sort(key=lambda x: x['timestamp'])

    output_lines = []
    for up in all_updates:
        # Format: 3/18/26 7:26 AM
        # astimezone() converts to local time of the bot
        ts_str = up['timestamp'].astimezone().strftime("%#m/%#d/%y, %#I:%M %p")
        if up['type'] == "level":
            output_lines.append(f"{up['player']} reached level {up['level']} {up['skill']}! {ts_str}")
        else:
            output_lines.append(f"{up['player']} received a new collection log item: {up['item']}! {ts_str}")

    await m.edit(content="\n".join(output_lines))

if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE" or not TOKEN:
        print("Please configure your DISCORD_TOKEN in config.json")
    else:
        bot.run(TOKEN)
