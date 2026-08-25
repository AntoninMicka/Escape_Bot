from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .storage import JsonStorage, Storage, create_storage
from .storage_migration import migrate_storage


RESET_CONFIRMATION = "RESET-EVENT-DATA"


def archive_event(source: Storage, archive_root: str | Path, label: str = "event") -> tuple[Path, dict[str, int]]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_label = "".join(character for character in label.lower() if character.isalnum() or character in "-_")[:40]
    destination = Path(archive_root).resolve() / f"{timestamp}-{safe_label or 'event'}"
    if destination.exists():
        raise FileExistsError(f"Archiv už existuje: {destination}")
    target = JsonStorage(destination)
    report = migrate_storage(source, target, apply=True)
    (destination / "archive-report.json").write_text(
        json.dumps({"created_at": datetime.now(UTC).isoformat(), "source": source.backend_name, **report}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination, report


def reset_event(storage: Storage, confirmation: str) -> None:
    if confirmation != RESET_CONFIRMATION:
        raise ValueError(f"Reset vyžaduje potvrzení {RESET_CONFIRMATION}.")
    settings = storage.load_runtime_settings()
    settings["gameplay_enabled"] = False
    settings["leaderboard_finalized"] = False
    settings["leaderboard_finalized_at"] = ""
    storage.save_sessions({})
    storage.save_lobbies([])
    storage.save_leaderboard([])
    storage.save_runtime_settings(settings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Archivace a bezpečný reset krátkodobé akce")
    parser.add_argument("--backend", choices=("json", "postgres"), default=os.getenv("ESCAPEBOT_STORAGE_BACKEND", "postgres"))
    parser.add_argument("--database-url", default=os.getenv("ESCAPEBOT_DATABASE_URL", ""))
    parser.add_argument("--data-dir", default=os.getenv("ESCAPEBOT_DATA_DIR", "backend"))
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--label", default="event")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--confirm-reset", default="")
    arguments = parser.parse_args()

    source = create_storage(arguments.backend, data_dir=arguments.data_dir, database_url=arguments.database_url)
    try:
        archive_path, report = archive_event(source, arguments.archive_root, arguments.label)
        if arguments.reset:
            reset_event(source, arguments.confirm_reset)
        print(json.dumps({
            "archive": str(archive_path),
            "reset": arguments.reset,
            **report,
        }, ensure_ascii=False, indent=2))
    finally:
        source.close()


if __name__ == "__main__":
    main()
