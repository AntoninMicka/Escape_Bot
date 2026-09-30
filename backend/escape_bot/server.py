import asyncio
import ast
import json
import logging
import os
import subprocess
import socket
import secrets
import threading
import hmac
import re
import uvicorn
from io import BytesIO
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .command_validation import CommandValidationError
from .protocol import Message
from .game_engine import ApplyResult
from .session_adapter import GameSessionAdapter
from .state_machine import EscapeBotStateMachine
from .scenario import ScenarioLoader, build_checkpoint_qr_set, build_demo_checkpoint_catalog, build_puzzle_telemetry, build_scenario_progress
from .scenario import Scenario
from .scenario_catalog import load_scenario_catalog
from .scenario_composer import compose_documents
from .team_lobby import Lobby, LobbyRegistry, classify_activity
from .mine_karel import safe_path as karel_safe_path
from .storage import Storage, create_storage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EscapeBot")

# Dynamické nalezení absolutní cesty do složky client/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_DIR = os.path.join(BASE_DIR, "client")
DATA_DIR = os.path.abspath(os.getenv("ESCAPEBOT_DATA_DIR", os.path.join(BASE_DIR, "backend")))
STORAGE_BACKEND = os.getenv("ESCAPEBOT_STORAGE_BACKEND", "json").strip().lower()
storage: Storage = create_storage(STORAGE_BACKEND, data_dir=DATA_DIR)


def configure_storage(backend: str | None = None, database_url: str | None = None) -> None:
    """Apply a launch-time override before the application lifespan starts."""
    global STORAGE_BACKEND, storage
    previous = storage
    storage = create_storage(backend, data_dir=DATA_DIR, database_url=database_url)
    STORAGE_BACKEND = storage.backend_name
    previous.close()

# Úložiště pro nezávislé relace hráčů (session_id -> state_machine)
active_sessions: dict[str, EscapeBotStateMachine] = {}
session_command_adapters: dict[str, GameSessionAdapter] = {}
lobby_registry = LobbyRegistry()
session_connections: dict[str, set[WebSocket]] = {}
connection_info: dict[WebSocket, dict[str, object]] = {}
waiting_players: dict[str, dict[str, object]] = {}
recovery_tokens: dict[str, dict[str, object]] = {}
terminal_pairings: dict[str, dict[str, object]] = {}
admin_support_sessions: dict[WebSocket, set[str]] = {}
admin_spectator_sessions: dict[WebSocket, str] = {}
authenticated_admin_sockets: set[WebSocket] = set()
public_display_status: dict[str, object] = {}
ADMIN_RESOLUTION_PRESETS = {
    "technical": {"label": "Technická chyba / uznat bez postihu", "penalty": 0},
    "minor_help": {"label": "Drobná pomoc Game Mastera", "penalty": 20},
    "minigame_skip": {"label": "Přeskočení minihry", "penalty": 50},
    "cipher_solved": {"label": "Šifra vyřešená Game Masterem", "penalty": 75},
}


def admin_capabilities_payload() -> dict[str, object]:
    """Describe only admin actions implemented by this runtime."""
    return {
        "actions": [
            "managed_team_create", "managed_start", "managed_start_override",
            "event_runtime", "leaderboard_finalize", "event_settings",
            "score_adjustment", "session_extend", "session_end", "support_message",
            "checkpoint", "scenario_play_modes", "scenario_availability", "terminal_catalog", "terminal_reservation", "terminal_release", "spectate",
            "game_reset", "game_player", "team_finalize", "player_recovery", "team_delete",
        ],
        "http_actions": [],
        "checkpoint_states": ["found", "solved"],
        "game_reset_adapters": ["line_game", "mine_karel", "triad", "sokoban"],
        "game_player_actions": ["exclude", "include", "reset"],
        "terminal_reservation": True,
        "scenario_play_modes": True,
        "terminal_catalog": True,
        "terminal_assignment": True,
        "scenario_availability": True,
        "terminal_release": True,
    }


ADMIN_MESSAGE_TYPES = frozenset({
    "admin.list", "admin.penalty", "admin.score_adjustment", "admin.delete",
    "admin.qr_set", "admin.online_mode", "admin.operations", "admin.launch_mode",
    "admin.schedule_settings", "admin.event_settings", "admin.display_announcements",
    "admin.display_leaderboard", "admin.evaluate_team", "admin.session_extend",
    "admin.session_end", "admin.checkpoint", "admin.game_reset", "admin.game_player",
    "admin.player_recovery", "admin.leaderboard_delete", "admin.leaderboard_finalize",
    "admin.support_join", "admin.support_leave", "admin.support_message",
    "admin.spectate_start", "admin.spectate_stop", "admin.scenario_source",
    "admin.scenario_validate", "admin.scenario_play_modes", "admin.scenario_availability", "admin.terminal_catalog",
    "admin.terminal_reserve", "admin.terminal_release", "admin.terminal_assign", "admin.team_create",
    "admin.team_add_player", "admin.team_start", "admin.queue_expedite",
})


DEMO_MODE_ENABLED = os.getenv("ESCAPEBOT_DEMO_MODE", "").lower() in {"1", "true", "yes", "on"}
ADMIN_TOKEN = os.getenv("ESCAPEBOT_ADMIN_TOKEN", "")
runtime_settings = {"online_mode": False, "gameplay_enabled": True, "max_active_teams": 4,
                    "launch_mode": "free", "start_queue": [],
                    "start_interval_minutes": 15, "soft_start_interval_minutes": 15,
                    "hard_start_interval_minutes": 5, "game_duration_minutes": 165,
                    "deadline_penalty": 100, "abandonment_penalty": 100, "completion_bonus": 100,
                    "opening_time": "08:00", "closing_time": "20:00", "timezone": "Europe/Prague",
                    "display_announcements": [], "display_leaderboard": True,
                    "leaderboard_finalized": False, "leaderboard_finalized_at": "",
                    "event": {"id": "", "name": "", "starts_at": "", "ends_at": "", "scenario_ids": [],
                              "leaderboard_finalized": False, "leaderboard_finalized_at": ""}}

def configured_event() -> dict[str, object] | None:
    event = runtime_settings.get("event")
    return normalize_event(event) if isinstance(event, dict) and str(event.get("id", "")).strip() else None

def normalize_event(event: dict[str, object]) -> dict[str, object]:
    """Return the current event schema while accepting legacy scenario_ids."""
    def number(value: object, default: float = 0.0) -> float:
        try: return float(value)
        except (TypeError, ValueError): return default
    raw_games = event.get("games")
    if not isinstance(raw_games, list):
        raw_games = [{"game_id": str(game_id), "role": "primary" if index == 0 else "competitive"}
                     for index, game_id in enumerate(event.get("scenario_ids", []))]
    games = []
    seen = set()
    for index, raw in enumerate(raw_games):
        raw = raw if isinstance(raw, dict) else {"game_id": str(raw)}
        game_id = str(raw.get("game_id", "")).strip()
        if not game_id or game_id in seen: continue
        role = str(raw.get("role", "primary" if index == 0 else "competitive"))
        if role not in {"primary", "competitive", "side"}: role = "competitive"
        games.append({"game_id": game_id, "role": role,
                      "queue_enabled": bool(raw.get("queue_enabled", role != "side")),
                      "leaderboard_enabled": bool(raw.get("leaderboard_enabled", role != "side")),
                      "weight": max(0.0, number(raw.get("weight", 1.0), 1.0)),
                      "start_interval_minutes": max(0, int(number(raw.get("start_interval_minutes", 0)))),
                      "max_active_teams": max(0, int(number(raw.get("max_active_teams", 0))))})
        seen.add(game_id)
    primary_id = str(event.get("primary_game_id", ""))
    if primary_id not in seen and games: primary_id = games[0]["game_id"]
    for game in games: game["role"] = "primary" if game["game_id"] == primary_id else ("competitive" if game["role"] == "primary" else game["role"])
    status = str(event.get("status", "open" if str(event.get("id", "")).strip() else "draft"))
    if status not in {"draft", "ready", "open", "paused", "ended", "archived"}: status = "draft"
    branding = event.get("branding") if isinstance(event.get("branding"), dict) else {}
    return {**event, "primary_game_id": primary_id, "games": games, "scenario_ids": [game["game_id"] for game in games],
            "status": status, "timezone": str(event.get("timezone", runtime_settings.get("timezone", "Europe/Prague"))),
            "branding": {"title": str(branding.get("title", event.get("name", ""))), "logo_url": str(branding.get("logo_url", "")),
                         "accent_color": str(branding.get("accent_color", "#65f7ff"))}}

def event_game_config(scenario_id: str) -> dict[str, object] | None:
    event = configured_event()
    if event is None: return None
    return next((game for game in event["games"] if game["game_id"] == scenario_id), None)

def event_allows_scenario(scenario_id: str) -> bool:
    event = configured_event()
    if event is None:
        return True
    return any(game["game_id"] == scenario_id for game in event["games"])

def leaderboard_is_finalized() -> bool:
    event = configured_event()
    return bool(event.get("leaderboard_finalized", False)) if event else bool(runtime_settings.get("leaderboard_finalized", False))

def normalize_display_announcement(item: object) -> dict[str, object] | None:
    """Unwrap current, JSON-stringified, and legacy Python-repr announcements."""
    priority = "normal"
    value = item
    for _ in range(8):
        if isinstance(value, dict):
            candidate = str(value.get("priority", priority))
            if candidate in {"emergency", "high", "normal", "low"}: priority = candidate
            value = value.get("text", "")
            continue
        text = str(value).strip()
        if text.startswith("{") and text.endswith("}"):
            parsed = None
            try: parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                try: parsed = ast.literal_eval(text)
                except (ValueError, SyntaxError): pass
            if isinstance(parsed, dict):
                value = parsed
                continue
        if not text: return None
        source = item if isinstance(item, dict) else {}
        category = str(source.get("category", "organization"))
        if category not in {"organization", "lost_found", "refreshment", "results", "important"}: category = "organization"
        fallback_priority = str(source.get("fallback_priority", "high"))
        if fallback_priority not in {"high", "normal", "low"}: fallback_priority = "high"
        try: override_minutes = max(0.0, min(1440.0, float(source.get("override_minutes", 0))))
        except (TypeError, ValueError): override_minutes = 0.0
        return {"id": str(source.get("id", "")) or secrets.token_hex(6), "text": text, "priority": priority,
                "category": category, "published": bool(source.get("published", True)),
                "starts_at": str(source.get("starts_at", "")), "ends_at": str(source.get("ends_at", "")),
                "link_url": str(source.get("link_url", "")), "link_label": str(source.get("link_label", "Více informací")),
                "override_minutes": override_minutes, "override_until": str(source.get("override_until", "")),
                "fallback_priority": fallback_priority, "event_id": str(source.get("event_id", "")),
                "game_id": str(source.get("game_id", ""))}
    text = str(value).strip()
    return {"id": secrets.token_hex(6), "text": text, "priority": priority, "category": "organization",
            "published": True, "starts_at": "", "ends_at": "", "link_url": "", "link_label": "Více informací",
            "override_minutes": 0.0, "override_until": "", "fallback_priority": "high", "event_id": "", "game_id": ""} if text else None

def display_status_payload() -> dict[str, object]:
    updated_at = str(public_display_status.get("updated_at", ""))
    online = False
    if updated_at:
        try: online = (datetime.now(UTC) - datetime.fromisoformat(updated_at)).total_seconds() < 15
        except ValueError: pass
    return {**public_display_status, "online": online}

def _local_now() -> datetime:
    try: return datetime.now(ZoneInfo(str(runtime_settings.get("timezone", "Europe/Prague"))))
    except Exception: return datetime.now(ZoneInfo("Europe/Prague"))

def start_availability(now: datetime | None = None, lobby_type: str = "on_site_qr", scenario_id: str = "") -> dict[str, object]:
    current = now or _local_now()
    event = configured_event()
    game_config = event_game_config(scenario_id) if scenario_id else None
    operating_hours_applied = event is not None or lobby_type != "online_doom"
    duration = max(1, int(runtime_settings.get("game_duration_minutes", 165)))
    interval = max(0, int(game_config.get("start_interval_minutes") or runtime_settings.get("start_interval_minutes", 15))) if game_config else max(0, int(runtime_settings.get("start_interval_minutes", 15)))
    maximum = max(1, int(game_config.get("max_active_teams") or runtime_settings.get("max_active_teams", 4))) if game_config else max(1, int(runtime_settings.get("max_active_teams", 4)))
    def clock(value: object, fallback: str) -> datetime:
        try:
            hour, minute = map(int, str(value).split(":")); return current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except Exception:
            hour, minute = map(int, fallback.split(":")); return current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    opening = clock(runtime_settings.get("opening_time"), "08:00")
    closing = clock(runtime_settings.get("closing_time"), "20:00")
    latest_start = closing - timedelta(minutes=duration)
    active = []
    active_deadlines = []
    starts = []
    for session_id, machine in active_sessions.items():
        lobby = lobby_registry.by_session.get(session_id)
        started_at = machine.state.flags.get("operations_started_at")
        parsed_start = None
        if started_at:
            try:
                parsed_start = datetime.fromisoformat(str(started_at)).astimezone(current.tzinfo)
                starts.append(parsed_start)
            except ValueError: pass
        within_expected_duration = parsed_start is not None and parsed_start + timedelta(minutes=duration) > current
        if lobby and lobby.started and within_expected_duration and not machine.state.flags.get("game_completed") and not machine.state.flags.get("administratively_ended"):
            active.append(session_id)
            active_deadlines.append(parsed_start + timedelta(minutes=duration))
    next_interval = max(starts) + timedelta(minutes=interval) if starts else current
    next_start = max(current, next_interval)
    if operating_hours_applied:
        next_start = max(next_start, opening)
    if len(active) >= maximum and active_deadlines:
        next_start = max(next_start, min(active_deadlines))
    reasons = []
    if scenario_id and scenario_id in set(runtime_settings.get("disabled_scenario_ids", [])):
        reasons.append("Tento scénář je správcem zakázaný.")
    if not runtime_settings.get("gameplay_enabled", True): reasons.append("Herní provoz je zastaven správcem.")
    if event:
        if event.get("status") in {"draft", "ready"}: reasons.append("Event ještě není otevřený.")
        if event.get("status") == "paused": reasons.append("Event je dočasně pozastavený.")
        if event.get("status") in {"ended", "archived"}: reasons.append("Event už byl ukončen.")
        try:
            event_start = datetime.fromisoformat(str(event.get("starts_at", ""))).astimezone(current.tzinfo)
            event_end = datetime.fromisoformat(str(event.get("ends_at", ""))).astimezone(current.tzinfo)
            opening, closing, latest_start = event_start, event_end, event_end - timedelta(minutes=duration)
            next_start = max(next_start, opening)
            if current < opening: reasons.append("Event ještě nezačal.")
            if current > latest_start: reasons.append("Nejzazší čas startu v rámci eventu už uplynul.")
        except ValueError:
            reasons.append("Event nemá platně nastavenou provozní dobu.")
        if scenario_id and not event_allows_scenario(scenario_id): reasons.append("Tato hra do aktuálního eventu nepatří.")
    else:
        if operating_hours_applied and current < opening: reasons.append("Provoz ještě nezačal.")
        if operating_hours_applied and current > latest_start: reasons.append("Dnešní nejzazší čas startu už uplynul.")
    if len(active) >= maximum: reasons.append("Kapacita současně hrajících týmů je naplněna.")
    if current < next_interval: reasons.append("Ještě neuplynul minimální rozestup mezi starty.")
    allowed = not reasons
    return {"start_allowed": allowed, "reason": " ".join(reasons), "server_time": current.isoformat(),
            "next_start_at": (next_start.isoformat() if not operating_hours_applied or next_start <= latest_start else None),
            "latest_start_at": latest_start.isoformat(), "opening_at": opening.isoformat(), "closing_at": closing.isoformat(),
            "active_teams": len(active), "max_active_teams": maximum, "game_duration_minutes": duration,
            "start_interval_minutes": interval, "gameplay_enabled": bool(runtime_settings.get("gameplay_enabled", True)),
            "operating_hours_applied": operating_hours_applied, "event_id": str(event.get("id", "")) if event else ""}

