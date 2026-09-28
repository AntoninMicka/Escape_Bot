# Roadmap: migrace Escape Botu na Cloudflare

## Cíl

Přesunout veřejný klient, API, WebSocket komunikaci a trvalý stav Escape Botu na
Cloudflare tak, aby každá rozehraná hra měla jeden autoritativní stav, přežila
hibernaci i nové nasazení a nebyla závislá na paměti jednoho FastAPI procesu.

Migrace zachová současný WebSocket protokol, chování klientů a možnost návratu
na stávající provozní variantu. Produkční přepnutí proběhne až po živém testu na
telefonech a terminálech.

## Rozhodnutí o cílové architektuře

```text
Telefon / terminál / nástěnka / admin
                 │ HTTPS + WSS
                 ▼
         Cloudflare Worker
         ├── Workers Static Assets
         ├── autentizace a routing
         └── směrování podle session_id
                 │
                 ▼
 GameSession Durable Object, jeden pro každou hru
 ├── autoritativní snapshot hry
 ├── WebSockety hráčů a terminálů
 ├── serializované herní povely
 ├── chat a přítomnost
 └── deadline alarmy
                 │
        ┌────────┴────────┐
        ▼                 ▼
 Event Durable Object     D1
 event, fronta, admin,    katalog, index relací,
 nástěnka, oznámení       výsledky a audit
                          │
                          ▼
                          R2
                    exporty a velká aktiva
```

Cloudflare Container není cílovým runtime. Může dočasně hostovat současný
FastAPI image, ale jeho lokální disk je pomíjivý a sám neřeší procesní stav
WebSocketů. FastAPI v Python Workeru je vhodné prověřit pro čistou výpočetní
část, nikoli jako přímé spuštění současného `server.py`.

## Zásady migrace

- `GameSession` Durable Object je autoritou jedné rozehrané relace.
- Paměť Workeru ani Durable Objectu není trvalý stav; po probuzení musí být vše
  obnovitelné z úložiště a WebSocket attachments.
- Stávající typy zpráv z `docs/protocol.md` se během první migrace nemění.
- Herní příkazy, které mění skóre nebo postup, nesou stabilní `operation_id`.
- D1 je globální index a projekce; autoritativní rozehraný snapshot patří
  příslušnému `GameSession` objektu.
- Přenos výsledků z Durable Objectu do D1 je idempotentní. Nelze předpokládat
  distribuovanou transakci mezi oběma úložišti.
- Nová relace používá neměnný snapshot konkrétní verze scénáře a deploymentu.
- Povinný průchod hrou nesmí záviset na externí AI službě.
- Původní GCP cesta zůstane dostupná pro rollback do dokončení živé akceptace.

## CF-01: architektonický spike

**Odhad: 2–3 pracovní dny**

1. Založit samostatnou Cloudflare aplikaci a `wrangler` konfiguraci pro vývoj,
   staging a produkci.
2. Přidat Worker s `/api/health` a `/ws`.
3. Implementovat zkušební `GameSession` Durable Object se třemi WebSocket
   klienty, broadcastem a uloženým snapshotem.
4. Ověřit hibernaci, znovuvytvoření objektu, WebSocket attachments a alarm.
5. Ověřit `lobby.resume` po odpojení, uspání telefonu a návratu aplikace.
6. Zapsat ADR s rozhodnutím o Python/TypeScript hranici a rozmístění dat.

Akceptace:

- tři klienti sdílejí jednu relaci a nevidí data jiné relace;
- objekt obnoví snapshot po znovuvytvoření;
- iPhone po uspání obnoví spojení a autoritativní stav;
- lokální test používá Miniflare/Vitest, staging skutečné Cloudflare prostředí.

## CF-02: oddělení herní domény od transportu

**Odhad: 5–8 pracovních dnů**

1. Rozdělit současný `backend/escape_bot/server.py` na transport, aplikační
   orchestraci a čistou doménovou logiku.
2. Zavést deterministické rozhraní ve tvaru
   `apply(snapshot, command, actor, now) -> result`.
3. Výsledek rozdělí nový snapshot, odpověď odesílateli, týmové broadcasty,
   auditní události a následující deadline.
4. Odstranit z doménové vrstvy závislosti na WebSocketu, filesystemu,
   globálních kolekcích, vláknu a lokálních hodinách.
5. Doplnit validační schéma příkazů a verzování snapshotu.
6. Spustit stejné scénářové testy proti původnímu i novému adaptéru.

