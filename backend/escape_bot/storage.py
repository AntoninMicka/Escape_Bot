from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol


class Storage(Protocol):
    """Persistence contract independent of the concrete storage backend."""

    @property
    def backend_name(self) -> str: ...

    def load_sessions(self) -> dict[str, Any]: ...
    def save_sessions(self, data: dict[str, Any]) -> None: ...
    def load_lobbies(self) -> list[dict[str, Any]]: ...
    def save_lobbies(self, data: list[dict[str, Any]]) -> None: ...
    def load_runtime_settings(self) -> dict[str, Any]: ...
    def save_runtime_settings(self, data: dict[str, Any]) -> None: ...
    def load_leaderboard(self) -> list[dict[str, Any]]: ...
    def save_leaderboard(self, data: list[dict[str, Any]]) -> None: ...
    def check_ready(self) -> dict[str, object]: ...


class JsonStorage:
    """Atomic JSON persistence used by local and single-instance deployments."""

    _FILES = {
        "sessions": "sessions.json",
        "lobbies": "lobbies.json",
        "runtime_settings": "runtime_settings.json",
        "leaderboard": "leaderboard.json",
    }

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir).resolve()

    @property
    def backend_name(self) -> str:
        return "json"

    def _path(self, dataset: str) -> Path:
        return self.data_dir / self._FILES[dataset]

    def _load(self, dataset: str, default: Any, expected_type: type) -> Any:
        path = self._path(dataset)
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, expected_type):
            raise ValueError(f"Datová sada {dataset} nemá očekávaný formát.")
        return data

    def _save(self, dataset: str, data: object) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".escape-bot-", suffix=".json", dir=self.data_dir
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._path(dataset))
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def load_sessions(self) -> dict[str, Any]:
        return self._load("sessions", {}, dict)

    def save_sessions(self, data: dict[str, Any]) -> None:
        self._save("sessions", data)

    def load_lobbies(self) -> list[dict[str, Any]]:
        return self._load("lobbies", [], list)

    def save_lobbies(self, data: list[dict[str, Any]]) -> None:
        self._save("lobbies", data)

    def load_runtime_settings(self) -> dict[str, Any]:
        return self._load("runtime_settings", {}, dict)

    def save_runtime_settings(self, data: dict[str, Any]) -> None:
        self._save("runtime_settings", data)

    def load_leaderboard(self) -> list[dict[str, Any]]:
        return self._load("leaderboard", [], list)

    def save_leaderboard(self, data: list[dict[str, Any]]) -> None:
        self._save("leaderboard", data)

    def check_ready(self) -> dict[str, object]:
        """Verify the dependency with a real write, sync and delete cycle."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(prefix=".escape-bot-ready-", dir=self.data_dir)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write("ready")
                file.flush()
                os.fsync(file.fileno())
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
        return {"backend": self.backend_name, "writable": True}
