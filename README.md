# Discord notification bot

A Python bot that connects to Discord, replies to `/ping`, and automatically
pings a configured role when a chosen YouTube channel goes live.

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
   YOUTUBE_API_KEY=your_youtube_data_api_key_here
   YOUTUBE_CHANNEL_ID=your_youtube_channel_id_here
   TWITCH_STREAM_URL=https://www.twitch.tv/your_twitch_channel
   ```

   Keep the token private. The root `.gitignore` already excludes `.env` and
   `.venv`; `.env.example` contains only a placeholder and can be committed.

4. In [Google Cloud Console](https://console.cloud.google.com/), create or
   select a project, enable **YouTube Data API v3**, and create an API key under
   **APIs & Services > Credentials**. Put the key after `YOUTUBE_API_KEY=`.
   Restricting the key to the YouTube Data API is recommended.
5. Find the YouTube channel ID. It normally begins with `UC` and appears in a
   channel URL such as `youtube.com/channel/UC...`. The channel owner can also
   find it under **YouTube Studio > Settings > Channel > Advanced settings**.
   Put the ID after `YOUTUBE_CHANNEL_ID=`.
6. Put the full Twitch channel URL after `TWITCH_STREAM_URL=`. This bot does not
   monitor Twitch yet; it includes the link in each YouTube live alert.
7. In the Discord application's **OAuth2 URL Generator**, select the `bot` and
   `applications.commands` scopes. Give the bot **View Channels** and **Send
   Messages** permissions, open the generated URL, and add it to a server you
   manage. No privileged intents are needed for this step.
8. Start the bot:

   ```powershell
   .\.venv\Scripts\python.exe bot.py
   ```

When it is ready, the terminal prints `Connected to Discord as <bot name>!`.
In your server, select this bot's `/ping` command; it should reply `Pong!`.
In the channel where alerts should appear, run `/set-role` and choose a role
from Discord's role picker. The command is available to members with **Manage
Server** permission. For the alert to notify role members, either make the role
mentionable in its Discord settings or give the bot **Mention @everyone, @here,
and All Roles** permission. Run `/set-role` again whenever you want to change
the role or alert channel. Run `/test-live` to send a simulated alert through
the same notification function used for real streams.

The bot checks YouTube about once a minute. When it sees a live stream, it sends
one alert per configured Discord server and remembers the stream so restarting
the bot does not announce it twice. The message presents YouTube and Twitch as
clickable link labels. Global slash-command changes may take some time to appear
after startup. Keep the terminal running while using the bot; press **Ctrl+C**
to stop it.

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
- **`/set-role`** receives a Discord role and stores both its ID and the current
  channel's ID in `role_config.json`. It confirms the choice without pinging the
  role. The command works only in servers and defaults to members with **Manage
  Server** permission.
- **`/test-live`** creates a simulated livestream and passes it to
  `announce_live_stream()`. It sends only to the current server and does not add
  the test to `youtube_state.json`, so the command can be run repeatedly.
- **`youtube_monitor`** runs once per minute. It asks the YouTube Data API for
  recent upload activity for the configured channel ID, checks those videos for
  an active live broadcast, and calls `announce_live_stream()` when it finds
  one. This avoids the much tighter polling limit associated with YouTube's
  search endpoint.
- **`announce_live_stream()`** sends a message containing the saved role mention,
  stream title, and clickable YouTube and Twitch links. The role mention appears
  once, and `AllowedMentions` permits only that configured role. Sent stream IDs
  are stored per Discord server in `youtube_state.json` to prevent duplicate
  alerts.
- **`main()`** loads `.env` beside `bot.py` using `python-dotenv`, reads
  `DISCORD_TOKEN` using `os.getenv`, checks that it is set, and calls `bot.run`
  to log in and keep the connection running. An existing environment variable
  takes precedence over `.env`. The `if __name__ == "__main__"` guard starts
  the bot only when you run this file directly.
- **`.env.example`** is the shareable configuration template. Your local
  **`.env`** holds the actual Discord token, YouTube API key, YouTube channel ID,
  and Twitch stream URL.
- **`requirements.txt`** lists the dependencies: `discord.py` communicates with
  Discord, `python-dotenv` loads settings from `.env`, and `aiohttp` makes the
  asynchronous YouTube API requests. The version ranges allow compatible
  updates within each major version.
- **`role_config.json`** and **`youtube_state.json`** are created while the bot
  runs. Both contain local runtime state and are ignored by Git.
- **`.gitignore`** already protects the local token file from being added to
  Git and excludes the virtual environment. No change was needed.

The slash-command registration follows the
[discord.py CommandTree documentation](https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.app_commands.CommandTree.sync).
