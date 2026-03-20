# osrs-hiscores-bot
A Discord bot that displays OSRS overall hiscores of specific players when commanded to with `!hiscores` command, and 24 hour updates with the `!updates` command.

## How to configure the bot

1. Create and authorize your bot to join your Discord server. [Read more about creating Discord bots](https://docs.discord.com/developers/platform/bots).
1. Add your bot's Discord token to `DISCORD_TOKEN` in `config.json`.
2. Add the player names to `config.json`.
3. In a Powershell terminal, `cd` to your project folder `PATH` and run `python bot.py`. This runs the bot and allows you to invoke the `!hiscores` command in Discord. If this terminal is closed, the bot won't work.
4. In one of the channels of your Discord server, enter the message `!hiscores`. This invokes the bot to display the hiscores of all the players specified in `config.json`. They will be listed in order from highest to lowest, with numbers next to their names.

