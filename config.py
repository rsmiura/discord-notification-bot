"""Load settings once; importing modules does not read secrets or start the bot."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    discord_token: str = field(repr=False)
    youtube_api_key: str = field(default="", repr=False)
    youtube_channel_id: str = ""
    twitch_stream_url: str = ""
    data_dir: Path = PROJECT_DIR

    @property
    def missing_monitor_settings(self) -> list[str]:
        values = {
            "YOUTUBE_API_KEY": self.youtube_api_key,
            "YOUTUBE_CHANNEL_ID": self.youtube_channel_id,
            "TWITCH_STREAM_URL": self.twitch_stream_url,
        }
        return [name for name, value in values.items() if not value]

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> "Settings":
        def value(name: str) -> str:
            result = env.get(name, "").strip()
            if result.startswith("your_") or result.endswith("/your_twitch_channel"):
                return ""
            return result

        token = value("DISCORD_TOKEN")
        if not token:
            raise ValueError("Set DISCORD_TOKEN in your .env file before running the bot.")
        data_dir = Path(value("DATA_DIR") or ".")
        if not data_dir.is_absolute():
            data_dir = PROJECT_DIR / data_dir
        return cls(
            discord_token=token,
            youtube_api_key=value("YOUTUBE_API_KEY"),
            youtube_channel_id=value("YOUTUBE_CHANNEL_ID"),
            twitch_stream_url=value("TWITCH_STREAM_URL").strip("<>"),
            data_dir=data_dir.resolve(),
        )


def load_settings() -> Settings:
    load_dotenv(PROJECT_DIR / ".env")
    return Settings.from_environment(os.environ)
