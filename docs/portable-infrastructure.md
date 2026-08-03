# Přenosná lokální infrastruktura

Tento dokument porovnává dvě možné infrastruktury pro provoz Escape Botu v hotelu nebo jiném areálu bez závislosti na místním internetu. První varianta používá jeden centrální backend a kabelově připojené přístupové body. Druhá je experimentální distribuovaná varianta, ve které každý uzel Turris současně funguje jako AP, aplikační server a replika herních dat.

Internet není součástí kritické cesty hry ani v jedné variantě. Může sloužit pouze pro vzdálený dohled, stažení aktualizací před akcí a odeslání telemetrie po skončení.

## Společné požadavky

- Hra, administrace, DNS, DHCP a synchronizace času musí fungovat lokálně.
- Hráčská zařízení se připojují ke stejnému SSID a používají stejné zabezpečení ve všech zónách.
- Hra musí mít důvěryhodné HTTPS a WSS. Doporučené řešení je vlastní veřejná doména a předem vydaný certifikát; lokální DNS překládá doménu na privátní adresu služby.
- Síť pro hráče, administraci a správu infrastruktury mají být oddělené VLAN a pravidly firewallu.
- Výpadek internetu nesmí ukončit rozehranou relaci.
- Veškeré vybavení musí před odjezdem projít testem se stejnou konfigurací, jaká bude použita na místě.
- Captive portal může hráči usnadnit nalezení adresy, ale není náhradou důvěryhodného HTTPS. Vestavěné captive prohlížeče navíc nemusejí spolehlivě podporovat kameru, PWA a WebSockety.

## Varianta A: centrální backend a řízená AP

### Topologie

```text
                     internet nebo LTE
                        (volitelné)
                             │
                    MikroTik RB5009
                    router + CAPsMAN
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
      mini-PC/SSD         cAP ax 1          cAP ax 2 ...
      backend + DB       kabel + PoE        kabel + PoE
           │
       HTTPS/WSS

        router, server a AP napájí společná UPS
```

Pro malou instalaci v jedné nebo dvou zónách může RB5009 nahradit hAP ax3. Pro větší přenosnou sestavu je vhodný RB5009UPr+S+IN, protože nabízí PoE-out na osmi portech. Uvnitř lze použít cAP ax, pro venkovní stanoviště wAP ax. CAPsMAN udržuje společnou konfiguraci AP.

Backend zůstává na samostatném mini-PC s SSD. Router proto může být aktualizován nebo restartován nezávisle na aplikačním prostředí a chyba hry neohrozí DHCP, DNS ani směrování.

### Rádiová síť

AP mají společné SSID, typ zabezpečení a heslo, ale rozdílné, předem naplánované kanály. Pouhé stejné SSID nezaručuje plynulý roaming; klient vždy rozhoduje, kdy AP opustí. Lze zapnout 802.11k/v a po testu používaných telefonů také 802.11r. Výkon AP nemá být automaticky nastaven na maximum, protože by klienti zůstávali připojení ke vzdálenému bodu.

Kabelový ethernet s PoE je výchozí backhaul. Jediný bezdrátový spoj je přípustný pro stanoviště, kam kabel skutečně nelze přivést; nemá se z něj stavět vícehopová páteř.

### Doporučené síťové zóny

| VLAN | Účel | Povolený provoz |
|---|---|---|
| 10 | správa infrastruktury | routery, AP, SSH a monitoring pouze ze správcovských zařízení |
| 20 | hráči | DHCP, DNS, NTP a HTTPS/WSS k backendu |
| 30 | Game Master | admin rozhraní, monitoring a servis backendu |
| 40 | volitelné technologie | fyzické zámky, ESP32 a další herní hardware |

Izolace klientů je vhodná, pokud veškerá týmová komunikace prochází backendem. Před jejím zapnutím je nutné ověřit skenování týmového QR a případné budoucí lokální peer-to-peer funkce.

### Výhody a omezení

Výhodou je jednoduchý konzistenční model, jedna databáze, snadné zálohování a nejnižší počet pohyblivých částí. Porucha serveru však zastaví hru. Praktickou ochranou je náhradní předkonfigurovaný mini-PC nebo obnovitelný image a průběžná kopie databáze na druhé úložiště.

