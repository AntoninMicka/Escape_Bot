# Escape Bot WebSocket Protocol

Transport: JSON messages over WebSocket.

Default endpoint: `/ws` na stejném hostiteli jako webový klient (při lokálním HTTPS typicky `wss://localhost:8088/ws`).

Cloudflare transport vždy přidává stabilní `client_id` do query stringu. Klient
bez uložené relace se nejprve připojí pouze s `client_id`; bootstrap po
`lobby.solo`, `lobby.create` nebo `lobby.join` odpoví interní zprávou
`lobby.route` a klient otevře nové spojení s `session_id` a `client_id`.
Rozehraná a uložená relace bootstrap přeskakuje a připojuje se přímo ke svému
`GameSession` Durable Objectu. `lobby.route` není herní doménová událost a
klient ji neukládá do historie relace.

Every message has:

```json
{
  "type": "message.type",
  "request_id": "optional-client-id",
  "operation_id": "optional-stable-mutation-id",
  "payload": {}
}
```

`request_id` slouží ke korelaci jednoho požadavku a odpovědi. Herní příkazy,
které mění stav nebo skóre, navíc používají stabilní `operation_id` dlouhé 1 až
128 znaků. Klient jej vytvoří před prvním odesláním, ponechá příkaz v lokální
frontě do `operation.ack` nebo jiné odpovědi se stejným `operation_id` a po
reconnectu odešle tentýž příkaz se stejným ID. Backend takový retry znovu
neaplikuje, ale vrátí uložené odpovědi pouze jeho odesílateli; týmové efekty a
zprávy podruhé nebroadcastuje. Lobby, terminálové párování, podpora,
administrace a read-only dotazy tuto doménovou idempotency frontu nepoužívají.

## Client -> Backend

### Týmové lobby

Před `client.hello` používá webový klient jednu ze zpráv `lobby.solo`, `lobby.create`, `lobby.join` nebo `lobby.resume`. Založení obsahuje stabilní `client_id` zařízení, povinné `name`, povinné `team_name` a příznak demo režimu. Název týmu je unikátní bez ohledu na velikost písmen a nadbytečné mezery. `lobby.join` navíc posílá `join_code` a povinné jméno hráče; klient jej získá z URL týmového QR, kamerovým načtením QR v lobby nebo ručním zadáním. `lobby.resume` používá uložené `session_id`.

Zakladatel týmové relace ji spustí zprávou `lobby.start`. Backend spuštění odmítne, pokud chybí název týmu nebo jméno kteréhokoli registrovaného hráče. Poté rozešle `lobby.state` a zahajovací herní zprávy všem připojeným zařízením. `lobby.state` obsahuje název a režim týmu, týmový QR kód, trvalý počet registrovaných hráčů (`player_count`/`registered_players`), momentální počet spojení (`online_count`), seznam připojení a bodovou úpravu. Uspání či výpadek zařízení mění pouze online stav a nikdy nepřepíná tým do sólo režimu.

Každý `lobby.resume` rozehrané relace vrací úplný autoritativní snapshot: `lobby.state`, `chat.history`, `game.state` a `scenario.progress`; v demo režimu také `demo.catalog`. Klient obnovu aktivně vyžádá při událostech `visibilitychange`, `pageshow` a `online`. Pokud uspáním vznikne zdánlivě otevřený, ale nefunkční WebSocket, neúspěšná synchronizační sonda jej uzavře a vyvolá nové připojení.

Trvalý odchod hráč potvrzuje zprávou `lobby.leave` s jedinečným
`operation_id`. Server ověří identitu připojeného socketu a odpoví
`lobby.left`; klient teprve po tomto potvrzení odstraní lokálně uloženou relaci.
Hráč zůstává v historickém seznamu `players` s `left_at`, ale nepočítá se do
`registered_players`, autorizace herních příkazů ani aktivních účastníků
miniher. Režim `team` a dosažené `max_players` se nemění. Odchod zakladatele
převede jeho roli na nejdříve připojeného aktivního hráče. Odchod posledního
aktivního hráče ukončí rozehranou hru jako `abandoned`; před startem navíc
uvolní připojovací kód a frontu. Samotný odchod nikdy nedokončuje týmovou
minihru ani nepřiděluje její bonus. Opakování stejného `operation_id` pouze
vrátí `lobby.left` s `changed: false`.

