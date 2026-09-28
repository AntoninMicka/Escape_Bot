# Cloudflare runtime (CF-01 až CF-03)

Samostatný Cloudflare runtime Escape Botu. CF-01 ověřuje Worker, Durable Object
a WebSocket hibernaci, CF-03 přidává reprodukovatelný balíček klienta pro
Workers Static Assets. Současný FastAPI provoz tím není nahrazený a produkční
nasazení zatím není určené k použití.

Používá stejný Cloudflare účet a lokální Wrangler přihlášení jako ostatní
projekty, ale nesdílí s nimi Worker, Durable Object namespace, D1 databázi ani
secrety. Názvy prostředí jsou `escape-bot-cf-development`,
`escape-bot-cf-staging` a `escape-bot-cf-production`; Worker
`prijimaci-vycvik` ani jeho `prijimaci-vycvik-db` se nepoužijí.

## Co ověřuje

- Worker endpoint `/api/health`;
- deterministické směrování `/ws` podle `session_id`;
- SQLite-backed `GameSession` Durable Object;
- Hibernation WebSocket API a serializovanou identitu klienta;
- broadcast třem klientům jedné relace;
- perzistentní autoritativní snapshot a úplný `lobby.resume` po evikci;
- Durable Object alarm pro časový deadline;
- oddělení stavu různých relací.
- statický klient na `/`, `/admin`, `/terminal` a `/display`;
- service worker a fingerprintovaný WebGL build;
- Worker-first směrování `/api/*` a `/ws`.

Zprávy `spike.*` jsou pouze testovací kontrakt. Nejsou součástí produkčního
Escape Bot protokolu.

## Lokální kontrola

```bash
cd cloudflare
npm ci
npm run check
npm exec wrangler deploy -- --dry-run --env staging
```

`npm run build` nejprve sestaví WebGL a potom vytvoří `cloudflare/dist`. Do
výsledku kopíruje jen používané klientské soubory, nikoli `node_modules` ani
zdrojový WebGL projekt. `dist` je generovaný a neukládá se do Gitu.

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
npm run deploy:staging
curl https://STAGING-DOMAIN/api/health
```

Na stagingu je nutné ručně projít `/`, `/admin`, `/display`, `/terminal` a
Chronomap, ověřit aktualizaci service workeru a HTTPS kameru v Safari na
fyzickém iPhonu. WebSocket zatím používá spike kontrakt CF-01; úplný klientský
protokol je úkolem CF-04.

Produkční deploy má samostatný explicitní příkaz `npm run deploy:production`.
Obecný `npm run deploy` záměrně není definován, aby nebylo možné bez výběru
prostředí změnit výchozí Worker.

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
