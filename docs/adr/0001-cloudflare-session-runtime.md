# ADR 0001: Cloudflare runtime pro herní relaci

- Stav: navrženo ve spike CF-01
- Datum: 2026-09-28

## Kontext

Současný FastAPI server drží rozehrané stavové automaty, připojené WebSockety,
terminálová párování i admin broadcasty v procesní paměti. Tento model vyžaduje
jediný proces a po restartu musí složitě obnovovat stav z globálních dokumentů.
Cloudflare Worker je naopak bezstavový a jednotlivé požadavky mohou obsloužit
různé instance.

Jedna týmová relace potřebuje sekvenční zpracování příkazů, konzistentní stav,
dlouho otevřené WebSockety a autoritativní obnovu po uspání telefonu.

## Rozhodnutí

Každou týmovou relaci bude koordinovat jeden SQLite-backed `GameSession`
Durable Object určený deterministicky podle `session_id`.

Vstupní Worker bude pouze validovat a směrovat HTTPS/WSS požadavky. `GameSession`
bude vlastnit autoritativní snapshot, spojení hráčů a terminálů, týmové
broadcasty a deadline alarmy. WebSockety použijí Hibernation API; identita
spojení bude v serializovaném attachmentu, nikoli pouze v paměti objektu.

Globální eventový stav není součástí tohoto spike. Pozdější `EventCoordinator`
bude samostatný objekt pro konkrétní event. D1 bude sloužit jako dotazovatelný
index, leaderboard a auditní projekce, ne jako autorita právě zpracovávaného
herního příkazu.

Stávající názvy protokolových zpráv zůstanou pro první migrační etapu zachovány.
Resume musí poslat `lobby.state`, `chat.history`, `game.state` a
`scenario.progress` z jednoho uloženého snapshotu.

Durable Object musí být vybrán před přijetím WebSocketu a přijaté spojení nelze
přesunout do jiného objektu. Reconnect známé relace proto předá `session_id` a
`client_id` už v URL. Nový hráč bez relace použije bootstrap/event endpoint,
získá směrovací identitu a následně otevře týmový WebSocket. Jde o změnu
transportního bootstrapu, nikoli názvů aplikačních zpráv.

## Hranice Pythonu a TypeScriptu

Durable Object, WebSocket lifecycle, routing a persistence budou v TypeScriptu,
protože jde o nativní koordinační vrstvu platformy. Herní pravidla se nejprve
oddělí od FastAPI do deterministického Python rozhraní. V CF-02 se změří dvě
varianty:

1. Python Worker volaný Service Bindingem se snapshotem a příkazem;
2. postupný port čistého reduceru do TypeScriptu.

Výchozí preference je zachovat Python pravidla, pokud spike prokáže kompatibilní
závislosti, přijatelnou latenci a jednoznačné transakční pořadí. Python Worker
nesmí vlastnit WebSockety ani autoritativní snapshot.

## Konzistence

Změna relace se nejprve zapíše do storage Durable Objectu a teprve potom se
potvrdí nebo broadcastuje klientům. Operace měnící postup či skóre budou mít
stabilní `operation_id`. Projekce do D1 bude idempotentní a obnovitelná z
uloženého outboxu; mezi Durable Objectem a D1 se nepředpokládá distribuovaná
transakce.

## Důsledky

- různé týmy se přirozeně škálují do různých objektů;
- příkazy jedné relace jsou serializované bez distribuovaného zámku;
- objekt musí být kdykoli obnovitelný bez procesní cache;
- cross-session admin přehled vyžaduje eventový index a nesmí procházet paměť;
- lokální test nestačí k potvrzení chování iOS a skutečné Cloudflare hibernace;
- produkční migrace vyžaduje kompatibilní export a rollback na stávající GCP.

## Výsledek spike

Implementace v `cloudflare/` ověřuje lokálně směrování, tři WebSocket klienty,
uložený snapshot, úplný resume po evikci a Durable Object alarm. Za dokončení
CF-01 se považuje až stejné ověření ve staging Cloudflare prostředí a fyzický
iPhone suspend/resume test.
