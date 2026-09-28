# Cloudflare CF-01 spike

Izolovaný technický spike pro budoucí Cloudflare runtime Escape Botu. Není
zapojený do současného FastAPI serveru ani klienta a není určený k produkčnímu
nasazení.

## Co ověřuje

- Worker endpoint `/api/health`;
- deterministické směrování `/ws` podle `session_id`;
- SQLite-backed `GameSession` Durable Object;
- Hibernation WebSocket API a serializovanou identitu klienta;
- broadcast třem klientům jedné relace;
- perzistentní autoritativní snapshot a úplný `lobby.resume` po evikci;
- Durable Object alarm pro časový deadline;
- oddělení stavu různých relací.

Zprávy `spike.*` jsou pouze testovací kontrakt. Nejsou součástí produkčního
Escape Bot protokolu.

## Lokální kontrola

```bash
cd cloudflare
npm ci
npm run check
npm exec wrangler deploy -- --dry-run --env staging
```

Cloudflare Vitest runner otevírá lokální loopback port. V omezeném sandboxu
proto může vyžadovat povolení síťového socketu, přestože nekontaktuje produkční
službu.

Lokální vývojový server:

```bash
npm run dev
```

## Staging akceptace

Staging nasazení je samostatný explicitní krok a vyžaduje přihlášený Wrangler a
Cloudflare účet:

```bash
npm exec wrangler deploy -- --env staging
curl https://STAGING-DOMAIN/api/health
```

Po nasazení je nutné zopakovat WebSocket resume po uspání fyzického iPhonu.
Teprve poté lze CF-01 označit za dokončený.

## Důležitá transportní změna

Durable Object musí být vybrán před přijetím WebSocketu. Nové cloudové připojení
proto předá `session_id` a `client_id` v URL. Nový hráč bez relace se v pozdější
etapě nejprve připojí k bootstrap/event endpointu, získá směrovací identitu a
otevře cílový týmový WebSocket. Již přijatý WebSocket nelze mezi Durable Objects
přesunout.

Typy aplikačních zpráv z `docs/protocol.md` zůstanou zachovány; změní se pouze
bootstrap transportu a reconnect URL.
