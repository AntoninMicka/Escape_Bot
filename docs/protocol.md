# Escape Bot WebSocket Protocol

Transport: JSON messages over WebSocket.

Default endpoint: `/ws` na stejném hostiteli jako webový klient (při lokálním HTTPS typicky `wss://localhost:8088/ws`).

Every message has:

```json
{
  "type": "message.type",
  "request_id": "optional-client-id",
  "payload": {}
}
```

## Client -> Backend

### `client.hello`

Starts a session.

```json
{
  "type": "client.hello",
  "request_id": "hello-1",
  "payload": {
    "client_name": "Escape Bot QML",
    "protocol_version": 1
  }
}
```

### `player.message`

Sends text from the player.

```json
{
  "type": "player.message",
  "request_id": "msg-42",
  "payload": {
    "text": "Nasel jsem symbol pod stolem."
  }
}
```

### `camera.frame`

Sends an extracted still frame reference or base64 blob.

```json
{
  "type": "camera.frame",
  "request_id": "frame-3",
  "payload": {
    "mime_type": "image/jpeg",
    "data": "<base64-or-local-ref>"
  }
}
```

### `qr.detected`

Reports a decoded QR value.

```json
{
  "type": "qr.detected",
  "request_id": "qr-7",
  "payload": {
    "value": "escapebot://checkpoint/4ec67b900c4a491ba180c8a48d5309f2"
  }
}
```

QR payload obsahuje neprůhledný token definovaný ve scénáři. Server odmítne neznámé tokeny a checkpointy naskenované před splněním jejich předchůdců.

### `cipher_tool.unlock`

Trvale odemkne pasivní šifrovací pomůcku pro aktuální relaci. Pokud ji hráč nezískal checkpointem, server jednorázově odečte cenu ze scénáře.

```json
{
  "type": "cipher_tool.unlock",
  "payload": {
    "tool_id": "pigpen"
  }
}
```

### `puzzle.submit`

Odešle řešení nalezené hádanky. Backend ověří, že její fyzický checkpoint byl skutečně nalezen, zaznamená pokus a teprve správným řešením označí checkpoint jako dokončený.

```json
{
  "type": "puzzle.submit",
  "payload": {
    "puzzle_id": "reception_deduction",
    "answer": "2147"
  }
}
```

### `puzzle.hint`

Vyžádá další stupňovanou nápovědu. Každý stupeň odečte body pouze při prvním zobrazení.

### `line_game.move`

Prohodí dvě ortogonálně sousední barvy v interaktivní kalibrační mřížce. Souřadnice jsou indexované od nuly; backend kontroluje odemčení checkpointu, časový limit a to, zda výměna vytvořila alespoň jednu řadu.

```json
{
  "type": "line_game.move",
  "payload": {
    "puzzle_id": "timeline_lines",
    "first": [2, 4],
    "second": [2, 5]
  }
}
```

### `line_game.reset`

Spustí nový pokus: obnoví pětibarevnou mřížku, průběh všech tří cílů i časový limit.

```json
{
  "type": "line_game.reset",
  "payload": {
    "puzzle_id": "timeline_lines"
  }
}
```

### `sokoban.command`

Provede deterministickou sekvenci pohybů Elary. Povolené hodnoty jsou `up`, `down`, `left` a `right`; sekvence se zastaví před první neprůchodnou stěnou nebo článkem. Stejnou zprávu vytváří parser českých povelů z kanálu Elary.

```json
{
  "type": "sokoban.command",
  "payload": {
    "puzzle_id": "sports_sokoban",
    "commands": ["right", "up", "left"]
  }
}
```

### `sokoban.undo` a `sokoban.reset`

`undo` vrátí poslední skutečně provedený krok včetně zatlačení článku. `reset` obnoví počáteční mapu a zvýší počítadlo restartů.

### `arg.verify`

Asks backend to verify a physical discovery.

```json
{
  "type": "arg.verify",
  "request_id": "verify-1",
  "payload": {
    "discovery_id": "lobby-panel-a",
    "evidence": {
      "qr_value": "escapebot://clue/lobby-panel-a"
    }
  }
}
```

## Backend -> Client

### `game.state`

Broadcasts current state.

```json
{
  "type": "game.state",
  "payload": {
    "phase": "investigating",
    "unlocked_discoveries": ["lobby-panel-a"],
    "inventory": []
  }
}
```

### `qr.result`

Vrátí výsledek kontroly časové kotvy. `duplicate` znamená, že kotva již byla v dané relaci započítána.

```json
{
  "type": "qr.result",
  "payload": {
    "accepted": true,
    "duplicate": false,
    "checkpoint_id": "reception_archive"
  }
}
```

### `cipher_tool.result`

Potvrdí odemčení pomůcky a uvádí skutečně odečtené body v poli `charged`.

### `puzzle.result`

Vrátí `correct`, identifikátor hádanky a aktuální počet pokusů. Aktualizovaný `game.state` následně obsahuje veřejné zadání hádanky a stav `found` nebo `solved`; správná odpověď se klientovi neposílá.

### `line_game.result`

Potvrdí nebo odmítne výměnu či restart. Úspěšná výměna obsahuje `scored`, počet `cascades` a `game_complete`. Při dokončení obsahuje také `score_delta`: před třetí minutou +5 bodů za každých 10 sekund náskoku, po třetí minutě −5 bodů za každých 10 sekund zpoždění. Změna je současně potvrzena zprávou `score.update`. Autoritativní mřížka, deadline, zbývající čas a průběh cílů jsou vždy poslány v následném `game.state` uvnitř příslušné hádanky.

### `sokoban.result`

Obsahuje počet požadovaných a skutečně provedených kroků, počet zatlačení, příznaky `blocked`, `level_complete` a případně `game_complete`. Pole `frames` obsahuje po každém provedeném kroku povel, pozici Elary, pozice článků, počítadla a příznak zatlačení; klient z něj přehrává animaci. Při překážce `blocked_command` určuje první nevykonaný povel. Každá poprvé dokončená úroveň vrátí `score_delta` a zprávu `score.update`; aktuálně jde o +30 bodů. Každá úroveň má vlastní dvouminutový deadline. Po dokončení celé aktivní sady následuje běžný `puzzle.result`, příběhová zpráva a aktualizovaný `game.state` s odměnami checkpointu.

## Vývojový demo režim

Klient může v `client.hello` poslat `demo_mode: true`. Pouze backend spuštěný s proměnnou `ESCAPEBOT_DEMO_MODE=1` odpoví zprávou `demo.catalog` obsahující simulovatelné checkpointy. Produkční backend vrátí stejný typ zprávy s `enabled: false` a QR tokeny nezveřejní.

Po každé herní zprávě demo klient dostane také `scenario.progress`. Jde o prezentačně nezávislý snapshot s aktuální fází, skóre, inventářem a uzly ve stavech `complete`, `active`, `available` nebo `locked`. Stejný formát je určen pro budoucí administrátorský přehled více relací; admin rozhraní později pouze seskupí jeden snapshot pro každé `session_id`.

### `bot.message`

Displays bot dialogue.

```json
{
  "type": "bot.message",
  "payload": {
    "text": "Ten panel neni dekorace. Zkus zjistit, co napaji.",
    "mood": "tense"
  }
}
```

### `effect.trigger`

Triggers visual or audio atmosphere.

```json
{
  "type": "effect.trigger",
  "payload": {
    "effect": "glitch",
    "intensity": 0.6,
    "duration_ms": 1200
  }
}
```