def runtime_payload() -> dict[str, object]:
    games = []
    for entry in scenario_catalog.entries.values():
        if entry.id in set(runtime_settings.get("disabled_scenario_ids", [])):
            continue
        if not event_allows_scenario(entry.id):
            continue
        item = entry.public()
        config = event_game_config(entry.id)
        item["event_role"] = str(config.get("role", "competitive")) if config else "competitive"
        item["queue_enabled"] = bool(config.get("queue_enabled", True)) if config else True
        item["leaderboard_enabled"] = bool(config.get("leaderboard_enabled", True)) if config else True
        item["lobby_types"] = [kind for kind in ("online_doom", "on_site_qr", "geo") if scenario_supports_lobby(entry, kind)]
        games.append(item)
    event = configured_event()
    games.sort(key=lambda item: (0 if item.get("event_role") == "primary" else 1 if item.get("event_role") == "competitive" else 2, str(item.get("title", ""))))
    return {**runtime_settings, "event": event or runtime_settings.get("event", {}), "start_queue": public_start_queue(),
            "leaderboard_finalized": leaderboard_is_finalized(),
            "mapillary": {"enabled": bool(os.getenv("ESCAPEBOT_MAPILLARY_TOKEN", "")),
                           "access_token": os.getenv("ESCAPEBOT_MAPILLARY_TOKEN", "")},
            "availability": start_availability(scenario_id=selected_scenario_id),
            "availability_by_lobby_type": {
                kind: start_availability(lobby_type=kind) for kind in ("online_doom", "on_site_qr", "geo")
            },
            "checkpoints": build_demo_checkpoint_catalog(scenario), "games": games,
            "puzzle_catalog": admin_puzzle_catalog(),
            "configurable_games": [{**entry.public(), "enabled": entry.id not in set(runtime_settings.get("disabled_scenario_ids", []))}
                                   for entry in scenario_catalog.entries.values()],
            "scenario_available": scenario_available and bool(games)}

def dequeue_team(session_id: str) -> bool:
    """Remove a session from the persisted queue metadata, if present."""
    queue = runtime_settings.get("start_queue", [])
    if not isinstance(queue, list):
        runtime_settings["start_queue"] = []
        return True
    filtered = [
        item for item in queue
        if str(item.get("session_id", "") if isinstance(item, dict) else item) != session_id
    ]
    changed = len(filtered) != len(queue)
    runtime_settings["start_queue"] = filtered
    return changed

def public_start_queue() -> list[dict[str, object]]:
    """Project waiting on-site team lobbies into the public display queue."""
    def queued(lobby: Lobby) -> str: return min((str(lobby.players[player_id].get("joined_at", "")) for player_id in lobby.active_player_ids), default=lobby.session_id)
    waiting = [lobby for lobby in lobby_registry.by_session.values() if lobby.mode == "team" and not lobby.started
               and bool(lobby.active_player_ids)
               and lobby.lobby_type in {"on_site_qr", "geo"}
               and (event_game_config(lobby.scenario_id) is None or bool(event_game_config(lobby.scenario_id).get("queue_enabled")))]
    event = configured_event(); primary = str(event.get("primary_game_id", "")) if event else ""
    waiting.sort(key=lambda lobby: (0 if lobby.scenario_id == primary else 1, lobby.scenario_id, queued(lobby)))
    game_positions: dict[str, int] = {}
    result = []
    for lobby in waiting:
        config = event_game_config(lobby.scenario_id) or {}
        position = game_positions.get(lobby.scenario_id, 0) + 1; game_positions[lobby.scenario_id] = position
        availability = start_availability(lobby_type=lobby.lobby_type, scenario_id=lobby.scenario_id)
        try: planned = datetime.fromisoformat(str(availability.get("next_start_at")))
        except ValueError: planned = _local_now()
        interval = timedelta(minutes=max(0, int(config.get("start_interval_minutes") or runtime_settings.get("start_interval_minutes", 15))))
        scenario_entry = scenario_catalog.entries.get(lobby.scenario_id)
        result.append({"session_id": lobby.session_id, "team_name": lobby.team_name, "position": position,
                       "planned_start_at": (planned + interval * (position - 1)).isoformat(), "queued_at": queued(lobby),
                       "scenario_id": lobby.scenario_id, "game_title": scenario_entry.title if scenario_entry else lobby.scenario_id,
                       "event_role": str(config.get("role", "competitive"))})
    return result

def require_start_available(lobby_type: str = "on_site_qr", scenario_id: str = "") -> None:
    if not scenario_available:
        raise ValueError("Není dostupný žádný platný scénář. Správce může chyby opravit v editoru her.")
    availability = start_availability(lobby_type=lobby_type, scenario_id=scenario_id)
    if not availability["start_allowed"]:
        next_start = availability.get("next_start_at")
        suffix = f" Další možný start: {datetime.fromisoformat(str(next_start)).strftime('%H:%M')}." if next_start else ""
        raise ValueError(str(availability.get("reason", "Start hry nyní není možný.")) + suffix)

def require_admin_start_available(override_soft: bool = False) -> None:
    availability = start_availability()
    if not availability["hard_start_allowed"]:
        raise ValueError(str(availability.get("hard_reason") or "Start hry nyní blokuje hard limit."))
    if availability["soft_limit_active"] and not override_soft:
        raise ValueError(str(availability.get("soft_reason")) + " Start potvrďte s obejitím soft limitu.")

async def start_due_queue_team(current: datetime) -> bool:
    """Start the first queued team once its reserved slot and all hard rules allow it."""
    if runtime_settings.get("launch_mode", "free") != "free": return False
    queue = queue_payload(current)
    if not queue: return False
    first = queue[0]
    try: due = current >= datetime.fromisoformat(str(first["planned_start_at"])).astimezone(current.tzinfo)
    except ValueError: return False
    if not due: return False
    availability = start_availability(current)
    if not availability["hard_start_allowed"]: return False
    if availability["soft_limit_active"] and not bool(first.get("soft_override")): return False
    lobby = lobby_registry.by_session.get(str(first["session_id"]))
    if lobby is None or lobby.started or not lobby.active_player_ids: return False
    lobby.started = True
    machine = ensure_state_machine(lobby.session_id)
    machine.state.flags["operations_started_at"] = datetime.now(UTC).isoformat()
    machine.state.flags["queue_auto_start"] = True
    dequeue_team(lobby.session_id)
    first_player = lobby.active_player_ids[0]
    hello = Message("client.hello", {"session_id": lobby.session_id, "demo_mode": False,
        "_client_id": first_player, "_participant_ids": lobby.active_player_ids, "_team_mode": lobby.mode,
        "_participant_names": {key: str(lobby.players[key].get("name", "Hráč")) for key in lobby.active_player_ids}})
    result = await apply_game_command(lobby.session_id, machine, hello, now=current)
    responses = [Message("queue.auto_started", {"message": "Váš rezervovaný čas nastal. Hra byla automaticky spuštěna."})]
    responses.extend(result.sender_messages)
    responses.extend(result.broadcast_messages)
    responses.extend(apply_lobby_score(lobby, machine))
    responses.append(Message("scenario.progress", build_scenario_progress(scenario, machine.state.snapshot())))
    save_lobbies(); save_sessions(); save_runtime_settings()
    await broadcast_lobby(lobby); await broadcast_session(lobby.session_id, responses)
    update = Message("runtime.settings", runtime_payload())
    for active_socket in list(getattr(app.state, "active_websockets", set())):
        try: await send_message(active_socket, update)
        except Exception: pass
    for admin_socket in list(authenticated_admin_sockets):
        try: await send_admin_overview(admin_socket)
        except Exception: pass
    return True

async def queue_monitor() -> None:
    while True:
        await start_due_queue_team(_local_now())
        await asyncio.sleep(1)

async def operations_monitor() -> None:
    while True:
        current = _local_now(); duration = int(runtime_settings.get("game_duration_minutes", 165))
        closing_text = str(runtime_settings.get("closing_time", "20:00"))
        try: closing_hour, closing_minute = map(int, closing_text.split(":"))
        except ValueError: closing_hour, closing_minute = 20, 0
        closing = current.replace(hour=closing_hour, minute=closing_minute, second=0, microsecond=0)
        event = configured_event()
        if event:
            try: closing = datetime.fromisoformat(str(event.get("ends_at", ""))).astimezone(current.tzinfo)
            except ValueError: pass
        changed = False
        for session_id, machine in active_sessions.items():
            lobby = lobby_registry.by_session.get(session_id); started_at = machine.state.flags.get("operations_started_at")
            if not lobby or not lobby.started or not started_at: continue
            if machine.state.flags.get("game_completed"):
                update = apply_outcome_score(machine, "completed", int(runtime_settings.get("completion_bonus", 100)))
                if update:
                    changed = True
                    for entry in global_leaderboard:
                        if str(entry.get("session_id", "")) == session_id:
                            entry["score"] = machine.state.score
                            save_leaderboard()
                    await broadcast_session(session_id, [update, machine._state_message()])
                if record_completed_result(session_id, lobby, machine):
                    changed = True
                    leaderboard_update = Message("leaderboard.update", {"entries": leaderboard_entries()})
                    for active_socket in list(getattr(app.state, "active_websockets", set())):
                        try: await send_message(active_socket, leaderboard_update)
                        except Exception: pass
                continue
            if machine.state.flags.get("administratively_ended") or machine.state.flags.get("out_of_competition"): continue
            extension = max(0, int(machine.state.flags.get("deadline_extension_minutes", 0)))
            try:
                duration_deadline = datetime.fromisoformat(str(started_at)).astimezone(current.tzinfo) + timedelta(minutes=duration + extension)
                deadline = duration_deadline if lobby.lobby_type == "online_doom" and event is None else min(duration_deadline, closing)
            except ValueError: continue
            if current >= deadline:
                ended_at = datetime.now(UTC).isoformat()
                penalty = max(0, min(1000, int(runtime_settings.get("deadline_penalty", 100))))
                updates = apply_deadline_end(machine, ended_at, penalty)
                changed = True
                await broadcast_session(session_id, updates)
                for terminal_socket in list(connected_terminal_sockets(session_id)):
                    await release_terminal(terminal_socket, session_id, "Čas hry vypršel. Terminál je znovu volný.")
                continue
            last_activity = machine.state.last_activity_at or str(started_at)
            try: inactive_seconds = (datetime.now(UTC) - datetime.fromisoformat(str(last_activity)).astimezone(UTC)).total_seconds()
            except ValueError: inactive_seconds = 0
            # Otevřené připojení znamená, že tým může stále řešit fyzickou část bez
            # zpráv do backendu. Za opuštěnou proto považujeme jen dlouho neaktivní
            # relaci, u níž už není online žádné hráčské zařízení.
            if inactive_seconds >= 3600 and not connected_client_ids(session_id):
                ended_at = datetime.now(UTC).isoformat()
                penalty = max(0, min(1000, int(runtime_settings.get("abandonment_penalty", 100))))
                updates = apply_operational_end(machine, ended_at, "abandoned", penalty, "Hra byla automaticky ukončena po hodině bez aktivity.")
                changed = True
                await broadcast_session(session_id, updates)
                for terminal_socket in list(connected_terminal_sockets(session_id)):
                    await release_terminal(terminal_socket, session_id, "Hra byla ukončena pro neaktivitu. Terminál je znovu volný.")
        if changed: save_sessions()
        await asyncio.sleep(30)


def apply_deadline_end(machine: EscapeBotStateMachine, ended_at: str, penalty: int) -> list[Message]:
    """Pause at the deadline and offer a single team decision."""
    if machine.state.flags.get("deadline_reached_at"):
        return []
    machine.state.flags["deadline_reached_at"] = ended_at
    machine.state.flags["deadline_choice_pending"] = True
    machine.state.flags["administratively_ended"] = True
    machine.state.flags["administratively_ended_at"] = ended_at
    machine.state.flags["administratively_ended_reason"] = "deadline"
    updates: list[Message] = []
    applied_penalty = 0
    if penalty and not machine.state.flags.get("deadline_penalty_applied"):
        applied_penalty = penalty
        score_before = machine.state.score
        adjustment = {
            "delta": -penalty,
            "amount": penalty,
            "reason": "Nedokončení hry v časovém limitu",
            "at": ended_at,
            "score_before": score_before,
            "score_after": score_before - penalty,
            "automatic": True,
        }
        machine.state.score -= penalty
        machine.state.flags["deadline_penalty_applied"] = True
        machine.state.flags.setdefault("admin_score_adjustments", []).append(adjustment)
        machine.state.flags.setdefault("admin_penalties", []).append(adjustment)
        updates.append(Message("score.update", {
            "score": machine.state.score,
            "delta": -penalty,
            "bonus": 0,
            "penalty": penalty,
            "reason": "deadline_penalty",
            "description": adjustment["reason"],
        }))
    # The deadline penalty belongs to the competitive result. Everything earned
    # or lost while finishing outside the time limit remains gameplay-only.
    machine.state.flags["competition_score"] = machine.state.score
    machine.state.flags["competition_score_frozen_at"] = ended_at
    suffix = f" Byl odečten postih {applied_penalty} bodů." if applied_penalty else ""
    updates.extend([
        Message("operations.stopped", {"reason": "deadline", "penalty": applied_penalty,
            "message": f"Časový limit hry vypršel.{suffix} Můžete hru ukončit, nebo dohrát mimo soutěž."}),
        machine._state_message(),
    ])
    return updates


def apply_outcome_score(machine: EscapeBotStateMachine, outcome: str, amount: int) -> Message | None:
    """Apply a configured outcome adjustment once, including restored historical sessions."""
    if outcome == "completed" and machine.state.flags.get("out_of_competition"):
        return None
    key = f"outcome_score_applied_{outcome}"
    if machine.state.flags.get(key) or amount <= 0:
        return None
    delta = amount if outcome == "completed" else -amount
    reason = "Bonus za úspěšné dokončení hry" if outcome == "completed" else "Postih za opuštění hry"
    at = datetime.now(UTC).isoformat()
    score_before = machine.state.score
    machine.state.score += delta
    machine.state.flags[key] = True
    adjustment = {"delta": delta, "amount": amount, "reason": reason, "at": at,
                  "score_before": score_before, "score_after": machine.state.score, "automatic": True}
    machine.state.flags.setdefault("admin_score_adjustments", []).append(adjustment)
    if delta < 0:
        machine.state.flags.setdefault("admin_penalties", []).append(adjustment)
    return Message("score.update", {"score": machine.state.score, "delta": delta,
        "bonus": max(0, delta), "penalty": max(0, -delta), "reason": f"outcome_{outcome}", "description": reason})


def apply_operational_end(machine: EscapeBotStateMachine, ended_at: str, reason: str, penalty: int, message: str) -> list[Message]:
    """End one unfinished session and audit the reason and optional one-time penalty."""
    machine.state.flags["administratively_ended"] = True
    machine.state.flags["administratively_ended_at"] = ended_at
    machine.state.flags["administratively_ended_reason"] = reason
    machine.state.flags["deadline_choice_pending"] = False
    updates: list[Message] = []
    if reason == "abandoned":
        update = apply_outcome_score(machine, "abandoned", penalty)
        if update: updates.append(update)
    machine.state.flags.setdefault("admin_actions", []).append({"action": "session_end", "label": message, "reason": reason, "at": ended_at})
    updates.extend([Message("operations.stopped", {"reason": reason, "penalty": penalty, "message": message}), machine._state_message()])
    return updates

global_leaderboard = []


def leaderboard_entries() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for stored in global_leaderboard:
        entry = dict(stored)
        if not entry.get("players"):
            lobby = lobby_registry.by_session.get(str(entry.get("session_id", "")))
            if lobby:
                entry["players"] = [str(player.get("name", "")) for player in lobby.players.values() if player.get("name")]
        entry.setdefault("players", [])
        lobby = lobby_registry.by_session.get(str(entry.get("session_id", "")))
        if not entry.get("scenario_id") and lobby:
            entry["scenario_id"] = lobby.scenario_id
        scenario_entry = scenario_catalog.entries.get(str(entry.get("scenario_id", "")))
        entry.setdefault("scenario_id", "legacy")
        entry.setdefault("game_title", scenario_entry.title if scenario_entry else "Starší výsledky")
        entry.setdefault("event_id", "")
        entry.setdefault("event_name", "")
        if entry.get("mode") not in {"solo", "team"}:
            # Starší záznamy režim neukládaly. Pokud už lobby není dostupná,
            # jediné jméno je nejspolehlivější zpětně kompatibilní vodítko.
            entry["mode"] = lobby.mode if lobby else ("solo" if len(entry["players"]) == 1 else "team")
        if not entry.get("duration_seconds"):
            machine = active_sessions.get(str(entry.get("session_id", "")))
            started_at = machine.state.flags.get("operations_started_at") if machine else None
            completed_at = entry.get("completed_at")
            if started_at and completed_at:
                try:
                    entry["duration_seconds"] = max(0, round((datetime.fromisoformat(str(completed_at)) - datetime.fromisoformat(str(started_at))).total_seconds()))
                except ValueError:
                    pass
        result.append(entry)
    return sorted(result, key=lambda item: (-int(item.get("score", 0)), int(item.get("duration_seconds") or 10**9)))

