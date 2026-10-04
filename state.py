"""JSON storage compatible with the original bot's file names and format."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class StateError(Exception):
    """State could not be read or saved safely."""


class StateStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self._roles = self._read("role_config.json")
        self._announced = self._read("youtube_state.json")
        for guild_id, settings in self._roles.items():
            if not guild_id.isdigit() or not isinstance(settings, dict):
                raise StateError("Invalid role_config.json. Restore a valid backup.")
            if any(type(settings.get(key)) is not int for key in ("role_id", "channel_id")):
                raise StateError("Invalid role_config.json. Expected numeric role_id and channel_id.")
        for guild_id, ids in self._announced.items():
            if (not guild_id.isdigit() or not isinstance(ids, list)
                    or not all(isinstance(i, str) for i in ids)):
                raise StateError("Invalid youtube_state.json. Restore a valid backup.")

    def _read(self, name: str) -> dict[str, Any]:
        try:
            data = json.loads((self.directory / name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            raise StateError(
                f"Cannot read {name}. Check permissions and JSON syntax; the file was not changed."
            ) from None
        if not isinstance(data, dict):
            raise StateError(f"Invalid {name}: expected a JSON object.")
        return data

    def _write(self, name: str, data: dict) -> None:
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory,
                prefix=f".{name}.", suffix=".tmp", delete=False,
            ) as file:
                temporary = Path(file.name)
                json.dump(data, file, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            # Replacing the file avoids leaving half-written JSON after interruption.
            temporary.replace(self.directory / name)
        except OSError:
            raise StateError(f"Cannot save {name}. Check DATA_DIR permissions and disk space.") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def destinations(self) -> dict[str, dict[str, int]]:
        return {key: dict(value) for key, value in self._roles.items()}

    def set_destination(self, guild_id: int, role_id: int, channel_id: int) -> None:
        updated = self.destinations()
        updated[str(guild_id)] = {"role_id": role_id, "channel_id": channel_id}
        self._write("role_config.json", updated)
        self._roles = updated

    def was_announced(self, guild_id: str, video_id: str) -> bool:
        return video_id in self._announced.get(guild_id, [])

    def mark_announced(self, guild_id: str, video_id: str) -> None:
        ids = self._announced.setdefault(guild_id, [])
        if video_id not in ids:
            ids.append(video_id)
        self._announced[guild_id] = ids[-100:]
        # Retain memory of a sent alert even if its disk write fails.
        self._write("youtube_state.json", self._announced)
