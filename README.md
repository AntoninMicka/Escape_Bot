# Escape Bot

Escape Bot je lokální ARG/escape-room systém s odlehčeným webovým frontendem, centrálním Python backendem (orchestrátorem) a AI vrstvou pro analýzu fyzických stop, nápovědy a reakce.

## Cíle první verze

- Backend sloužící jako herní State Machine a komunikační centrum (WebSockets / HTTP).
- HTML/JS/CSS webový interkom (náhrada za složitý nativní klient) pro snadné nasazení na iPady a počítače v místnosti.
- Scénář "Ztracená v jiné dimenzi" - řešení hádanek napříč dimenzemi.
- Adaptéry pro Ollama a ComfyUI bez pevné vazby na konkrétní workflow.
- Základní ARG verifikace fyzických objevů.
- Připravené místo pro CRT/glitch shadery a zvukové události.

## Struktura

```text
Escape_Bot/
  backend/          Python webserver, WebSocket protokol, orchestrátor a stav hry
  client/           HTML/JS/CSS webová aplikace interkomu a rébusů
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

## Rychlý start klienta (Interkom)

```bash
cd Escape_Bot/client
python3 -m http.server 8080
```
