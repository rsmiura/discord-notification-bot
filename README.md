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
compose.yaml           # Docker Compose service and persistent state volume
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

## Deployment

For Google Cloud Compute Engine, use an Ubuntu VM with Docker Engine and the
Docker Compose plugin installed. The VM needs outbound internet access; no bot
ports or additional inbound firewall rules are required. Enable Docker at boot:

```sh
sudo systemctl enable --now docker
docker compose version
```

The commands below assume your user can run Docker. Compose builds the existing
Python slim Dockerfile, runs service `bot` as container `discord-bot`, and reads
`.env` at runtime. The image runs as UID 10001. Secrets and runtime files remain
excluded from the build context.

### Initial deployment

If `discord-bot` already exists, use the migration instructions below first.

```sh
git clone https://github.com/rsmiura/discord-notification-bot.git
cd discord-notification-bot
# Create .env only if it does not already exist; never overwrite existing secrets.
(umask 077; test -e .env || cp .env.example .env)
chmod 600 .env
nano .env
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Fill in the real credentials directly on the VM. Never commit `.env`.
Use `config --quiet` for validation: plain `docker compose config` can print
resolved secrets.

The named volume `discord-notification-bot_bot-data` stores role settings and
announcement history at `/data`. Compose overrides `DATA_DIR` to this location.
On a fresh installation, run `/set-role` in Discord. Keep only one bot instance
running to avoid duplicate alerts.

### Future updates and everyday commands

Once these Compose files are committed and pushed to GitHub, update the VM with:

```sh
git pull
docker compose up -d --build
```

```sh
docker compose logs -f       # Follow logs; Ctrl+C only stops following
docker compose ps           # Check status
docker compose restart      # Restart the existing service
docker compose down         # Stop and remove the Compose container/network
```

`up -d` runs in the background. `restart: unless-stopped` restarts the container
after crashes and Docker/VM restarts, unless you explicitly stopped it.
After `down`, run `up -d` to start it again.
Use `up -d --build` after code or environment changes; `restart` does not load
a changed `.env`.

Normal `down` preserves the named volume and host `.env`.
**Do not add `--volumes` or `-v` to `down`: that deletes the saved bot state.**

### Migrate the existing manually created discord-bot container

Run the following in **Bash on the VM**, from the updated repository directory
with your existing `.env` present. This causes a brief outage. It builds first,
discovers the old bot's configured state path without printing secrets, backs
up its JSON files, and retains the old container as `discord-bot-manual-backup`.
Its restart policy is disabled so it cannot start alongside Compose after a reboot.

The preflight checks refuse to overwrite a previous backup container or Compose
volume. If either exists, inspect that deployment before migrating again.

```sh
(
  set -eu
  test -f .env
  docker compose config --quiet
  docker inspect --format '{{.State.Running}}' discord-bot
  if docker container inspect discord-bot-manual-backup >/dev/null 2>&1; then
    echo "Backup container already exists; stop and inspect it first."
    exit 1
  fi
  if docker volume inspect discord-notification-bot_bot-data >/dev/null 2>&1; then
    echo "Compose state volume already exists; stop and inspect it first."
    exit 1
  fi
  docker compose build
  old_data_dir=$(docker exec discord-bot python -c 'from config import load_settings; print(load_settings().data_dir)')
  test -n "$old_data_dir"
  backup_dir=$(mktemp -d "$HOME/discord-bot-state.XXXXXX")
  docker stop discord-bot
  # Missing state files are allowed for a new bot; other copy failures abort.
  for file in role_config.json youtube_state.json; do
    if ! docker cp "discord-bot:$old_data_dir/$file" "$backup_dir/$file" 2>"$backup_dir/copy-error.txt"; then
      if ! grep -q "Could not find the file" "$backup_dir/copy-error.txt"; then
        echo "State backup failed; inspect $backup_dir/copy-error.txt before continuing."
        exit 1
      fi
    fi
  done
  docker rename discord-bot discord-bot-manual-backup
  docker update --restart=no discord-bot-manual-backup
  docker compose create bot
  for file in role_config.json youtube_state.json; do
    if test -f "$backup_dir/$file"; then
      docker cp "$backup_dir/$file" "discord-bot:/data/$file"
    fi
  done
  # docker cp creates root-owned files; give the bot ownership of its new volume.
  docker compose run --rm --no-deps --user root --entrypoint chown bot -R 10001:10001 /data
  docker compose up -d --build
  docker compose ps
  printf 'State backup retained at %s\n' "$backup_dir"
)
docker compose logs -f
```

The old container must be running for the state-path discovery step. If it is
stopped, verify its state location before proceeding. If migration fails, stop
and investigate; do not start both copies. Neither your old container nor its
original volumes nor the backup directory is deleted by this procedure. The
`--rm` above removes only the short-lived ownership helper container.

To roll back after the container has been renamed:

```sh
docker compose down
docker rename discord-bot-manual-backup discord-bot
docker update --restart=unless-stopped discord-bot
docker start discord-bot
```

Rollback uses the old snapshot; alerts sent since migration may repeat. Keep the
backup container until you have verified the new service.

### Local Compose test (PowerShell)

Start Docker Desktop in Linux-container mode and use your existing `.env`.
Run only one instance using the bot token; stop any local Python copy first.
If a manual `discord-bot` container already exists locally, preserve its state
and migrate it rather than attempting to create another container with that name.

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs -f
# Press Ctrl+C to leave log following, then:
docker compose restart
docker compose ps
docker compose down
```

A fresh local Compose volume does not automatically import root-level JSON files.
Use `/set-role` to configure it, or copy the files before startup as in the
migration procedure. `/test-live` will send a real role mention.

See the [Compose service reference](https://docs.docker.com/reference/compose-file/services/)
and [volume retention on down](https://docs.docker.com/reference/cli/docker/compose/down/).
