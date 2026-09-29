# Cloudflare runtime (CF-01 až CF-05)

Samostatný Cloudflare runtime Escape Botu. CF-01 ověřuje Worker, Durable Object
a WebSocket hibernaci, CF-03 přidává reprodukovatelný balíček klienta pro
Workers Static Assets. Současný FastAPI provoz tím není nahrazený a produkční
nasazení zatím není určené k použití.

Aktuální parita zásahů Game Mastera nad hádankami, minihrami a navržený
kontrakt pro explicitní odchod hráče jsou popsány v
[`docs/cloudflare-admin-action-inventory.md`](../docs/cloudflare-admin-action-inventory.md).

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
- Worker-first směrování `/api/*` a `/ws`;
- autentizované načtení týmů do omezeného cloudového admin přehledu;
- jednorázové obnovení hráčské identity na novém zařízení;
- autentizované správcovské vyřazení registrovaného hráče, i když je offline.
- samostatný SQLite-backed `EventCoordinator` pro každý event, včetně
  idempotentní konfigurace a ochrany proti přepsání novější revize.

Zprávy `spike.*` jsou pouze testovací kontrakt. Nejsou součástí produkčního
Escape Bot protokolu.

## Lokální kontrola

Z kořene repozitáře lze stejné operace spouštět jednotným wrapperem:

```bash
./run.sh setup cloudflare
./run.sh dev cloudflare
./run.sh debug cloudflare
./run.sh test cloudflare
./run.sh deploy cloudflare staging --dry-run
```

Pro lokální admin rozhraní lze vytvořit ignorovaný soubor
`cloudflare/.dev.vars` s řádkem `ADMIN_TOKEN=...`. Debug režim nastaví
`WRANGLER_LOG=debug`. Skutečný staging nebo produkční deploy vyžaduje potvrzení
slovem `DEPLOY`; `--yes` je určené pouze pro vědomou automatizaci. Produkční
deploy wrapper odmítne, pokud pracovní strom není čistý.

Nasazení existujícího kontejnerového runtime na GCP VM je dostupné odděleně a
vyžaduje neměnný Artifact Registry digest:

```bash
./run.sh deploy gcp \
  --project=PROJECT --zone=ZONE --vm=VM \
  --image=REGION-docker.pkg.dev/PROJECT/escape-bot/app@sha256:DIGEST \
  --dry-run
```

Bez `--dry-run` wrapper zobrazí přesný cíl, vyžádá potvrzení a předá řízení
existujícímu `deploy/gcp/deploy.sh`, který po nasazení ověří health a readiness.

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

Správcovské API vyžaduje secret `ADMIN_TOKEN`; hodnota není součástí repozitáře.
Lokální test používá pouze známý neprodukční token z výchozího Wrangler profilu.
Pro staging a produkci se token nastaví zvlášť:

```bash
npm exec wrangler secret put ADMIN_TOKEN -- --env staging
npm exec wrangler secret put ADMIN_TOKEN -- --env production
```

CF-05 zpřístupňuje konfiguraci konkrétního eventu přes autorizované
`GET` a `PUT /api/admin/events/:event_id`. Zápis vyžaduje stabilní
`operation_id`; volitelné `expected_revision` odmítne změnu, pokud správce
vychází ze staršího snapshotu. Celkový začátek a konec tvoří pevnou obálku;
pro každý její kalendářní den se ukládá samostatné povolené provozní okno
(výchozí `08:00–20:00`) nebo lze celý den vypnout. Platný provoz je vždy
průnikem obálky a denního okna. Konfigurace kontroluje časové pásmo, úplnost a
pořadí denních limitů, právě jednu hlavní hru a existenci všech her v runtime
katalogu. Uložení z administrace event zároveň aktivuje, filtruje veřejný
katalog a rozešle nový `runtime.settings` připojeným bootstrap klientům. Aktivní výběr přežije evikci;
`DELETE /api/admin/events/active` pouze odstraní omezení, nikoli uložený event.
Cloudový runtime zveřejňuje vypočtenou dostupnost a nejzazší start a před
zahájením týmové i sólo hry časová pravidla znovu autoritativně ověří. Start je
povolen pouze eventu ve stavu `open` a jen tehdy, když se celá nastavená délka
hry vejde do aktuálního denního okna i celkové obálky. Přímý WebSocket požadavek
tuto kontrolu neobejde; již rozehrané relace změna rozvrhu násilně neukončuje.
Před skutečným startem adresář relací navíc atomicky rezervuje startovní slot.
Do dostupnosti započítá rozehrané týmy i krátké souběžné rezervace a podle
konfigurace konkrétní hry vynutí `max_active_teams` a
`start_interval_minutes`. Rezervace je pro stejnou relaci idempotentní a po
nastavené délce hry automaticky vyprší, takže výpočet nemusí synchronně
procházet všechny týmové Durable Objecty; při dřívějším dokončení ji týmová
relace bezpečně uvolní.