Cloudflare adaptér zatím obsluhuje z herních příkazů `player.message`,
`phase.hint`, `qr.detected`, `puzzle.submit` pro rébusy s textovou odpovědí a
`puzzle.hint`; z interaktivních miniher podporuje `line_game.move`,
`line_game.reset`, `karel.command`, `karel.reset`, `triad.place` a
`triad.reset`, `sokoban.command`, `sokoban.undo` a `sokoban.reset`. Sokobanové
povely lze stejně jako v původním backendu zadávat česky přes `player.message`
v kanálu `lost`. Podporované je také `archive.arrange`; skládání obrazu a
následné `puzzle.submit` zůstávají oddělené kroky. `finale.activate` ověřuje a
uzavírá kompletní herní průchod. `game.deadline_choice` řeší pokračování po
časovém limitu a `team_game.player.restore` dovoluje hráči pouze vrátit
správcem vyřazeného spoluhráče. Před potvrzením uloží nový
stav, chat i omezenou účtenku podle
`operation_id`. Opakované doručení vrátí uložené odpovědi pouze původnímu
odesílateli a týmový chat ani herní efekt znovu nerozešle. Výsledek tahu
`line_game.result` i hráčova mřížka jsou soukromé pro dané zařízení, zatímco
týmový postup a skóre se sdílejí.

Pro reverzní připojení notebook pošle `lobby.identify` a dostane `lobby.player_identity` s jednorázovým osmimístným kódem. Zobrazí jej jako `escapebot://player/<code>`. Zakladatel kód načte a odešle v `lobby.add_player`; backend čekající WebSocket připojí do stejné lobby. Kód je jednorázový a zařízení se dále chová jako běžný hráč.

Velikost týmu upravuje skóre podle nejvyššího počtu registrovaných zařízení: sólo `+20`, tým o dvou hráčích `+10`, tři hráči beze změny a každý hráč nad tři `−30`. Pozdější připojení pouze dorovná rozdíl proti již použité úpravě.

### Samostatný herní terminál

Stránka `/terminal` pošle `terminal.register` a dostane jednorázový `terminal.ready` s QR hodnotou `escapebot://terminal/<code>`. QR načte telefon už připojeného hráče běžnou zprávou `qr.detected`. Server terminál naváže na stejnou relaci a identitu tohoto hráče, ale nepřidá jej do `Lobby.players`, nezvýší `max_players` a nezmění týmovou bodovou úpravu.

Rezervace váže pouze zařízení na hádanku, nikdy zařízení na konkrétní tým. V
Cloudflare runtime ji adresář Durable Objectů spravuje autentizovaným API
`POST /api/admin/terminal-reserve`; párovací i přesměrovací tokeny jsou
jednorázové a v úložišti jsou pouze jejich SHA-256 otisky.

Scénář může zároveň určit výchozí prezentační režim:

```json
"terminal": {"mode": "exclusive", "label": "Finální konzole"}
```

První tým, který načte QR a má rezervovanou hádanku právě dostupnou, terminál
převezme. Terminálový QR podle potřeby sám aktivuje checkpoint. Režim
`exclusive` potom na telefonech ponechá jen pokyn přejít k terminálu. Dokončení
hádanky terminál uvolní po prezentační prodlevě; odpojení nebo nová registrace
jej uvolní okamžitě. Ve všech případech rezervace `terminál → hádanka` zůstává
zachována pro další tým.

### `client.hello`

Starts a session.

