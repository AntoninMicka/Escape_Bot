# Escape Bot

Escape Bot je lokální ARG/escape-room systém s odlehčeným webovým frontendem, centrálním Python backendem (orchestrátorem) a AI vrstvou pro analýzu fyzických stop, nápovědy a reakce.

## Cíle první verze

- Backend sloužící jako herní State Machine a komunikační centrum (WebSockets / HTTP).
- HTML/JS/CSS webový interkom (náhrada za složitý nativní klient) pro snadné nasazení na iPady a počítače v místnosti.
- Scénář "Ztracená v čase" pro Hotel Kraskov – oprava stroje času pomocí logických hádanek, fyzických artefaktů a QR checkpointů.
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

Server standardně zpřístupní web i WebSocket na `https://localhost:8088`.

Po otevření webu hráč zvolí sólo nebo založí tým. Pro fyzický startovní QR použijte adresu terminálu s parametrem `?team=1`, například:

```text
https://ADRESA-SERVERU:8088/?team=1
```

Zakladateli se v čekárně zobrazí unikátní QR pro ostatní zařízení. Příběh spustí až po připojení týmu. Sólo získává 20 bodů, dva hráči 10 bodů, tři hráči hrají bez úpravy a každý další hráč znamená 30 bodů dolů.

Notebook bez pohodlné kamery může zvolit **PŘIPOJIT NOTEBOOK** a zobrazit vlastní hráčský QR. Zakladatel ho načte telefonem ve své čekárně nebo opíše osmimístné ID. Jde o běžného hráče a zařízení se započítá do velikosti týmu. Doporučené uspořádání je jeden hráč na notebooku a ostatní na vlastních telefonech či noteboocích, vždy právě jedno zařízení na hráče.

### Vývojový demo režim

Pro ladění checkpointů bez kamery spusťte backend z kořene projektu:

```bash
./start_backend.sh --demo
```

Potom otevřete:

```text
https://localhost:8088/?demo=1
```

V záložce **SKENER** se místo kamery zobrazí tlačítka všech QR checkpointů a živá vizualizace průchodu scénářem. Ta ukazuje aktuální fázi, dokončené, dostupné a uzamčené uzly, skóre, inventář a pomůcky. Tlačítka posílají stejné zprávy jako reálný skener, proto zůstává aktivní kontrola pořadí, odměn i duplicit. Demo katalog backend neposkytne, pokud nebyl spuštěn s `--demo`.

## Rychlý start klienta (Interkom)

```bash
cd Escape_Bot/client
python3 -m http.server 8088
```