Každý event poskytuje samostatný hibernovatelný kanál
`/ws?channel=event&event_id=…` pro runtime změny a `leaderboard.update`.
Týmové zprávy zůstávají v příslušném `GameSession`. Dokončení hry jednorázově
uzamkne výsledek a publikuje jej do `EventCoordinatoru`; opakovaný přenos se
stejným identifikátorem nic nepřičte ani nepřepíše. Řádné dokončení přidá bonus
100 bodů právě jednou. Dohrání mimo soutěž naopak publikuje soutěžní skóre
zmrazené při deadline, takže následující bonusy a postihy zůstávají pouze v
herním průchodu. Ručně ukončenou relaci správce vyhodnotí přes
`POST /api/admin/sessions/:session_id/finalize` a celé pořadí uzavře přes
`POST /api/admin/events/active/leaderboard/finalize`.
Globální výběr hádanek povolených pro terminály spravuje autorizovaný a
idempotentní `POST /api/admin/terminal-catalog`; používá stejný dokument jako
`scenario-play-modes`, takže katalog a režimy hraní se nemohou rozejít.
Fanout do týmových relací používá samostatné časové omezení každého cíle;
chyba nebo neodpovídající Durable Object proto nezadrží zdravé týmy ani
eventový kanál.

Čekající tým se může zařadit do perzistentní fronty nebo ji opustit. Veřejná
projekce je řazená podle role hry, konkrétní hry a času zařazení a obsahuje
pozici i plánovaný start. Alarm adresářového Durable Objectu přežije hibernaci,
v rezervovaném čase znovu ověří eventové okno, kapacitu a rozestup a první
způsobilý tým automaticky spustí. Aktualizace fronty se rozešle bootstrap i
týmovým klientům; nedostupná týmová relace neblokuje broadcast ostatním.

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
hodnocení, dokončení hry a rozešle finální efekt. Cloudový admin po ověření
tokenu načte z lobby adresáře týmy, jejich hráče, online stav, skóre, postup a
stav podporovaných týmových miniher. Podle serverových `admin_capabilities` může
Game Master auditovaně potvrdit nebo dokončit checkpoint s volitelným postihem
a restartovat aktivní Kalibraci, Karla, Tři v řadě nebo Sokoban. U týmové
Kalibrace a Tří v řadě může hráče vyřadit, znovu vrátit nebo restartovat pouze
jeho vlastní desku bez změny checkpointu a spoluhráčů. Záložka Režimy hry
ukládá atomicky způsob hraní všech hádanek (`phones`, `supplemental`,
`exclusive`) a změnu okamžitě rozešle rozehraným relacím; opakovaný požadavek
se stejným `operation_id` změnu znovu neprovede. Samostatný terminál se registruje v lobby
adresáři, správce jej rezervuje pro hádanku a první způsobilý tým jej
jednorázovým QR přesměruje do svého `GameSession`. Terminál nezvyšuje počet
hráčů a po dokončení, odpojení nebo nové registraci se bezpečně uvolní při
zachování rezervace. Eventový admin overview a další správcovské operace ještě
čekají na další části CF-04 a CF-05.
Automatizované scénářové testy procházejí celou sólo hru přes Worker a
WebSocket a samostatně dokončí tříčlennou týmovou relaci. Ověřují odemčení
pokoje 108, všechny checkpointy a minihry, soukromí hráčských desek v
`line_game` a `triad`, týmové sjednocení podmínek, dokončení finále a obnovu
autoritativního stavu po evikci Durable Objectu uprostřed hry i po
`game.complete`.
Fyzická akceptace stejného průchodu na třech hráčských zařízeních je odložená
do doby, kdy budou zařízení k dispozici; automatizované pokrytí tím není
nahrazeno za živou akceptaci.
Samostatné API už dovoluje správci vyřadit registrovaného hráče z aktivní
`line_game` nebo `triad` i bez jeho WebSocketového připojení. Produkční deadline
už používá Durable Object alarm: po jednorázovém
postihu zmrazí soutěžní skóre a tým může hru ukončit nebo pokračovat mimo
soutěž. Hráči smějí v aktivní týmové minihře pouze obnovit správcem vyřazeného
spoluhráče; sami nikoho vyřadit nemohou.

Správce může z cloudového přehledu vystavit návratový QR platný 10 minut.
Adresář ukládá pouze hash jednorázového tokenu. Po použití se nové zařízení
přesměruje do stejného `GameSession`, zatímco staré se odpojí; přenesou se
soukromé desky, výsledky, vyřazení, navigátor i idempotency účtenky a počet
registrovaných hráčů se nezmění.

Cloudový přehled je stále označený jako omezená správa. Zobrazuje pouze
autoritativně přenesené zásahy: návratový QR, náhled hráče, podporu, vyřazení
hráče, prodloužení a provozní ukončení hry, bodovou úpravu a finalizaci
výsledku. Tlačítka bez bezpečného Worker endpointu zůstávají skrytá. Úplný
víceeventový přehled bude používat nový `EventCoordinator`; jeho
perzistentní konfigurace, aktivní výběr, HTTP API a napojení admin formuláře už
jsou součástí CF-05, zatímco současné načtení týmů z adresáře lobby zůstává
mezikrokem CF-04.

Produkční deploy má samostatný explicitní příkaz `npm run deploy:production`.
Obecný `npm run deploy` záměrně není definován, aby nebylo možné bez výběru
prostředí změnit výchozí Worker.

Produkční Worker používá tři Cloudflare Custom Domains nad stejnými Durable
Objecty a stejným stavem hry:

- `https://escape.antoninmicka.cz`
- `https://escape.tonymicka.cz`
- `https://escape.proofofidea.cz`

Wrangler při produkčním deployi spravuje jejich DNS záznamy a TLS certifikáty.
Všechny tři domény proto musí být ve stejném dostupném Cloudflare účtu a před
prvním deployem nesmí mít konfliktní A, AAAA nebo CNAME záznam daného názvu.

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
