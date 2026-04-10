import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time


# Load Configuration & State
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
STATE_PATH = os.path.join(os.path.dirname(__file__), 'state.json')
WEEKLY_STATE_PATH = os.path.join(os.path.dirname(__file__), 'weekly_state.json')

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

config = load_json(CONFIG_PATH)
state = load_json(STATE_PATH)

TOKEN = config.get("DISCORD_TOKEN")
PLAYERS = config.get("players", [])
AUTO_UPDATE_CHANNEL_ID = config.get("AUTO_UPDATE_CHANNEL_ID")
WEEKLY_CHANNEL_ID = config.get("WEEKLY_CHANNEL_ID")
POLLING_INTERVAL_MINUTES = config.get("POLLING_INTERVAL_MINUTES", 5)

# OSRS Skill List in Hiscores Order
OSRS_SKILLS = [
    "Overall", "Attack", "Defence", "Strength", "Hitpoints", "Ranged", "Prayer", "Magic",
    "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking", "Crafting", "Smithing",
    "Mining", "Herblore", "Agility", "Thieving", "Slayer", "Farming", "Runecraft",
    "Hunter", "Construction"
]

# Setup Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def fetch_hiscores(session, player_name):
    """Fetches all skill levels and stats for a player from official Hiscores."""
    url = f"https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={player_name}"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.text()
                lines = data.split('\n')
                stats = {"player": player_name, "levels": {}}
                
                # First line is Overall
                if lines[0]:
                    overall_parts = lines[0].split(',')
                    stats["rank"] = int(overall_parts[0])
                    stats["level"] = int(overall_parts[1])
                    stats["xp"] = int(overall_parts[2])
                
                # Parse all skills (level and xp)
                stats["xp_per_skill"] = {}
                for i, skill in enumerate(OSRS_SKILLS):
                    if i < len(lines) and lines[i]:
                        parts = lines[i].split(',')
                        if len(parts) >= 3:
                            stats["levels"][skill.lower()] = int(parts[1])
                            stats["xp_per_skill"][skill.lower()] = int(parts[2])
                        elif len(parts) >= 2:
                            stats["levels"][skill.lower()] = int(parts[1])
                
                return stats
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
    if not auto_updates.is_running():
        auto_updates.start()
    if not weekly_auto_update.is_running():
        weekly_auto_update.start()
    if not weekly_snapshot_reset.is_running():
        weekly_snapshot_reset.start()
    # Take initial weekly snapshot if none exists (for future week tracking)
    weekly_state = load_json(WEEKLY_STATE_PATH)
    if not weekly_state.get("snapshot"):
        await take_weekly_snapshot()

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

async def get_updates_data(session, players):
    """Fetches and returns updates for the given players from the last 24 hours."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    all_updates = []

    for player in players:
        # 1. Level ups from WOM
        wom_data = await fetch_wom_gains(session, player)
        if wom_data and isinstance(wom_data, dict) and 'data' in wom_data:
            data_obj = wom_data['data']
            if isinstance(data_obj, dict) and 'skills' in data_obj:
                for skill, skill_data in data_obj['skills'].items():
                    if skill_data.get('level', {}).get('gained', 0) > 0:
                        level = skill_data['level']['end']
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
        items_list = []
        if isinstance(cl_data, list):
            items_list = cl_data
        elif isinstance(cl_data, dict) and 'data' in cl_data:
            items_list = cl_data['data']
        
        for item in items_list:
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

    # Sort all updates by timestamp
    all_updates.sort(key=lambda x: x['timestamp'])
    return all_updates

def create_update_embed(up):
    """Creates a styled Discord Embed for a single update."""
    # astimezone() converts to local time of the bot
    ts_str = up['timestamp'].astimezone().strftime("%#m/%#d/%y, %#I:%M %p")
    
    if up['type'] == "level":
        embed = discord.Embed(
            title="Level Up!",
            description=f"**{up['player']}** reached level **{up['level']} {up['skill']}**!",
            color=discord.Color.green(),
            timestamp=up['timestamp']
        )
    else:
        embed = discord.Embed(
            title="New Collection Log Item!",
            description=f"**{up['player']}** received a new item: **{up['item']}**!",
            color=discord.Color.gold(),
            timestamp=up['timestamp']
        )
    
    embed.set_footer(text=f"Time: {ts_str}")
    return embed

@bot.command(name='updates')
async def updates_command(ctx):
    if not PLAYERS:
        await ctx.send("No players are currently configured to be tracked.")
        return

    m = await ctx.send(f"Checking for updates for {len(PLAYERS)} players from the last 24 hours...")
    
    async with aiohttp.ClientSession() as session:
        updates = await get_updates_data(session, PLAYERS)
    
    if not updates:
        await m.edit(content="No updates found for the last 24 hours.")
        return

    await m.delete()
    for up in updates:
        embed = create_update_embed(up)
        await ctx.send(embed=embed)

async def take_weekly_snapshot():
    """Takes a snapshot of all players' current hiscores and saves it as the weekly baseline."""
    weekly_state = load_json(WEEKLY_STATE_PATH)
    snapshot = {}

    async with aiohttp.ClientSession() as session:
        for player in PLAYERS:
            stats = await fetch_hiscores(session, player)
            if "error" not in stats:
                snapshot[player] = {
                    "total_level": stats.get("level", 0),
                    "total_xp": stats.get("xp", 0),
                    "levels": stats.get("levels", {}),
                    "xp_per_skill": stats.get("xp_per_skill", {})
                }

    weekly_state["snapshot"] = snapshot
    weekly_state["snapshot_taken_at"] = datetime.now(timezone.utc).isoformat()
    save_json(WEEKLY_STATE_PATH, weekly_state)
    print(f"Weekly snapshot taken at {weekly_state['snapshot_taken_at']} for {len(snapshot)} players.")

