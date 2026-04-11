import aiohttp
import asyncio
import json
from datetime import datetime, timedelta, timezone

PLAYERS = ["Papyrus", "Renzo"]

async def fetch_wom_gains(session, player_name):
    url = f"https://api.wiseoldman.net/v2/players/{player_name}/gained?period=day"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        print(f"WOM Error for {player_name}: {e}")
    return None

async def fetch_cl_recent_items(session, player_name):
    url = f"https://templeosrs.com/api/collection-log/player_recent_items.php?player={player_name}&count=25"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        print(f"CL Error for {player_name}: {e}")
    return None

async def test_updates():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    all_updates = []

    async with aiohttp.ClientSession() as session:
        for player in PLAYERS:
            # 1. Level ups from WOM
            print(f"Checking WOM for {player}...")
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

            # 2. Collection Log items
            print(f"Checking CL (Temple) for {player}...")
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

    if not all_updates:
        print("No updates found for the last 24 hours.")
        return

    all_updates.sort(key=lambda x: x['timestamp'])

    for up in all_updates:
        # Using a safer strftime for test
        ts_str = up['timestamp'].strftime("%m/%d/%y %I:%M %p")
        if up['type'] == "level":
            print(f"{up['player']} reached level {up['level']} {up['skill']}! {ts_str}")
        else:
            print(f"{up['player']} received a new collection log item: {up['item']}! {ts_str}")

if __name__ == "__main__":
    asyncio.run(test_updates())
