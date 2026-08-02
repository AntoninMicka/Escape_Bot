from __future__ import annotations

import secrets
import uuid
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


@dataclass
class Lobby:
    session_id: str
    mode: str
    creator_id: str
    join_code: str | None = None
    started: bool = False
    players: dict[str, dict[str, Any]] = field(default_factory=dict)
    max_players: int = 0
    applied_score_adjustment: int = 0

    def add_player(self, client_id: str, name: str = "") -> None:
        if client_id not in self.players:
            self.players[client_id] = {
                "id": client_id,
                "name": name.strip()[:24] or f"Hráč {len(self.players) + 1}",
                "joined_at": datetime.now(UTC).isoformat(),
            }
        elif name.strip():
            self.players[client_id]["name"] = name.strip()[:24]
        self.max_players = max(self.max_players, len(self.players))

    def score_delta(self) -> int:
        desired = team_size_adjustment(self.mode, self.max_players)
        delta = desired - self.applied_score_adjustment
        self.applied_score_adjustment = desired
        return delta

    def public(self, client_id: str, connected_ids: set[str]) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "join_code": self.join_code,
            "started": self.started,
            "is_creator": client_id == self.creator_id,
            "player_count": sum(player_id in connected_ids for player_id in self.players),
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

    def create(self, client_id: str, mode: str, name: str = "") -> Lobby:
        if mode not in {"solo", "team"}:
            raise ValueError("Neznámý herní režim.")
        session_id = uuid.uuid4().hex
        join_code = self._new_join_code() if mode == "team" else None
        lobby = Lobby(session_id=session_id, mode=mode, creator_id=client_id, join_code=join_code)
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
                join_code=item.get("join_code"),
                started=bool(item.get("started")),
                players=dict(item.get("players", {})),
                max_players=int(item.get("max_players", 0)),
                applied_score_adjustment=int(item.get("applied_score_adjustment", 0)),
            )
            self.by_session[lobby.session_id] = lobby
            if lobby.join_code:
                self.by_join_code[lobby.join_code] = lobby.session_id