def result_duration_seconds(machine: EscapeBotStateMachine, completed_at: str) -> int | None:
    started_at = machine.state.flags.get("operations_started_at")
    if not started_at or not completed_at:
        return None
    try:
        return max(0, round((datetime.fromisoformat(str(completed_at)) - datetime.fromisoformat(str(started_at))).total_seconds()))
    except ValueError:
        return None

def leaderboard_identity(lobby: Lobby) -> dict[str, object]:
    event = configured_event()
    game_config = event_game_config(lobby.scenario_id) or {}
    scenario_entry = scenario_catalog.entries.get(lobby.scenario_id)
    return {
        "scenario_id": lobby.scenario_id,
        "game_title": scenario_entry.title if scenario_entry else lobby.scenario_id,
        "event_id": str(event.get("id", "")) if event else "",
        "event_name": str(event.get("name", "")) if event else "",
        "competition_role": str(game_config.get("role", "competitive")),
        "leaderboard_enabled": bool(game_config.get("leaderboard_enabled", True)),
        "competition_weight": float(game_config.get("weight", 1.0)),
    }

def leaderboard_score(machine: EscapeBotStateMachine) -> int:
    """Return the live score, or the competitive score frozen at the deadline."""
    frozen = machine.state.flags.get("competition_score")
    if frozen is not None:
        try:
            return int(frozen)
        except (TypeError, ValueError):
            pass
    return int(machine.state.score)

def record_completed_result(session_id: str, lobby: Lobby, machine: EscapeBotStateMachine) -> bool:
    """Persist one completed result while retaining event and scenario identity."""
    if leaderboard_is_finalized() or any(entry.get("session_id") == session_id for entry in global_leaderboard):
        return False
    completed_at = str(machine.state.flags.get("completed_at", ""))
    global_leaderboard.append({
        "entry_id": secrets.token_hex(8),
        "session_id": session_id,
        "name": lobby.team_name,
        "players": [str(player.get("name", "")) for player in lobby.players.values() if player.get("name")],
        "mode": lobby.mode,
        "score": leaderboard_score(machine),
        "duration_seconds": result_duration_seconds(machine, completed_at),
        "completed_at": completed_at,
        "out_of_competition": bool(machine.state.flags.get("out_of_competition")),
        "diploma_eligible": True,
        **leaderboard_identity(lobby),
    })
    save_leaderboard()
    return True

def save_leaderboard():
    storage.save_leaderboard(global_leaderboard)

def load_leaderboard():
    global global_leaderboard
    try:
        global_leaderboard = storage.load_leaderboard()
        changed = False
        for entry in global_leaderboard:
            if not entry.get("entry_id"):
                entry["entry_id"] = secrets.token_hex(8)
                changed = True
        if changed:
            save_leaderboard()
        logger.info(f"Úspěšně načtena Síň slávy ({len(global_leaderboard)} záznamů).")
    except Exception as e:
        logger.error(f"Chyba při načítání Síně slávy: {e}")

def save_sessions():
    data = {
        sid: session_command_adapters.setdefault(sid, GameSessionAdapter()).snapshot(sm)
        for sid, sm in active_sessions.items()
    }
    storage.save_sessions(data)

def load_sessions(_default_scenario):
    try:
        data = storage.load_sessions()
        for sid, s_data in data.items():
            lobby = lobby_registry.by_session.get(sid)
            entry = scenario_catalog.entries.get(lobby.scenario_id if lobby else selected_scenario_id)
            if entry is None:
                logger.error("Relace %s nebyla obnovena: scénář není dostupný.", sid)
                continue
            sm = EscapeBotStateMachine(entry.scenario, clock=lambda: datetime.now(UTC))
            session_command_adapters[sid] = GameSessionAdapter.restore(sm, s_data)
            active_sessions[sid] = sm
        logger.info(f"Úspěšně obnoveno {len(active_sessions)} uložených relací.")
    except Exception as e:
        logger.error(f"Chyba při načítání uložených relací: {e}")

def save_lobbies():
    storage.save_lobbies(lobby_registry.snapshot())

def load_lobbies():
    try:
        lobby_registry.restore(storage.load_lobbies())
    except Exception as error:
        logger.error(f"Chyba při načítání týmových lobby: {error}")

def load_runtime_settings():
    try:
        runtime_settings.update(storage.load_runtime_settings())
        stored = runtime_settings.get("display_announcements", [])
        if isinstance(stored, list):
            normalized = [result for item in stored if (result := normalize_display_announcement(item))]
            if normalized != stored:
                runtime_settings["display_announcements"] = normalized
                save_runtime_settings()
    except Exception as error:
        logger.error(f"Chyba nastavení režimu: {error}")

def save_runtime_settings():
    storage.save_runtime_settings(runtime_settings)

scenario_catalog = load_scenario_catalog(
    os.getenv("ESCAPEBOT_TEMPLATE_DIR", os.path.join(BASE_DIR, "backend", "content", "templates")),
    os.getenv("ESCAPEBOT_REALIZATION_DIR", os.path.join(BASE_DIR, "backend", "content", "realizations")),
)
selected_scenario_id = os.getenv("ESCAPEBOT_SCENARIO_ID", "hotel_kraskov")
selected_scenario = scenario_catalog.entries.get(selected_scenario_id)
if selected_scenario is None and scenario_catalog.entries:
    selected_scenario = next(iter(scenario_catalog.entries.values()))
scenario_available = selected_scenario is not None
scenario = selected_scenario.scenario if selected_scenario else Scenario({
    "id": "unavailable", "title": "Žádný platný scénář", "scenario_flow": [],
    "phases": {}, "rooms": {}, "puzzles": {}, "checkpoints": {}, "cipher_tools": {},
})
for scenario_error in scenario_catalog.errors:
    logger.error("Scénář nebyl načten (%s): %s", scenario_error["path"], scenario_error["message"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.check_ready()
    if os.getenv("ESCAPEBOT_ENV", "development").lower() == "production" and not ADMIN_TOKEN:
        raise RuntimeError("V produkci je povinná proměnná ESCAPEBOT_ADMIN_TOKEN.")
    load_leaderboard()
    load_lobbies()
    load_runtime_settings()
    # 1. Načtení uložených stavů her z předchozího běhu
    load_sessions(scenario)
    monitor_task = asyncio.create_task(operations_monitor())
    queue_monitor_task = asyncio.create_task(queue_monitor())
    yield
    monitor_task.cancel()
    queue_monitor_task.cancel()
    storage.close()

# --- Inicializace FastAPI ---
app = FastAPI(title="Escape Bot", lifespan=lifespan)
allowed_hosts = [item.strip() for item in os.getenv("ESCAPEBOT_ALLOWED_HOSTS", "*").split(",") if item.strip()]
for local_host in ("127.0.0.1", "localhost"):
    if local_host not in allowed_hosts:
        allowed_hosts.append(local_host)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["*"])

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # The WebGL vertical slice is embedded from this same origin. SAMEORIGIN
    # keeps third-party framing blocked while allowing the local PWA iframe.
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), microphone=()")
    if request.url.path in {"/", "/index.html", "/admin", "/display", "/display.html", "/sw.js"}:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    if os.getenv("ESCAPEBOT_ENV", "development").lower() == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def connected_client_ids(session_id: str) -> set[str]:
    lobby = lobby_registry.by_session.get(session_id)
    active_ids = set(lobby.active_player_ids) if lobby else set()
    return {
        str(connection_info[websocket].get("client_id", ""))
        for websocket in session_connections.get(session_id, set())
        if websocket in connection_info
        and connection_info[websocket].get("role") != "terminal"
        and str(connection_info[websocket].get("client_id", "")) in active_ids
    }


def connected_terminal_sockets(session_id: str) -> set[WebSocket]:
    return {
        websocket for websocket in session_connections.get(session_id, set())
        if connection_info.get(websocket, {}).get("role") == "terminal"
    }


def scenario_puzzle_key(scenario_id: str, puzzle_id: str) -> str:
    return f"{scenario_id}::{puzzle_id}"


def puzzle_play_mode(puzzle_id: str, scenario_id: str = "") -> str:
    configured = runtime_settings.get("puzzle_play_modes", {})
    value = str(configured.get(scenario_puzzle_key(scenario_id, puzzle_id), configured.get(puzzle_id, ""))) if isinstance(configured, dict) else ""
    if value in {"phones", "supplemental", "exclusive"}:
        return value
    configured_ids = set(runtime_settings.get("terminal_puzzle_ids", []))
    return "exclusive" if scenario_puzzle_key(scenario_id, puzzle_id) in configured_ids or puzzle_id in configured_ids else "phones"


def terminal_reservations() -> dict[str, dict[str, str]]:
    value = runtime_settings.setdefault("terminal_reservations", {})
    return value if isinstance(value, dict) else {}


def terminal_puzzle_is_available(state_machine: EscapeBotStateMachine, puzzle_id: str, scenario_id: str = "") -> bool:
    active_scenario = state_machine.scenario
    puzzle = active_scenario.data.get("puzzles", {}).get(puzzle_id, {})
    checkpoint_id = str(puzzle.get("checkpoint_id", ""))
    checkpoint = active_scenario.data.get("checkpoints", {}).get(checkpoint_id, {})
    checkpoint_state = state_machine.state.checkpoint_states.get(checkpoint_id, {})
    status = checkpoint_state.get("status")
    if puzzle_play_mode(puzzle_id, scenario_id) == "phones" or status == "solved" or not checkpoint:
        return False
    if status == "found":
        return True
    required_phase = checkpoint.get("requires_phase")
    if required_phase and state_machine.state.phase.value != required_phase:
        return False
    return all(state_machine.state.checkpoint_states.get(str(required), {}).get("status") == "solved"
               for required in checkpoint.get("requires", []))


def available_terminal_puzzles(state_machine: EscapeBotStateMachine, scenario_id: str = "") -> list[dict[str, str]]:
    """Return terminal-enabled puzzles that the team may currently open."""
    options = []
    for puzzle_id, puzzle in state_machine.scenario.data.get("puzzles", {}).items():
        if terminal_puzzle_is_available(state_machine, puzzle_id, scenario_id):
            options.append({"id": puzzle_id, "scenario_id": scenario_id, "title": str(puzzle.get("title", puzzle_id))})
    return options


def admin_puzzle_catalog() -> list[dict[str, str]]:
    """Return terminal settings grouped by physical scenario; online-only games are excluded."""
    items = []
    for entry in scenario_catalog.entries.values():
        modes = set(entry.modes)
        if not modes & {"on_site_qr", "physical_indoor", "physical_outdoor", "hybrid", "geo", "osm", "gnss", "location"}:
            continue
        for puzzle_id, puzzle in entry.scenario.data.get("puzzles", {}).items():
            items.append({
                "key": scenario_puzzle_key(entry.id, str(puzzle_id)),
                "id": str(puzzle_id), "scenario_id": entry.id, "scenario_title": entry.title,
                "title": str(puzzle.get("title", puzzle_id)), "type": str(puzzle.get("type", "unknown")),
                "checkpoint_id": str(puzzle.get("checkpoint_id", "")), "instructions": str(puzzle.get("instructions", "")),
                "play_mode": puzzle_play_mode(str(puzzle_id), entry.id),
            })
    return sorted(items, key=lambda item: (item["scenario_title"].casefold(), item["title"].casefold()))


def terminal_eligible_team_count(terminal_id: str = "") -> int:
    """Count online teams whose current game state permits scanning a terminal."""
    reservation = terminal_reservations().get(terminal_id, {}) if terminal_id else {}
    if not reservation:
        return 0
    count = 0
    for session_id, state_machine in active_sessions.items():
        lobby = lobby_registry.by_session.get(session_id)
        flags = state_machine.state.flags
        if not lobby or not lobby.started or flags.get("game_completed") or flags.get("administratively_ended"):
            continue
        if str(reservation.get("scenario_id", "")) != lobby.scenario_id:
            continue
        player_online = any(connection_info.get(sock, {}).get("role") != "terminal"
                            for sock in session_connections.get(session_id, set()))
        if not player_online:
            continue
        available = {item["id"] for item in available_terminal_puzzles(state_machine, lobby.scenario_id)}
        if str(reservation.get("puzzle_id", "")) in available:
            count += 1
    return count


def terminal_status_payload(terminal_id: str) -> dict[str, object]:
    reservation = terminal_reservations().get(terminal_id, {})
    scenario_id = str(reservation.get("scenario_id", ""))
    puzzle_id = str(reservation.get("puzzle_id", ""))
    entry = scenario_catalog.entries.get(scenario_id)
    puzzle = entry.scenario.data.get("puzzles", {}).get(puzzle_id, {}) if entry else {}
    return {
        "eligible_team_count": terminal_eligible_team_count(terminal_id),
        "puzzle_id": puzzle_id,
        "scenario_id": scenario_id,
        "scenario_title": entry.title if entry else scenario_id,
        "puzzle_title": str(puzzle.get("title", puzzle_id)),
        "reserved": bool(puzzle_id),
    }


def terminal_overview() -> list[dict[str, object]]:
    devices = []
    seen = set()
    for websocket, info in connection_info.items():
        terminal_id = str(info.get("terminal_id", ""))
        if not terminal_id or info.get("role") not in {"terminal_waiting", "terminal"} or terminal_id in seen:
            continue
        seen.add(terminal_id)
        reservation = terminal_reservations().get(terminal_id, {})
        session_id = str(info.get("session_id", ""))
        lobby = lobby_registry.by_session.get(session_id)
        devices.append({
            "id": terminal_id,
            "label": str(info.get("terminal_label", f"Terminál {terminal_id[-4:]}")),
            "status": "attached" if info.get("role") == "terminal" else "free",
            "session_id": session_id,
            "team_name": lobby.team_name if lobby else "",
            "scenario_id": str(reservation.get("scenario_id", "")),
            "puzzle_id": str(reservation.get("puzzle_id", "")),
        })
    return sorted(devices, key=lambda item: str(item["label"]).casefold())


def state_message_for(websocket: WebSocket, session_id: str, state_machine: EscapeBotStateMachine) -> Message:
    """Build a personalized snapshot and add presentation-only terminal status."""
    info = connection_info.get(websocket, {})
    player_id = str(info.get("client_id", ""))
    message = state_machine._state_message(player_id)
    attached = bool(connected_terminal_sockets(session_id))
    terminal_device = info.get("role") == "terminal"
    assigned = str(state_machine.state.flags.get("terminal_assignment", ""))
    lobby = lobby_registry.by_session.get(session_id)
    scenario_id = lobby.scenario_id if lobby else ""
    for puzzle in message.payload.get("puzzles", []):
        puzzle_id = str(puzzle.get("id", ""))
        play_mode = puzzle_play_mode(puzzle_id, scenario_id)
        if play_mode == "phones":
            puzzle.pop("terminal", None)
            continue
        configured = puzzle.get("terminal") if isinstance(puzzle.get("terminal"), dict) else {}
        puzzle["terminal"] = {
            "mode": play_mode,
            "label": str(configured.get("label", puzzle.get("title", "Herní terminál"))),
            "attached": attached,
            "device": terminal_device,
            "assigned": puzzle_id == assigned,
        }
    return message


def bind_terminal(websocket: WebSocket, session_id: str, controller_id: str) -> None:
    """Attach a display to an existing player identity without adding a lobby player."""
    previous = str(connection_info.get(websocket, {}).get("session_id", ""))
    if previous:
        session_connections.get(previous, set()).discard(websocket)
    previous_info = connection_info.get(websocket, {})
    connection_info[websocket] = {
        "session_id": session_id,
        "client_id": controller_id,
        "demo": False,
        "role": "terminal",
        "terminal_id": str(previous_info.get("terminal_id", "")),
        "terminal_label": str(previous_info.get("terminal_label", "")),
    }
    session_connections.setdefault(session_id, set()).add(websocket)


async def release_terminal_after_completion(websocket: WebSocket, session_id: str, delay_seconds: float) -> None:
    await asyncio.sleep(max(0, delay_seconds))
    await release_terminal(websocket, session_id, "Hádanka byla dokončena. Terminál je znovu volný.")