```json
{
  "type": "client.hello",
  "request_id": "hello-1",
  "payload": {
    "client_name": "Escape Bot QML",
    "protocol_version": 1
  }
}
```

### `player.message`

Sends text from the player.

```json
{
  "type": "player.message",
  "request_id": "msg-42",
  "payload": {
    "text": "Nasel jsem symbol pod stolem."
  }
}
```

Kanál `support` je vyhrazený pro komunikaci týmu s Game Masterem. Backend jej ukládá do historie relace a neposílá jej do herního stavového automatu, takže text podpory nemůže změnit postup hry.

### Administrační podpora

Podpůrný chat je správci dostupný trvale přes `admin.support_message`; zpráva obsahuje `session_id`, administrační token a `text`.

Nová zpráva týmu nebo Game Mastera vyvolá samostatný serverový push `admin.support_update` s identifikátorem týmu a aktuální historií podpory. Klient díky tomu nepřekresluje celý `admin.overview`; periodický refresh používá pouze na otevřené záložce týmového přehledu.

Živý náhled celé hry se spouští pomocí `admin.spectate_start` a ukončuje přes `admin.spectate_stop`. Server po připojení pošle standardní `chat.history`, `game.state`, `scenario.progress` a následně stejný živý broadcast jako hráčům týmu. Admin zůstává read-only a není přidán mezi hráčská zařízení relace.

Ruční dokončení checkpointu přes `admin.checkpoint` přijímá `penalty_preset`. Povolené předvolby definuje server a posílá je v `admin.overview`; zahrnují technický skip bez postihu, drobnou pomoc, přeskočení minihry a šifru vyřešenou Game Masterem.

Životní cyklus konkrétní relace lze řídit zprávami `admin.session_extend` a `admin.session_end`. Prodloužení přijímá `session_id` a `minutes`; ukončení přijímá `session_id` a důvod `abandoned`, `technical` nebo `manual`. Opuštěná hra dostane nastavený postih, technické a běžné ruční ukončení jsou bez automatického postihu. Backend zároveň automaticky ukončuje nedokončené hry po provozním limitu a dlouho neaktivní offline hry. Úpravy výsledku jsou idempotentní a v auditu uchovávají skóre před změnou a po ní.

Provozní nastavení obsahuje vedle `deadline_penalty` také `abandonment_penalty` a `completion_bonus`. Bonus za řádné dokončení i oba automatické postihy se na relaci aplikují nejvýše jednou, včetně relací obnovených ze staršího uloženého stavu.

### `camera.frame`

Sends an extracted still frame reference or base64 blob.

```json
{
  "type": "camera.frame",
  "request_id": "frame-3",
  "payload": {
    "mime_type": "image/jpeg",
    "data": "<base64-or-local-ref>"
  }
}
```

### `qr.detected`

Reports a decoded QR value.

```json
{
  "type": "qr.detected",
  "request_id": "qr-7",
  "payload": {
    "value": "escapebot://checkpoint/4ec67b900c4a491ba180c8a48d5309f2"
  }
}
```

QR payload obsahuje neprůhledný token definovaný ve scénáři. Server odmítne neznámé tokeny a checkpointy naskenované před splněním jejich předchůdců.

### `cipher_tool.unlock`

Trvale odemkne pasivní šifrovací pomůcku pro aktuální relaci. Pokud ji hráč nezískal checkpointem, server jednorázově odečte cenu ze scénáře.

```json
{
  "type": "cipher_tool.unlock",
  "payload": {
    "tool_id": "pigpen"
  }
}
```

### `puzzle.submit`

Odešle řešení nalezené hádanky. Backend ověří, že její fyzický checkpoint byl skutečně nalezen, zaznamená pokus a teprve správným řešením označí checkpoint jako dokončený.

```json
{
  "type": "puzzle.submit",
  "payload": {
    "puzzle_id": "reception_deduction",
    "answer": "2147"
  }
}
```

### `puzzle.hint`

