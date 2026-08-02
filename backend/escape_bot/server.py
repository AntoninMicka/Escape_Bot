import asyncio
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
from datetime import UTC, datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .protocol import Message
from .state_machine import EscapeBotStateMachine
from .scenario import ScenarioLoader, build_checkpoint_qr_set, build_demo_checkpoint_catalog, build_scenario_progress
from .ollama_adapter import OllamaAdapter
from .team_lobby import Lobby, LobbyRegistry, classify_activity

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EscapeBot")

# Dynamické nalezení absolutní cesty do složky client/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_DIR = os.path.join(BASE_DIR, "client")
SESSIONS_FILE = os.path.join(BASE_DIR, "backend", "sessions.json")
LOBBIES_FILE = os.path.join(BASE_DIR, "backend", "lobbies.json")
RUNTIME_SETTINGS_FILE = os.path.join(BASE_DIR, "backend", "runtime_settings.json")

# Úložiště pro nezávislé relace hráčů (session_id -> state_machine)
active_sessions: dict[str, EscapeBotStateMachine] = {}
lobby_registry = LobbyRegistry()
session_connections: dict[str, set[WebSocket]] = {}
connection_info: dict[WebSocket, dict[str, object]] = {}
waiting_players: dict[str, dict[str, object]] = {}
recovery_tokens: dict[str, dict[str, object]] = {}
DEMO_MODE_ENABLED = os.getenv("ESCAPEBOT_DEMO_MODE", "").lower() in {"1", "true", "yes", "on"}
ADMIN_TOKEN = os.getenv("ESCAPEBOT_ADMIN_TOKEN", "")
runtime_settings = {"online_mode": False}

LEADERBOARD_FILE = os.path.join(BASE_DIR, "backend", "leaderboard.json")
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
        result.append(entry)
    return sorted(result, key=lambda item: int(item.get("score", 0)), reverse=True)