async def release_terminal(websocket: WebSocket, session_id: str, reason: str) -> None:
    info = connection_info.get(websocket, {})
    if info.get("role") != "terminal" or str(info.get("session_id", "")) != session_id:
        return
    session_connections.get(session_id, set()).discard(websocket)
    terminal_id = str(info.get("terminal_id", ""))
    terminal_label = str(info.get("terminal_label", ""))
    connection_info[websocket] = {"role": "terminal_waiting", "terminal_id": terminal_id,
                                  "terminal_label": terminal_label}
    machine = active_sessions.get(session_id)
    if machine and not connected_terminal_sockets(session_id):
        machine.state.flags.pop("terminal_assignment", None)
        save_sessions()
    try:
        await send_message(websocket, Message("terminal.released", {
            "reason": reason,
        }))
    except Exception:
        return
    if machine:
        await broadcast_session(session_id, [machine._state_message()])
    for admin_socket in list(authenticated_admin_sockets):
        try: await send_admin_overview(admin_socket)
        except Exception: pass


def schedule_completed_terminal_releases(session_id: str, state_machine: EscapeBotStateMachine) -> None:
    assigned = str(state_machine.state.flags.get("terminal_assignment", ""))
    puzzle = state_machine.scenario.data.get("puzzles", {}).get(assigned, {})
    checkpoint = state_machine.state.checkpoint_states.get(str(puzzle.get("checkpoint_id", "")), {})
    if not assigned or checkpoint.get("status") != "solved":
        return
    delay = float(puzzle.get("countdown_seconds", 10)) + 8.5 if puzzle.get("type") == "finale" else 3.5
    for terminal_socket in connected_terminal_sockets(session_id):
        info = connection_info.get(terminal_socket, {})
        if info.get("release_pending"):
            continue
        info["release_pending"] = True
        asyncio.create_task(release_terminal_after_completion(terminal_socket, session_id, delay))


async def send_message(websocket: WebSocket, message: Message) -> None:
    await websocket.send_text(json.dumps(message.to_json()))


async def broadcast_session(session_id: str, messages: list[Message], exclude: WebSocket | None = None) -> None:
    for websocket in list(session_connections.get(session_id, set())):
        if websocket is exclude:
            continue
        for message in messages:
            try:
                outgoing = message
                if message.type == "game.state" and session_id in active_sessions:
                    outgoing = state_message_for(websocket, session_id, active_sessions[session_id])
                    outgoing.request_id = message.request_id
                    outgoing.operation_id = message.operation_id
                await send_message(websocket, outgoing)
            except Exception:
                pass
    for admin_socket, watched_session in list(admin_spectator_sessions.items()):
        if watched_session != session_id or admin_socket is exclude:
            continue
        for message in messages:
            try:
                await send_message(admin_socket, message)
            except Exception:
                pass


async def broadcast_lobby(lobby: Lobby) -> None:
    connected = connected_client_ids(lobby.session_id)
    for websocket in list(session_connections.get(lobby.session_id, set())):
        info = connection_info.get(websocket, {})
        payload = lobby.public(str(info.get("client_id", "")), connected)
        try:
            await send_message(websocket, Message("lobby.state", payload))
        except Exception:
            pass


def attach_to_lobby(websocket: WebSocket, lobby: Lobby, client_id: str, demo_client: bool) -> None:
    previous = connection_info.get(websocket, {}).get("session_id")
    if previous:
        session_connections.get(str(previous), set()).discard(websocket)
    connection_info[websocket] = {
        "session_id": lobby.session_id,
        "client_id": client_id,
        "demo": demo_client,
    }
    session_connections.setdefault(lobby.session_id, set()).add(websocket)


def ensure_state_machine(session_id: str) -> EscapeBotStateMachine:
    if session_id not in active_sessions:
        lobby = lobby_registry.by_session.get(session_id)
        entry = scenario_catalog.entries.get(lobby.scenario_id if lobby else selected_scenario_id)
        if entry is None:
            raise ValueError("Scénář zvolený pro tuto lobby není dostupný.")
        active_sessions[session_id] = EscapeBotStateMachine(entry.scenario, clock=lambda: datetime.now(UTC))
    session_command_adapters.setdefault(session_id, GameSessionAdapter())
    return active_sessions[session_id]


async def apply_game_command(
    session_id: str,
    state_machine: EscapeBotStateMachine,
    message: Message,
    *,
    now: datetime | None = None,
) -> ApplyResult:
    adapter = session_command_adapters.setdefault(session_id, GameSessionAdapter())
    return await adapter.apply(state_machine, message, now=now)


def scenario_supports_lobby(entry, lobby_type: str) -> bool:
    modes = set(entry.modes)
    if lobby_type == "on_site_qr":
        return bool(modes & {"on_site_qr", "physical_indoor", "physical_outdoor", "hybrid"})
    if lobby_type == "online_doom":
        return bool(modes & {"online_doom", "doom", "online"})
    return bool(modes & {"geo", "osm", "gnss", "location"})


def apply_lobby_score(lobby: Lobby, state_machine: EscapeBotStateMachine) -> list[Message]:
    delta = lobby.score_delta()
    if not delta:
        return []
    state_machine.state.score += delta
    return [
        Message("score.update", {
            "score": state_machine.state.score,
            "delta": delta,
            "bonus": max(0, delta),
            "penalty": max(0, -delta),
            "reason": "team_size",
            "players": lobby.max_players,
        }),
        state_machine._state_message(),
    ]


def require_admin(payload: dict[str, object]) -> None:
    supplied = str(payload.get("admin_token", ""))
    if not ADMIN_TOKEN:
        raise ValueError("Admin režim není na backendu povolen.")
    if not hmac.compare_digest(supplied, ADMIN_TOKEN):
        raise ValueError("Neplatné administrátorské heslo.")


def admin_overview(watched_sessions: set[str] | None = None) -> list[dict[str, object]]:
    teams: list[dict[str, object]] = []
    for lobby in lobby_registry.by_session.values():
        machine = active_sessions.get(lobby.session_id)
        state = machine.state.snapshot() if machine else {}
        progress = build_scenario_progress(machine.scenario, state) if machine else {"nodes": []}
        nodes = list(progress.get("nodes", []))
        flags = state.get("flags", {})
        penalties = list(flags.get("admin_penalties", []))
        score_adjustments = list(flags.get("admin_score_adjustments", []))
        checkpoint_states = dict(state.get("checkpoint_states", {}))
        timeline: list[dict[str, object]] = []
        for checkpoint_id, checkpoint in checkpoint_states.items():
            found_at = checkpoint.get("first_scanned_at") or checkpoint.get("found_at")
            if found_at:
                timeline.append({"at": found_at, "type": "checkpoint_found", "label": checkpoint_id})
            if checkpoint.get("solved_at"):
                timeline.append({"at": checkpoint["solved_at"], "type": "checkpoint_solved", "label": checkpoint_id})
        recorded_adjustments = {(item.get("at"), item.get("reason")) for item in score_adjustments}
        for adjustment in score_adjustments:
            timeline.append({"at": adjustment.get("at", ""), "type": "admin_score_adjustment", "label": adjustment.get("reason", ""), "delta": adjustment.get("delta", 0)})
        for penalty in penalties:
            if (penalty.get("at"), penalty.get("reason")) not in recorded_adjustments:
                timeline.append({"at": penalty.get("at", ""), "type": "admin_penalty", "label": penalty.get("reason", ""), "amount": penalty.get("amount", 0)})
        for action in flags.get("admin_actions", []):
            timeline.append({"at": action.get("at", ""), "type": "admin_action", "label": action.get("label", "")})
        timeline.extend(list(state.get("event_history", [])))
        timeline.sort(key=lambda item: str(item.get("at", "")), reverse=True)
        karel_games = dict(state.get("karel_games", {}))
        sokoban_games = dict(state.get("sokoban_games", {}))
        line_games = dict(state.get("interactive_games", {}))
        triad_games = dict(state.get("triad_games", {}))
        archive_games = dict(state.get("archive_games", {}))
        connected_ids = connected_client_ids(lobby.session_id)
        line_player_games = []
        for game_id, container in line_games.items():
            stored_players = container.get("players", {}) if isinstance(container, dict) and isinstance(container.get("players"), dict) else {}
            for player_index, player_id in enumerate(lobby.players):
                game = stored_players.get(player_id, {}) if stored_players else (container if player_index == 0 and isinstance(container, dict) else {})
                line_player_games.append((game_id, player_id, game))
        triad_player_games = []
        for game_id, container in triad_games.items():
            stored_players = container.get("players", {}) if isinstance(container, dict) and isinstance(container.get("players"), dict) else {}
            for player_index, player_id in enumerate(lobby.players):
                game = stored_players.get(player_id, {}) if stored_players else (container if player_index == 0 and isinstance(container, dict) else {})
                triad_player_games.append((game_id, player_id, game))
        last_activity = str(state.get("last_activity_at", "")) or (str(timeline[0].get("at", "")) if timeline else "")
        if not last_activity:
            joined = [str(player.get("joined_at", "")) for player in lobby.players.values() if player.get("joined_at")]
            last_activity = min(joined) if joined else ""
        inactive_seconds = 0
        if last_activity:
            try: inactive_seconds = max(0, int((datetime.now(UTC) - datetime.fromisoformat(last_activity)).total_seconds()))
            except ValueError: pass
        game_completed = bool(flags.get("game_completed"))
        administratively_ended = bool(flags.get("administratively_ended"))
        activity_status = classify_activity(lobby.started, game_completed, inactive_seconds)
        terminal_options = available_terminal_puzzles(machine, lobby.scenario_id) if machine else []
        teams.append({
            **lobby.public("", connected_ids),
            "score": int(state.get("score", 1000)),
            "phase": str(state.get("phase", "boot")),
            "completed_nodes": sum(node.get("status") == "complete" for node in nodes),
            "total_nodes": len(nodes),
            "progress": progress,
            "admin_penalties": penalties,
            "admin_score_adjustments": score_adjustments,
            "last_activity": last_activity,
            "inactive_seconds": inactive_seconds,
            "activity_status": activity_status,
            "game_completed": game_completed,
            "administratively_ended": administratively_ended,
            "out_of_competition": bool(flags.get("out_of_competition")),
            "end_reason": str(flags.get("administratively_ended_reason", "completed" if game_completed else "")),
            "ended_at": str(flags.get("administratively_ended_at", flags.get("completed_at", ""))),
            "deadline_extension_minutes": int(flags.get("deadline_extension_minutes", 0)),
            "administratively_evaluated": bool(flags.get("administratively_evaluated")),
            "terminal_online": bool(connected_terminal_sockets(lobby.session_id)),
            "terminal_assignment": str(flags.get("terminal_assignment", "")),
            "terminal_options": terminal_options,
            "timeline": timeline,
            "hints_used": dict(state.get("hints_used", {})),
            "puzzle_attempts": dict(state.get("puzzle_attempts", {})),
            # A lobby can survive while its session snapshot is missing (for
            # example after an interrupted development reset). Keep it visible
            # to the administrator instead of failing the entire overview.
            "puzzle_telemetry": build_puzzle_telemetry(machine.scenario, state) if machine else [],
            "recent_messages": list(state.get("chat_history", []))[-8:],
            "support_chat": [item for item in state.get("chat_history", []) if item.get("channel") == "support"],
            "admin_support_joined": lobby.session_id in (watched_sessions or set()),
            "game_metrics": {
                "line": [{"id": game_id, "player_id": player_id, "player_name": str(lobby.players.get(player_id, {}).get("name", "Hráč")),
                          "connected": player_id in connected_ids,
                          "excluded": player_id in state.get("game_exclusions", {}).get(game_id, []), "status": game.get("status", "not_started"),
                          "swaps": game.get("swaps", 0), "progress": dict(game.get("progress", {})),
                          "result": state.get("game_results", {}).get(game_id, {}).get(player_id)}
                         for game_id, player_id, game in line_player_games],
                "karel": [{"id": game_id, "level": game.get("level_label", ""), "completed": len(game.get("completed_levels", [])),
                           "moves": game.get("total_moves", 0), "strikes": game.get("total_strikes", 0), "restarts": game.get("restarts", 0),
                           "player": list(game.get("player", [])), "rows": game.get("rows", 0), "columns": game.get("columns", 0),
                           "mines": list(game.get("mines", [])), "revealed": list(game.get("revealed", [])),
                           "exit": list(game.get("exit", [])), "safe_path": karel_safe_path({
                               "rows": game.get("rows", 0), "columns": game.get("columns", 0), "start": game.get("start", []),
                               "exit": game.get("exit", []), "mines": game.get("mines", []),
                           }) if game.get("rows") and game.get("columns") else []}
                          for game_id, game in karel_games.items()],
                "sokoban": [{"id": game_id, "level": game.get("level_label", ""), "completed": len(game.get("completed_levels", [])),
                              "moves": game.get("total_moves", 0), "pushes": game.get("total_pushes", 0), "restarts": game.get("restarts", 0),
                              "player": list(game.get("player", [])), "boxes": list(game.get("boxes", [])), "targets": list(game.get("targets", []))}
                             for game_id, game in sokoban_games.items()],
                "triad": [{"id": game_id, "player_id": player_id, "player_name": str(lobby.players.get(player_id, {}).get("name", "Hráč")),
                           "connected": player_id in connected_ids,
                           "excluded": player_id in state.get("game_exclusions", {}).get(game_id, []), "status": game.get("status", "not_started"),
                           "placements": game.get("placements", 0), "completed_orientations": list(game.get("completed_orientations", [])),
                           "result": state.get("game_results", {}).get(game_id, {}).get(player_id)}
                          for game_id, player_id, game in triad_player_games],
                "archive": [{"id": game_id, "assembled": bool(game.get("assembled")), "moves": int(game.get("moves", 0)),
                             "order": list(game.get("order", [])), "rotations": dict(game.get("rotations", {}))}
                            for game_id, game in archive_games.items()],
            },
        })
    return sorted(teams, key=lambda team: str(team.get("team_name", "")).casefold())


async def send_admin_overview(websocket: WebSocket) -> None:
    disabled_scenarios = set(runtime_settings.get("disabled_scenario_ids", []))
    await send_message(websocket, Message("admin.overview", {
        "teams": admin_overview(admin_support_sessions.get(websocket, set())),
        "leaderboard": leaderboard_entries(),
        "admin_capabilities": admin_capabilities_payload(),
        "abandonment_thresholds": {"suspicious_seconds": 1800, "abandoned_seconds": 3600},
        "resolution_presets": ADMIN_RESOLUTION_PRESETS,
        "scenario_catalog": [{**entry.public(), "enabled": entry.id not in disabled_scenarios}
                             for entry in scenario_catalog.entries.values()],
        "scenario_errors": scenario_catalog.errors,
        "selected_scenario_id": selected_scenario.id if selected_scenario else "",
        "puzzle_catalog": admin_puzzle_catalog(),
        "terminals": terminal_overview(),
        "display_status": display_status_payload(),
    }))


async def push_admin_support_update(session_id: str) -> None:
    lobby = lobby_registry.by_session.get(session_id)
    machine = active_sessions.get(session_id)
    if not lobby or not machine:
        return
    payload = {
        "session_id": session_id,
        "team_name": lobby.team_name,
        "support_chat": [item for item in machine.state.chat_history if item.get("channel") == "support"],
    }
    for admin_socket in list(authenticated_admin_sockets):
        try:
            await send_message(admin_socket, Message("admin.support_update", payload))
        except Exception:
            pass


async def sync_started_client(websocket: WebSocket, state_machine: EscapeBotStateMachine, demo_client: bool) -> None:
    """Send a complete authoritative snapshot after join, resume, or device wake-up."""
    info = connection_info.get(websocket, {})
    player_id = str(info.get("client_id", ""))
    lobby = lobby_registry.by_session.get(str(info.get("session_id", "")))
    if lobby:
        state_machine._current_player_id = player_id or state_machine._current_player_id
        state_machine._participant_ids = lobby.active_player_ids
        state_machine._team_mode = lobby.mode
        state_machine._participant_names = {player_id: str(lobby.players[player_id].get("name", "Hráč")) for player_id in lobby.active_player_ids}
    if state_machine.state.flags.get("administratively_ended"):
        await send_message(websocket, state_message_for(websocket, str(info.get("session_id", "")), state_machine))
        await send_message(websocket, Message("operations.stopped", {"message": "Tato hra už byla ukončena a čeká na vyhodnocení."}))
        return
    await send_message(websocket, Message("chat.history", {"messages": state_machine.state.chat_history}))
    await send_message(websocket, state_message_for(websocket, str(info.get("session_id", "")), state_machine))
    await send_message(websocket, Message(
        "scenario.progress",
        build_scenario_progress(state_machine.scenario, state_machine.state.snapshot()),
    ))
    if demo_client:
        await send_message(websocket, Message("demo.catalog", {
            "enabled": True,
            "checkpoints": build_demo_checkpoint_catalog(state_machine.scenario),
        }))
    await send_message(websocket, Message("runtime.settings", runtime_payload()))


