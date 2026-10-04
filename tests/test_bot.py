import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot import NotificationBot
from config import PROJECT_DIR, Settings
from monitors.youtube import YouTubeMonitor, YouTubeAPIError
from notifications import LiveNotifier, LiveStream, format_live_notification
from state import StateError, StateStore


class ConfigTests(unittest.TestCase):
    def test_missing_token_and_placeholders(self):
        for env in ({}, {"DISCORD_TOKEN": "your_discord_bot_token_here"}):
            with self.assertRaisesRegex(ValueError, "DISCORD_TOKEN"):
                Settings.from_environment(env)
        settings = Settings.from_environment({
            "DISCORD_TOKEN": " token ", "YOUTUBE_API_KEY": "your_youtube_data_api_key_here",
        })
        self.assertEqual(settings.discord_token, "token")
        self.assertIn("YOUTUBE_API_KEY", settings.missing_monitor_settings)
        self.assertNotIn("token", repr(settings))

    def test_paths_and_optional_settings(self):
        settings = Settings.from_environment({
            "DISCORD_TOKEN": "secret",
            "YOUTUBE_API_KEY": "key",
            "YOUTUBE_CHANNEL_ID": "UCexample",
            "TWITCH_STREAM_URL": " <https://www.twitch.tv/example> ",
            "DATA_DIR": "data",
        })
        self.assertEqual(settings.data_dir, PROJECT_DIR / "data")
        self.assertEqual(settings.twitch_stream_url, "https://www.twitch.tv/example")
        self.assertEqual(settings.missing_monitor_settings, [])


class StateTests(unittest.TestCase):
    def test_existing_format_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "role_config.json").write_text(
                json.dumps({"1": {"role_id": 2, "channel_id": 3}}), encoding="utf-8"
            )
            store = StateStore(path)
            self.assertEqual(store.destinations()["1"]["role_id"], 2)
            store.mark_announced("1", "video")
            reopened = StateStore(path)
            self.assertTrue(reopened.was_announced("1", "video"))
            self.assertFalse(reopened.was_announced("2", "video"))
            self.assertFalse(list(path.glob("*.tmp")))

    def test_corrupt_state_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "youtube_state.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(StateError):
                StateStore(path.parent)
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_failed_write_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory))
            store.set_destination(1, 2, 3)
            with patch("state.os.fsync", side_effect=OSError):
                with self.assertRaises(StateError):
                    store.set_destination(1, 4, 5)
            self.assertEqual(StateStore(Path(directory)).destinations()["1"]["role_id"], 2)


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = Settings(
            "secret", "key", "UCexample", "https://www.twitch.tv/example",
            Path(self.directory.name),
        )
        self.store = StateStore(self.settings.data_dir)
        self.store.set_destination(1, 2, 3)
        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.send = AsyncMock()
        role = SimpleNamespace(id=2, mention="<@&2>")
        guild = MagicMock()
        guild.get_role.return_value = role
        guild.get_channel_or_thread.return_value = self.channel
        self.client = MagicMock()
        self.client.get_guild.return_value = guild
        self.notifier = LiveNotifier(self.client, self.settings, self.store)
        self.stream = LiveStream("video", "Cozy Stream", "https://www.youtube.com/watch?v=video")

    def test_exact_custom_message(self):
        message = format_live_notification(self.stream, "<@&2>", self.settings.twitch_stream_url)
        self.assertEqual(message,
            '🔔 <@&2> boop!\nMiwi is streaming "**Cozy Stream**" '
            'live on [YouTube](https://www.youtube.com/watch?v=video) and '
            '[Twitch](<https://www.twitch.tv/example>) ! (,,⟡o⟡,,)')
        hostile = LiveStream("v", "@everyone *title*", "https://youtube.com/watch?v=v")
        self.assertNotIn("@everyone", format_live_notification(hostile, "<@&2>", "url"))

    async def test_duplicate_prevention_concurrency_and_restart(self):
        counts = await asyncio.gather(
            self.notifier.announce(self.stream), self.notifier.announce(self.stream)
        )
        self.assertEqual(sum(counts), 1)
        restarted = LiveNotifier(self.client, self.settings, StateStore(self.settings.data_dir))
        self.assertEqual(await restarted.announce(self.stream), 0)
        self.channel.send.assert_awaited_once()
        mentions = self.channel.send.await_args.kwargs["allowed_mentions"]
        self.assertFalse(mentions.everyone)
        self.assertFalse(mentions.users)

    async def test_failed_delivery_retries_and_test_does_not_save(self):
        self.channel.send.side_effect = discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "Forbidden"
        )
        self.assertEqual(await self.notifier.announce(self.stream), 0)
        self.assertFalse(self.store.was_announced("1", "video"))
        self.channel.send.side_effect = None
        self.assertEqual(await self.notifier.announce(self.stream), 1)
        for _ in range(2):
            self.assertEqual(await self.notifier.send_test(1), 1)
        self.assertFalse(self.store.was_announced("1", "test-live-notification"))

    async def test_commands_and_shared_test_service(self):
        client = NotificationBot(self.settings)
        try:
            self.assertEqual(
                {c.name for c in client.tree.get_commands()}, {"ping", "set-role", "test-live"}
            )
            interaction = SimpleNamespace(
                guild_id=1, channel_id=3, response=AsyncMock(), followup=AsyncMock()
            )
            await client.tree.get_command("ping").callback(interaction)
            interaction.response.send_message.assert_awaited_once_with("Pong!")
            interaction.response.reset_mock()
            await client.tree.get_command("set-role").callback(
                interaction, SimpleNamespace(id=2, mention="<@&2>", is_default=lambda: False)
            )
            self.assertEqual(client.store.destinations()["1"], {"role_id": 2, "channel_id": 3})
            with patch.object(client.notifier, "send_test", new=AsyncMock(return_value=1)) as send:
                await client.tree.get_command("test-live").callback(interaction)
                send.assert_awaited_once_with(1)
            for name in ("set-role", "test-live"):
                command = client.tree.get_command(name)
                self.assertTrue(command.guild_only)
                self.assertTrue(command.default_permissions.manage_guild)
        finally:
            await client.close()

    async def test_shutdown_closes_http_session(self):
        client = NotificationBot(self.settings)
        client.http_session = AsyncMock()
        await client.close()
        client.http_session.close.assert_awaited_once()


