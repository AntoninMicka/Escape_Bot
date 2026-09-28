# ADR 0002: Deterministická hranice herního enginu

- Stav: přijato pro CF-02
- Datum: 2026-09-28

## Kontext

Současný server volá `EscapeBotStateMachine` přímo z websocketové vrstvy a ukládá
její stav jako neobalený snapshot. Cloudflare Durable Object ale potřebuje herní
logiku, kterou lze spustit nad předaným snapshotem bez závislosti na FastAPI,
souborovém systému nebo lokálních hodinách procesu. Opakované doručení stejného
příkazu zároveň nesmí provést změnu podruhé.

## Rozhodnutí

Zavádíme aplikační hranici:

```text
apply(snapshot, command, actor, now) -> result
```

`GameEngine` obnoví stavový automat ze snapshotu, předá mu autoritativní UTC čas
a vrátí:

- verzovaný snapshot,
- protokolové odpovědi pouze odesílateli,
- zprávy určené k týmovému broadcastu,
- nově vzniklé auditní události,
- nejbližší budoucí deadline,
- informaci, zda šlo o opakované doručení operace.

Snapshot verze 1 obsahuje `state` a omezený seznam `operation_receipts`.
`operation_id` je idempotency klíč: opakovaný příkaz vrátí původní výsledek bez
další mutace. Po dobu migrace engine přijímá i původní neobalený snapshot a při
prvním příkazu jej převede na aktuální verzi.

Každý veřejný typ příkazu má před spuštěním stavového automatu explicitní
schéma. Transportní metadata aktéra se z payloadu oddělí a neprocházejí jako
veřejná pole příkazu. Neplatný nebo neznámý příkaz skončí terminální odpovědí
`command.rejected` se stejným `operation_id`, aniž by změnil snapshot, audit či
čas poslední aktivity. Již uložená idempotency účtenka má před validací retry
přednost, takže opakované doručení vždy vrátí původní výsledek. Při retry se
uložené týmové zprávy vrátí pouze odesílateli; celý tým je znovu nedostane.

Čas je vstup příkazu. Stavový automat proto používá injektované hodiny a během
jednoho příkazu nesmí číst systémový čas přímo. Stejně tak nečte procesní
proměnné a nevolá Ollama ani jinou síťovou službu; případné generativní služby
patří do aplikační orchestrace jako samostatný efekt. FastAPI transport zůstává
jako adaptér nad novým enginem. Uložený snapshot si ponechává původní strukturu
stavu a metadata enginu ukládá pod `_game_engine`. Starší server tento neznámý
klíč ignoruje, takže rollback nevyžaduje zpětnou migraci dat.

## Důsledky

- Herní pravidla lze spouštět shodně v Python serveru i z budoucího cloudového
  adaptéru.
- Retry příkazu je deterministický, pokud volající zachová `operation_id`.
- Alarm Durable Objectu lze naplánovat podle `next_deadline_at`.
- Webový klient ukládá nepotvrzené herní příkazy do omezené lokální fronty,
  potvrzuje je první odpovědí se stejným `operation_id` a po reconnectu je
  opakuje až po obnovení stejné lobby.
- Paritní test musí pro reprezentativní sekvenci porovnávat odpovědi i stav
  původního rozhraní s novou hranicí.
- Kompletní scénářový journey test používá obě rozhraní souběžně, porovnává je
  po každém příkazu a uprostřed hry obnoví engine z JSON snapshotu.
