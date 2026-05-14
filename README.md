# Escape Bot

Escape Bot je lokální ARG/escape-room klient s QML frontendem, Python backendem a AI vrstvou pro analýzu fyzických stop, nápovědy a atmosférické video/audio reakce.

## Cíle první verze

- JSON protokol přes WebSocket mezi nativním klientem a backendem.
- Python state machine pro řízení stavu hry.
- QML komunikátor s nativní C++ obsluhou kamery a QR vstupem.
- Adaptéry pro Ollama a ComfyUI bez pevné vazby na konkrétní workflow.
- Základní ARG verifikace fyzických objevů.
- Připravené místo pro CRT/glitch shadery a zvukové události.

## Struktura

```text
Escape_Bot/
  backend/          Python server, protokol a stav hry
  client/           Qt/QML klient, kamera, QR bridge, shadery
  docs/             Návrh protokolu a architektonické poznámky
  ai/               Adaptéry pro Ollama a ComfyUI
  arg/              Definice fyzických objevů a rébusů
  todo.md           Projektový checklist
```

## Rychlý start backendu

```bash
cd Escape_Bot/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m escape_bot.server
```

Server poslouchá na `ws://127.0.0.1:8765`.

## Rychlý start klienta

Klient je připravený jako Qt 6/CMake projekt. QR dekódování je zatím vyhrazené v `CameraQrBridge`; konkrétní implementace může použít ZXing-C++ nebo OpenCV podle cílové platformy.

```bash
cd Escape_Bot/client
cmake -S . -B build
cmake --build build
```