async def leave_lobby_player(websocket: WebSocket, lobby: Lobby, client_id: str, operation_id: str) -> None:
    """Persist an explicit player departure without deleting historical identity."""
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", operation_id):
        raise ValueError("Odchodu ze hry chybí platné operation_id.")
    now = datetime.now(UTC).isoformat()
    result = lobby.leave_player(client_id, operation_id, now)
    if not result["changed"]:
        await send_message(websocket, Message("lobby.left", result, operation_id=operation_id))
        return

    active_ids = lobby.active_player_ids
    machine = active_sessions.get(lobby.session_id)
    updates: list[Message] = []
    if machine:
        machine._participant_ids = active_ids
        machine._participant_names = {player_id: str(lobby.players[player_id].get("name", "Hráč")) for player_id in active_ids}
        machine.state.event_history.append({
            "at": now,
            "type": "lobby.leave",
            "details": {"player_id": client_id, "remaining_players": str(len(active_ids))},
        })
        machine.state.event_history = machine.state.event_history[-500:]

    ended = False
    if not active_ids:
        if lobby.join_code:
            lobby_registry.by_join_code.pop(lobby.join_code, None)
            lobby.join_code = None
        dequeue_team(lobby.session_id)
        if lobby.started and machine and not machine.state.flags.get("game_completed") and not machine.state.flags.get("administratively_ended"):
            penalty = max(0, min(1000, int(runtime_settings.get("abandonment_penalty", 100))))
            updates = apply_operational_end(
                machine,
                now,
                "abandoned",
                penalty,
                "Poslední aktivní hráč opustil hru; relace byla ukončena jako opuštěná.",
            )
            ended = True
    result["game_ended"] = ended
    lobby.leave_receipts[f"{client_id}:{operation_id}"] = dict(result)
    save_lobbies()
    if machine:
        save_sessions()
    if not active_ids:
        save_runtime_settings()

    await broadcast_lobby(lobby)
    if updates:
        await broadcast_session(lobby.session_id, updates)
    for player_socket in list(session_connections.get(lobby.session_id, set())):
        if str(connection_info.get(player_socket, {}).get("client_id", "")) != client_id:
            continue
        try:
            await send_message(player_socket, Message("lobby.left", result, operation_id=operation_id))
        except Exception:
            pass
    if not active_ids:
        runtime_update = Message("runtime.settings", runtime_payload())
        for active_socket in list(getattr(app.state, "active_websockets", set())):
            try: await send_message(active_socket, runtime_update)
            except Exception: pass
    for admin_socket in list(authenticated_admin_sockets):
        try: await send_admin_overview(admin_socket)
        except Exception: pass


@app.get("/api/qr")
async def qr_code(data: str) -> Response:
    if not data or len(data) > 500:
        return Response(status_code=400)
    try:
        import qrcode
        image = qrcode.make(data)
        output = BytesIO()
        image.save(output, format="PNG")
        return Response(content=output.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})
    except ImportError:
        return Response(content="QR generator není nainstalován.", status_code=503, media_type="text/plain")


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "environment": os.getenv("ESCAPEBOT_ENV", "development")}


@app.get("/api/ready")
async def ready() -> JSONResponse:
    try:
        storage_status = storage.check_ready()
    except Exception as error:
        logger.warning("Kontrola připravenosti úložiště selhala: %s", error)
        return JSONResponse({"status": "not_ready", "storage": {"backend": storage.backend_name}}, status_code=503)
    return JSONResponse({"status": "ready", "storage": storage_status, "active_sessions": len(active_sessions)})


@app.get("/api/captive")
async def captive_portal_status() -> Response:
    """CAPPORT stav lokální herní sítě podle RFC 8908."""
    return Response(
        content=json.dumps({
            "captive": True,
            "user-portal-url": "https://10.42.0.1:8088/",
            "venue-info-url": "https://10.42.0.1:8088/",
        }),
        media_type="application/captive+json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/world-geometry/{geometry_id}")
async def world_geometry(geometry_id: str) -> Response:
    assets = {
        "pardubice_center": os.path.join(BASE_DIR, "backend", "content", "maps", "pardubice_center.geometry.json"),
    }
    path = assets.get(geometry_id)
    if path is None or not os.path.isfile(path):
        return JSONResponse({"error": "Geometrie mapy není dostupná."}, status_code=404)
    with open(path, "r", encoding="utf-8") as source:
        content = source.read()
    return Response(content=content, media_type="application/json", headers={"Cache-Control": "no-store"})


@app.get("/admin")
async def admin_page() -> RedirectResponse:
    return RedirectResponse(url="/?admin=1", status_code=307)