Tato varianta je doporučená pro první produkční instalaci.

## Varianta B: distribuovaný Turris mesh s backendem na každém AP

### Cíl

Každé stanoviště tvoří samostatný uzel Turris Omnia, který poskytuje:

- lokální Wi-Fi AP se společným hráčským SSID,
- lokální instanci klienta, backendu a reverzní proxy,
- kopii scénáře, assetů a databázového stavu,
- replikační službu pro výměnu událostí s ostatními uzly,
- monitoring vlastního napájení, rádia a aplikace.

Jeden z uzlů je při běžném provozu zvolen jako síťová brána, ale nesmí být jediným držitelem herních dat. Mesh propojuje uzly i bez internetu.

### Fyzická a rádiová topologie

```text
       hráči                     hráči
          │                         │
   ┌──────┴──────┐   mesh    ┌─────┴───────┐
   │ Turris A    │◀═════════▶│ Turris B    │
   │ AP+backend  │           │ AP+backend  │
   │ replika DB  │           │ replika DB  │
   └──────┬──────┘           └─────┬───────┘
          ║          mesh           ║
          ╚══════════╦══════════════╝
                     ║
              ┌──────╨──────┐
              │ Turris C    │── hráči
              │ AP+backend  │
              │ replika DB  │
              └─────────────┘
```

Stejné SSID a heslo se týká klientské Wi-Fi, nikoli identity jednotlivých zařízení. Každý uzel musí mít unikátní hostname, management IP, certifikát zařízení a replikační klíč.

Pro stabilní variantu jsou potřeba oddělené rádiové role:

1. klientské rádio vysílá společné SSID pro hráče;
2. backhaul rádio provozuje zabezpečený 802.11s mesh nebo jiný bodový spoj pouze mezi uzly.

Sdílení jednoho rádia mezi klienty a backhaulem je možné pro prototyp, ale snižuje kapacitu a zvyšuje citlivost na rušení. Použití 5 GHz pouze pro mesh a 2,4 GHz pro hráče zase zhorší klientskou kapacitu a roaming. Pro produkci je proto vhodné doplnit samostatné backhaul rádio nebo tam, kde je to možné, mesh propojit ethernetem. Více než dva bezdrátové skoky mezi krajním uzlem a jeho sousedy není vhodné.

### Objevování nejbližšího backendu

Společné SSID samo o sobě nepřesměruje otevřený WebSocket na nový server při přechodu hráče k jinému AP. Klient proto musí získat aplikační vrstvu pro změnu uzlu:

1. Každý backend odpovídá na stejné lokální servisní adrese a současně má unikátní adresu uzlu.
2. Klient uchovává týmový a session token nezávisle na konkrétním serveru.
3. Při ztrátě WSS provede discovery dostupných uzlů, zvolí zdravý uzel s nejnižší odezvou a obnoví relaci.
4. Backend před přijetím zápisu ověří, že má aktuální stav a právo danou týmovou relaci měnit.

Pouhé DNS round-robin ani jedna virtuální IP tento problém při rozdělení meshe bezpečně neřeší. Discovery a reconnect musejí být součástí klienta.

### Konzistenční model

Současné ukládání snapshotů do JSON souborů není určeno pro aktivní zápis na více serverech. Distribuovaná varianta proto vyžaduje událostní replikační vrstvu.

Každá změna obsahuje minimálně:

- globálně unikátní `event_id`,
- `team_id` a `session_id`,
- pořadové číslo relace,
- ID a čas uzlu,
- typ události a verzovaný payload,
- hash předchozí události nebo očekávanou verzi stavu.

Zpracování musí být idempotentní: opakované doručení stejné události nesmí znovu přičíst body, použít nápovědu ani dokončit checkpoint.

#### Doporučené pravidlo jednoho zapisujícího uzlu

Každou týmovou relaci v daném okamžiku vlastní jeden autoritativní uzel. Ostatní drží read-only repliku. Vlastnictví má krátký lease a lze je převzít pouze po dosažení kvóra uzlů. Tento model je pro skóre a pořadí hádanek bezpečnější než automatické slučování všech změn.

