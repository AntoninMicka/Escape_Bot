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
- protokolové odpovědi,
- nově vzniklé auditní události,
- nejbližší budoucí deadline,
- informaci, zda šlo o opakované doručení operace.

Snapshot verze 1 obsahuje `state` a omezený seznam `operation_receipts`.
`operation_id` je idempotency klíč: opakovaný příkaz vrátí původní výsledek bez
další mutace. Po dobu migrace engine přijímá i původní neobalený snapshot a při
prvním příkazu jej převede na aktuální verzi.

Čas je vstup příkazu. Stavový automat proto používá injektované hodiny a během
jednoho příkazu nesmí číst systémový čas přímo. FastAPI transport zůstává v této
etapě beze změny; přepnutí persistence na obálku bude samostatný integrační krok.

## Důsledky

- Herní pravidla lze spouštět shodně v Python serveru i z budoucího cloudového
  adaptéru.
- Retry příkazu je deterministický, pokud volající zachová `operation_id`.
- Alarm Durable Objectu lze naplánovat podle `next_deadline_at`.
- Změna formátu perzistence vyžaduje explicitní migraci serverového adaptéru.
- Paritní test musí pro reprezentativní sekvenci porovnávat odpovědi i stav
  původního rozhraní s novou hranicí.
