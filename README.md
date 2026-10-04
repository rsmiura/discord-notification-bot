# Discord notification bot

Step 1: a minimal Python bot that connects to Discord and replies to `/ping`
with `Pong!`. No notification integrations are implemented yet.

## Setup (Windows PowerShell)

Run these commands from the project folder. If `.venv` already exists, skip
the first command. Calling its Python directly avoids needing to activate it.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

1. Open the [Discord Developer Portal](https://discord.com/developers/applications)
   and create an application for this bot.
2. On its **Bot** page, obtain the bot token (reset it if needed).
3. Copy the template below, then edit `.env` and replace the placeholder with
   your token. Skip the copy command if you already have a `.env` file.

   ```powershell
   Copy-Item .env.example .env
   ```

   ```dotenv
   DISCORD_TOKEN=your_discord_bot_token_here
   ```

   Keep the token private. The root `.gitignore` already excludes `.env` and
   `.venv`; `.env.example` contains only a placeholder and can be committed.

4. In the application's **OAuth2 URL Generator**, select the `bot` and
   `applications.commands` scopes. Give the bot **View Channels** and **Send
   Messages** permissions, open the generated URL, and add it to a server you
   manage. No privileged intents are needed for this step.
5. Start the bot:

   ```powershell
   .\.venv\Scripts\python.exe bot.py
   ```

When it is ready, the terminal prints `Connected to Discord as <bot name>!`.
In your server, select this bot's `/ping` command; it should reply `Pong!`.
Global slash commands may take some time to appear after the first startup.
Keep the terminal running while using the bot; press **Ctrl+C** to stop it.

## How the files and code work

- **`bot.py`** contains the entire bot. `NotificationBot` extends
  `discord.Client`, which manages the Discord connection. Its `CommandTree`
  stores slash commands, and `setup_hook()` calls `sync()` to register them
  with Discord during startup. `on_ready()` runs when the connection is ready
  and prints the success message; it may run again after a reconnect.
- **`@bot.tree.command(...)`** registers the `ping` function as `/ping`.
  Discord passes an `interaction` representing the command invocation.
  `interaction.response.send_message("Pong!")` sends the reply.
  `async` and `await` let the bot wait for network operations without blocking
  other events.
- **`main()`** loads `.env` beside `bot.py` using `python-dotenv`, reads
  `DISCORD_TOKEN` using `os.getenv`, checks that it is set, and calls `bot.run`
  to log in and keep the connection running. An existing environment variable
  takes precedence over `.env`. The `if __name__ == "__main__"` guard starts
  the bot only when you run this file directly.
- **`.env.example`** is the shareable configuration template. Your local
  **`.env`** holds the actual token.
- **`requirements.txt`** lists the two dependencies: `discord.py` communicates
  with Discord, and `python-dotenv` loads environment settings from `.env`.
  The version ranges allow compatible updates within each major version.
- **`.gitignore`** already protects the local token file from being added to
  Git and excludes the virtual environment. No change was needed.

The slash-command registration follows the
[discord.py CommandTree documentation](https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.app_commands.CommandTree.sync).
