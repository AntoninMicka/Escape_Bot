from __future__ import annotations

import secrets
import uuid
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def team_size_adjustment(mode: str, max_players: int) -> int:
    if mode == "solo":
        return 20
    if max_players < 3:
        return (3 - max_players) * 10
    if max_players > 3:
        return -(max_players - 3) * 30
    return 0


def classify_activity(started: bool, completed: bool, inactive_seconds: int) -> str:
    if not started or completed:
        return "active"
    if inactive_seconds >= 3600:
        return "abandoned"
    if inactive_seconds >= 1800:
        return "suspicious"
    return "active"


@dataclass
class Lobby:
    session_id: str
    mode: str
    creator_id: str
    team_name: str
    join_code: str | None = None
    started: bool = False
    players: dict[str, dict[str, Any]] = field(default_factory=dict)
    max_players: int = 0
    applied_score_adjustment: int = 0

    def add_player(self, client_id: str, name: str = "") -> None:
        clean_name = " ".join(name.strip().split())[:24]
        if client_id not in self.players:
            if not clean_name:
                raise ValueError("Jméno hráče je povinné.")
            self.players[client_id] = {
                "id": client_id,
                "name": clean_name,
                "joined_at": datetime.now(UTC).isoformat(),
            }
        elif clean_name:
            self.players[client_id]["name"] = clean_name
        self.max_players = max(self.max_players, len(self.players))

    def score_delta(self) -> int:
        desired = team_size_adjustment(self.mode, self.max_players)
        delta = desired - self.applied_score_adjustment
        self.applied_score_adjustment = desired
        return delta

    def transfer_player(self, old_client_id: str, new_client_id: str) -> dict[str, Any]:
        if old_client_id not in self.players:
            raise ValueError("Původní hráč v týmu neexistuje.")
        if not new_client_id:
            raise ValueError("Chybí identifikátor nového zařízení.")
        if new_client_id in self.players and new_client_id != old_client_id:
            raise ValueError("Nové zařízení už v tomto týmu patří jinému hráči.")
        player = self.players.pop(old_client_id)
        player["id"] = new_client_id
        player["recovered_at"] = datetime.now(UTC).isoformat()
        self.players[new_client_id] = player
        if self.creator_id == old_client_id:
            self.creator_id = new_client_id
        return player

    def public(self, client_id: str, connected_ids: set[str]) -> dict[str, Any]:
        online_count = sum(player_id in connected_ids for player_id in self.players)
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "team_name": self.team_name,
            "join_code": self.join_code,
            "started": self.started,
            "is_creator": client_id == self.creator_id,
            # Velikost týmu je vlastnost relace. Uspání telefonu mění pouze
            # dostupnost hráče, nikdy týmový režim ani bodové vyhodnocení.
            "player_count": len(self.players),
            "online_count": online_count,
            "registered_players": len(self.players),
            "max_players": self.max_players,
            "score_adjustment": self.applied_score_adjustment,
            "players": [
                {**player, "connected": player["id"] in connected_ids}
                for player in self.players.values()
            ],
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "creator_id": self.creator_id,
            "team_name": self.team_name,
            "join_code": self.join_code,
            "started": self.started,
            "players": self.players,
            "max_players": self.max_players,
            "applied_score_adjustment": self.applied_score_adjustment,
        }


class LobbyRegistry:
    def __init__(self) -> None:
        self.by_session: dict[str, Lobby] = {}
        self.by_join_code: dict[str, str] = {}

    def create(self, client_id: str, mode: str, name: str = "", team_name: str = "") -> Lobby:
        if mode not in {"solo", "team"}:
            raise ValueError("Neznámý herní režim.")
        clean_team_name = " ".join(team_name.strip().split())[:32]
        if not clean_team_name:
            raise ValueError("Název týmu je povinný.")
        normalized = _normalize_team_name(clean_team_name)
        if any(_normalize_team_name(lobby.team_name) == normalized for lobby in self.by_session.values()):
            raise ValueError("Tým s tímto názvem už existuje. Zvolte jiný název.")
        session_id = uuid.uuid4().hex
        join_code = self._new_join_code() if mode == "team" else None
        lobby = Lobby(session_id=session_id, mode=mode, creator_id=client_id, team_name=clean_team_name, join_code=join_code)
        lobby.add_player(client_id, name)
        if mode == "solo":
            lobby.started = True
        self.by_session[session_id] = lobby
        if join_code:
            self.by_join_code[join_code] = session_id
        return lobby

    def join(self, join_code: str, client_id: str, name: str = "") -> Lobby:
        session_id = self.by_join_code.get(join_code.strip().upper())
        if not session_id:
            raise ValueError("Připojovací kód není platný nebo server mezitím restartoval.")
        lobby = self.by_session[session_id]
        lobby.add_player(client_id, name)
        return lobby

    def resume(self, session_id: str, client_id: str, name: str = "") -> Lobby:
        lobby = self.by_session.get(session_id)
        if lobby is None or client_id not in lobby.players:
            raise ValueError("Uloženou týmovou relaci se nepodařilo obnovit.")
        lobby.add_player(client_id, name)
        return lobby

    def _new_join_code(self) -> str:
        while True:
            code = secrets.token_hex(4).upper()
            if code not in self.by_join_code:
                return code

    def snapshot(self) -> list[dict[str, Any]]:
        return [lobby.snapshot() for lobby in self.by_session.values()]

    def restore(self, items: list[dict[str, Any]]) -> None:
        self.by_session.clear()
        self.by_join_code.clear()
        for item in items:
            lobby = Lobby(
                session_id=str(item["session_id"]),
                mode=str(item["mode"]),
                creator_id=str(item["creator_id"]),
                team_name=str(item.get("team_name", f"Obnovený tým {str(item['session_id'])[:6]}")),
                join_code=item.get("join_code"),
                started=bool(item.get("started")),
                players=dict(item.get("players", {})),
                max_players=int(item.get("max_players", 0)),
                applied_score_adjustment=int(item.get("applied_score_adjustment", 0)),
            )
            self.by_session[lobby.session_id] = lobby
            if lobby.join_code:
                self.by_join_code[lobby.join_code] = lobby.session_id


def _normalize_team_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
