# Escape Bot WebSocket Protocol

Transport: JSON messages over WebSocket.

Default endpoint: `ws://127.0.0.1:8765`.

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

## Vývojový demo režim

Klient může v `client.hello` poslat `demo_mode: true`. Pouze backend spuštěný s proměnnou `ESCAPEBOT_DEMO_MODE=1` odpoví zprávou `demo.catalog` obsahující simulovatelné checkpointy. Produkční backend vrátí stejný typ zprávy s `enabled: false` a QR tokeny nezveřejní.

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
