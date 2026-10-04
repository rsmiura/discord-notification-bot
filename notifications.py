"""The shared path for real livestream alerts and /test-live."""

import asyncio
import logging
from dataclasses import dataclass

import discord

from config import Settings
from state import StateStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveStream:
    video_id: str
    title: str
    url: str


def format_live_notification(stream: LiveStream, role_mention: str, twitch_url: str) -> str:
    title = discord.utils.escape_mentions(discord.utils.escape_markdown(stream.title))
    return (
        f"🔔 {role_mention} boop!\n"
        f'Miwi is streaming "**{title}**" '
        f"live on [YouTube]({stream.url}) and "
        f"[Twitch](<{twitch_url}>) ! (,,⟡o⟡,,)"
    )


class LiveNotifier:
    def __init__(self, client: discord.Client, settings: Settings, store: StateStore):
        self.client = client
        self.settings = settings
        self.store = store
        self._lock = asyncio.Lock()

    async def announce(
        self, stream: LiveStream, guild_ids: set[str] | None = None,
        remember: bool = True,
    ) -> int:
        if not self.settings.twitch_stream_url:
            logger.warning("Cannot send live notification: set TWITCH_STREAM_URL")
            return 0
        sent_count = 0
        async with self._lock:
            for guild_id, destination in self.store.destinations().items():
                if guild_ids is not None and guild_id not in guild_ids:
                    continue
                if remember and self.store.was_announced(guild_id, stream.video_id):
                    continue
                guild = self.client.get_guild(int(guild_id))
                if guild is None:
                    continue
                role = guild.get_role(destination["role_id"])
                channel = guild.get_channel_or_thread(destination["channel_id"])
                if role is None or not isinstance(channel, discord.abc.Messageable):
                    logger.warning("Saved role or channel unavailable in guild %s", guild_id)
                    continue
                try:
                    await channel.send(
                        format_live_notification(stream, role.mention, self.settings.twitch_stream_url),
                        allowed_mentions=discord.AllowedMentions(
                            roles=[role], users=False, everyone=False, replied_user=False,
                        ),
                    )
                except discord.HTTPException as error:
                    logger.warning("Discord alert failed in guild %s (HTTP %s)", guild_id, error.status)
                    continue
                sent_count += 1
                if remember:
                    self.store.mark_announced(guild_id, stream.video_id)
        return sent_count

    async def send_test(self, guild_id: int) -> int:
        if not self.settings.youtube_channel_id:
            raise ValueError("Set YOUTUBE_CHANNEL_ID in your .env file before testing.")
        if not self.settings.twitch_stream_url:
            raise ValueError("Set TWITCH_STREAM_URL in your .env file before testing.")
        stream = LiveStream(
            "test-live-notification", "Test livestream notification",
            f"https://www.youtube.com/channel/{self.settings.youtube_channel_id}/live",
        )
        return await self.announce(stream, guild_ids={str(guild_id)}, remember=False)
