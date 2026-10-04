import json
import os
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv


ROLE_CONFIG_PATH = Path(__file__).with_name("role_config.json")
YOUTUBE_STATE_PATH = Path(__file__).with_name("youtube_state.json")
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"


def load_role_config():
    if not ROLE_CONFIG_PATH.exists():
        return {}

    try:
        return json.loads(ROLE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_role_config(config):
    ROLE_CONFIG_PATH.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )


def load_youtube_state():
    if not YOUTUBE_STATE_PATH.exists():
        return {}

    try:
        return json.loads(YOUTUBE_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_youtube_state(state):
    YOUTUBE_STATE_PATH.write_text(
        json.dumps(state, indent=2) + "\n",
        encoding="utf-8",
    )


class NotificationBot(discord.Client):
    def __init__(self):
        # Slash commands do not need the privileged Message Content intent.
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Publish the slash commands to Discord once during startup.
        synced = await self.tree.sync()
        print(f"Synced {len(synced)} command(s): {synced}")

        if (
            os.getenv("YOUTUBE_API_KEY")
            and os.getenv("YOUTUBE_CHANNEL_ID")
            and os.getenv("TWITCH_STREAM_URL")
        ):
            self.youtube_monitor.start()
        else:
            print(
                "YouTube monitoring is disabled. Set YOUTUBE_API_KEY, "
                "YOUTUBE_CHANNEL_ID, and TWITCH_STREAM_URL in .env to enable it."
            )

    async def on_ready(self):
        print(f"Connected to Discord as {self.user}!", flush=True)

    async def fetch_live_youtube_streams(self):
        api_key = os.environ["YOUTUBE_API_KEY"]
        channel_id = os.environ["YOUTUBE_CHANNEL_ID"]

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{YOUTUBE_API_URL}/activities",
                params={
                    "part": "contentDetails",
                    "channelId": channel_id,
                    "maxResults": 50,
                    "key": api_key,
                },
            ) as response:
                response.raise_for_status()
                activities = await response.json()

            video_ids = [
                item["contentDetails"]["upload"]["videoId"]
                for item in activities.get("items", [])
                if "upload" in item.get("contentDetails", {})
            ]
            if not video_ids:
                return []

            async with session.get(
                f"{YOUTUBE_API_URL}/videos",
                params={
                    "part": "snippet,liveStreamingDetails",
                    "id": ",".join(video_ids),
                    "key": api_key,
                },
            ) as response:
                response.raise_for_status()
                videos = await response.json()

        return [
            video
            for video in videos.get("items", [])
            if video.get("snippet", {}).get("liveBroadcastContent") == "live"
        ]

    async def announce_live_stream(self, video, guild_ids=None, remember=True):
        config = load_role_config()
        state = load_youtube_state() if remember else {}
        changed = False
        sent_count = 0

        video_id = video["id"]
        title = discord.utils.escape_mentions(
            discord.utils.escape_markdown(video["snippet"]["title"])
        )
        youtube_url = video.get(
            "url",
            f"https://www.youtube.com/watch?v={video_id}",
        )
        twitch_url = os.environ.get("TWITCH_STREAM_URL", "").strip().strip("<>")
        if not twitch_url:
            print("Could not send live notification: TWITCH_STREAM_URL is not set")
            return 0

        for guild_id, settings in config.items():
            if guild_ids is not None and guild_id not in guild_ids:
                continue

            if not isinstance(settings, dict):
                continue

            announced_ids = state.setdefault(guild_id, [])
            if remember and video_id in announced_ids:
                continue

            guild = self.get_guild(int(guild_id))
            if guild is None:
                continue

            role = guild.get_role(settings.get("role_id"))
            channel = guild.get_channel(settings.get("channel_id"))
            if role is None or channel is None:
                continue

            try:
                await channel.send(
                    f"🔔 {role.mention} boop!\n"
                    f"Miwi is streaming \"**{title}**\"\nlive on "
                    f"[YouTube]({youtube_url}) and "
                    f"[Twitch](<{twitch_url}>) ! (,,⟡o⟡,,)",
                    allowed_mentions=discord.AllowedMentions(
                        roles=[role],
                        users=False,
                        everyone=False,
                        replied_user=False,
                    ),
                )
            except discord.HTTPException as error:
                print(f"Could not send YouTube notification in {guild}: {error}")
                continue

            sent_count += 1
            if remember:
                announced_ids.append(video_id)
                state[guild_id] = announced_ids[-100:]
                changed = True

        if changed:
            save_youtube_state(state)

        return sent_count

    @tasks.loop(seconds=60)
    async def youtube_monitor(self):
        try:
            live_streams = await self.fetch_live_youtube_streams()
            for video in live_streams:
                await self.announce_live_stream(video)
        except (aiohttp.ClientError, KeyError, ValueError) as error:
            print(f"Could not check YouTube: {error}")

    @youtube_monitor.before_loop
    async def before_youtube_monitor(self):
        await self.wait_until_ready()


bot = NotificationBot()


@bot.tree.command(name="ping", description="Check whether the bot is responding.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")


@bot.tree.command(name="set-role", description="Choose the role used for notifications.")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(role="The role to ping for notifications")
async def set_role(interaction: discord.Interaction, role: discord.Role):
    if role.is_default():
        await interaction.response.send_message(
            "Choose a role other than @everyone.",
            ephemeral=True,
        )
        return

    config = load_role_config()
    config[str(interaction.guild_id)] = {
        "role_id": role.id,
        "channel_id": interaction.channel_id,
    }
    save_role_config(config)

    await interaction.response.send_message(
        f"Notification role set to {role.mention}. Live alerts will be sent "
        "in this channel.",
        allowed_mentions=discord.AllowedMentions.none(),
        ephemeral=True,
    )


@bot.tree.command(name="test-live", description="Send a test livestream notification.")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def test_live(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
    if not channel_id:
        await interaction.followup.send(
            "Set YOUTUBE_CHANNEL_ID in your .env file before testing.",
            ephemeral=True,
        )
        return

    if not os.environ.get("TWITCH_STREAM_URL", "").strip().strip("<>"):
        await interaction.followup.send(
            "Set TWITCH_STREAM_URL in your .env file before testing.",
            ephemeral=True,
        )
        return

    test_video = {
        "id": "test-live-notification",
        "snippet": {"title": "Test livestream notification"},
        "url": f"https://www.youtube.com/channel/{channel_id}/live",
    }
    sent_count = await bot.announce_live_stream(
        test_video,
        guild_ids={str(interaction.guild_id)},
        remember=False,
    )

    if sent_count:
        await interaction.followup.send(
            "Test notification sent using the live notification function.",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            "I could not send the test. Run `/set-role` in the alert channel first.",
            ephemeral=True,
        )


def main():
    # Find .env beside this file, even when run from another directory.
    load_dotenv(Path(__file__).with_name(".env"))
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "your_discord_bot_token_here":
        raise SystemExit("Set DISCORD_TOKEN in your .env file before running the bot.")

    bot.run(token)


if __name__ == "__main__":
    main()