class YouTubeTests(unittest.IsolatedAsyncioTestCase):
    def make_monitor(self):
        return YouTubeMonitor(
            AsyncMock(), Settings("token", "secret-key", "UCexample", "url"),
            MagicMock(), SimpleNamespace(announce=AsyncMock()),
        )

    async def test_only_live_videos_are_announced(self):
        monitor = self.make_monitor()
        activities = {"items": [
            {"contentDetails": {"upload": {"videoId": name}}}
            for name in ("live", "upcoming", "finished")
        ]}
        videos = {"items": [
            {"id": name, "snippet": {"title": name, "liveBroadcastContent": status}}
            for name, status in (("live", "live"), ("upcoming", "upcoming"), ("finished", "none"))
        ]}
        with patch.object(monitor, "_get", new=AsyncMock(side_effect=[activities, videos])):
            await monitor.poll()
        monitor.notifier.announce.assert_awaited_once_with(
            LiveStream("live", "live", "https://www.youtube.com/watch?v=live")
        )

    async def test_failure_is_sanitized_and_next_poll_recovers(self):
        monitor = self.make_monitor()
        stream = LiveStream("id", "title", "url")
        with patch.object(monitor, "fetch_live_streams", new=AsyncMock(
            side_effect=[TimeoutError("secret-key"), [stream]]
        )):
            with self.assertLogs("monitors.youtube", level="WARNING") as logs:
                await monitor.poll()
            self.assertNotIn("secret-key", str(logs.output))
            await monitor.poll()
        monitor.notifier.announce.assert_awaited_once_with(stream)

    async def test_http_error_does_not_contain_api_key(self):
        monitor = self.make_monitor()
        response = MagicMock(status=403)
        response.__aenter__ = AsyncMock(return_value=response)
        response.__aexit__ = AsyncMock(return_value=False)
        monitor.session.get.return_value = response
        with self.assertRaises(YouTubeAPIError) as caught:
            await monitor._get("activities")
        self.assertNotIn("secret-key", str(caught.exception))
        self.assertIn("403", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