Vyžádá další stupňovanou nápovědu. Každý stupeň odečte body pouze při prvním zobrazení.

### `line_game.move`

Prohodí dvě ortogonálně sousední barvy v interaktivní kalibrační mřížce.
Souřadnice jsou indexované od nuly; backend kontroluje odemčení checkpointu,
časový limit a to, zda výměna vytvořila alespoň jednu řadu. Řada může být přímá
nebo pravoúhle lomená přes libovolný společný kámen. Ramena 3 + 2 se počítají
jako čtveřice a ramena 3 + 3 jako pětice; samotné spojení 2 + 2 neboduje.

```json
{
  "type": "line_game.move",
  "payload": {
    "puzzle_id": "timeline_lines",
    "first": [2, 4],
    "second": [2, 5]
  }
}
```

### `line_game.reset`

Spustí nový pokus: obnoví pětibarevnou mřížku, průběh všech tří cílů i časový limit.

```json
{
  "type": "line_game.reset",
  "payload": {
    "puzzle_id": "timeline_lines"
  }
}
```

### `karel.command`

Provede nejvýše 30 kroků na společném minovém poli. Povolené směry jsou `up`,
`down`, `left` a `right`. Sekvence končí po vstupu na minu, dosažení východu
nebo před krokem mimo mřížku.

```json
{
  "type": "karel.command",
  "payload": {
    "puzzle_id": "courtyard_karel",
    "commands": ["down", "down", "right"]
  }
}
```

### `karel.reset`

Obnoví aktuální pole, pozici, odhalené buňky a tříminutový limit. Již dokončené
úrovně a jejich jednorázově přidělené body zůstávají zachované.

### `triad.place`

Umístí zvolený symbol na volné pole hráčovy soukromé desky. Server poté provede
deterministický blokovací tah protivníka. Vodorovné, svislé a oba diagonální
směry se započítávají jako tři týmové podmínky; každý hráč musí dokončit počet
směrů určený scénářem.

```json
{
  "type": "triad.place",
  "payload": {
    "puzzle_id": "temporal_triad",
    "row": 2,
    "column": 3,
    "symbol": "cyan"
  }
}
```

### `triad.reset`

Obnoví desku, protivníka, dokončené směry a časový limit aktuálního hráče.

### `sokoban.command`

Provede deterministickou sekvenci pohybů Elary. Povolené hodnoty jsou `up`, `down`, `left` a `right`; sekvence se zastaví před první neprůchodnou stěnou nebo článkem. Stejnou zprávu vytváří parser českých povelů z kanálu Elary.

```json
{
  "type": "sokoban.command",
  "payload": {
    "puzzle_id": "sports_sokoban",
    "commands": ["right", "up", "left"]
  }
}
```

### `sokoban.undo` a `sokoban.reset`

`undo` vrátí poslední skutečně provedený krok včetně zatlačení článku. `reset` obnoví počáteční mapu a zvýší počítadlo restartů.

### `archive.arrange`

Posune archivní kartu vlevo či vpravo, otočí ji o 90 stupňů nebo prohodí dva
dílky. Akce mají hodnoty `left`, `right`, `rotate` a `swap`; u prohození je
`target_id` povinný. Odpověď `archive.result` oznámí, zda už je obraz sestavený.
Odhalený klíč a pořadí modulů se objeví až v následném `game.state`. Samotné
sestavení checkpoint neuzavře — hráč ještě odešle dešifrovaný text přes
`puzzle.submit`.

### `finale.activate`

Odešle návratový rok, čas a seřazené moduly finální konzole. Server nejprve
ověří všechny povinné checkpointy, předměty a příznaky. Úspěch označí finální
checkpoint jako vyřešený, nastaví fázi `portal_open`, uloží čas dokončení a
hodnocení podle výsledného skóre a rozešle `finale.result`, `effect.trigger` a
`game.complete`. Opakování již dokončené aktivace vrací `already_complete`
bez změny času dokončení nebo počtu pokusů.