@app.get("/display")
async def public_display_page() -> RedirectResponse:
    return RedirectResponse(url="/display.html", status_code=307)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await send_message(websocket, Message("runtime.settings", runtime_payload()))
    logger.info("Nový klient připojen přes WebSockets, čekám na relaci...")
    session_id = None
    state_machine = None
    demo_client = False
    client_id = None
    
    if not hasattr(app.state, "active_websockets"):
        app.state.active_websockets = set()
    app.state.active_websockets.add(websocket)

    try:
        while True:
            message_str = await websocket.receive_text()
            try:
                data = json.loads(message_str)
                msg = Message.from_json(data)

                if msg.type in ADMIN_MESSAGE_TYPES:
                    try:
                        require_admin(msg.payload)
                        authenticated_admin_sockets.add(websocket)
                        if msg.type == "admin.list":
                            await send_admin_overview(websocket)
                            await send_message(websocket, Message("runtime.settings", runtime_payload()))
                            continue
                        if msg.type == "admin.qr_set":
                            requested_id = str(msg.payload.get("scenario_id", selected_scenario.id if selected_scenario else ""))
                            entry = scenario_catalog.entries.get(requested_id)
                            if entry is None:
                                raise ValueError("Požadovaný scénář není v katalogu dostupný.")
                            await send_message(websocket, Message("admin.qr_set", {"scenario": entry.scenario.data.get("title", "Escape Bot"), "checkpoints": build_checkpoint_qr_set(entry.scenario)}))
                            continue
                        if msg.type == "admin.scenario_source":
                            requested_id = str(msg.payload.get("scenario_id", selected_scenario.id if selected_scenario else ""))
                            entry = scenario_catalog.entries.get(requested_id)
                            if entry is None:
                                raise ValueError("Požadovaný scénář není v katalogu dostupný.")
                            await send_message(websocket, Message("admin.scenario_source", {
                                "scenario_id": entry.id,
                                "template": entry.template,
                                "realization": entry.realization,
                            }))
                            continue
                        if msg.type == "admin.scenario_validate":
                            template = msg.payload.get("template")
                            realization = msg.payload.get("realization")
                            if not isinstance(template, dict) or not isinstance(realization, dict):
                                raise ValueError("Editor musí odeslat šablonu i realizaci jako objekty JSON.")
                            compiled = compose_documents(template, realization)
                            candidate = Scenario(compiled.data, compiled.provenance)
                            from .scenario import validate_checkpoint_navigation
                            validate_checkpoint_navigation(candidate)
                            await send_message(websocket, Message("admin.scenario_validation", {
                                "valid": True, "scenario_id": realization.get("id", ""),
                                "title": compiled.data.get("title", ""), "provenance": compiled.provenance,
                            }))
                            continue
                        if msg.type == "admin.terminal_catalog":
                            requested = msg.payload.get("puzzle_ids", [])
                            if not isinstance(requested, list):
                                raise ValueError("Katalog terminálu musí být seznam hádanek.")
                            known = {item["key"] for item in admin_puzzle_catalog()}
                            puzzle_ids = list(dict.fromkeys(str(item) for item in requested))
                            if not puzzle_ids or any(item not in known for item in puzzle_ids):
                                raise ValueError("Vyberte alespoň jednu platnou hádanku pro terminál.")
                            runtime_settings["terminal_puzzle_ids"] = puzzle_ids
                            previous_modes = runtime_settings.get("puzzle_play_modes", {})
                            runtime_settings["puzzle_play_modes"] = {
                                puzzle_key: (
                                    str(previous_modes.get(puzzle_key))
                                    if puzzle_key in puzzle_ids and str(previous_modes.get(puzzle_key)) in {"supplemental", "exclusive"}
                                    else "supplemental" if puzzle_key in puzzle_ids else "phones"
                                ) for puzzle_key in known
                            }
                            for terminal_id, reservation in list(terminal_reservations().items()):
                                key = scenario_puzzle_key(str(reservation.get("scenario_id", "")), str(reservation.get("puzzle_id", "")))
                                if key not in puzzle_ids:
                                    terminal_reservations().pop(terminal_id, None)
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try:
                                    await send_message(active_socket, update)
                                    info = connection_info.get(active_socket, {})
                                    if info.get("role") == "terminal_waiting":
                                        await send_message(active_socket, Message("terminal.status", terminal_status_payload(str(info.get("terminal_id", "")))))
                                except Exception: pass
                            for active_session, machine in active_sessions.items():
                                await broadcast_session(active_session, [machine._state_message()])
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.scenario_play_modes":
                            requested = msg.payload.get("modes", {})
                            known = {item["key"] for item in admin_puzzle_catalog()}
                            if not isinstance(requested, dict) or set(requested) != known:
                                raise ValueError("Nastavení musí obsahovat všechny hádanky scénáře.")
                            modes = {str(key): str(value) for key, value in requested.items()}
                            if any(value not in {"phones", "supplemental", "exclusive"} for value in modes.values()):
                                raise ValueError("Neplatný způsob hraní hádanky.")
                            runtime_settings["puzzle_play_modes"] = modes
                            runtime_settings["terminal_puzzle_ids"] = [key for key, value in modes.items() if value != "phones"]
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            for active_session, machine in active_sessions.items():
                                await broadcast_session(active_session, [machine._state_message()])
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.scenario_availability":
                            requested = msg.payload.get("enabled_scenario_ids", [])
                            if not isinstance(requested, list):
                                raise ValueError("Seznam povolených scénářů nemá platný formát.")
                            enabled = set(str(item) for item in requested)
                            known = set(scenario_catalog.entries)
                            if not enabled or not enabled <= known:
                                raise ValueError("Musí zůstat povolený alespoň jeden platný scénář.")
                            runtime_settings["disabled_scenario_ids"] = sorted(known - enabled)
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.terminal_reserve":
                            terminal_id = str(msg.payload.get("terminal_id", "")).strip()
                            scenario_id = str(msg.payload.get("scenario_id", "")).strip()
                            terminal_socket = next((sock for sock, info in connection_info.items()
                                                    if info.get("role") == "terminal_waiting" and info.get("terminal_id") == terminal_id), None)
                            if terminal_socket is None:
                                raise ValueError("Terminál už není volný nebo není online.")
                            puzzle_id = str(msg.payload.get("puzzle_id", "")).strip()
                            if not puzzle_id:
                                terminal_reservations().pop(terminal_id, None)
                            else:
                                valid = {(item["scenario_id"], item["id"]) for item in admin_puzzle_catalog() if item["play_mode"] != "phones"}
                                if (scenario_id, puzzle_id) not in valid:
                                    raise ValueError("Vyberte hádanku povolenou pro terminály.")
                                terminal_reservations()[terminal_id] = {"scenario_id": scenario_id, "puzzle_id": puzzle_id}
                            save_runtime_settings()
                            await send_message(terminal_socket, Message("terminal.status", terminal_status_payload(terminal_id)))
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.terminal_release":
                            terminal_id = str(msg.payload.get("terminal_id", "")).strip()
                            terminal_socket = next((sock for sock, info in connection_info.items()
                                                    if info.get("role") == "terminal" and info.get("terminal_id") == terminal_id), None)
                            if terminal_socket is None:
                                raise ValueError("Terminál už není připojený ke hře.")
                            terminal_session = str(connection_info[terminal_socket].get("session_id", ""))
                            await release_terminal(terminal_socket, terminal_session, "Terminál odpojil Game Master.")
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.online_mode":
                            runtime_settings["online_mode"] = bool(msg.payload.get("enabled"))
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            continue
                        if msg.type == "admin.launch_mode":
                            mode = str(msg.payload.get("mode", ""))
                            if mode not in {"free", "managed"}: raise ValueError("Neznámý režim spouštění.")
                            runtime_settings["launch_mode"] = mode
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.team_create":
                            if runtime_settings.get("launch_mode", "free") != "managed":
                                raise ValueError("Administrátorské lobby lze zakládat pouze v řízeném režimu.")
                            lobby = lobby_registry.create_managed(str(msg.payload.get("team_name", "")))
                            ensure_state_machine(lobby.session_id)
                            save_lobbies(); save_sessions()
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.team_add_player":
                            target_session = str(msg.payload.get("session_id", ""))
                            lobby = lobby_registry.by_session.get(target_session)
                            if lobby is None or lobby.started: raise ValueError("Cílová lobby už není dostupná.")
                            player_code = str(msg.payload.get("player_code", "")).strip().upper().removeprefix("ESCAPEBOT://PLAYER/")
                            waiting = waiting_players.pop(player_code, None)
                            if waiting is None: raise ValueError("Hráčské ID není platné nebo už bylo použito.")
                            waiting_socket = waiting["websocket"]
                            waiting_client_id = str(waiting["client_id"])
                            lobby.add_player(waiting_client_id, str(waiting.get("name", "")))
                            attach_to_lobby(waiting_socket, lobby, waiting_client_id, bool(waiting.get("demo")))
                            save_lobbies(); await broadcast_lobby(lobby)
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.queue_expedite":
                            target_session = str(msg.payload.get("session_id", ""))
                            queue = clean_start_queue()
                            if not queue or queue[0]["session_id"] != target_session:
                                raise ValueError("Zkrátit čekání lze pouze prvnímu týmu ve frontě.")
                            result = expedite_queue_head()
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.team_start":
                            target_session = str(msg.payload.get("session_id", ""))
                            lobby = lobby_registry.by_session.get(target_session)
                            if lobby is None: raise ValueError("Tým už neexistuje.")
                            if lobby.started: raise ValueError("Hra tohoto týmu už byla spuštěna.")
                            if not lobby.active_player_ids: raise ValueError("Před spuštěním se musí připojit alespoň jeden hráč.")
                            require_admin_start_available(bool(msg.payload.get("override_soft")))
                            lobby.started = True
                            machine = ensure_state_machine(target_session)
                            machine.state.flags["operations_started_at"] = datetime.now(UTC).isoformat()
                            machine.state.flags["managed_start"] = True
                            dequeue_team(target_session)
                            first_player = lobby.active_player_ids[0]
                            hello = Message("client.hello", {"session_id": target_session, "demo_mode": False,
                                "_client_id": first_player, "_participant_ids": lobby.active_player_ids, "_team_mode": lobby.mode,
                                "_participant_names": {key: str(lobby.players[key].get("name", "Hráč")) for key in lobby.active_player_ids}})
                            result = await apply_game_command(target_session, machine, hello)
                            responses = [*result.sender_messages, *result.broadcast_messages]
                            responses.extend(apply_lobby_score(lobby, machine))
                            responses.append(Message("scenario.progress", build_scenario_progress(scenario, machine.state.snapshot())))
                            save_lobbies(); save_sessions(); save_runtime_settings()
                            await broadcast_lobby(lobby); await broadcast_session(target_session, responses)
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket)
                            continue
                        if msg.type == "admin.schedule_settings":
                            values = {"max_active_teams": int(msg.payload.get("max_active_teams", 4)),
                                      "soft_start_interval_minutes": int(msg.payload.get("soft_start_interval_minutes", 15)),
                                      "hard_start_interval_minutes": int(msg.payload.get("hard_start_interval_minutes", 5)),
                                      "game_duration_minutes": int(msg.payload.get("game_duration_minutes", 165)),
                                      "deadline_penalty": int(msg.payload.get("deadline_penalty", 100)),
                                      "abandonment_penalty": int(msg.payload.get("abandonment_penalty", 100)),
                                      "completion_bonus": int(msg.payload.get("completion_bonus", 100)),
                                      "opening_time": str(msg.payload.get("opening_time", "08:00")),
                                      "closing_time": str(msg.payload.get("closing_time", "20:00")),
                                      "timezone": str(msg.payload.get("timezone", "Europe/Prague"))}
                            if not 1 <= values["max_active_teams"] <= 100: raise ValueError("Kapacita musí být 1–100 týmů.")
                            if not 0 <= values["hard_start_interval_minutes"] <= 240: raise ValueError("Hard rozestup musí být 0–240 minut.")
                            if not values["hard_start_interval_minutes"] <= values["soft_start_interval_minutes"] <= 240: raise ValueError("Soft rozestup musí být mezi hard limitem a 240 minutami.")
                            if not 15 <= values["game_duration_minutes"] <= 720: raise ValueError("Délka hry musí být 15–720 minut.")
                            if not 0 <= values["deadline_penalty"] <= 1000: raise ValueError("Postih za nedokončení musí být 0–1000 bodů.")
                            if not 0 <= values["abandonment_penalty"] <= 1000: raise ValueError("Postih za opuštění musí být 0–1000 bodů.")
                            if not 0 <= values["completion_bonus"] <= 1000: raise ValueError("Bonus za dokončení musí být 0–1000 bodů.")
                            for key in ("opening_time", "closing_time"):
                                datetime.strptime(values[key], "%H:%M")
                            ZoneInfo(values["timezone"])
                            values["start_interval_minutes"] = values["soft_start_interval_minutes"]
                            runtime_settings.update(values); save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket); continue
                        if msg.type == "admin.event_settings":
                            event_id = str(msg.payload.get("id", "")).strip()
                            if not event_id:
                                runtime_settings["event"] = {"id": "", "name": "", "starts_at": "", "ends_at": "", "status": "draft", "primary_game_id": "", "games": [], "scenario_ids": [], "leaderboard_finalized": False, "leaderboard_finalized_at": ""}
                            else:
                                starts_at = datetime.fromisoformat(str(msg.payload.get("starts_at", "")))
                                ends_at = datetime.fromisoformat(str(msg.payload.get("ends_at", "")))
                                if starts_at.tzinfo is None or ends_at.tzinfo is None: raise ValueError("Časy eventu musí obsahovat časovou zónu.")
                                if starts_at >= ends_at: raise ValueError("Konec eventu musí následovat po jeho začátku.")
                                raw_games = msg.payload.get("games", [])
                                if not isinstance(raw_games, list): raise ValueError("Konfigurace her eventu musí být seznam.")
                                games = normalize_event({"games": raw_games, "primary_game_id": msg.payload.get("primary_game_id", "")})["games"]
                                scenario_ids = [str(item["game_id"]) for item in games]
                                unknown = [item for item in scenario_ids if item not in scenario_catalog.entries]
                                if not scenario_ids: raise ValueError("Event musí obsahovat alespoň jednu hru.")
                                if unknown: raise ValueError("Event odkazuje na neznámé hry: " + ", ".join(unknown))
                                primary_ids = [item["game_id"] for item in games if item["role"] == "primary"]
                                if len(primary_ids) != 1: raise ValueError("Event musí mít právě jednu hlavní hru.")
                                status = str(msg.payload.get("status", "draft"))
                                if status not in {"draft", "ready", "open", "paused", "ended", "archived"}: raise ValueError("Neznámý stav eventu.")
                                event_timezone = str(msg.payload.get("timezone", runtime_settings.get("timezone", "Europe/Prague")))
                                ZoneInfo(event_timezone)
                                previous = configured_event()
                                same_event = previous is not None and str(previous.get("id")) == event_id
                                runtime_settings["event"] = {"id": event_id, "name": str(msg.payload.get("name", "")).strip() or event_id,
                                    "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(), "scenario_ids": scenario_ids,
                                    "status": status, "timezone": event_timezone,
                                    "primary_game_id": primary_ids[0], "games": games,
                                    "branding": {"title": str(msg.payload.get("branding_title", "")).strip(),
                                                 "logo_url": str(msg.payload.get("branding_logo_url", "")).strip(),
                                                 "accent_color": str(msg.payload.get("branding_accent_color", "#65f7ff")).strip()},
                                    "leaderboard_finalized": bool(previous.get("leaderboard_finalized", False)) if same_event else False,
                                    "leaderboard_finalized_at": str(previous.get("leaderboard_finalized_at", "")) if same_event else ""}
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket); continue
                        if msg.type == "admin.display_announcements":
                            raw_announcements = msg.payload.get("announcements", [])
                            if not isinstance(raw_announcements, list): raise ValueError("Oznámení musí být seznam položek.")
                            announcements = [result for item in raw_announcements if (result := normalize_display_announcement(item))]
                            if len(announcements) > 20 or any(len(item["text"]) > 500 for item in announcements):
                                raise ValueError("Lze uložit nejvýše 20 oznámení, každé do 500 znaků.")
                            for item in announcements:
                                for key in ("starts_at", "ends_at"):
                                    if item[key]: datetime.fromisoformat(item[key])
                                if item["override_until"]: datetime.fromisoformat(item["override_until"])
                                if len(item["link_url"]) > 500 or len(item["link_label"]) > 80: raise ValueError("Odkaz oznámení je příliš dlouhý.")
                                event = configured_event()
                                if item["game_id"] and not item["event_id"]: raise ValueError("Oznámení hry musí patřit eventu.")
                                if item["event_id"] and (event is None or item["event_id"] != event["id"]): raise ValueError("Oznámení odkazuje na jiný než aktivní event.")
                                if item["game_id"] and item["game_id"] not in event["scenario_ids"]: raise ValueError("Oznámení odkazuje na hru mimo aktivní event.")
                                if item["priority"] == "emergency" and item["override_minutes"] and not item["override_until"]:
                                    item["override_until"] = (datetime.now(UTC) + timedelta(minutes=float(item["override_minutes"]))).isoformat()
                                if item["priority"] != "emergency": item["override_until"] = ""
                            runtime_settings["display_announcements"] = announcements
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket); continue
                        if msg.type == "admin.display_leaderboard":
                            runtime_settings["display_leaderboard"] = bool(msg.payload.get("enabled"))
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            continue
                        if msg.type == "admin.operations":
                            enabled = bool(msg.payload.get("enabled")); runtime_settings["gameplay_enabled"] = enabled
                            if not enabled:
                                ended_at = datetime.now(UTC).isoformat()
                                for session_id, machine in active_sessions.items():
                                    lobby_item = lobby_registry.by_session.get(session_id)
                                    if lobby_item and lobby_item.started and not machine.state.flags.get("game_completed"):
                                        machine.state.flags["administratively_ended"] = True
                                        machine.state.flags["administratively_ended_at"] = ended_at
                                        machine.state.flags["administratively_ended_reason"] = "manual"
                                        machine.state.flags["deadline_choice_pending"] = False
                                        await broadcast_session(session_id, [Message("operations.stopped", {"message": "Herní provoz byl ukončen Game Masterem. Výsledek týmu je připraven k vyhodnocení."}), machine._state_message()])
                                        for terminal_socket in list(connected_terminal_sockets(session_id)):
                                            await release_terminal(terminal_socket, session_id, "Herní provoz byl ukončen. Terminál je znovu volný.")
                            save_runtime_settings(); save_sessions()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket); continue
                        if msg.type == "admin.leaderboard_delete":
                            if leaderboard_is_finalized():
                                raise ValueError("Uzavřené celkové pořadí už nelze měnit.")
                            entry_id = str(msg.payload.get("entry_id", "")).strip()
                            index = next((index for index, entry in enumerate(global_leaderboard) if str(entry.get("entry_id", "")) == entry_id), None)
                            if index is None:
                                raise ValueError("Záznam v Síni slávy už neexistuje.")
                            removed = global_leaderboard.pop(index)
                            save_leaderboard()
                            update = Message("leaderboard.update", {"entries": leaderboard_entries()})
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket)
                            logger.info("Admin odstranil výsledek týmu %s ze Síně slávy.", removed.get("name", ""))
                            continue
                        if msg.type == "admin.leaderboard_finalize":
                            if runtime_settings.get("gameplay_enabled", True):
                                raise ValueError("Nejprve zastavte herní provoz. Po uzavření pořadí už nelze bezpečně přijímat další výsledky.")
                            event = configured_event()
                            if event is None:
                                raise ValueError("Diplomy za umístění lze uzavřít pouze pro definovaný event.")
                            event["leaderboard_finalized"] = True
                            event["leaderboard_finalized_at"] = datetime.now(UTC).isoformat()
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket)
                            continue

                        target_session = str(msg.payload.get("session_id", "")).strip()
                        lobby = lobby_registry.by_session.get(target_session)
                        if lobby is None:
                            raise ValueError("Týmová relace už neexistuje.")

                        if msg.type == "admin.terminal_assign":
                            machine = ensure_state_machine(target_session)
                            puzzle_id = str(msg.payload.get("puzzle_id", "")).strip()
                            allowed = set(runtime_settings.get("terminal_puzzle_ids", []))
                            puzzle = scenario.data.get("puzzles", {}).get(puzzle_id)
                            if not connected_terminal_sockets(target_session):
                                raise ValueError("Nejprve k tomuto týmu připojte herní terminál.")
                            if puzzle_id not in allowed or not puzzle:
                                raise ValueError("Tato hádanka není v globálním katalogu terminálu.")
                            checkpoint = machine.state.checkpoint_states.get(str(puzzle.get("checkpoint_id", "")), {})
                            if checkpoint.get("status") != "found":
                                raise ValueError("Na terminál lze přidělit pouze právě dostupnou hádanku.")
                            machine.state.flags["terminal_assignment"] = puzzle_id
                            machine.state.flags.setdefault("admin_actions", []).append({
                                "action": "terminal_assign",
                                "label": f"Terminál: {puzzle.get('title', puzzle_id)}",
                                "at": datetime.now(UTC).isoformat(),
                                "puzzle_id": puzzle_id,
                            })
                            save_sessions()
                            await broadcast_session(target_session, [machine._state_message()])
                            await send_admin_overview(websocket)
                            continue

                        if msg.type == "admin.spectate_start":
                            machine = ensure_state_machine(target_session)
                            admin_spectator_sessions[websocket] = target_session
                            await send_message(websocket, Message("admin.spectate_started", {"session_id": target_session, "team_name": lobby.team_name}))
                            await send_message(websocket, Message("chat.history", {"messages": machine.state.chat_history}))
                            await send_message(websocket, machine._state_message())
                            await send_message(websocket, Message("scenario.progress", build_scenario_progress(machine.scenario, machine.state.snapshot())))
                            await send_message(websocket, Message("runtime.settings", runtime_payload()))
                            continue
                        if msg.type == "admin.spectate_stop":
                            admin_spectator_sessions.pop(websocket, None)
                            await send_message(websocket, Message("admin.spectate_stopped", {}))
                            await send_admin_overview(websocket)
                            continue

                        if msg.type in {"admin.support_join", "admin.support_leave", "admin.support_message"}:
                            watched = admin_support_sessions.setdefault(websocket, set())
                            machine = ensure_state_machine(target_session)
                            if msg.type == "admin.support_join":
                                watched.add(target_session)
                                notice = {"role": "bot", "channel": "support", "text": "Game Master se připojil k podpoře týmu.", "at": datetime.now(UTC).isoformat()}
                                machine.state.chat_history.append(notice)
                                save_sessions()
                                await broadcast_session(target_session, [Message("bot.message", notice)])
                            elif msg.type == "admin.support_leave":
                                watched.discard(target_session)
                                notice = {"role": "bot", "channel": "support", "text": "Game Master ukončil přímé připojení k týmu.", "at": datetime.now(UTC).isoformat()}
                                machine.state.chat_history.append(notice)
                                save_sessions()
                                await broadcast_session(target_session, [Message("bot.message", notice)])
                            else:
                                text_value = " ".join(str(msg.payload.get("text", "")).strip().split())[:500]
                                if not text_value:
                                    raise ValueError("Zpráva podpory je prázdná.")
                                support_message = {"role": "bot", "channel": "support", "text": text_value, "sender": "Game Master", "at": datetime.now(UTC).isoformat()}
                                machine.state.chat_history.append(support_message)
                                machine.state.last_activity_at = support_message["at"]
                                save_sessions()
                                await broadcast_session(target_session, [Message("bot.message", support_message)])
                                await push_admin_support_update(target_session)
                                continue
                            await send_admin_overview(websocket)
                            continue

                        if msg.type == "admin.player_recovery":
                            player_id = str(msg.payload.get("player_id", "")).strip()
                            player = lobby.players.get(player_id)
                            if player is None:
                                raise ValueError("Hráč v této relaci neexistuje.")
                            for token, item in list(recovery_tokens.items()):
                                if item.get("session_id") == target_session and item.get("player_id") == player_id:
                                    recovery_tokens.pop(token, None)
                            token = secrets.token_hex(8).upper()
                            recovery_tokens[token] = {
                                "session_id": target_session,
                                "player_id": player_id,
                                "expires_at": (datetime.now(UTC).timestamp() + 600),
                            }
                            await send_message(websocket, Message("admin.player_recovery", {
                                "token": token,
                                "player_name": player.get("name", ""),
                                "team_name": lobby.team_name,
                                "expires_in_seconds": 600,
                            }))
                            continue

                        if msg.type == "admin.session_extend":
                            machine = ensure_state_machine(target_session)
                            if machine.state.flags.get("game_completed") or machine.state.flags.get("administratively_ended"):
                                raise ValueError("Ukončenou hru už nelze prodloužit.")
                            minutes = int(msg.payload.get("minutes", 15))
                            if minutes not in {5, 10, 15, 30, 45, 60}:
                                raise ValueError("Nepovolená délka prodloužení.")
                            total = int(machine.state.flags.get("deadline_extension_minutes", 0)) + minutes
                            machine.state.flags["deadline_extension_minutes"] = total
                            machine.state.flags.setdefault("admin_actions", []).append({"action": "session_extend", "label": f"Prodloužení hry o {minutes} minut", "minutes": minutes, "at": datetime.now(UTC).isoformat()})
                            save_sessions()
                            await broadcast_session(target_session, [Message("bot.message", {"text": f"Game Master prodloužil čas hry o {minutes} minut.", "mood": "positive", "channel": "general"}), machine._state_message()])
                            await send_admin_overview(websocket); continue

                        if msg.type == "admin.session_end":
                            machine = ensure_state_machine(target_session)
                            if machine.state.flags.get("game_completed") or machine.state.flags.get("administratively_ended"):
                                raise ValueError("Hra už je ukončena.")
                            reason = str(msg.payload.get("reason", "manual")).strip()
                            allowed = {"abandoned": "Opuštěná hra", "technical": "Ukončeno kvůli technické závadě", "manual": "Ručně ukončeno Game Masterem"}
                            if reason not in allowed: raise ValueError("Neplatný důvod ukončení.")
                            penalty = int(runtime_settings.get("abandonment_penalty", 100)) if reason == "abandoned" else 0
                            updates = apply_operational_end(machine, datetime.now(UTC).isoformat(), reason, penalty, allowed[reason])
                            save_sessions()
                            await broadcast_session(target_session, updates)
                            for terminal_socket in list(connected_terminal_sockets(target_session)):
                                await release_terminal(terminal_socket, target_session, "Hra byla ukončena. Terminál je znovu volný.")
                            await send_admin_overview(websocket); continue

                        if msg.type == "admin.evaluate_team":
                            machine = ensure_state_machine(target_session)
                            if not machine.state.flags.get("administratively_ended") and not machine.state.flags.get("game_completed"):
                                raise ValueError("Vyhodnotit lze pouze dokončenou nebo provozně ukončenou hru.")
                            if leaderboard_is_finalized() and not any(entry.get("session_id") == target_session for entry in global_leaderboard):
                                raise ValueError("Celkové pořadí je už organizačně uzavřeno.")
                            if not any(entry.get("session_id") == target_session for entry in global_leaderboard):
                                completed_at = datetime.now(UTC).isoformat()
                                global_leaderboard.append({"entry_id": secrets.token_hex(8), "session_id": target_session,
                                    "name": lobby.team_name, "players": [str(player.get("name", "")) for player in lobby.players.values()],
                                    "mode": lobby.mode, "score": leaderboard_score(machine),
                                    "duration_seconds": result_duration_seconds(machine, completed_at),
                                    "completed_at": completed_at, "administrative": True,
                                    "out_of_competition": bool(machine.state.flags.get("out_of_competition")),
                                    **leaderboard_identity(lobby)})
                                save_leaderboard()
                            machine.state.flags["administratively_evaluated"] = True; save_sessions()
                            update = Message("leaderboard.update", {"entries": leaderboard_entries()})
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket); continue

                        if msg.type == "admin.game_player":
                            machine = ensure_state_machine(target_session)
                            machine._participant_ids = lobby.active_player_ids
                            machine._participant_names = {key: str(lobby.players[key].get("name", "Hráč")) for key in lobby.active_player_ids}
                            machine._team_mode = lobby.mode
                            result = machine.admin_set_game_player(str(msg.payload.get("puzzle_id", "")), str(msg.payload.get("player_id", "")), str(msg.payload.get("action", "")))
                            save_sessions()
                            updates = [machine._state_message()]
                            if result.get("team_complete"):
                                puzzle = machine.scenario.data.get("puzzles", {}).get(str(result.get("puzzle_id", "")), {})
                                updates.insert(0, Message("bot.message", puzzle.get("success_message", {})))
                                updates.insert(0, Message("puzzle.result", {"correct": True, "puzzle_id": result.get("puzzle_id"), "team_summary": result.get("team_summary")}))
                            await broadcast_session(target_session, updates)
                            await send_message(websocket, Message("admin.game_player", result))
                            await send_admin_overview(websocket)
                            continue

                        if msg.type in {"admin.penalty", "admin.score_adjustment"}:
                            delta = (-int(msg.payload.get("amount", 0)) if msg.type == "admin.penalty"
                                     else int(msg.payload.get("delta", 0)))
                            reason = " ".join(str(msg.payload.get("reason", "")).strip().split())[:160]
                            if delta == 0 or abs(delta) > 1000:
                                raise ValueError("Bodová úprava musí být nenulové celé číslo v rozsahu −1000 až +1000.")
                            if not reason:
                                raise ValueError("U bodové úpravy je povinný důvod.")
                            machine = ensure_state_machine(target_session)
                            score_before = machine.state.score
                            machine.state.score += delta
                            adjustment = {
                                "delta": delta,
                                "amount": abs(delta),
                                "reason": reason,
                                "at": datetime.now(UTC).isoformat(),
                                "score_before": score_before,
                                "score_after": machine.state.score,
                            }
                            machine.state.flags.setdefault("admin_score_adjustments", []).append(adjustment)
                            if delta < 0:
                                machine.state.flags.setdefault("admin_penalties", []).append(adjustment)
                            leaderboard_changed = False
                            for entry in global_leaderboard:
                                if str(entry.get("session_id", "")) == target_session:
                                    entry["score"] = leaderboard_score(machine)
                                    leaderboard_changed = True
                            if leaderboard_changed:
                                save_leaderboard()
                            save_sessions()
                            await broadcast_session(target_session, [
                                Message("score.update", {
                                    "score": machine.state.score,
                                    "delta": delta,
                                    "bonus": max(0, delta),
                                    "penalty": max(0, -delta),
                                    "reason": "admin_score_adjustment",
                                    "description": reason,
                                }),
                                Message("bot.message", {
                                    "text": f"Administrátorská úprava {delta:+d} bodů: {reason}",
                                    "mood": "positive" if delta > 0 else "tense",
                                    "channel": "general",
                                }),
                                machine._state_message(),
                            ])
                            if leaderboard_changed:
                                update = Message("leaderboard.update", {"entries": leaderboard_entries()})
                                for active_socket in list(app.state.active_websockets):
                                    try: await send_message(active_socket, update)
                                    except Exception: pass
                            await send_admin_overview(websocket)
                            continue

                        if msg.type == "admin.checkpoint":
                            checkpoint_id = str(msg.payload.get("checkpoint_id", "")).strip()
                            status = str(msg.payload.get("status", "")).strip()
                            machine = ensure_state_machine(target_session)
                            preset_id = str(msg.payload.get("penalty_preset", "technical"))
                            preset = ADMIN_RESOLUTION_PRESETS.get(preset_id)
                            if preset is None:
                                raise ValueError("Neznámá předvolba postihu.")
                            penalty = int(preset["penalty"]) if status == "solved" else 0
                            result = machine.admin_set_checkpoint(checkpoint_id, status)
                            label = f"Checkpoint {checkpoint_id}: {status} · {preset['label']}"
                            if penalty:
                                machine.state.score -= penalty
                                machine.state.flags.setdefault("admin_penalties", []).append({"amount": penalty, "reason": str(preset["label"]), "at": datetime.now(UTC).isoformat()})
                            machine.state.flags.setdefault("admin_actions", []).append({
                                "action": "checkpoint", "label": label, "at": datetime.now(UTC).isoformat(), **result,
                            })
                            save_sessions()
                            updates = [
                                Message("bot.message", {"text": f"Game Master upravil postup: {label}.", "mood": "info", "channel": "general"}),
                                machine._state_message(),
                                Message("scenario.progress", build_scenario_progress(machine.scenario, machine.state.snapshot())),
                            ]
                            if penalty:
                                updates.insert(0, Message("score.update", {"score": machine.state.score, "delta": -penalty, "penalty": penalty, "reason": "admin_resolution", "description": preset["label"]}))
                            await broadcast_session(target_session, updates)
                            await send_admin_overview(websocket)
                            continue

                        if msg.type == "admin.game_reset":
                            puzzle_id = str(msg.payload.get("puzzle_id", "")).strip()
                            machine = ensure_state_machine(target_session)
                            result = machine.admin_reset_game(puzzle_id)
                            label = f"Restart minihry {puzzle_id}"
                            machine.state.flags.setdefault("admin_actions", []).append({
                                "action": "game_reset", "label": label, "at": datetime.now(UTC).isoformat(), **result,
                            })
                            save_sessions()
                            await broadcast_session(target_session, [
                                Message("bot.message", {"text": f"Game Master provedl: {label}.", "mood": "info", "channel": "general"}),
                                machine._state_message(),
                                Message("scenario.progress", build_scenario_progress(machine.scenario, machine.state.snapshot())),
                            ])
                            await send_admin_overview(websocket)
                            continue

                        affected = list(session_connections.get(target_session, set()))
                        for player_socket in affected:
                            try:
                                await send_message(player_socket, Message("admin.session_removed", {
                                    "message": "Týmová relace byla odstraněna administrátorem.",
                                }))
                                await player_socket.close(code=4001, reason="Session removed by administrator")
                            except Exception:
                                pass
                        if lobby.join_code:
                            lobby_registry.by_join_code.pop(lobby.join_code, None)
                        dequeue_team(target_session)
                        lobby_registry.by_session.pop(target_session, None)
                        active_sessions.pop(target_session, None)
                        session_command_adapters.pop(target_session, None)
                        session_connections.pop(target_session, None)
                        save_lobbies()
                        save_sessions()
                        save_runtime_settings()
                        update = Message("runtime.settings", runtime_payload())
                        for active_socket in list(app.state.active_websockets):
                            try: await send_message(active_socket, update)
                            except Exception: pass
                        await send_admin_overview(websocket)
                        continue
                    except (ValueError, TypeError) as error:
                        await send_message(websocket, Message("admin.error", {"message": str(error)}))
                        continue

                if msg.type in {"lobby.solo", "lobby.create", "lobby.join", "lobby.resume", "lobby.start", "lobby.queue", "lobby.dequeue", "lobby.identify", "lobby.add_player", "lobby.recover", "lobby.leave"}:
                    try:
                        requested_client_id = str(msg.payload.get("client_id", "")).strip()
                        if not requested_client_id:
                            raise ValueError("Chybí identifikátor zařízení.")
                        name = str(msg.payload.get("name", "")).strip()
                        team_name = str(msg.payload.get("team_name", "")).strip()
                        lobby_type = str(msg.payload.get("lobby_type", "on_site_qr")).strip()
                        requested_scenario_id = str(msg.payload.get("scenario_id", selected_scenario_id)).strip()
                        requested_demo = DEMO_MODE_ENABLED and bool(msg.payload.get("demo_mode"))
                        if msg.type == "lobby.leave":
                            info = connection_info.get(websocket, {})
                            attached_client_id = str(info.get("client_id", ""))
                            lobby = lobby_registry.by_session.get(str(info.get("session_id", "")))
                            if lobby is None or attached_client_id != requested_client_id or attached_client_id not in lobby.players:
                                raise ValueError("Odchod může potvrdit pouze aktivní hráč této relace.")
                            await leave_lobby_player(websocket, lobby, attached_client_id, str(msg.operation_id or ""))
                            continue
                        if msg.type in {"lobby.queue", "lobby.dequeue"}:
                            info = connection_info.get(websocket, {})
                            lobby = lobby_registry.by_session.get(str(info.get("session_id", "")))
                            if lobby is None or not lobby.is_active_player(requested_client_id):
                                raise ValueError("Nejprve se připojte k týmové lobby.")
                            if msg.type == "lobby.queue": queue_team(lobby.session_id)
                            else: dequeue_team(lobby.session_id)
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            continue
                        if msg.type == "lobby.recover":
                            token = str(msg.payload.get("recovery_token", "")).strip().upper().removeprefix("ESCAPEBOT://RECOVER/")
                            recovery = recovery_tokens.pop(token, None)
                            if recovery is None or float(recovery.get("expires_at", 0)) < datetime.now(UTC).timestamp():
                                raise ValueError("Návratový kód není platný, už byl použit nebo vypršel.")
                            lobby = lobby_registry.by_session.get(str(recovery.get("session_id", "")))
                            if lobby is None:
                                raise ValueError("Týmová relace už neexistuje.")
                            old_client_id = str(recovery.get("player_id", ""))
                            player = lobby.transfer_player(old_client_id, requested_client_id)
                            ensure_state_machine(lobby.session_id).transfer_player_game_identity(old_client_id, requested_client_id)
                            for old_socket in list(session_connections.get(lobby.session_id, set())):
                                if str(connection_info.get(old_socket, {}).get("client_id", "")) == old_client_id:
                                    try:
                                        await send_message(old_socket, Message("admin.session_removed", {"message": "Identita hráče byla obnovena na novém zařízení."}))
                                        await old_socket.close(code=4002, reason="Player identity transferred")
                                    except Exception: pass
                            session_id = lobby.session_id
                            client_id = requested_client_id
                            demo_client = requested_demo
                            attach_to_lobby(websocket, lobby, client_id, demo_client)
                            state_machine = ensure_state_machine(session_id)
                            save_lobbies()
                            await broadcast_lobby(lobby)
                            await send_message(websocket, Message("lobby.recovered", {"player_name": player.get("name", ""), "team_name": lobby.team_name}))
                            if lobby.started:
                                await sync_started_client(websocket, state_machine, demo_client)
                            continue
                        if msg.type == "lobby.identify":
                            if not name:
                                raise ValueError("Před zobrazením hráčského QR zadejte jméno hráče.")
                            previous_code = str(connection_info.get(websocket, {}).get("player_code", ""))
                            if previous_code:
                                waiting_players.pop(previous_code, None)
                            player_code = secrets.token_hex(4).upper()
                            while player_code in waiting_players:
                                player_code = secrets.token_hex(4).upper()
                            waiting_players[player_code] = {
                                "websocket": websocket,
                                "client_id": requested_client_id,
                                "name": name,
                                "demo": requested_demo,
                            }
                            connection_info[websocket] = {"client_id": requested_client_id, "player_code": player_code, "demo": requested_demo}
                            await send_message(websocket, Message("lobby.player_identity", {"player_code": player_code}))
                            continue
                        if msg.type == "lobby.add_player":
                            info = connection_info.get(websocket, {})
                            lobby = lobby_registry.by_session.get(str(info.get("session_id", "")))
                            if lobby is None or requested_client_id != lobby.creator_id or not lobby.is_active_player(requested_client_id):
                                raise ValueError("Hráče může tímto způsobem přidat pouze zakladatel týmu.")
                            player_code = str(msg.payload.get("player_code", "")).strip().upper().removeprefix("ESCAPEBOT://PLAYER/")
                            waiting = waiting_players.pop(player_code, None)
                            if waiting is None:
                                raise ValueError("Hráčské ID není platné nebo už bylo použito.")
                            waiting_socket = waiting["websocket"]
                            waiting_client_id = str(waiting["client_id"])
                            lobby.add_player(waiting_client_id, str(waiting.get("name", "")))
                            attach_to_lobby(waiting_socket, lobby, waiting_client_id, bool(waiting.get("demo")))
                            session_id = lobby.session_id
                            client_id = requested_client_id
                            state_machine = ensure_state_machine(session_id)
                            save_lobbies()
                            await broadcast_lobby(lobby)
                            if lobby.started:
                                await sync_started_client(waiting_socket, state_machine, bool(waiting.get("demo")))
                                score_messages = apply_lobby_score(lobby, state_machine)
                                if score_messages:
                                    await broadcast_session(session_id, score_messages)
                            continue
                        if msg.type == "lobby.solo":
                            require_start_available(lobby_type, requested_scenario_id)
                            entry = scenario_catalog.entries.get(requested_scenario_id)
                            if entry is None or not scenario_supports_lobby(entry, lobby_type):
                                raise ValueError("Vybraná hra není pro tento typ lobby dostupná.")
                            lobby = lobby_registry.create(requested_client_id, "solo", name, team_name, lobby_type, requested_scenario_id)
                        elif msg.type == "lobby.create":
                            require_start_available(lobby_type, requested_scenario_id)
                            entry = scenario_catalog.entries.get(requested_scenario_id)
                            if entry is None or not scenario_supports_lobby(entry, lobby_type):
                                raise ValueError("Vybraná hra není pro tento typ lobby dostupná.")
                            # Mobile Safari can suspend a socket immediately after
                            # sending. A retry must recover the created lobby instead
                            # of failing on its now-duplicate team name.
                            lobby = lobby_registry.pending_team_for_creator(requested_client_id, team_name)
                            if lobby is None:
                                lobby = lobby_registry.create(requested_client_id, "team", name, team_name, lobby_type, requested_scenario_id)
                            else:
                                lobby.add_player(requested_client_id, name)
                        elif msg.type == "lobby.join":
                            lobby = lobby_registry.join(str(msg.payload.get("join_code", "")), requested_client_id, name)
                        elif msg.type == "lobby.resume":
                            lobby = lobby_registry.resume(str(msg.payload.get("session_id", "")), requested_client_id, name)
                        else:
                            info = connection_info.get(websocket, {})
                            lobby = lobby_registry.by_session.get(str(info.get("session_id", "")))
                            if lobby is None or requested_client_id != lobby.creator_id or not lobby.is_active_player(requested_client_id):
                                raise ValueError("Hru může spustit pouze zakladatel týmu.")
                            if not lobby.team_name or any(not str(lobby.players[player_id].get("name", "")).strip() for player_id in lobby.active_player_ids):
                                raise ValueError("Před spuštěním musí mít tým i všichni hráči vyplněné jméno.")
                            require_start_available(lobby.lobby_type, lobby.scenario_id)
                            lobby.started = True
                            dequeue_team(lobby.session_id)

                        session_id = lobby.session_id
                        client_id = requested_client_id
                        demo_client = requested_demo
                        attach_to_lobby(websocket, lobby, client_id, demo_client)
                        state_machine = ensure_state_machine(session_id)
                        if msg.type in {"lobby.solo", "lobby.start"}:
                            state_machine.state.flags["operations_started_at"] = datetime.now(UTC).isoformat()
                            availability_update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                    try: await send_message(active_socket, availability_update)
                                    except Exception: pass
                            save_runtime_settings()
                        save_lobbies()
                        await broadcast_lobby(lobby)

                        if lobby.started:
                            score_messages = apply_lobby_score(lobby, state_machine)
                            if msg.type in {"lobby.solo", "lobby.start"}:
                                hello = Message("client.hello", {"session_id": session_id, "demo_mode": demo_client,
                                                                "_client_id": client_id, "_participant_ids": lobby.active_player_ids,
                                                                "_team_mode": lobby.mode,
                                                                "_participant_names": {key: str(lobby.players[key].get("name", "Hráč")) for key in lobby.active_player_ids}})
                                result = await apply_game_command(str(session_id), state_machine, hello)
                                responses = [*result.sender_messages, *result.broadcast_messages]
                                responses.extend(score_messages)
                                if demo_client:
                                    responses.append(Message("demo.catalog", {
                                        "enabled": True,
                                        "checkpoints": build_demo_checkpoint_catalog(state_machine.scenario),
                                    }))
                                responses.append(Message("scenario.progress", build_scenario_progress(state_machine.scenario, state_machine.state.snapshot())))
                                await broadcast_session(session_id, responses)
                            else:
                                await sync_started_client(websocket, state_machine, demo_client)
                                if score_messages:
                                    await broadcast_session(session_id, score_messages)
                            await send_message(websocket, Message("runtime.settings", runtime_payload()))
                        continue
                    except ValueError as error:
                        await send_message(websocket, Message("lobby.error", {"message": str(error)}))
                        continue

                if msg.type == "qr.detected" and str(msg.payload.get("value", "")).lower().startswith("escapebot://terminal/"):
                    if not session_id or not state_machine or not client_id:
                        await send_message(websocket, Message("terminal.attach_result", {
                            "success": False,
                            "reason": "Nejprve se připojte k rozehrané týmové relaci.",
                        }))
                        continue
                    pairing_code = str(msg.payload.get("value", "")).rsplit("/", 1)[-1].strip().upper()
                    pairing = terminal_pairings.get(pairing_code)
                    if pairing is None or float(pairing.get("expires_at", 0)) < datetime.now(UTC).timestamp():
                        terminal_pairings.pop(pairing_code, None)
                        await send_message(websocket, Message("terminal.attach_result", {
                            "success": False,
                            "reason": "Párovací QR terminálu už není platný. Na tabletu vytvořte nový.",
                        }))
                        continue
                    terminal_socket = pairing.get("websocket")
                    terminal_id = str(pairing.get("terminal_id", ""))
                    if not isinstance(terminal_socket, WebSocket):
                        await send_message(websocket, Message("terminal.attach_result", {
                            "success": False,
                            "reason": "Terminál už není připojený.",
                        }))
                        continue
                    lobby = lobby_registry.by_session.get(str(session_id))
                    if lobby is None or not lobby.is_active_player(str(client_id)):
                        await send_message(websocket, Message("terminal.attach_result", {
                            "success": False,
                            "reason": "Terminál může odemknout pouze člen týmu.",
                        }))
                        continue
                    reservation = terminal_reservations().get(terminal_id, {})
                    reserved_scenario = str(reservation.get("scenario_id", ""))
                    reserved_puzzle = str(reservation.get("puzzle_id", ""))
                    available = {item["id"] for item in available_terminal_puzzles(state_machine, lobby.scenario_id)}
                    if reserved_scenario != lobby.scenario_id or reserved_puzzle not in available:
                        await send_message(websocket, Message("terminal.attach_result", {
                            "success": False,
                            "reason": "Tento terminál je vyhrazen jiné hádance, než má váš tým právě dostupnou.",
                        }))
                        continue
                    active_scenario = state_machine.scenario
                    puzzle = active_scenario.data.get("puzzles", {}).get(reserved_puzzle, {})
                    checkpoint_id = str(puzzle.get("checkpoint_id", ""))
                    if checkpoint_id not in state_machine.state.checkpoint_states:
                        checkpoint = active_scenario.data.get("checkpoints", {}).get(checkpoint_id, {})
                        token = str(checkpoint.get("token", ""))
                        activation_result = await apply_game_command(str(session_id), state_machine, Message("qr.detected", {
                            "value": f"escapebot://checkpoint/{token}",
                        }))
                        activation_responses = [
                            *activation_result.sender_messages,
                            *activation_result.broadcast_messages,
                        ]
                        result = next((response for response in activation_responses if response.type == "qr.result"), None)
                        if result is None or not result.payload.get("accepted"):
                            await send_message(websocket, Message("terminal.attach_result", {
                                "success": False,
                                "reason": str(result.payload.get("reason", "Hádanku zatím nelze na terminálu aktivovat.")) if result else "Hádanku zatím nelze na terminálu aktivovat.",
                            }))
                            continue
                        save_sessions()
                        await broadcast_session(str(session_id), activation_responses)
                    terminal_pairings.pop(pairing_code, None)
                    bind_terminal(terminal_socket, str(session_id), str(client_id))
                    state_machine.state.flags["terminal_assignment"] = reserved_puzzle
                    save_sessions()
                    attached_payload = {
                        "success": True,
                        "session_id": str(session_id),
                        "team_name": lobby.team_name,
                        "controller_name": str(lobby.players[str(client_id)].get("name", "Hráč")),
                    }
                    await send_message(websocket, Message("terminal.attach_result", attached_payload))
                    await send_message(terminal_socket, Message("terminal.attached", attached_payload))
                    await sync_started_client(terminal_socket, state_machine, False)
                    await broadcast_session(str(session_id), [state_machine._state_message()])
                    for admin_socket in list(authenticated_admin_sockets):
                        try: await send_admin_overview(admin_socket)
                        except Exception: pass
                    continue
                
                # Zpracování požadavků na Síň slávy (mimo state machine)
                if msg.type == "leaderboard.get":
                    await websocket.send_text(json.dumps(Message("leaderboard.update", {"entries": leaderboard_entries()}).to_json()))
                    continue
                if msg.type == "display.heartbeat":
                    public_display_status.update({"updated_at": datetime.now(UTC).isoformat(),
                        "mode": str(msg.payload.get("mode", "auto"))[:40], "screen": str(msg.payload.get("screen", ""))[:80],
                        "fullscreen": bool(msg.payload.get("fullscreen")), "wake_lock": bool(msg.payload.get("wake_lock")),
                        "user_agent": str(msg.payload.get("user_agent", ""))[:200]})
                    await send_message(websocket, Message("runtime.settings", runtime_payload()))
                    continue
                    
                if msg.type == "leaderboard.save":
                    lobby = lobby_registry.by_session.get(str(session_id))
                    machine = active_sessions.get(str(session_id))
                    if not lobby or not machine or not machine.state.flags.get("game_completed"):
                        await send_message(websocket, Message("error", {"message": "Výsledek lze zapsat až po dokončení hry."}))
                        continue
                    if leaderboard_is_finalized():
                        await send_message(websocket, Message("error", {"message": "Celkové pořadí je už organizačně uzavřeno."}))
                        continue
                    record_completed_result(str(session_id), lobby, machine)
                    
                    update_msg = json.dumps(Message("leaderboard.update", {"entries": leaderboard_entries()}).to_json())
                    for ws in list(app.state.active_websockets):
                        try:
                            await ws.send_text(update_msg)
                        except Exception:
                            pass
                    continue

                if msg.type == "client.hello":
                    session_id = msg.payload.get("session_id", "default_session")
                    demo_client = DEMO_MODE_ENABLED and bool(msg.payload.get("demo_mode"))
                    if session_id not in active_sessions:
                        logger.info(f"Vytvářím novou herní relaci pro: {session_id}")
                        active_sessions[session_id] = EscapeBotStateMachine(scenario, clock=lambda: datetime.now(UTC))
                        session_command_adapters[session_id] = GameSessionAdapter()
                    else:
                        logger.info(f"Obnovuji existující relaci pro: {session_id}")
                        
                    state_machine = active_sessions[session_id]
                    client_id = str(msg.payload.get("client_id", "legacy-client"))
                    connection_info[websocket] = {"session_id": session_id, "client_id": client_id, "demo": demo_client}
                    session_connections.setdefault(session_id, set()).add(websocket)

                if state_machine:
                    if client_id:
                        msg.payload["_client_id"] = client_id
                    lobby_context = lobby_registry.by_session.get(str(session_id))
                    if lobby_context:
                        if not lobby_context.is_active_player(str(client_id)) and connection_info.get(websocket, {}).get("role") != "terminal":
                            await send_message(websocket, Message("error", {"message": "Tento hráč hru trvale opustil."}))
                            continue
                        msg.payload["_participant_ids"] = lobby_context.active_player_ids
                        msg.payload["_team_mode"] = lobby_context.mode
                        msg.payload["_participant_names"] = {key: str(lobby_context.players[key].get("name", "Hráč")) for key in lobby_context.active_player_ids}
                    if msg.type == "player.message" and str(msg.payload.get("channel", "")) == "support" and session_id:
                        text_value = " ".join(str(msg.payload.get("text", "")).strip().split())[:500]
                        if not text_value:
                            await send_message(websocket, Message("error", {"message": "Zpráva podpory je prázdná."}))
                            continue
                        lobby = lobby_registry.by_session.get(str(session_id))
                        player = lobby.players.get(str(client_id), {}) if lobby else {}
                        support_message = {"role": "player", "channel": "support", "text": text_value, "sender": str(player.get("name", "Hráč")), "at": datetime.now(UTC).isoformat()}
                        state_machine.state.chat_history.append(support_message)
                        state_machine.state.last_activity_at = support_message["at"]
                        save_sessions()
                        await broadcast_session(str(session_id), [Message("team.player_message", {"client_id": client_id, "channel": "support", "text": text_value})], exclude=websocket)
                        await push_admin_support_update(str(session_id))
                        continue
                    if msg.type == "game.deadline_choice" and (not lobby_context or client_id not in lobby_context.players or socket_info.get("role") == "terminal"):
                        await send_message(websocket, Message("error", {"message": "O pokračování rozhodují hráči týmu."}))
                        continue
                    try:
                        result = await apply_game_command(str(session_id), state_machine, msg)
                    except CommandValidationError as error:
                        await send_message(websocket, Message(
                            "command.rejected",
                            {"command": msg.type, "reason": str(error)},
                            request_id=msg.request_id,
                            operation_id=msg.operation_id,
                        ))
                        continue
                    if msg.type == "client.hello" and bool(msg.payload.get("demo_mode")):
                        if demo_client:
                            checkpoints = build_demo_checkpoint_catalog(state_machine.scenario)
                            sender_messages = list(result.sender_messages)
                            sender_messages.append(Message("demo.catalog", {"enabled": True, "checkpoints": checkpoints}))
                        else:
                            sender_messages = list(result.sender_messages)
                            sender_messages.append(Message("demo.catalog", {
                                "enabled": False,
                                "checkpoints": [],
                                "reason": "Backend nebyl spuštěn s parametrem --demo.",
                            }))
                    else:
                        sender_messages = list(result.sender_messages)
                    broadcast_messages = list(result.broadcast_messages)
                    progress_message = Message(
                        "scenario.progress",
                        build_scenario_progress(state_machine.scenario, state_machine.state.snapshot()),
                    )
                    if result.replayed:
                        sender_messages.append(progress_message)
                    else:
                        broadcast_messages.append(progress_message)
                    if msg.type == "player.message" and session_id and not result.replayed:
                        await broadcast_session(session_id, [Message("team.player_message", {
                            "client_id": client_id,
                            "channel": msg.payload.get("channel", "general"),
                            "text": msg.payload.get("text", ""),
                        })], exclude=websocket)
                    save_sessions()
                    if session_id:
                        schedule_completed_terminal_releases(str(session_id), state_machine)
                    if session_id and any(response.type == "game.complete" for response in broadcast_messages):
                        completion_update = apply_outcome_score(state_machine, "completed", int(runtime_settings.get("completion_bonus", 100)))
                        if completion_update:
                            broadcast_messages.insert(0, completion_update)
                            broadcast_messages.append(state_machine._state_message())
                            save_sessions()
                        completion_message = next(response for response in broadcast_messages if response.type == "game.complete")
                        completion_message.payload["leaderboard_score"] = leaderboard_score(state_machine)
                        completion_message.payload["score_frozen"] = "competition_score" in state_machine.state.flags
                        completed_lobby = lobby_registry.by_session.get(str(session_id))
                        if completed_lobby and record_completed_result(str(session_id), completed_lobby, state_machine):
                            leaderboard_update = Message("leaderboard.update", {"entries": leaderboard_entries()})
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, leaderboard_update)
                                except Exception: pass
                        availability_update = Message("runtime.settings", runtime_payload())
                        for active_socket in list(app.state.active_websockets):
                            try: await send_message(active_socket, availability_update)
                            except Exception: pass
                    if msg.operation_id:
                        await send_message(websocket, Message(
                            "operation.ack",
                            {"operation_id": msg.operation_id},
                            operation_id=msg.operation_id,
                        ))
                    if session_id:
                        for response in sender_messages:
                            await send_message(websocket, response)
                        await broadcast_session(session_id, broadcast_messages)
                    else:
                        for response in [*sender_messages, *broadcast_messages]:
                            await send_message(websocket, response)
                else:
                    logger.warning("Přijata zpráva před inicializací relace (client.hello chybí).")

            except Exception as e:
                logger.error(f"Chyba při zpracování zprávy: {e}")
    except WebSocketDisconnect:
        app.state.active_websockets.discard(websocket)
        admin_support_sessions.pop(websocket, None)
        admin_spectator_sessions.pop(websocket, None)
        authenticated_admin_sockets.discard(websocket)
        for pairing_code, pairing in list(terminal_pairings.items()):
            if pairing.get("websocket") is websocket:
                terminal_pairings.pop(pairing_code, None)
        info = connection_info.pop(websocket, {})
        player_code = str(info.get("player_code", ""))
        if player_code:
            waiting_players.pop(player_code, None)
        disconnected_session = str(info.get("session_id", ""))
        if disconnected_session:
            session_connections.get(disconnected_session, set()).discard(websocket)
            lobby = lobby_registry.by_session.get(disconnected_session)
            if lobby:
                await broadcast_lobby(lobby)
            machine = active_sessions.get(disconnected_session)
            if machine and info.get("role") == "terminal":
                await broadcast_session(disconnected_session, [machine._state_message()])
        if info.get("role") in {"terminal", "terminal_waiting"}:
            for admin_socket in list(authenticated_admin_sockets):
                try: await send_admin_overview(admin_socket)
                except Exception: pass
        logger.info(f"Klient odpojen (Relace: {session_id}).")