Stav feature větve: deterministické `apply`, verzovaný snapshot, idempotentní
`operation_id`, oddělené odpovědi odesílateli a týmové broadcasty, FastAPI
adaptér, validační schémata příkazů a explicitní autoritativní čas bez síťových
či procesních závislostí v doménové cestě jsou implementované. Zbývá převést
celý scenario journey na paritní test původního a nového rozhraní.

Akceptace:

- celý současný scenario journey projde přes nové doménové API;
- opakování stejného `operation_id` nepřičte body ani bonus dvakrát;
- deadline používá předaný autoritativní čas;
- stávající FastAPI provoz zůstává funkční.

## CF-03: statický klient na Workers Static Assets

**Odhad: 2–4 pracovní dny**

1. Připravit reprodukovatelný build adresář bez `node_modules` a zdrojových
   duplicit WebGL assetů.
2. Nasadit `/`, `/admin`, `/display`, `/terminal`, service worker a WebGL build
   jako Workers Static Assets.
3. Směrovat `/api/*` a `/ws` přednostně do Workeru.
4. Nastavit cache pravidla: fingerprintovaná aktiva immutable, HTML, manifest,
   `sw.js` a world JSON s revalidací.
5. Přidat CSP, `X-Content-Type-Options`, `Referrer-Policy` a vhodnou
   `Permissions-Policy` pro kameru.

Akceptace:

- klient, admin, nástěnka, terminál a Chronomap se načtou ze staging domény;
- service worker nezachová nekompatibilní starou verzi klienta;
- kamera funguje na HTTPS a iOS Safari;
- žádný jednotlivý asset nepřekračuje limit platformy.

## CF-04: kompletní herní relace v Durable Objectu

**Odhad: 8–12 pracovních dnů**

1. Směrovat spojení deterministicky podle `session_id`.
2. Přesunout lobby, hráče, chat, herní snapshot, terminálové rezervace a
   přítomnost do `GameSession` objektu.
3. Implementovat WebSocket Hibernation API a serializované metadata spojení.
4. Persistovat změnu před potvrzením příkazu klientovi.
5. Nahradit procesní časovače Durable Object alarms.
6. Zachovat úplný resume tok: `lobby.state`, `chat.history`, `game.state`,
   `scenario.progress` a podle režimu `demo.catalog`.
7. Ošetřit vyřazení offline hráče, přenos identity a uvolnění terminálu.

Akceptace:

- sólo i tříčlenný tým dokončí hru;
- restart/deploy a hibernace neztratí stav;
- dva týmy nemohou smíchat hráče, chat, checkpointy ani skóre;
- offline hráče lze vyřadit a tým může pokračovat;
- skóre po časovém limitu respektuje zmrazení soutěžní hodnoty.

## CF-05: event, admin a veřejná nástěnka

**Odhad: 6–9 pracovních dnů**

1. Vytvořit jeden `EventCoordinator` Durable Object pro každý event.
2. Přesunout runtime nastavení, startovní frontu, oznámení, globální stop,
   finalizaci výsledků a nastavení nástěnky.
3. Skládat admin overview z indexu relací; neprocházet globální paměť procesu.
4. Připojit admin support a spectator režim k cílové relaci.
5. Oddělit eventové broadcasty od týmových broadcastů.
6. Nahradit sdílený admin token krátkou autentizovanou relací; nouzový token
   ponechat pouze jako explicitní break-glass mechanismus.

Akceptace:

- nastavení eventu se okamžitě projeví všem dotčeným relacím;
- nástěnka správně filtruje event a hru;
- admin zásah je autorizovaný, idempotentní a auditovaný;
- jeden pomalý nebo poškozený tým neblokuje ostatní relace.

## CF-06: D1 projekce, audit, import a export

**Odhad: 5–8 pracovních dnů**

1. Zavést migrace pro `events`, `deployments`, `session_index`, `players`,
   `leaderboard_entries`, `audit_events` a `idempotency_operations`.
2. Implementovat outbox/projection tok mezi relací a D1.
3. Zajistit UPSERT výsledku podle `session_id` a stabilního identifikátoru hry.
4. Přenést existující JSON/PostgreSQL importní validace na D1 import.
5. Připravit významové porovnání zdroje a cíle.
6. Ukládat provozní exporty a eventové archivy do R2.
7. Sepsat obnovu D1 pomocí Time Travel a obnovu projekce ze zdrojových událostí.

Akceptace:

- opakovaný import ani opakovaná projekce nevytvoří duplicity;
- leaderboard obsahuje přesně jeden výsledek relace;
- audit dovede vysvětlit ruční změny skóre a ukončení hry;
- export lze načíst a významově porovnat v odděleném testovacím prostředí.

## CF-07: zátěžová a živá akceptace

**Odhad: 4–6 pracovních dnů**

1. Automaticky simulovat plánovanou kapacitu týmů a zařízení plus 50% rezervu.
2. Testovat souběžné checkpointy, admin zásahy, reconnect a duplicitní zprávy.
3. Během hry nasadit novou kompatibilní verzi Workeru.
4. Ověřit výpadek D1 projekce bez ztráty autoritativního herního stavu.
5. Projít fyzickou hru na iPhone, Androidu, notebooku a herním terminálu.
6. Změřit p95/p99 odezvy, počet reconnectů, chyby Durable Objects a cenu
   realistického eventu.

Akceptace:

- žádná ztráta nebo dvojí přičtení bodů;
- obnovení klienta do 15 sekund po ztrátě spojení;
- p95 běžné herní zprávy pod 300 ms pro evropské hráče;
- kompletní fyzický průchod včetně kamery a terminálu;
- písemně zaznamenaný kapacitní a nákladový výsledek.

## CF-08: produkční přepnutí a stabilizace

**Odhad: 2–3 pracovní dny plus 1–2 týdny provozního dohledu**

1. Nasadit ověřenou verzi na produkční Cloudflare prostředí.
2. Zastavit nové starty na původním backendu a dokončit rozehrané relace.
3. Vytvořit finální export a zálohu původního prostředí.
4. Importovat eventy, výsledky, nastavení a audit do D1.
5. Spustit produkční smoke test před přepnutím DNS.
6. Přepnout DNS a sledovat reconnecty, chyby, latence a projekce výsledků.
7. Při splnění rollback podmínky vrátit DNS; nepřepisovat chybový stav.
8. Původní GCP prostředí odstranit až po úspěšném eventu, ověřeném exportu a
   skončení dohodnuté retenční doby.

Rollback podmínky:

- neúspěšný smoke test nebo resume;
- ztráta, smíchání nebo dvojí zápis skóre;
- nefunkční kamera či terminál v povinném průchodu;
- neobnovitelný rozdíl mezi autoritativním stavem a D1 projekcí;
- p95 nad dohodnutým limitem po vyloučení klientské sítě.

## Souhrnný odhad

| Milník | Odhad |
|---|---:|
| CF-01 Architektonický spike | 2–3 dny |
| CF-02 Oddělení herní domény | 5–8 dnů |
| CF-03 Statický klient | 2–4 dny |
| CF-04 GameSession Durable Object | 8–12 dnů |
| CF-05 Event, admin a nástěnka | 6–9 dnů |
| CF-06 D1, audit, import a export | 5–8 dnů |
| CF-07 Zátěžová a živá akceptace | 4–6 dnů |
| CF-08 Přepnutí | 2–3 dny |
| **Celkem implementace** | **34–53 pracovních dnů** |

Pro jednoho vývojáře jde přibližně o **7–11 pracovních týdnů** čisté práce.
Po započtení provozních oken, oprav z fyzických testů a 20% rezervy je realistický
kalendářní plán **9–13 týdnů**. Dva vývojáři mohou dobu zkrátit přibližně na
**6–8 týdnů**, ale CF-02, CF-04 a produkční akceptace jsou převážně sekvenční.

Odhad předpokládá:

- zachování současného klientského UX a WebSocket protokolu;
- bez současného přepisování editoru scénářů a plateb;
- dostupný Cloudflare účet, doménu a placený Workers plán pro staging;
- nejvýše několik desítek současně aktivních týmů;
- alespoň dva vyhrazené dny pro fyzické testy zařízení.

Největší nejistotou je hranice Python/TypeScript a převod procesního stavu ze
`server.py`. Po CF-01 je nutné odhad znovu zpřesnit; očekávaná přesnost poté je
přibližně ±20 %.

## Doporučené pořadí větví a pull requestů

Každý milník realizovat v samostatné feature větvi a samostatném PR do
`develop`. CF-03 lze po uzavření CF-01 realizovat souběžně s CF-02. CF-05 může
začít po ustálení kontraktu `GameSession`, ale produkční spojení má smysl až po
CF-04. CF-06 lze připravovat souběžně s CF-05.

První implementační větev po této roadmapě:

```text
feature/cf-01-durable-object-spike
```
