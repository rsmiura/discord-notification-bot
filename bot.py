"""Application entry point and Discord client lifecycle."""

import asyncio
import logging
import signal
from contextlib import suppress

import aiohttp
import discord
from discord import app_commands

from commands import register_commands
from config import Settings, load_settings
from monitors.youtube import YouTubeMonitor
from notifications import LiveNotifier
from state import StateError, StateStore

logger = logging.getLogger(__name__)


class NotificationBot(discord.Client):
    def __init__(self, settings: Settings):
        super().__init__(intents=discord.Intents.default())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.store = StateStore(settings.data_dir)
        self.notifier = LiveNotifier(self, settings, self.store)
        self.youtube: YouTubeMonitor | None = None
        self.http_session: aiohttp.ClientSession | None = None
        register_commands(self.tree, self.notifier)

    async def setup_hook(self) -> None:
        synced = await self.tree.sync()
        logger.info("Synced %d slash commands", len(synced))
        if self.settings.missing_monitor_settings:
            logger.warning(
                "YouTube monitoring disabled. Set these variables in .env: %s",
                ", ".join(self.settings.missing_monitor_settings),
            )
            return
        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self.youtube = YouTubeMonitor(self, self.settings, self.http_session, self.notifier)
        self.youtube.poll.start()

    async def on_ready(self) -> None:
        logger.info("Connected to Discord as %s!", self.user)

    async def close(self) -> None:
        if self.youtube is not None:
            task = self.youtube.poll.get_task()
            self.youtube.poll.cancel()
            if task is not None:
                with suppress(asyncio.CancelledError, Exception):
                    await task
        if self.http_session is not None:
            await self.http_session.close()
        await super().close()


async def run_bot(settings: Settings) -> None:
    async with NotificationBot(settings) as client:
        loop = asyncio.get_running_loop()
        runner = asyncio.current_task()
        signals = []
        # Docker sends SIGTERM; cancellation exits the client's context cleanly.
        if runner is not None:
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, runner.cancel)
                    signals.append(sig)
                except NotImplementedError:
                    pass  # Windows uses asyncio.run's normal Ctrl+C handling.
        try:
            await client.start(settings.discord_token)
        finally:
            for sig in signals:
                loop.remove_signal_handler(sig)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run_bot(load_settings()))
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Bot stopped")
    except (ValueError, StateError) as error:
        raise SystemExit(str(error)) from None
    except discord.LoginFailure:
        raise SystemExit("Discord login failed. Check DISCORD_TOKEN in .env.") from None


if __name__ == "__main__":
    main()