# Servírování statických souborů (klienta) napřímo pod stejným portem
app.mount("/", StaticFiles(directory=CLIENT_DIR, html=True), name="client")

def generate_ssl_certs(cert_path, key_path):
    try:
        logger.info("OpenSSL certifikáty nenalezeny. Pokouším se je automaticky vygenerovat...")
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-out", cert_path, "-keyout", key_path, "-days", "365",
            "-subj", "/CN=localhost"
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("Certifikáty úspěšně vygenerovány.")
        return True
    except Exception as e:
        logger.warning(f"Automatické generování certifikátů selhalo (je nainstalován OpenSSL?): {e}")
        return False

def start_http_redirect_server(http_port=8087, https_port=8088):
    def _run():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', http_port))
                s.listen(5)
                logger.info(f"Spuštěn pomocný HTTP server (port {http_port}) pro přesměrování na HTTPS (port {https_port}).")
                while True:
                    conn, addr = s.accept()
                    try:
                        data = conn.recv(1024).decode('utf-8', errors='ignore')
                        if not data:
                            continue
                        host = "localhost"
                        for line in data.split('\r\n'):
                            if line.lower().startswith("host:"):
                                host = line.split(":", 1)[1].strip().split(":")[0]
                                break
                        redirect_url = f"https://{host}:{https_port}/"
                        response = f"HTTP/1.1 301 Moved Permanently\r\nLocation: {redirect_url}\r\nConnection: close\r\n\r\n"
                        conn.sendall(response.encode('utf-8'))
                    except Exception:
                        pass
                    finally:
                        conn.close()
        except Exception as e:
            logger.error(f"Nelze spustit HTTP redirect server: {e}")
    threading.Thread(target=_run, daemon=True).start()