async def build_weekly_embed():
    """Builds the weekly gains leaderboard by comparing current OSRS hiscores against the stored snapshot."""
    weekly_state = load_json(WEEKLY_STATE_PATH)
    snapshot = weekly_state.get("snapshot", {})

    if not snapshot:
        return None

    player_gains = []

    async with aiohttp.ClientSession() as session:
        for player in PLAYERS:
            if player not in snapshot:
                continue

            stats = await fetch_hiscores(session, player)
            if "error" in stats:
                continue

            baseline = snapshot[player]
            xp_gained = stats.get("xp", 0) - baseline.get("total_xp", 0)

            # Calculate total levels gained across individual skills
            current_levels = stats.get("levels", {})
            baseline_levels = baseline.get("levels", {})
            levels_gained = 0
            for skill, current_lvl in current_levels.items():
                if skill == "overall":
                    continue
                old_lvl = baseline_levels.get(skill, 0)
                diff = current_lvl - old_lvl
                if diff > 0:
                    levels_gained += diff

            if xp_gained >= 1:
                player_gains.append({
                    "player": player,
                    "xp_gained": xp_gained,
                    "levels_gained": levels_gained
                })

    # Sort by total XP earned descending (primary), then levels descending (secondary)
    player_gains.sort(key=lambda x: (-x['xp_gained'], -x['levels_gained']))

    if not player_gains:
        return None

    embed = discord.Embed(
        title="\U0001f4c5 Weekly Gains Leaderboard",
        description="Total levels and XP earned this week",
        color=discord.Color.blue()
    )

    for i, pg in enumerate(player_gains, start=1):
        xp_str = f"{pg['xp_gained']:,}"
        value = f"Total XP earned: {xp_str}\nTotal levels earned: {pg['levels_gained']}"
        embed.add_field(name=f"{i}. {pg['player']}", value=value, inline=False)

    embed.set_footer(text=f"Updated: {datetime.now(timezone.utc).strftime('%m/%d/%Y %H:%M UTC')}")
    return embed

@bot.command(name='weekly')
async def weekly_command(ctx):
    """Shows the weekly gains leaderboard on demand."""
    if not PLAYERS:
        await ctx.send("No players are currently configured to be tracked.")
        return

    m = await ctx.send(f"Fetching weekly gains for {len(PLAYERS)} players...")
    embed = await build_weekly_embed()

    if embed is None:
        await m.edit(content="No players earned any XP this week.")
        return

    await m.edit(content=None, embed=embed)

