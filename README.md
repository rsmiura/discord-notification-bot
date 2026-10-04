# Discord notification bot

A small Python bot that watches one YouTube channel and sends livestream alerts
to configured Discord servers. Each alert mentions the chosen role once and
includes clickable YouTube and Twitch links.

## Features

- `/ping` responds with `Pong!`.
- `/set-role` chooses the livestream role and uses the current channel for alerts.
- `/test-live` sends a simulated alert through the same service as real streams.
- YouTube is checked every 60 seconds using the official YouTube Data API v3.
- The latest 100 announced stream IDs are remembered per Discord server.
- Configuration, commands, notifications, API polling, and storage have separate modules.

Twitch is a link in the alert, not a separate live detector. X/Twitter integration
is not implemented and requires no credentials.

## Project structure

```text
bot.py                 # Entry point, Discord connection, startup and shutdown
commands.py            # /ping, /set-role, /test-live
config.py              # Environment loading and settings
notifications.py       # Shared alert formatting and delivery
state.py               # Validated JSON storage and atomic file replacement
monitors/
    __init__.py
    youtube.py         # YouTube requests and background polling
tests/
    test_bot.py        # Offline regression tests
.env.example           # Configuration template (no credentials)
requirements.txt
Dockerfile
.dockerignore
```

Runtime files are ignored by Git: `role_config.json` holds the role/channel for
each server, and `youtube_state.json` remembers announced streams.

## Requirements and external APIs

- Python 3.12 or newer; Docker uses Python 3.12.
- A Discord application and bot token.
- For automatic monitoring: a YouTube Data API v3 key, the actual YouTube channel
  ID (starting with `UC`), and a Twitch channel URL.
- Outbound internet access to Discord and Google's YouTube API.

Dependencies are `discord.py`, `python-dotenv`, and `aiohttp`. The tests use
Python's built-in `unittest` and make no live API requests.

## Setup

Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
Obtain its token on the Bot page. Invite it to your server using the `bot` and
`applications.commands` scopes. Grant **View Channels**, **Send Messages**, and
**Embed Links** in the destination channel. No privileged gateway intents are needed.

For a role ping to notify members, make the role mentionable or grant the bot
**Mention @everyone, @here, and All Roles**. The two configuration/test commands
default to members with **Manage Server**; server administrators can customize
application command permissions in Discord.

Enable **YouTube Data API v3** in a Google Cloud project and create an API key.
Restrict that key to the YouTube Data API. See the
[official setup guide](https://developers.google.com/youtube/v3/getting-started).
Use a channel ID, not a handle or URL; a channel URL in the form
`youtube.com/channel/UC...` contains the ID.

### Windows PowerShell

Run from the project directory. Skip creating the virtual environment if it
already exists.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you do not already have a `.env` file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally. Keep your existing file when upgrading.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `DISCORD_TOKEN` | Required bot token. Never share or commit it. |
| `YOUTUBE_API_KEY` | API key for YouTube Data API v3. |
| `YOUTUBE_CHANNEL_ID` | Actual channel ID; handle conversion is not supported. |
| `TWITCH_STREAM_URL` | Full Twitch channel URL included in each alert. |
| `DATA_DIR` | Optional state directory. Defaults to the project directory locally and `/data` in Docker. |

All three monitoring values must be set to enable YouTube polling. Without
them the bot still connects and `/ping` works; startup logs name the missing
settings. `/test-live` needs the channel ID and Twitch URL but does not call
YouTube. Example placeholders are treated as missing values.

Settings load once at startup from the `.env` beside `bot.py`. Existing process
environment variables take precedence. Relative `DATA_DIR` paths resolve from
the project directory. Restart the bot after editing settings.

## Run locally

Windows:

```powershell
.\.venv\Scripts\python.exe bot.py
```

Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python bot.py
```

Wait for the connected message in the terminal. In Discord, run `/set-role`
in the desired alert channel, select the role, then run `/test-live`. The test
really mentions that role and can be repeated; it does not change the saved
stream history. Global command updates can take time to appear.

The notification text and clickable link formatting are kept in
`format_live_notification()` in `notifications.py`. Both real streams and
tests call `LiveNotifier.announce()`.

Press **Ctrl+C** to stop locally. Linux/Docker SIGTERM also closes the polling
task, HTTP session, and Discord connection.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

On Linux use `.venv/bin/python` in place of the Windows executable.

Tests cover configuration, the exact notification text, role mention restrictions,
state compatibility and restart deduplication, failed delivery retries,
concurrent delivery, the three slash commands, live-video filtering, API failure
recovery, sanitized errors, and HTTP-session cleanup. They use temporary state
directories and never read your real `.env`.

## State and reliability

Existing root-level JSON files retain their names and formats; upgrading does
not require migration. State is loaded at startup and updated by the bot.
Restart after manually editing a state file. To change `DATA_DIR`, stop the bot
and copy both existing JSON files into that directory first.

JSON saves use a temporary file and atomic replacement. Malformed or unreadable
state causes a clear startup error instead of silently forgetting announcements;
repair the file or restore a backup. Missing files are treated as a new setup.

Temporary YouTube/network errors are logged without API keys and retried on the
next poll. Discord send failures do not mark a stream as announced. A successful
alert is saved immediately for that server.

Run one bot instance against a given state directory. JSON state cannot make the
Discord send and disk write one transaction: a crash between them, a disk failure,
or deleting the state file can still cause a repeat after restart. Keep backups.

The existing detector checks the latest 50 activity entries for active videos.
It is not a guaranteed real-time feed: YouTube indexing delays or absent activity
entries can delay or miss alerts. An already-live, previously unannounced stream
may be announced at startup. This refactor keeps that detection behavior.

## Docker / Linux deployment

The image uses an official Python slim base and runs as an unprivileged user.
Only application files are copied; `.env`, Git history, runtime JSON, virtual
environments, and tests are excluded from the build context. Secrets are supplied
at runtime. No incoming ports need to be published.

From the repository directory:

```sh
docker build -t discord-notification-bot .
docker volume create discord-bot-data
docker run -d --name discord-notification-bot --restart unless-stopped --env-file .env -e DATA_DIR=/data -v discord-bot-data:/data discord-notification-bot
docker logs -f discord-notification-bot
```

A new volume starts with no role settings or stream history. Run `/set-role` to
configure a new installation. To preserve existing state instead, stop the local
bot, create the named volume, then copy the existing files before the first run:

```sh
docker create --name discord-bot-state --user root -v discord-bot-data:/data discord-notification-bot
docker cp role_config.json discord-bot-state:/data/role_config.json
# Only if this file exists:
docker cp youtube_state.json discord-bot-state:/data/youtube_state.json
docker rm discord-bot-state
docker run --rm --user root -v discord-bot-data:/data --entrypoint chown discord-notification-bot -R 10001:10001 /data
```

These commands copy files; they do not delete your local originals. If using a
Linux bind mount instead, its directory must be writable by UID 10001.
Preserve the volume when replacing the container. Use `docker stop
discord-notification-bot` for a clean shutdown. Avoid running the local bot and
container simultaneously.

The container layout follows
[Docker's build guidance](https://docs.docker.com/build/building/best-practices/);
background polling uses
[discord.py task helpers](https://discordpy.readthedocs.io/en/stable/ext/tasks/index.html).
