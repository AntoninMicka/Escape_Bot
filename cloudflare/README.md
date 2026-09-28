# Cloudflare runtime (CF-01 až CF-04)

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
- zkompilovaný scénářový snapshot, úvodní dialog a postup fázemi;
- perzistentní chat, fázové nápovědy a idempotentní účtenky prvních herních příkazů;
- pořadí QR checkpointů, textové rébusy a jejich stupňované nápovědy;
- Durable Object alarm pro časový deadline;
- oddělení stavu různých relací;
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

Délku celé hry a jednorázový postih určují pro každé prostředí Wrangler
proměnné `GAME_DURATION_MINUTES` a `DEADLINE_PENALTY`.

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
fyzickém iPhonu. Rozpracovaný CF-04 podporuje bootstrap, sólo/týmovou lobby,
připojení kódem, spuštění, autoritativní resume snapshot, textový úvod scénáře,
QR checkpointy a rébusy s odpovědí. Kalibrace `line_game` včetně samostatné
mřížky každého hráče, týmového postupu, obnovení a idempotentních tahů už běží
v Durable Objectu. Stejně je přenesené společné minové pole `mine_karel`,
včetně skrytých min, indicií, časových limitů úrovní, skóre a obnovení. Minihra
`triad` má vlastní desku každého hráče, deterministického protivníka a sdílené
týmové pokrytí směrů. Sdílený `sokoban` ukládá postup třemi sektory, historii
pro undo, čas každé úrovně a navigátory; české povely z kanálu Elary se parsují
stejně jako přímé API příkazy. Archivní skládačka `archive_vector` je rovněž
perzistentní: sdílí pořadí a natočení dílků, ale klíč
a pořadí modulů odhalí až po správném sestavení obrazu; checkpoint dokončí až
následná správná textová odpověď. `finale.activate` ověřuje úplnou trasu,
inventář, servisní příznaky, rok, čas a pořadí modulů; při úspěchu uloží konečné
hodnocení, dokončení hry a rozešle finální efekt. Terminálové rezervace,
administrace a správcovské vyřazení hráče ještě čekají na další části CF-04 a
CF-05. Produkční deadline už používá Durable Object alarm: po jednorázovém
postihu zmrazí soutěžní skóre a tým může hru ukončit nebo pokračovat mimo
soutěž. Hráči smějí v aktivní týmové minihře pouze obnovit správcem vyřazeného
spoluhráče; sami nikoho vyřadit nemohou.

Produkční deploy má samostatný explicitní příkaz `npm run deploy:production`.
Obecný `npm run deploy` záměrně není definován, aby nebylo možné bez výběru
prostředí změnit výchozí Worker.

Po nasazení je nutné zopakovat WebSocket resume po uspání fyzického iPhonu.
Teprve poté lze CF-01 označit za dokončený.

## Důležitá transportní změna

Durable Object musí být vybrán před přijetím WebSocketu. Uložená cloudová relace
proto předá `session_id` a `client_id` v URL. Nový hráč bez relace se nejprve
připojí k bootstrap Durable Objectu, získá přes `lobby.route` směrovací identitu
a otevře cílový týmový WebSocket. Již přijatý WebSocket se mezi Durable Objects
nepřesouvá.

Typy aplikačních zpráv z `docs/protocol.md` zůstanou zachovány; změní se pouze
bootstrap transportu a reconnect URL.