### `game.deadline_choice`

Po vypršení produkčního Durable Object alarmu server hru pozastaví, jednou
uplatní postih a uloží `competition_score`. Volba `end` ukončení potvrdí;
`continue` odblokuje hru s příznakem `out_of_competition`. Následující herní
bonusy a postihy mohou měnit živé skóre, ale už nikdy nezmění zmrazené soutěžní
skóre určené pro žebříček.

### `team_game.player.restore`

Vrátí správcem vyřazeného spoluhráče do aktivního `line_game` nebo `triad`.
Odesílatel musí být jiný registrovaný hráč stejného týmu. Hráčský protokol
záměrně nemá odpovídající akci pro vyřazení; tu smí provádět pouze správce.

### `POST /api/admin/game-player` (Cloudflare)

Oddělený správcovský HTTP endpoint vyřadí registrovaného člena z aktivní
`line_game` nebo `triad`, případně jej do minihry vrátí, i když hráč právě nemá
otevřený WebSocket. Požadavek
musí mít hlavičku `Authorization: Bearer <ADMIN_TOKEN>` a JSON tělo:

```json
{
  "session_id": "9c812e8581794fcbadcc02ad9d593618",
  "puzzle_id": "timeline_lines",
  "player_id": "phone-bob",
  "action": "include",
  "operation_id": "include-phone-bob-001"
}
```

Podporované akce jsou `exclude`, `include` a `reset`. `reset` obnoví pouze desku
zvoleného hráče a odstraní jeho individuální výsledek; stav spoluhráčů,
checkpoint, skóre a případné vyřazení hráče zachová. Opakování stejného
`operation_id` ani požadavek na již platné vyřazení či zařazení změnu neprovede
a vrátí `changed: false`. Zásah se zapíše do časové osy a server rozešle
autoritativní stav. Obnova spoluhráčem zůstává dostupná příkazem
`team_game.player.restore`; běžný herní WebSocket nemá správcovskou akci pro
vyřazení.

### `GET /api/admin/overview` (Cloudflare)

Požadavek s hlavičkou `Authorization: Bearer <ADMIN_TOKEN>` vrátí omezený
cloudový přehled týmů evidovaných v lobby adresáři. Každý `GameSession` sestaví
vlastní snapshot registrovaných hráčů, online stavu, skóre, postupu a aktivních
`line_game`/`triad` desek. Webová stránka `/admin` používá tento endpoint na
Cloudflare; při běhu proti FastAPI zachová původní zprávu `admin.list`.

Odpověď kvůli zpětné kompatibilitě stále obsahuje `cloudflare_limited: true`,
ale klient podle něj nerozhoduje. `admin_capabilities.actions` určuje podporované
administrátorské operace a `admin_capabilities.http_actions` jejich HTTP
transport; ostatní podporované akce používají legacy WebSocket. Další pole
určují checkpointové přechody, adaptéry restartovatelných miniher, hráčské akce
a terminálové operace. Neimplementovaná akce proto není zobrazena ani omylem
odeslána nesprávným transportem.

### Checkpointové zásahy a restart minihry (Cloudflare)

`POST /api/admin/sessions/:session_id/checkpoint` přijímá `checkpoint_id`, stav
`found` nebo `solved`, `penalty_preset` a jedinečné `operation_id`. Ruční nález
inicializuje stejný týmový stav minihry jako platné QR. Dokončení aplikuje odměny
a nejvýše jednou odečte postih z presetů zveřejněných v `admin.overview`.

`POST /api/admin/sessions/:session_id/game-reset` přijímá `puzzle_id` a
`operation_id`. Restartuje pouze aktivní nedokončenou minihru typu `line_game`,
`mine_karel`, `triad` nebo `sokoban`; ostatní postup relace, checkpoint a
vyřazení hráčů zachová. Oba endpointy vyžadují `Authorization: Bearer
<ADMIN_TOKEN>`, ukládají audit a při opakování stejného `operation_id` vracejí
`changed: false` bez další penalizace či resetu.