@tasks.loop(hours=24)
async def weekly_auto_update():
    """Posts the weekly gains leaderboard to the configured channel once per day."""
    if not WEEKLY_CHANNEL_ID or WEEKLY_CHANNEL_ID in ["YOUR_CHANNEL_ID_HERE", "PLACEHOLDER"]:
        return

    try:
        channel_id = int(str(WEEKLY_CHANNEL_ID).split("/")[-1])
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = await bot.fetch_channel(channel_id)
        if not channel:
            return

        embed = await build_weekly_embed()
        if embed:
            await channel.send(embed=embed)
    except Exception as e:
        print(f"Error in weekly_auto_update task: {e}")

# EDT timezone (UTC-4) for scheduling
EASTERN_TZ = timezone(timedelta(hours=-4))

@tasks.loop(time=dt_time(hour=0, minute=0, tzinfo=EASTERN_TZ))
async def weekly_snapshot_reset():
    """Resets the weekly snapshot every Monday at 12:00 AM Eastern."""
    now = datetime.now(EASTERN_TZ)
    if now.weekday() == 0:  # Monday
        await take_weekly_snapshot()

@weekly_snapshot_reset.before_loop
async def before_weekly_snapshot_reset():
    await bot.wait_until_ready()

@weekly_auto_update.before_loop
async def before_weekly_auto_update():
    await bot.wait_until_ready()

@tasks.loop(minutes=POLLING_INTERVAL_MINUTES)
async def auto_updates():
    if not AUTO_UPDATE_CHANNEL_ID or AUTO_UPDATE_CHANNEL_ID in ["YOUR_CHANNEL_ID_HERE", "PLACEHOLDER"]:
        return

    try:
        channel_id = int(str(AUTO_UPDATE_CHANNEL_ID).split("/")[-1])
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = await bot.fetch_channel(channel_id)
        
        if not channel:
            return

        async with aiohttp.ClientSession() as session:
            for player in PLAYERS:
                if player not in state["players"]:
                    state["players"][player] = {"levels": {}, "last_cl_timestamp": 0}
                    initial_sync = True
                else:
                    initial_sync = False
                
                player_state = state["players"][player]
                new_achievements = []

                # 1. Check Official Hiscores for levels
                hiscores_data = await fetch_hiscores(session, player)
                if "levels" in hiscores_data:
                    for skill, current_level in hiscores_data["levels"].items():
                        old_level = player_state["levels"].get(skill)
                        
                        # Update state
                        player_state["levels"][skill] = current_level
                        
                        # Detect level up
                        if old_level is not None and current_level > old_level:
                            new_achievements.append({
                                "type": "level",
                                "player": player,
                                "skill": skill.capitalize(),
                                "level": current_level,
                                "timestamp": datetime.now(timezone.utc)
                            })

                # 2. Check Temple for CL items
                cl_data = await fetch_cl_recent_items(session, player)
                items_list = []
                if isinstance(cl_data, list):
                    items_list = cl_data
                elif isinstance(cl_data, dict) and 'data' in cl_data:
                    items_list = cl_data['data']
                
                max_ts = player_state.get("last_cl_timestamp", 0)
                new_max_ts = max_ts
                
                # Temple items are returned most recent first
                for item in items_list:
                    date_unix = int(item.get('date_unix', 0))
                    if date_unix > max_ts:
                        if not initial_sync:
                            new_achievements.append({
                                "type": "cl",
                                "player": player,
                                "item": item.get('item_name', item.get('name', 'Unknown Item')),
                                "timestamp": datetime.fromtimestamp(date_unix, tz=timezone.utc)
                            })
                        if date_unix > new_max_ts:
                            new_max_ts = date_unix
                
                player_state["last_cl_timestamp"] = new_max_ts

                # Post new achievements (if not initial sync)
                if not initial_sync:
                    # Sort achievements by timestamp before posting if multiple found
                    new_achievements.sort(key=lambda x: x['timestamp'])
                    for ach in new_achievements:
                        embed = create_update_embed(ach)
                        await channel.send(embed=embed)
            
            # Save state after processing all players
            save_json(STATE_PATH, state)

    except Exception as e:
        print(f"Error in auto_updates task: {e}")

if __name__ == "__main__":
    if TOKEN == "YOUR_BOT_TOKEN_HERE" or not TOKEN:
        print("Please configure your DISCORD_TOKEN in config.json")
    else:
        bot.run(TOKEN)