def main():
    ssl_cert_path = os.path.join(BASE_DIR, "backend", "cert.pem")
    ssl_key_path = os.path.join(BASE_DIR, "backend", "key.pem")
    
    if not (os.path.exists(ssl_cert_path) and os.path.exists(ssl_key_path)):
        generate_ssl_certs(ssl_cert_path, ssl_key_path)

    if os.path.exists(ssl_cert_path) and os.path.exists(ssl_key_path):
        logger.info("Nalezeny SSL certifikáty. Spouštím zabezpečený centrální uzel (HTTPS/WSS na portu 8088)...")
        start_http_redirect_server(http_port=8087, https_port=8088)
        uvicorn.run("escape_bot.server:app", host="0.0.0.0", port=8088, log_level="info", ssl_keyfile=ssl_key_path, ssl_certfile=ssl_cert_path)
    else:
        logger.info("Bez SSL certifikátů. Spouštím nezabezpečený centrální uzel (HTTP/WS na portu 8088)...")
        uvicorn.run("escape_bot.server:app", host="0.0.0.0", port=8088, log_level="info")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Escape Bot backend")
    parser.add_argument("--storage", choices=("json", "postgres"), help="Přepíše ESCAPEBOT_STORAGE_BACKEND")
    parser.add_argument("--database-url", help="Přepíše ESCAPEBOT_DATABASE_URL")
    arguments = parser.parse_args()
    if arguments.storage or arguments.database_url:
        configure_storage(arguments.storage, arguments.database_url)
    main()