### `POST /api/admin/scenario-play-modes` (Cloudflare)

Autentizovaný endpoint přijímá jedinečné `operation_id` a atomický objekt
`modes`, který musí obsahovat právě všechny hádanky cloudového katalogu. Každá
hodnota je `phones`, `supplemental` nebo `exclusive`. Po částech uložený či
neúplný dokument se odmítne, aby nevznikla směs staré a nové konfigurace.

Worker nastavení trvale uloží v adresářovém Durable Objectu, zapíše audit,
uvolní rezervace volných terminálů pro hádanky přepnuté na `phones` a rozešle
nové `runtime.settings` i autoritativní `game.state` rozehraným relacím.
Opakování stejného `operation_id` vrací `changed: false`.

### `POST /api/admin/terminal-catalog` (Cloudflare)

Autentizovaný endpoint přijímá jedinečné `operation_id` a neprázdné pole
`puzzle_ids`. Katalog není druhý konfigurační dokument: atomicky přepíše stejná
data jako režimy hraní. Již povolená hádanka si zachová `supplemental` nebo
`exclusive`, nově přidaná dostane bezpečnější `supplemental` a odebraná
`phones`. Režim pouze pro terminál se nastavuje v detailním editoru způsobů
hraní.

Změna se audituje, opakovaný identifikátor vrací `changed: false` a rezervace
volných terminálů na odebrané hádanky se zruší. Již připojený týmový terminál
se násilně neodpojuje. Nové nastavení se rozešle v `runtime.settings` a
rozehrané relace znovu publikují autoritativní `game.state`.

### `POST /api/admin/player-recovery` a `lobby.recover` (Cloudflare)

Autentizovaný správce pošle `session_id` a `player_id`. Worker vrátí náhodný
šestnáctimístný hexadecimální token platný 10 minut; v Durable Objectu adresáře
se ukládá pouze jeho SHA-256 hash. Nové zařízení odešle token z bootstrap
WebSocketu zprávou `lobby.recover` spolu se svým `client_id`.

Úspěšné použití token atomicky spotřebuje, přepíše identitu hráče v lobby a
přenese jeho `line_game`/`triad` desky, výsledky, vyřazení, navigátorskou stopu
Sokobanu a idempotency účtenky. Pokud šlo o zakladatele, přenese se také tato
role. Starý socket dostane `admin.session_removed` a zavře se; nový bootstrap
dostane `lobby.recovered` následované `lobby.route` do původního
`GameSession`. Opakované použití tokenu je odmítnuto.

### `arg.verify`

Asks backend to verify a physical discovery.

```json
{
  "type": "arg.verify",
  "request_id": "verify-1",
  "payload": {
    "discovery_id": "lobby-panel-a",
    "evidence": {
      "qr_value": "escapebot://clue/lobby-panel-a"
    }
  }
}
```

## Backend -> Client

### `operation.ack`

Potvrzuje, že příkaz označený `operation_id` byl aplikován a jeho nový snapshot
byl uložen. Klient po tomto potvrzení odstraní příkaz z lokální retry fronty.

### `command.rejected`

Odmítne herní příkaz, jehož payload neodpovídá schématu nebo jehož typ není
podporovaný. Odpověď obsahuje `command`, čitelný `reason` a přebírá původní
`request_id` i `operation_id`. Jde o terminální výsledek: klient příkaz se
stejným `operation_id` už neopakuje a autoritativní stav se nezmění.

### `game.state`

Broadcasts current state.

```json
{
  "type": "game.state",
  "payload": {
    "phase": "investigating",
    "unlocked_discoveries": ["lobby-panel-a"],
    "inventory": []
  }
}
```

### `qr.result`

Vrátí výsledek kontroly časové kotvy. `duplicate` znamená, že kotva již byla v dané relaci započítána.