Události vhodné pro slučování bez jednoho vlastníka, například telemetrické vzorky nebo stav dostupnosti uzlů, mohou používat CRDT nebo množinu s unikátními ID. Obchodní stav hry se automaticky slučovat nemá.

### Chování při rozdělení sítě

Je nutné předem zvolit mezi dostupností a konzistencí. Doporučená politika je:

- Část meshe s kvórem pokračuje v plném provozu.
- Izolovaný uzel dál poskytuje již stažený klient, příběh a statické assety.
- Izolovaný uzel nepovolí nové bodované změny relace, pokud nevlastnil relaci již před výpadkem a nelze bezpečně prodloužit lease.
- Hráči dostanou příběhovou zprávu o dočasné časové anomálii a pokyn zůstat v oblasti nebo přejít do dosahu dalšího bodu.
- Po obnovení spojení se události přenesou podle ID a pořadí; konflikty se neřeší principem „poslední zápis vyhrává“, ale označí se pro Game Mastera.

Pro vyšší dostupnost lze připustit omezený offline postup na vlastní riziko, ale takový režim potřebuje explicitní pravidla pro slučování každého typu herní události a auditní nástroj. Není vhodný jako první implementace.

### Replikovaná a nereplikovaná data

| Data | Způsob distribuce |
|---|---|
| verze aplikace, scénáře, obrázky a zvuky | podepsaný release balíček nasazený před akcí; během hry neměnný |
| týmové herní události | spolehlivý per-team log, potvrzení doručení a zachování pořadí |
| aktuální snapshot týmu | odvozený z event logu, pravidelně přenášený pro rychlé převzetí |
| přítomnost hráčů a WebSocketů | krátkodobý stav s TTL, nereplikovat jako trvalou pravdu |
| telemetrie | dávkově, tolerantně k duplicitám |
| admin zásahy | podepsané auditní události se stejnými pravidly jako stav hry |
| tajné klíče uzlů | unikátní pro uzel, nikdy nereplikovat běžným event logem |

Každý uzel potřebuje lokální trvalé úložiště vhodné pro databázi; backend nemá dlouhodobě zapisovat intenzivní log na základní interní flash. Aktualizace aplikace se provádí před akcí jako podepsaný, verzovaný image. Během hry musejí všechny uzly hlásit shodnou verzi protokolu a scénáře.

### Provozní dohled

Game Master potřebuje jednu konzoli s mapou uzlů, která ukazuje:

- dostupnost sousedů a kvalitu mesh spojů,
- vedoucí uzel clusteru a vlastníka každé relace,
- replikační zpoždění a poslední potvrzené pořadové číslo,
- konflikty, volné místo, teplotu a stav napájení,
- verzi aplikace, scénáře a databázového schématu.

Před akcí se musí nacvičit vypnutí jednoho uzlu, rozpad clusteru na dvě části, návrat starého uzlu, souběžný reconnect hráčů a obnova z poškozeného úložiště.

### Výhody a omezení

Distribuovaná varianta odstraní jediný aplikační server jako kritický bod a dovolí uchovávat klienta i stav blízko každého stanoviště. Může být zajímavou součástí technického konceptu hry a pomoci v areálech, kde nelze vést kabely.

Současně ale AP přestává být jednoduše vyměnitelným síťovým prvkem. Každý bod obsahuje databázi, certifikáty a aplikační runtime. Výpadky se mění z běžného síťového problému na problém distribuované konzistence. Varianta proto vyžaduje samostatný vývojový projekt a nemá být prvním produkčním nasazením Escape Botu.

## Orientační srovnání nákladů

Výpočet používá čtyři pokryté zóny a maloobchodní ceny s DPH dostupné v srpnu 2026. Jde o plánovací rozpětí, nikoli nabídku dodavatele. Nezahrnuje telefony hráčů, práci při instalaci ani cenu vývoje softwaru.

### Varianta A, čtyři zóny

