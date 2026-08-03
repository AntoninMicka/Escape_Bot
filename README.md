# Escape Bot

Escape Bot je lokální ARG/escape-room systém s odlehčeným webovým frontendem, centrálním Python backendem (orchestrátorem) a AI vrstvou pro analýzu fyzických stop, nápovědy a reakce.

## Cíle první verze

- Backend sloužící jako herní State Machine a komunikační centrum (WebSockets / HTTP).
- HTML/JS/CSS webový interkom (náhrada za složitý nativní klient) pro snadné nasazení na iPady a počítače v místnosti.
- Scénář "Ztracená v čase" pro Hotel Kraskov – oprava stroje času pomocí logických hádanek, fyzických artefaktů a QR checkpointů.
- Volitelné adaptéry pro Ollama a ComfyUI bez vlivu na deterministický herní průchod; LLM se zapíná pouze explicitně přes `ESCAPEBOT_LLM_ENABLED=1`.
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

Návrh přenosné lokální infrastruktury, včetně centralizované varianty MikroTik a experimentálního distribuovaného Turris meshe, je v dokumentu [`docs/portable-infrastructure.md`](docs/portable-infrastructure.md).

Nativní administrační wrapper s vloženým webovým adminem a podporou vytvoření Wi-Fi AP na Linuxu je v adresáři [`desktop/`](desktop/README.md).

Wrapper lze sestavit a rovnou spustit příkazem `./build_and_run_desktop.sh`.

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

Hráč na vlastním telefonu otevře úvodní lobby, vyplní své jméno, zvolí **PŘIPOJIT SE K TÝMU** a buď načte týmový QR leadera fotoaparátem, nebo zadá osmimístný týmový kód. Odkaz obsažený v týmovém QR otevře předvyplněné připojení, které hráče nejprve vyzve k zadání jména. Zakladatel musí zadat unikátní název týmu; bez názvu týmu a jmen všech hráčů backend hru nespustí.

Notebook bez pohodlné kamery může zvolit **PŘIPOJIT NOTEBOOK** a zobrazit vlastní hráčský QR. Zakladatel ho načte telefonem ve své čekárně nebo opíše osmimístné ID. Jde o běžného hráče a zařízení se započítá do velikosti týmu. Doporučené uspořádání je jeden hráč na notebooku a ostatní na vlastních telefonech či noteboocích, vždy právě jedno zařízení na hráče.

### Administrační režim

Administrační konzoli povolte při startu vlastním heslem:

```bash
./start_backend.sh --demo --admin-token=ZVOLENE_HESLO
```

Poté otevřete `https://ADRESA-SERVERU:8088/admin` (případně `/?admin=1`). Konzole ukazuje týmy, hráče a jejich online stav, skóre, fázi a postup scénářem. Umožňuje udělit bodový malus s povinným důvodem nebo po potvrzení tým a jeho rozehranou relaci odstranit. Heslo se drží pouze v aktuální kartě prohlížeče (`sessionStorage`); bez proměnné `ESCAPEBOT_ADMIN_TOKEN` zůstává administrační API vypnuté. Dostupnost backendu lze ověřit na `/api/health`.

Admin může globálně přepnout **ONLINE REŽIM**. V něm se fyzické QR checkpointy nahradí akčními tlačítky přímo v Chronomapě; používají stejnou kontrolu pořadí a odměn jako QR skener. Přepnutí se okamžitě projeví všem týmům a ukládá se do `backend/runtime_settings.json`. Tisk QR sady zůstává dostupný i v online režimu.

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

## Automatický průchod scénářem

Z kořene projektu lze spustit samostatný smoke test celé produkční cesty:

```bash
./backend/run_scenario_smoke.sh
```

Test založí sólo i tříčlenné lobby, projde úvodní komunikaci, všechny checkpointy, pokoj 104, hlavní hádanky a minihry, uprostřed obnoví uloženou relaci a ověří finální inventář, skóre i návrat Elary. Nevyužívá administrační dokončení checkpointů.
