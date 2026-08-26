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
import uvicorn
from io import BytesIO
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .protocol import Message
from .state_machine import EscapeBotStateMachine
from .scenario import ScenarioLoader, build_checkpoint_qr_set, build_demo_checkpoint_catalog, build_puzzle_telemetry, build_scenario_progress
from .scenario import Scenario
from .scenario_catalog import load_scenario_catalog
from .scenario_composer import compose_documents
from .ollama_adapter import OllamaAdapter
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
lobby_registry = LobbyRegistry()
session_connections: dict[str, set[WebSocket]] = {}
connection_info: dict[WebSocket, dict[str, object]] = {}
waiting_players: dict[str, dict[str, object]] = {}
recovery_tokens: dict[str, dict[str, object]] = {}
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
DEMO_MODE_ENABLED = os.getenv("ESCAPEBOT_DEMO_MODE", "").lower() in {"1", "true", "yes", "on"}
ADMIN_TOKEN = os.getenv("ESCAPEBOT_ADMIN_TOKEN", "")
runtime_settings = {"online_mode": False, "gameplay_enabled": True, "max_active_teams": 4,
                    "start_interval_minutes": 15, "game_duration_minutes": 165,
                    "deadline_penalty": 100, "abandonment_penalty": 100, "completion_bonus": 100,
                    "opening_time": "08:00", "closing_time": "20:00", "timezone": "Europe/Prague",
                    "display_announcements": [], "leaderboard_finalized": False, "leaderboard_finalized_at": "",
                    "event": {"id": "", "name": "", "starts_at": "", "ends_at": "", "scenario_ids": [],
                              "leaderboard_finalized": False, "leaderboard_finalized_at": ""}}

def configured_event() -> dict[str, object] | None:
    event = runtime_settings.get("event")
    return event if isinstance(event, dict) and str(event.get("id", "")).strip() else None

def event_allows_scenario(scenario_id: str) -> bool:
    event = configured_event()
    if event is None:
        return True
    return scenario_id in {str(item) for item in event.get("scenario_ids", [])}

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
                "fallback_priority": fallback_priority}
    text = str(value).strip()
    return {"id": secrets.token_hex(6), "text": text, "priority": priority, "category": "organization",
            "published": True, "starts_at": "", "ends_at": "", "link_url": "", "link_label": "Více informací",
            "override_minutes": 0.0, "override_until": "", "fallback_priority": "high"} if text else None

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
    operating_hours_applied = event is not None or lobby_type != "online_doom"
    duration = max(1, int(runtime_settings.get("game_duration_minutes", 165)))
    interval = max(0, int(runtime_settings.get("start_interval_minutes", 15)))
    maximum = max(1, int(runtime_settings.get("max_active_teams", 4)))
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
    if not runtime_settings.get("gameplay_enabled", True): reasons.append("Herní provoz je zastaven správcem.")
    if event:
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
        if not event_allows_scenario(entry.id):
            continue
        item = entry.public()
        item["lobby_types"] = [kind for kind in ("online_doom", "on_site_qr", "geo") if scenario_supports_lobby(entry, kind)]
        games.append(item)
    return {**runtime_settings, "start_queue": public_start_queue(),
            "leaderboard_finalized": leaderboard_is_finalized(),
            "mapillary": {"enabled": bool(os.getenv("ESCAPEBOT_MAPILLARY_TOKEN", "")),
                           "access_token": os.getenv("ESCAPEBOT_MAPILLARY_TOKEN", "")},
            "availability": start_availability(scenario_id=selected_scenario_id),
            "availability_by_lobby_type": {
                kind: start_availability(lobby_type=kind) for kind in ("online_doom", "on_site_qr", "geo")
            },
            "checkpoints": build_demo_checkpoint_catalog(scenario), "games": games,
            "configurable_games": [entry.public() for entry in scenario_catalog.entries.values()],
            "scenario_available": scenario_available and bool(games)}

