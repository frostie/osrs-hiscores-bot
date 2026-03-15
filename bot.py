import discord
from discord.ext import commands
import aiohttp
import json
import os

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

    # Sort results: valid entries first (sorted by XP descending), then errors
    results.sort(key=lambda x: (
        0 if "error" not in x else 1,
        -x.get("xp", 0)
    ))

    embed = discord.Embed(title="OSRS Overall Hiscores", color=discord.Color.green())
    
    for i, stat in enumerate(results, start=1):
        if "error" in stat:
            embed.add_field(name=f"{i}. {stat['player']}", value=f"Error: {stat['error']}", inline=False)
        else:
            rank_str = f"{stat['rank']:,}"
            xp_str = f"{stat['xp']:,}"
            value = f"**Level:** {stat['level']}\n**Rank:** {rank_str}\n**XP:** {xp_str}"
            embed.add_field(name=f"{i}. {stat['player']}", value=value, inline=False)

    await m.edit(content=None, embed=embed)

if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE" or not TOKEN:
        print("Please configure your DISCORD_TOKEN in config.json")
    else:
        bot.run(TOKEN)
