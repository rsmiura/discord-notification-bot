"""Poll recent YouTube activity using the official Data API."""

import asyncio
import logging
from typing import Any

import aiohttp
import discord
from discord.ext import tasks

from config import Settings
from notifications import LiveNotifier, LiveStream
from state import StateError

API_URL = "https://www.googleapis.com/youtube/v3"
logger = logging.getLogger(__name__)


class YouTubeAPIError(Exception):
    """A sanitized API failure, without the URL containing the API key."""


class YouTubeMonitor:
    def __init__(
        self, client: discord.Client, settings: Settings,
        session: aiohttp.ClientSession, notifier: LiveNotifier,
    ):
        self.client = client
        self.settings = settings
        self.session = session
        self.notifier = notifier

    async def _get(self, resource: str, **params: Any) -> dict:
        params["key"] = self.settings.youtube_api_key
        async with self.session.get(f"{API_URL}/{resource}", params=params) as response:
            if response.status != 200:
                # Never log the response URL: it contains the API key.
                raise YouTubeAPIError(
                    f"YouTube {resource} returned HTTP {response.status}. "
                    "Check API enablement, credentials, quota, and channel configuration."
                )
            result = await response.json()
            if not isinstance(result, dict):
                raise ValueError("Unexpected YouTube response")
            return result

    async def fetch_live_streams(self) -> list[LiveStream]:
        activities = await self._get(
            "activities", part="contentDetails",
            channelId=self.settings.youtube_channel_id, maxResults=50,
        )
        video_ids = [
            item["contentDetails"]["upload"]["videoId"]
            for item in activities.get("items", [])
            if "upload" in item.get("contentDetails", {})
        ]
        if not video_ids:
            return []
        videos = await self._get(
            "videos", part="snippet,liveStreamingDetails", id=",".join(video_ids)
        )
        return [
            LiveStream(video["id"], video["snippet"]["title"],
                       f"https://www.youtube.com/watch?v={video['id']}")
            for video in videos.get("items", [])
            if video.get("snippet", {}).get("liveBroadcastContent") == "live"
        ]

    @tasks.loop(seconds=60)
    async def poll(self) -> None:
        try:
            for stream in await self.fetch_live_streams():
                await self.notifier.announce(stream)
        except YouTubeAPIError as error:
            logger.warning("%s", error)
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError, TypeError):
            logger.warning("YouTube check failed due to a network or response error; retrying next poll")
        except StateError as error:
            logger.error("%s", error)

    @poll.before_loop
    async def before_poll(self) -> None:
        await self.client.wait_until_ready()
