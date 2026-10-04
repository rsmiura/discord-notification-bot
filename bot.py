import os
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv


class NotificationBot(discord.Client):
    def __init__(self):
        # Slash commands do not need the privileged Message Content intent.
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Publish the slash commands to Discord once during startup.
        synced = await self.tree.sync()
        print(f"Synced {len(synced)} command(s): {synced}")

    async def on_ready(self):
        print(f"Connected to Discord as {self.user}!", flush=True)


bot = NotificationBot()


@bot.tree.command(name="ping", description="Check whether the bot is responding.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")


def main():
    # Find .env beside this file, even when run from another directory.
    load_dotenv(Path(__file__).with_name(".env"))
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "your_discord_bot_token_here":
        raise SystemExit("Set DISCORD_TOKEN in your .env file before running the bot.")

    bot.run(token)


if __name__ == "__main__":
    main()
