import aiohttp
import asyncio

async def fetch_hiscores(session, player_name):
    url = f"https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player={player_name}"
    try:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.text()
                first_line = data.split('\n')[0]
                print(f"[{player_name}] First line: {first_line}")
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

async def main():
    PLAYERS = ["Lynx Titan", "Zezima", "Papyrus"]
    async with aiohttp.ClientSession() as session:
        for player in PLAYERS:
            stats = await fetch_hiscores(session, player)
            print(stats)

if __name__ == "__main__":
    asyncio.run(main())