def save_leaderboard():
    with open(LEADERBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(global_leaderboard, f, indent=2, ensure_ascii=False)

def load_leaderboard():
    global global_leaderboard
    if os.path.exists(LEADERBOARD_FILE):
        try:
            with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
                global_leaderboard = json.load(f)
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
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_sessions(scenario):
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sid, s_data in data.items():
                sm = EscapeBotStateMachine(scenario)
                sm.restore_state(s_data)
                active_sessions[sid] = sm
            logger.info(f"Úspěšně obnoveno {len(active_sessions)} uložených relací ze souboru sessions.json.")
        except Exception as e:
            logger.error(f"Chyba při načítání souboru relací: {e}")

def save_lobbies():
    with open(LOBBIES_FILE, "w", encoding="utf-8") as file:
        json.dump(lobby_registry.snapshot(), file, indent=2, ensure_ascii=False)

def load_lobbies():
    if not os.path.exists(LOBBIES_FILE):
        return
    try:
        with open(LOBBIES_FILE, "r", encoding="utf-8") as file:
            lobby_registry.restore(json.load(file))
    except Exception as error:
        logger.error(f"Chyba při načítání týmových lobby: {error}")

def load_runtime_settings():
    if os.path.exists(RUNTIME_SETTINGS_FILE):
        try:
            with open(RUNTIME_SETTINGS_FILE, "r", encoding="utf-8") as file: runtime_settings.update(json.load(file))
        except Exception as error: logger.error(f"Chyba nastavení režimu: {error}")

def save_runtime_settings():
    with open(RUNTIME_SETTINGS_FILE, "w", encoding="utf-8") as file: json.dump(runtime_settings, file, indent=2, ensure_ascii=False)

scenario_path = os.path.join(BASE_DIR, "backend", "scenario.json")
scenario = ScenarioLoader.load(scenario_path)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_leaderboard()
    load_lobbies()
    load_runtime_settings()
    # 1. Načtení uložených stavů her z předchozího běhu
    load_sessions(scenario)
    # 2. Kontrola AI modelů na pozadí 
    ai_checker = OllamaAdapter()
    asyncio.create_task(ai_checker.ensure_model())
    yield

# --- Inicializace FastAPI ---
app = FastAPI(title="Escape Bot", lifespan=lifespan)


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
                await send_message(websocket, message)
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
        active_sessions[session_id] = EscapeBotStateMachine(scenario)
    return active_sessions[session_id]


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


def admin_overview() -> list[dict[str, object]]:
    teams: list[dict[str, object]] = []
    for lobby in lobby_registry.by_session.values():
        machine = active_sessions.get(lobby.session_id)
        state = machine.state.snapshot() if machine else {}
        progress = build_scenario_progress(scenario, state) if machine else {"nodes": []}
        nodes = list(progress.get("nodes", []))
        flags = state.get("flags", {})
        penalties = list(flags.get("admin_penalties", []))
        checkpoint_states = dict(state.get("checkpoint_states", {}))
        timeline: list[dict[str, object]] = []
        for checkpoint_id, checkpoint in checkpoint_states.items():
            found_at = checkpoint.get("first_scanned_at") or checkpoint.get("found_at")
            if found_at:
                timeline.append({"at": found_at, "type": "checkpoint_found", "label": checkpoint_id})
            if checkpoint.get("solved_at"):
                timeline.append({"at": checkpoint["solved_at"], "type": "checkpoint_solved", "label": checkpoint_id})
        for penalty in penalties:
            timeline.append({"at": penalty.get("at", ""), "type": "admin_penalty", "label": penalty.get("reason", ""), "amount": penalty.get("amount", 0)})
        for action in flags.get("admin_actions", []):
            timeline.append({"at": action.get("at", ""), "type": "admin_action", "label": action.get("label", "")})
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
        activity_status = classify_activity(lobby.started, game_completed, inactive_seconds)
        teams.append({
            **lobby.public("", connected_client_ids(lobby.session_id)),
            "score": int(state.get("score", 1000)),
            "phase": str(state.get("phase", "boot")),
            "completed_nodes": sum(node.get("status") == "complete" for node in nodes),
            "total_nodes": len(nodes),
            "progress": progress,
            "admin_penalties": penalties,
            "last_activity": last_activity,
            "inactive_seconds": inactive_seconds,
            "activity_status": activity_status,
            "game_completed": game_completed,
            "timeline": timeline[:30],
            "hints_used": dict(state.get("hints_used", {})),
            "puzzle_attempts": dict(state.get("puzzle_attempts", {})),
            "recent_messages": list(state.get("chat_history", []))[-8:],
            "game_metrics": {
                "line": [{"id": game_id, "status": game.get("status", ""), "swaps": game.get("swaps", 0),
                          "progress": dict(game.get("progress", {}))}
                         for game_id, game in line_games.items()],
                "karel": [{"id": game_id, "level": game.get("level_label", ""), "completed": len(game.get("completed_levels", [])),
                           "moves": game.get("total_moves", 0), "strikes": game.get("total_strikes", 0), "restarts": game.get("restarts", 0),
                           "player": list(game.get("player", []))}
                          for game_id, game in karel_games.items()],
                "sokoban": [{"id": game_id, "level": game.get("level_label", ""), "completed": len(game.get("completed_levels", [])),
                              "moves": game.get("total_moves", 0), "pushes": game.get("total_pushes", 0), "restarts": game.get("restarts", 0),
                              "player": list(game.get("player", [])), "boxes": list(game.get("boxes", [])), "targets": list(game.get("targets", []))}
                             for game_id, game in sokoban_games.items()],
                "triad": [{"id": game_id, "status": game.get("status", ""), "placements": game.get("placements", 0),
                           "completed_orientations": list(game.get("completed_orientations", []))}
                          for game_id, game in triad_games.items()],
                "archive": [{"id": game_id, "assembled": bool(game.get("assembled")), "moves": int(game.get("moves", 0)),
                             "order": list(game.get("order", [])), "rotations": dict(game.get("rotations", {}))}
                            for game_id, game in archive_games.items()],
            },
        })
    return sorted(teams, key=lambda team: str(team.get("team_name", "")).casefold())


async def send_admin_overview(websocket: WebSocket) -> None:
    await send_message(websocket, Message("admin.overview", {
        "teams": admin_overview(),
        "leaderboard": leaderboard_entries(),
        "abandonment_thresholds": {"suspicious_seconds": 1800, "abandoned_seconds": 3600},
    }))


async def sync_started_client(websocket: WebSocket, state_machine: EscapeBotStateMachine, demo_client: bool) -> None:
    """Send a complete authoritative snapshot after join, resume, or device wake-up."""
    await send_message(websocket, Message("chat.history", {"messages": state_machine.state.chat_history}))
    await send_message(websocket, state_machine._state_message())
    await send_message(websocket, Message(
        "scenario.progress",
        build_scenario_progress(scenario, state_machine.state.snapshot()),
    ))
    if demo_client:
        await send_message(websocket, Message("demo.catalog", {
            "enabled": True,
            "checkpoints": build_demo_checkpoint_catalog(scenario),
        }))
    await send_message(websocket, Message("runtime.settings", {**runtime_settings, "checkpoints": build_demo_checkpoint_catalog(scenario)}))


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
    return {"status": "ok", "admin_enabled": bool(ADMIN_TOKEN), "online_mode": bool(runtime_settings.get("online_mode"))}


@app.get("/admin")
async def admin_page() -> RedirectResponse:
    return RedirectResponse(url="/?admin=1", status_code=307)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
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

                if msg.type in {"admin.list", "admin.penalty", "admin.delete", "admin.qr_set", "admin.online_mode", "admin.checkpoint", "admin.game_reset", "admin.player_recovery", "admin.leaderboard_delete"}:
                    try:
                        require_admin(msg.payload)
                        if msg.type == "admin.list":
                            await send_admin_overview(websocket)
                            await send_message(websocket, Message("runtime.settings", {**runtime_settings, "checkpoints": build_demo_checkpoint_catalog(scenario)}))
                            continue
                        if msg.type == "admin.qr_set":
                            await send_message(websocket, Message("admin.qr_set", {"scenario": scenario.data.get("title", "Escape Bot"), "checkpoints": build_checkpoint_qr_set(scenario)}))
                            continue
                        if msg.type == "admin.online_mode":
                            runtime_settings["online_mode"] = bool(msg.payload.get("enabled"))
                            save_runtime_settings()
                            update = Message("runtime.settings", {**runtime_settings, "checkpoints": build_demo_checkpoint_catalog(scenario)})
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, update)
                                except Exception: pass
                            continue
                        if msg.type == "admin.leaderboard_delete":
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

                        target_session = str(msg.payload.get("session_id", "")).strip()
                        lobby = lobby_registry.by_session.get(target_session)
                        if lobby is None:
                            raise ValueError("Týmová relace už neexistuje.")

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

                        if msg.type == "admin.penalty":
                            amount = int(msg.payload.get("amount", 0))
                            reason = " ".join(str(msg.payload.get("reason", "")).strip().split())[:160]
                            if amount < 1 or amount > 1000:
                                raise ValueError("Malus musí být v rozsahu 1 až 1000 bodů.")
                            if not reason:
                                raise ValueError("U malusu je povinný důvod.")
                            machine = ensure_state_machine(target_session)
                            machine.state.score -= amount
                            machine.state.flags.setdefault("admin_penalties", []).append({
                                "amount": amount,
                                "reason": reason,
                                "at": datetime.now(UTC).isoformat(),
                            })
                            save_sessions()
                            await broadcast_session(target_session, [
                                Message("score.update", {
                                    "score": machine.state.score,
                                    "delta": -amount,
                                    "bonus": 0,
                                    "penalty": amount,
                                    "reason": "admin_penalty",
                                    "description": reason,
                                }),
                                Message("bot.message", {
                                    "text": f"Administrátorský malus −{amount} bodů: {reason}",
                                    "mood": "tense",
                                    "channel": "general",
                                }),
                                machine._state_message(),
                            ])
                            await send_admin_overview(websocket)
                            continue

                        if msg.type == "admin.checkpoint":
                            checkpoint_id = str(msg.payload.get("checkpoint_id", "")).strip()
                            status = str(msg.payload.get("status", "")).strip()
                            machine = ensure_state_machine(target_session)
                            result = machine.admin_set_checkpoint(checkpoint_id, status)
                            label = f"Checkpoint {checkpoint_id}: {status}"
                            machine.state.flags.setdefault("admin_actions", []).append({
                                "action": "checkpoint", "label": label, "at": datetime.now(UTC).isoformat(), **result,
                            })
                            save_sessions()
                            await broadcast_session(target_session, [
                                Message("bot.message", {"text": f"Game Master upravil postup: {label}.", "mood": "info", "channel": "general"}),
                                machine._state_message(),
                                Message("scenario.progress", build_scenario_progress(scenario, machine.state.snapshot())),
                            ])
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
                                Message("scenario.progress", build_scenario_progress(scenario, machine.state.snapshot())),
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
                            lobby = lobby_registry.create(requested_client_id, "solo", name, team_name)
                        elif msg.type == "lobby.create":
                            lobby = lobby_registry.create(requested_client_id, "team", name, team_name)
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
                            lobby.started = True

                        session_id = lobby.session_id
                        client_id = requested_client_id
                        demo_client = requested_demo
                        attach_to_lobby(websocket, lobby, client_id, demo_client)
                        state_machine = ensure_state_machine(session_id)
                        save_lobbies()
                        await broadcast_lobby(lobby)

                        if lobby.started:
                            score_messages = apply_lobby_score(lobby, state_machine)
                            if msg.type in {"lobby.solo", "lobby.start"}:
                                hello = Message("client.hello", {"session_id": session_id, "demo_mode": demo_client})
                                responses = await state_machine.handle(hello)
                                responses.extend(score_messages)
                                if demo_client:
                                    responses.append(Message("demo.catalog", {
                                        "enabled": True,
                                        "checkpoints": build_demo_checkpoint_catalog(scenario),
                                    }))
                                responses.append(Message("scenario.progress", build_scenario_progress(scenario, state_machine.state.snapshot())))
                                await broadcast_session(session_id, responses)
                            else:
                                await sync_started_client(websocket, state_machine, demo_client)
                                if score_messages:
                                    await broadcast_session(session_id, score_messages)
                            await send_message(websocket, Message("runtime.settings", {**runtime_settings, "checkpoints": build_demo_checkpoint_catalog(scenario)}))
                        continue
                    except ValueError as error:
                        await send_message(websocket, Message("lobby.error", {"message": str(error)}))
                        continue
                
                # Zpracování požadavků na Síň slávy (mimo state machine)
                if msg.type == "leaderboard.get":
                    await websocket.send_text(json.dumps(Message("leaderboard.update", {"entries": leaderboard_entries()}).to_json()))
                    continue
                    
                if msg.type == "leaderboard.save":
                    lobby = lobby_registry.by_session.get(str(session_id))
                    machine = active_sessions.get(str(session_id))
                    if not lobby or not machine or not machine.state.flags.get("game_completed"):
                        await send_message(websocket, Message("error", {"message": "Výsledek lze zapsat až po dokončení hry."}))
                        continue
                    name = lobby.team_name
                    score = machine.state.score
                    if not any(e.get("session_id") == session_id for e in global_leaderboard):
                        global_leaderboard.append({"entry_id": secrets.token_hex(8), "session_id": session_id, "name": name, "players": [str(player.get("name", "")) for player in lobby.players.values() if player.get("name")], "score": score, "completed_at": machine.state.flags.get("completed_at", "")})
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
                    responses = await state_machine.handle(msg)
                    if msg.type == "client.hello" and bool(msg.payload.get("demo_mode")):
                        if demo_client:
                            checkpoints = build_demo_checkpoint_catalog(scenario)
                            responses.append(Message("demo.catalog", {"enabled": True, "checkpoints": checkpoints}))
                        else:
                            responses.append(Message("demo.catalog", {
                                "enabled": False,
                                "checkpoints": [],
                                "reason": "Backend nebyl spuštěn s parametrem --demo.",
                            }))
                    responses.append(Message(
                        "scenario.progress",
                        build_scenario_progress(scenario, state_machine.state.snapshot()),
                    ))
                    if msg.type == "player.message" and session_id:
                        await broadcast_session(session_id, [Message("team.player_message", {
                            "client_id": client_id,
                            "channel": msg.payload.get("channel", "general"),
                            "text": msg.payload.get("text", ""),
                        })], exclude=websocket)
                    save_sessions()
                    if session_id and any(response.type == "game.complete" for response in responses):
                        completed_lobby = lobby_registry.by_session.get(str(session_id))
                        if completed_lobby and not any(entry.get("session_id") == session_id for entry in global_leaderboard):
                            global_leaderboard.append({
                                "entry_id": secrets.token_hex(8),
                                "session_id": session_id,
                                "name": completed_lobby.team_name,
                                "players": [str(player.get("name", "")) for player in completed_lobby.players.values() if player.get("name")],
                                "score": state_machine.state.score,
                                "completed_at": state_machine.state.flags.get("completed_at", ""),
                            })
                            save_leaderboard()
                            leaderboard_update = Message("leaderboard.update", {"entries": leaderboard_entries()})
                            for active_socket in list(app.state.active_websockets):
                                try: await send_message(active_socket, leaderboard_update)
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
    main()
