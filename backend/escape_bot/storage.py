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
    def close(self) -> None: ...


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

    def close(self) -> None:
        pass


class PostgresStorage:
    """PostgreSQL JSONB storage with a small thread-safe connection pool."""

    _DATASETS = {
        "sessions": dict,
        "lobbies": list,
        "runtime_settings": dict,
        "leaderboard": list,
    }

    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 5) -> None:
        if not database_url:
            raise ValueError("Pro PostgreSQL úložiště chybí ESCAPEBOT_DATABASE_URL.")
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as error:
            raise RuntimeError("PostgreSQL podpora vyžaduje balíček psycopg[pool].") from error
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={"autocommit": False},
        )
        self._pool.open()

    @property
    def backend_name(self) -> str:
        return "postgres"

    def migrate_schema(self) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version integer PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS storage_documents (
                dataset text PRIMARY KEY,
                payload jsonb NOT NULL,
                version bigint NOT NULL DEFAULT 1,
                updated_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT storage_documents_dataset_check CHECK (
                    dataset IN ('sessions', 'lobbies', 'runtime_settings', 'leaderboard')
                )
            )""",
            "INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT (version) DO NOTHING",
        )
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            connection.commit()

    def _load(self, dataset: str, default: Any) -> Any:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload FROM storage_documents WHERE dataset = %s", (dataset,))
                row = cursor.fetchone()
        if row is None:
            return default
        data = row[0]
        expected_type = self._DATASETS[dataset]
        if not isinstance(data, expected_type):
            raise ValueError(f"Datová sada {dataset} nemá očekávaný formát.")
        return data

    def _save(self, dataset: str, data: object) -> None:
        from psycopg.types.json import Jsonb

        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO storage_documents(dataset, payload)
                       VALUES (%s, %s)
                       ON CONFLICT (dataset) DO UPDATE
                       SET payload = EXCLUDED.payload,
                           version = storage_documents.version + 1,
                           updated_at = now()""",
                    (dataset, Jsonb(data)),
                )
            connection.commit()

    def load_sessions(self) -> dict[str, Any]:
        return self._load("sessions", {})

    def save_sessions(self, data: dict[str, Any]) -> None:
        self._save("sessions", data)

    def load_lobbies(self) -> list[dict[str, Any]]:
        return self._load("lobbies", [])

    def save_lobbies(self, data: list[dict[str, Any]]) -> None:
        self._save("lobbies", data)

    def load_runtime_settings(self) -> dict[str, Any]:
        return self._load("runtime_settings", {})

    def save_runtime_settings(self, data: dict[str, Any]) -> None:
        self._save("runtime_settings", data)

    def load_leaderboard(self) -> list[dict[str, Any]]:
        return self._load("leaderboard", [])

    def save_leaderboard(self, data: list[dict[str, Any]]) -> None:
        self._save("leaderboard", data)

    def check_ready(self) -> dict[str, object]:
        with self._pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return {"backend": self.backend_name, "connected": True}

    def close(self) -> None:
        self._pool.close()


def create_storage(
    backend: str | None = None,
    *,
    data_dir: str | Path | None = None,
    database_url: str | None = None,
) -> Storage:
    selected = (backend or os.getenv("ESCAPEBOT_STORAGE_BACKEND", "json")).strip().lower()
    if selected == "json":
        directory = data_dir or os.getenv("ESCAPEBOT_DATA_DIR", "backend")
        return JsonStorage(directory)
    if selected in {"postgres", "postgresql"}:
        url = database_url if database_url is not None else os.getenv("ESCAPEBOT_DATABASE_URL", "")
        return PostgresStorage(url)
    raise ValueError(f"Nepodporovaný backend úložiště: {selected}")
