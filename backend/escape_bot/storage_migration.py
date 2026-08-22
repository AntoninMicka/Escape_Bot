from __future__ import annotations

import argparse
import json
import os
from typing import Any

from .storage import PostgresStorage, Storage, create_storage


def migration_report(source: Storage) -> tuple[dict[str, Any], dict[str, int]]:
    datasets = {
        "sessions": source.load_sessions(),
        "lobbies": source.load_lobbies(),
        "runtime_settings": source.load_runtime_settings(),
        "leaderboard": source.load_leaderboard(),
    }
    session_ids = set(datasets["sessions"])
    lobby_session_ids = {str(item.get("session_id", "")) for item in datasets["lobbies"]}
    missing_sessions = sorted(lobby_session_ids - session_ids)
    if missing_sessions:
        raise ValueError("Lobby bez odpovídající relace: " + ", ".join(missing_sessions))
    report = {
        "sessions": len(datasets["sessions"]),
        "lobbies": len(datasets["lobbies"]),
        "players": sum(len(item.get("players", {})) for item in datasets["lobbies"]),
        "leaderboard_entries": len(datasets["leaderboard"]),
        "runtime_settings": len(datasets["runtime_settings"]),
    }
    return datasets, report


def migrate_storage(source: Storage, target: Storage | None = None, *, apply: bool = False) -> dict[str, int]:
    datasets, report = migration_report(source)
    if not apply:
        return report
    if target is None:
        raise ValueError("Pro zápis migrace chybí cílové úložiště.")
    if isinstance(target, PostgresStorage):
        target.migrate_schema()
    target.save_sessions(datasets["sessions"])
    target.save_lobbies(datasets["lobbies"])
    target.save_runtime_settings(datasets["runtime_settings"])
    target.save_leaderboard(datasets["leaderboard"])
    verification = {
        "sessions": target.load_sessions(),
        "lobbies": target.load_lobbies(),
        "runtime_settings": target.load_runtime_settings(),
        "leaderboard": target.load_leaderboard(),
    }
    if verification != datasets:
        raise RuntimeError("Kontrola cílových dat po migraci selhala.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Kontrolovaná migrace persistence Escape Botu")
    parser.add_argument("--source", choices=("json", "postgres"), default=os.getenv("ESCAPEBOT_MIGRATION_SOURCE", "json"))
    parser.add_argument("--target", choices=("json", "postgres"), default=os.getenv("ESCAPEBOT_MIGRATION_TARGET", "postgres"))
    parser.add_argument("--source-data-dir", default=os.getenv("ESCAPEBOT_MIGRATION_SOURCE_DATA_DIR") or os.getenv("ESCAPEBOT_DATA_DIR", "backend"))
    parser.add_argument("--target-data-dir", default=os.getenv("ESCAPEBOT_MIGRATION_TARGET_DATA_DIR") or os.getenv("ESCAPEBOT_DATA_DIR", "backend"))
    parser.add_argument("--source-database-url", default=os.getenv("ESCAPEBOT_MIGRATION_SOURCE_DATABASE_URL", ""))
    parser.add_argument("--target-database-url", default=os.getenv("ESCAPEBOT_MIGRATION_TARGET_DATABASE_URL") or os.getenv("ESCAPEBOT_DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true", help="Provede zápis; bez této volby jde jen o validaci")
    arguments = parser.parse_args()
    source = create_storage(arguments.source, data_dir=arguments.source_data_dir, database_url=arguments.source_database_url)
    target = None
    try:
        if arguments.apply:
            target = create_storage(arguments.target, data_dir=arguments.target_data_dir, database_url=arguments.target_database_url)
        report = migrate_storage(source, target, apply=arguments.apply)
        print(json.dumps({"mode": "apply" if arguments.apply else "dry-run", **report}, ensure_ascii=False, indent=2))
    finally:
        source.close()
        if target is not None:
            target.close()


if __name__ == "__main__":
    main()
