import aiohttp
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
import sys

# Add current directory to path to import bot
sys.path.append(os.getcwd())
import bot

async def test_hiscore_tracking():
    print("Initializing test state...")
    test_state = {"players": {}}
    player = "FeWildWarden"
    
    # 1. Initial Sync (Simulate what bot.py does)
    print(f"Applying initial sync for {player} using Hiscores...")
    async with aiohttp.ClientSession() as session:
        if player not in test_state["players"]:
            test_state["players"][player] = {"levels": {}, "last_cl_timestamp": 0}
            print("Detected new player, performing initial sync.")
            
            # Fetch current levels from hiscores
            hiscores_data = await bot.fetch_hiscores(session, player)
            if "levels" in hiscores_data:
                test_state["players"][player]["levels"] = hiscores_data["levels"]
                print(f"Recorded {len(hiscores_data['levels'])} skill levels.")
            else:
                print(f"Error fetching hiscores: {hiscores_data.get('error')}")
                return

    current_overall = test_state['players'][player]['levels'].get('overall')
    print(f"Initial sync state recorded. Overall Level: {current_overall}")
    
    # 2. Simulate a level-up by artificially lowering woodcutting in state
    print("\nSimulating a level-up by artificially lowering a level in the stored state...")
    test_state["players"][player]["levels"]["woodcutting"] = test_state["players"][player]["levels"].get("woodcutting", 99) - 1
    
    # 3. Detect the "new" achievement
    print("Running detection logic...")
    new_achievements = []
    async with aiohttp.ClientSession() as session:
        hiscores_data = await bot.fetch_hiscores(session, player)
        if "levels" in hiscores_data:
            for skill, current_level in hiscores_data["levels"].items():
                old_level = test_state["players"][player]["levels"].get(skill)
                
                if old_level is not None and current_level > old_level:
                    print(f"ACHIEVEMENT DETECTED: {player} reached level {current_level} {skill}!")
                    new_achievements.append({
                        "type": "level",
                        "player": player,
                        "skill": skill,
                        "level": current_level
                    })
    
    if new_achievements:
        print("\nVerification Successful: New achievement detected correctly using Hiscores API.")
    else:
        print("\nVerification Failed: No achievement detected.")

if __name__ == "__main__":
    asyncio.run(test_hiscore_tracking())