| Položka | Počet | Odhad za kus | Odhad celkem |
|---|---:|---:|---:|
| MikroTik RB5009UPr+S+IN | 1 | 5 700–6 500 Kč | 5 700–6 500 Kč |
| MikroTik cAP ax | 4 | 2 500–3 000 Kč | 10 000–12 000 Kč |
| mini-PC se SSD | 1 | 6 000–10 000 Kč | 6 000–10 000 Kč |
| UPS, transportní box, kabely a drobný materiál | sada | — | 7 000–12 000 Kč |
| **Celkem** | | | **28 700–40 500 Kč** |

Pokud postačí tři AP nebo již existuje server či UPS, lze se dostat níže. Náhradní mini-PC nebo AP rozpočet zvýší přibližně o cenu daného zařízení.

### Varianta B, čtyři uzly Turris

| Položka | Počet | Odhad za kus | Odhad celkem |
|---|---:|---:|---:|
| Turris Omnia Wi-Fi 6 | 4 | 9 900–12 100 Kč | 39 600–48 400 Kč |
| lokální SSD/mSATA a příslušenství | 4 | 1 000–2 000 Kč | 4 000–8 000 Kč |
| napájení/UPS, držáky, transportní ochrana | sada | — | 10 000–16 000 Kč |
| volitelné oddělené backhaul rádio | 4 | 2 000–3 500 Kč | 8 000–14 000 Kč |
| **Celkem bez oddělených rádií** | | | **53 600–72 400 Kč** |
| **Celkem s oddělenými rádii** | | | **61 600–86 400 Kč** |

Při porovnání středů uvedených rozpětí vychází distribuovaná varianta přibližně o 28 tisíc Kč dráž bez samostatných backhaul rádií a asi o 39 tisíc Kč dráž s nimi. Skutečný rozdíl podle zvoleného vybavení může být přibližně 13–58 tisíc Kč. Největší rozdíl však bude ve vývoji a testování. Centralizovaná varianta odpovídá současnému modelu aplikace; distribuovaná vyžaduje event log, volbu vlastníka relace, discovery, reconnect, clusterovou administraci, řešení konfliktů a testy síťových partition. Před nákupem čtyř uzlů je vhodné ověřit koncept na třech zařízeních, protože tři uzly jsou minimum pro smysluplné kvórum po výpadku jednoho z nich.

## Doporučení a postup ověření

1. Pro první reálnou hru postavit variantu A a změřit reálné pokrytí, roaming, počet klientů a objem synchronizovaných dat.
2. Připravit backend na externí databázi a idempotentní příkazy; je to užitečné i bez meshe.
3. Distribuovaný proof of concept postavit na třech Turrisech, ne rovnou na celé trase.
4. Nejdřív ověřit 802.11s backhaul, discovery uzlů a reconnect klienta bez bodovaných změn.
5. Poté doplnit replikovaný event log a pravidlo jediného zapisujícího uzlu pro tým.
6. Simulovat výpadky a teprve podle výsledků rozhodnout, zda vyšší složitost přináší proti centrálnímu serveru praktickou výhodu.

## Zdroje k hardwaru a cenám

- [MikroTik hAP ax3](https://mikrotik.com/product/hap_ax3)
- [MikroTik cAP ax](https://mikrotik.com/product/cap_ax)
- [MikroTik RB5009UPr+S+IN](https://mikrotik.com/product/rb5009upr_s_in)
- [RouterOS WiFi a CAPsMAN](https://help.mikrotik.com/docs/spaces/ROS/pages/224559120/WiFi)
- [Turris Omnia](https://www.turris.com/en/produkty/omnia/)
- [Turris Omnia Wi-Fi 6 – datasheet](https://static.turris.com/docs/omnia/omnia-wifi6-datasheet.pdf)
- [Orientační cena cAP ax](https://www.zbozi.cz/vyrobek/mikrotik-cap-ax/)
- [Orientační cena RB5009UPr+S+IN](https://www.zbozi.cz/vyrobek/mikrotik-rb5009upr-s-in/)
- [Orientační cena Turris Omnia Wi-Fi 6](https://www.heureka.cz/?h%5Bfraze%5D=turris+omnia)