```json
{
  "type": "qr.result",
  "payload": {
    "accepted": true,
    "duplicate": false,
    "checkpoint_id": "reception_archive"
  }
}
```

### `cipher_tool.result`

Potvrdí odemčení pomůcky a uvádí skutečně odečtené body v poli `charged`.

### `puzzle.result`

Vrátí `correct`, identifikátor hádanky a aktuální počet pokusů. Aktualizovaný `game.state` následně obsahuje veřejné zadání hádanky a stav `found` nebo `solved`; správná odpověď se klientovi neposílá.

### `line_game.result`

Potvrdí nebo odmítne výměnu či restart. Úspěšná výměna obsahuje `scored`, počet `cascades` a `game_complete`. Při dokončení obsahuje také `score_delta`: před třetí minutou +5 bodů za každých 10 sekund náskoku, po třetí minutě −5 bodů za každých 10 sekund zpoždění. Změna je současně potvrzena zprávou `score.update`. Autoritativní mřížka, deadline, zbývající čas a průběh cílů jsou vždy poslány v následném `game.state` uvnitř příslušné hádanky.

Server posílá `line_game.result` pouze zařízení, které tah zadalo. Každý hráč
má vlastní perzistentní mřížku; `game.state` ji personalizuje podle `client_id`
a vedle ní obsahuje sdílený `team_progress` bez odhalení mřížek spoluhráčů.

### `karel.result`

Obsahuje provedené pohybové snímky, zásah miny, zablokovaný krok, dokončení
úrovně či celé minihry a změnu skóre. Miny ani interní historii pohybu server
neposílá; následný `game.state` obsahuje pouze veřejnou textovou mřížku,
odhalené číselné indicie, pozici Elary a zbývající čas.

### `triad.result`

Vrací umístěný symbol, nově vytvořené trojice, tah protivníka a stav
individuálního i týmového dokončení. Následný personalizovaný `game.state`
obsahuje pouze desku daného hráče a společný `team_progress`; interní desky
spoluhráčů se neposílají.

### `sokoban.result`

Obsahuje počet požadovaných a skutečně provedených kroků, počet zatlačení, příznaky `blocked`, `level_complete` a případně `game_complete`. Pole `frames` obsahuje po každém provedeném kroku povel, pozici Elary, pozice článků, počítadla a příznak zatlačení; klient z něj přehrává animaci. Při překážce `blocked_command` určuje první nevykonaný povel. Každá poprvé dokončená úroveň vrátí `score_delta` a zprávu `score.update`; aktuálně jde o +30 bodů. Každá úroveň má vlastní dvouminutový deadline. Po dokončení celé aktivní sady následuje běžný `puzzle.result`, příběhová zpráva a aktualizovaný `game.state` s odměnami checkpointu.

## Vývojový demo režim

Klient může v `client.hello` poslat `demo_mode: true`. Pouze backend spuštěný s proměnnou `ESCAPEBOT_DEMO_MODE=1` odpoví zprávou `demo.catalog` obsahující simulovatelné checkpointy. Produkční backend vrátí stejný typ zprávy s `enabled: false` a QR tokeny nezveřejní.

Po každé herní zprávě demo klient dostane také `scenario.progress`. Jde o prezentačně nezávislý snapshot s aktuální fází, skóre, inventářem a uzly ve stavech `complete`, `active`, `available` nebo `locked`. Stejný formát je určen pro budoucí administrátorský přehled více relací; admin rozhraní později pouze seskupí jeden snapshot pro každé `session_id`.

### `bot.message`

Displays bot dialogue.

```json
{
  "type": "bot.message",
  "payload": {
    "text": "Ten panel neni dekorace. Zkus zjistit, co napaji.",
    "mood": "tense"
  }
}
```

### `effect.trigger`

Triggers visual or audio atmosphere.

```json
{
  "type": "effect.trigger",
  "payload": {
    "effect": "glitch",
    "intensity": 0.6,
    "duration_ms": 1200
  }
}
```