def public_start_queue() -> list[dict[str, object]]:
    """Project waiting on-site team lobbies into the public display queue."""
    waiting = [lobby for lobby in lobby_registry.by_session.values()
               if lobby.mode == "team" and not lobby.started and lobby.lobby_type in {"on_site_qr", "geo"}]
    waiting.sort(key=lambda lobby: min((str(player.get("joined_at", "")) for player in lobby.players.values()), default=lobby.session_id))
    availability = start_availability(lobby_type="on_site_qr")
    base_text = availability.get("next_start_at")
    try: planned = datetime.fromisoformat(str(base_text)) if base_text else _local_now()
    except ValueError: planned = _local_now()
    interval = timedelta(minutes=max(0, int(runtime_settings.get("start_interval_minutes", 15))))
    result = []
    for index, lobby in enumerate(waiting):
        queued_at = min((str(player.get("joined_at", "")) for player in lobby.players.values()), default="")
        result.append({"session_id": lobby.session_id, "team_name": lobby.team_name, "position": index + 1,
                       "planned_start_at": (planned + interval * index).isoformat(), "queued_at": queued_at})
    return result

def require_start_available(lobby_type: str = "on_site_qr", scenario_id: str = "") -> None:
    if not scenario_available:
        raise ValueError("Není dostupný žádný platný scénář. Správce může chyby opravit v editoru her.")
    availability = start_availability(lobby_type=lobby_type, scenario_id=scenario_id)
    if not availability["start_allowed"]:
        next_start = availability.get("next_start_at")
        suffix = f" Další možný start: {datetime.fromisoformat(str(next_start)).strftime('%H:%M')}." if next_start else ""
        raise ValueError(str(availability.get("reason", "Start hry nyní není možný.")) + suffix)

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
                continue
            if machine.state.flags.get("administratively_ended"): continue
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
        if changed: save_sessions()
        await asyncio.sleep(30)


def apply_deadline_end(machine: EscapeBotStateMachine, ended_at: str, penalty: int) -> list[Message]:
    """Close an unfinished game at its deadline and apply the penalty exactly once."""
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
    suffix = f" Byl odečten postih {applied_penalty} bodů." if applied_penalty else ""
    updates.extend([
        Message("operations.stopped", {"reason": "deadline", "penalty": applied_penalty,
            "message": f"Časový limit hry vypršel.{suffix} Výsledek týmu je připraven k vyhodnocení."}),
        machine._state_message(),
    ])
    return updates


def apply_outcome_score(machine: EscapeBotStateMachine, outcome: str, amount: int) -> Message | None:
    """Apply a configured outcome adjustment once, including restored historical sessions."""
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

def leaderboard_identity(lobby: Lobby) -> dict[str, str]:
    event = configured_event()
    scenario_entry = scenario_catalog.entries.get(lobby.scenario_id)
    return {
        "scenario_id": lobby.scenario_id,
        "game_title": scenario_entry.title if scenario_entry else lobby.scenario_id,
        "event_id": str(event.get("id", "")) if event else "",
        "event_name": str(event.get("name", "")) if event else "",
    }

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
    data = {sid: sm.state.snapshot() for sid, sm in active_sessions.items()}
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
            sm = EscapeBotStateMachine(entry.scenario)
            sm.restore_state(s_data)
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
    # Volitelný experiment; produkční hra ani start serveru LLM nevyžadují.
    if os.getenv("ESCAPEBOT_LLM_ENABLED", "").lower() in {"1", "true", "yes", "on"}:
        ai_checker = OllamaAdapter()
        asyncio.create_task(ai_checker.ensure_model())
    yield
    monitor_task.cancel()
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
    return {
        str(connection_info[websocket].get("client_id", ""))
        for websocket in session_connections.get(session_id, set())
        if websocket in connection_info
    }


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
                    player_id = str(connection_info.get(websocket, {}).get("client_id", ""))
                    outgoing = active_sessions[session_id]._state_message(player_id)
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
        active_sessions[session_id] = EscapeBotStateMachine(entry.scenario)
    return active_sessions[session_id]


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
        teams.append({
            **lobby.public("", connected_client_ids(lobby.session_id)),
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
            "end_reason": str(flags.get("administratively_ended_reason", "completed" if game_completed else "")),
            "ended_at": str(flags.get("administratively_ended_at", flags.get("completed_at", ""))),
            "deadline_extension_minutes": int(flags.get("deadline_extension_minutes", 0)),
            "administratively_evaluated": bool(flags.get("administratively_evaluated")),
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
                          "excluded": player_id in state.get("game_exclusions", {}).get(game_id, []), "status": game.get("status", ""),
                          "swaps": game.get("swaps", 0), "progress": dict(game.get("progress", {})),
                          "result": state.get("game_results", {}).get(game_id, {}).get(player_id)}
                         for game_id, container in line_games.items()
                         for player_id, game in (container.get("players", {}) if isinstance(container.get("players"), dict) else {next(iter(lobby.players), "legacy-client"): container}).items()],
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
                           "excluded": player_id in state.get("game_exclusions", {}).get(game_id, []), "status": game.get("status", ""),
                           "placements": game.get("placements", 0), "completed_orientations": list(game.get("completed_orientations", [])),
                           "result": state.get("game_results", {}).get(game_id, {}).get(player_id)}
                          for game_id, container in triad_games.items()
                          for player_id, game in (container.get("players", {}) if isinstance(container.get("players"), dict) else {next(iter(lobby.players), "legacy-client"): container}).items()],
                "archive": [{"id": game_id, "assembled": bool(game.get("assembled")), "moves": int(game.get("moves", 0)),
                             "order": list(game.get("order", [])), "rotations": dict(game.get("rotations", {}))}
                            for game_id, game in archive_games.items()],
            },
        })
    return sorted(teams, key=lambda team: str(team.get("team_name", "")).casefold())


async def send_admin_overview(websocket: WebSocket) -> None:
    await send_message(websocket, Message("admin.overview", {
        "teams": admin_overview(admin_support_sessions.get(websocket, set())),
        "leaderboard": leaderboard_entries(),
        "abandonment_thresholds": {"suspicious_seconds": 1800, "abandoned_seconds": 3600},
        "resolution_presets": ADMIN_RESOLUTION_PRESETS,
        "scenario_catalog": scenario_catalog.public(),
        "scenario_errors": scenario_catalog.errors,
        "selected_scenario_id": selected_scenario.id if selected_scenario else "",
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
        state_machine._participant_ids = list(lobby.players)
        state_machine._team_mode = lobby.mode
        state_machine._participant_names = {player_id: str(player.get("name", "Hráč")) for player_id, player in lobby.players.items()}
    if state_machine.state.flags.get("administratively_ended"):
        await send_message(websocket, Message("operations.stopped", {"message": "Tato hra už byla ukončena a čeká na vyhodnocení."}))
        return
    await send_message(websocket, Message("chat.history", {"messages": state_machine.state.chat_history}))
    await send_message(websocket, state_machine._state_message(player_id))
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

                if msg.type in {"admin.list", "admin.penalty", "admin.score_adjustment", "admin.delete", "admin.qr_set", "admin.online_mode", "admin.operations", "admin.schedule_settings", "admin.event_settings", "admin.display_announcements", "admin.evaluate_team", "admin.session_extend", "admin.session_end", "admin.checkpoint", "admin.game_reset", "admin.game_player", "admin.player_recovery", "admin.leaderboard_delete", "admin.leaderboard_finalize", "admin.support_join", "admin.support_leave", "admin.support_message", "admin.spectate_start", "admin.spectate_stop", "admin.scenario_source", "admin.scenario_validate"}:
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
                        if msg.type == "admin.online_mode":
                            runtime_settings["online_mode"] = bool(msg.payload.get("enabled"))
                            save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            continue
                        if msg.type == "admin.schedule_settings":
                            values = {"max_active_teams": int(msg.payload.get("max_active_teams", 4)),
                                      "start_interval_minutes": int(msg.payload.get("start_interval_minutes", 15)),
                                      "game_duration_minutes": int(msg.payload.get("game_duration_minutes", 165)),
                                      "deadline_penalty": int(msg.payload.get("deadline_penalty", 100)),
                                      "abandonment_penalty": int(msg.payload.get("abandonment_penalty", 100)),
                                      "completion_bonus": int(msg.payload.get("completion_bonus", 100)),
                                      "opening_time": str(msg.payload.get("opening_time", "08:00")),
                                      "closing_time": str(msg.payload.get("closing_time", "20:00")),
                                      "timezone": str(msg.payload.get("timezone", "Europe/Prague"))}
                            if not 1 <= values["max_active_teams"] <= 100: raise ValueError("Kapacita musí být 1–100 týmů.")
                            if not 0 <= values["start_interval_minutes"] <= 240: raise ValueError("Rozestup musí být 0–240 minut.")
                            if not 15 <= values["game_duration_minutes"] <= 720: raise ValueError("Délka hry musí být 15–720 minut.")
                            if not 0 <= values["deadline_penalty"] <= 1000: raise ValueError("Postih za nedokončení musí být 0–1000 bodů.")
                            if not 0 <= values["abandonment_penalty"] <= 1000: raise ValueError("Postih za opuštění musí být 0–1000 bodů.")
                            if not 0 <= values["completion_bonus"] <= 1000: raise ValueError("Bonus za dokončení musí být 0–1000 bodů.")
                            for key in ("opening_time", "closing_time"):
                                datetime.strptime(values[key], "%H:%M")
                            ZoneInfo(values["timezone"])
                            runtime_settings.update(values); save_runtime_settings()
                            update = Message("runtime.settings", runtime_payload())
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket); continue
                        if msg.type == "admin.event_settings":
                            event_id = str(msg.payload.get("id", "")).strip()
                            if not event_id:
                                runtime_settings["event"] = {"id": "", "name": "", "starts_at": "", "ends_at": "", "scenario_ids": [], "leaderboard_finalized": False, "leaderboard_finalized_at": ""}
                            else:
                                starts_at = datetime.fromisoformat(str(msg.payload.get("starts_at", "")))
                                ends_at = datetime.fromisoformat(str(msg.payload.get("ends_at", "")))
                                if starts_at.tzinfo is None or ends_at.tzinfo is None: raise ValueError("Časy eventu musí obsahovat časovou zónu.")
                                if starts_at >= ends_at: raise ValueError("Konec eventu musí následovat po jeho začátku.")
                                scenario_ids = list(dict.fromkeys(str(item) for item in msg.payload.get("scenario_ids", [])))
                                unknown = [item for item in scenario_ids if item not in scenario_catalog.entries]
                                if not scenario_ids: raise ValueError("Event musí obsahovat alespoň jednu hru.")
                                if unknown: raise ValueError("Event odkazuje na neznámé hry: " + ", ".join(unknown))
                                previous = configured_event()
                                same_event = previous is not None and str(previous.get("id")) == event_id
                                runtime_settings["event"] = {"id": event_id, "name": str(msg.payload.get("name", "")).strip() or event_id,
                                    "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(), "scenario_ids": scenario_ids,
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
                                        await broadcast_session(session_id, [Message("operations.stopped", {"message": "Herní provoz byl ukončen Game Masterem. Výsledek týmu je připraven k vyhodnocení."})])
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
                                    "mode": lobby.mode, "score": machine.state.score,
                                    "duration_seconds": result_duration_seconds(machine, completed_at),
                                    "completed_at": completed_at, "administrative": True, **leaderboard_identity(lobby)})
                                save_leaderboard()
                            machine.state.flags["administratively_evaluated"] = True; save_sessions()
                            update = Message("leaderboard.update", {"entries": leaderboard_entries()})
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            await send_admin_overview(websocket); continue

                        if msg.type == "admin.game_player":
                            machine = ensure_state_machine(target_session)
                            machine._participant_ids = list(lobby.players)
                            machine._participant_names = {key: str(value.get("name", "Hráč")) for key, value in lobby.players.items()}
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
                                    entry["score"] = machine.state.score
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
                        lobby_registry.by_session.pop(target_session, None)
                        active_sessions.pop(target_session, None)
                        session_connections.pop(target_session, None)
                        save_lobbies()
                        save_sessions()
                        await send_admin_overview(websocket)
                        continue
                    except (ValueError, TypeError) as error:
                        await send_message(websocket, Message("admin.error", {"message": str(error)}))
                        continue

                if msg.type in {"lobby.solo", "lobby.create", "lobby.join", "lobby.resume", "lobby.start", "lobby.identify", "lobby.add_player", "lobby.recover"}:
                    try:
                        requested_client_id = str(msg.payload.get("client_id", "")).strip()
                        if not requested_client_id:
                            raise ValueError("Chybí identifikátor zařízení.")
                        name = str(msg.payload.get("name", "")).strip()
                        team_name = str(msg.payload.get("team_name", "")).strip()
                        lobby_type = str(msg.payload.get("lobby_type", "on_site_qr")).strip()
                        requested_scenario_id = str(msg.payload.get("scenario_id", selected_scenario_id)).strip()
                        requested_demo = DEMO_MODE_ENABLED and bool(msg.payload.get("demo_mode"))
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
                            if lobby is None or requested_client_id != lobby.creator_id:
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
                            if lobby is None or requested_client_id != lobby.creator_id:
                                raise ValueError("Hru může spustit pouze zakladatel týmu.")
                            if not lobby.team_name or any(not str(player.get("name", "")).strip() for player in lobby.players.values()):
                                raise ValueError("Před spuštěním musí mít tým i všichni hráči vyplněné jméno.")
                            require_start_available(lobby.lobby_type, lobby.scenario_id)
                            lobby.started = True

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
                        save_lobbies()
                        await broadcast_lobby(lobby)

                        if lobby.started:
                            score_messages = apply_lobby_score(lobby, state_machine)
                            if msg.type in {"lobby.solo", "lobby.start"}:
                                hello = Message("client.hello", {"session_id": session_id, "demo_mode": demo_client,
                                                                "_client_id": client_id, "_participant_ids": list(lobby.players),
                                                                "_team_mode": lobby.mode,
                                                                "_participant_names": {key: str(value.get("name", "Hráč")) for key, value in lobby.players.items()}})
                                responses = await state_machine.handle(hello)
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
                    name = lobby.team_name
                    score = machine.state.score
                    if not any(e.get("session_id") == session_id for e in global_leaderboard):
                        global_leaderboard.append({"entry_id": secrets.token_hex(8), "session_id": session_id, "name": name,
                            "players": [str(player.get("name", "")) for player in lobby.players.values() if player.get("name")],
                            "mode": lobby.mode, "score": score,
                            "duration_seconds": result_duration_seconds(machine, str(machine.state.flags.get("completed_at", ""))),
                            "completed_at": machine.state.flags.get("completed_at", ""), **leaderboard_identity(lobby)})
                        save_leaderboard()
                    
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
                        active_sessions[session_id] = EscapeBotStateMachine(scenario)
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
                        msg.payload["_participant_ids"] = list(lobby_context.players)
                        msg.payload["_team_mode"] = lobby_context.mode
                        msg.payload["_participant_names"] = {key: str(value.get("name", "Hráč")) for key, value in lobby_context.players.items()}
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
                    responses = await state_machine.handle(msg)
                    if msg.type == "client.hello" and bool(msg.payload.get("demo_mode")):
                        if demo_client:
                            checkpoints = build_demo_checkpoint_catalog(state_machine.scenario)
                            responses.append(Message("demo.catalog", {"enabled": True, "checkpoints": checkpoints}))
                        else:
                            responses.append(Message("demo.catalog", {
                                "enabled": False,
                                "checkpoints": [],
                                "reason": "Backend nebyl spuštěn s parametrem --demo.",
                            }))
                    responses.append(Message(
                        "scenario.progress",
                        build_scenario_progress(state_machine.scenario, state_machine.state.snapshot()),
                    ))
                    if msg.type == "player.message" and session_id:
                        await broadcast_session(session_id, [Message("team.player_message", {
                            "client_id": client_id,
                            "channel": msg.payload.get("channel", "general"),
                            "text": msg.payload.get("text", ""),
                        })], exclude=websocket)
                    save_sessions()
                    if session_id and any(response.type == "game.complete" for response in responses):
                        completion_update = apply_outcome_score(state_machine, "completed", int(runtime_settings.get("completion_bonus", 100)))
                        if completion_update:
                            responses.insert(0, completion_update)
                            responses.append(state_machine._state_message())
                            save_sessions()
                        completed_lobby = lobby_registry.by_session.get(str(session_id))
                        if completed_lobby and not leaderboard_is_finalized() and not any(entry.get("session_id") == session_id for entry in global_leaderboard):
                            global_leaderboard.append({
                                "entry_id": secrets.token_hex(8),
                                "session_id": session_id,
                                "name": completed_lobby.team_name,
                                "players": [str(player.get("name", "")) for player in completed_lobby.players.values() if player.get("name")],
                                "mode": completed_lobby.mode,
                                "score": state_machine.state.score,
                                "duration_seconds": result_duration_seconds(state_machine, str(state_machine.state.flags.get("completed_at", ""))),
                                "completed_at": state_machine.state.flags.get("completed_at", ""),
                                **leaderboard_identity(completed_lobby),
                            })
                            save_leaderboard()
                            leaderboard_update = Message("leaderboard.update", {"entries": leaderboard_entries()})
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, leaderboard_update)
                                except Exception: pass
                        availability_update = Message("runtime.settings", runtime_payload())
                        for active_socket in list(app.state.active_websockets):
                            try: await send_message(active_socket, availability_update)
                            except Exception: pass
                    if session_id:
                        await broadcast_session(session_id, responses)
                    else:
                        for response in responses:
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
