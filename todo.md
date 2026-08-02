# Kompletní checklist projektu "Escape Bot"

## 1. Návrh komunikačního protokolu (Frontend <-> Backend)
- [x] Definice formátu zpráv (JSON přes WebSockets).
- [x] Správa stavu hry a relací (State Machine v Pythonu).

## 2. Šablona pro QML rozhraní (Klientská aplikace)
- [x] Základní layout komunikátoru a interaktivní widgety.
- [x] Logika pro obsluhu kamery (extrakce snímků) a integrace čtečky QR kódů (přesunuto na WebRTC/JS).

## 3. Webová aplikace a infrastruktura (PWA / WASM)
- [ ] Kompilace C++/Qt frontendu do WebAssembly.
- [x] Konfigurace PWA (Manifest, Service Workers) pro běh na mobilu ve fullscreenu bez instalace.
- [ ] Zajištění HTTPS a nastavení webového serveru (nutnost pro přístup prohlížeče ke kameře a bezpečné spojení). **Registrace certifikátu u autority (např. Let's Encrypt)**, protože plně důvěryhodný certifikát je vyžadován i pro lokální běh PWA aplikace v místnosti.

## 4. Dynamické napojení na AI (Ollama a ComfyUI)
- [ ] Zpracování vizuálního vstupu pro analýzu reálných lokací a naskenovaných materiálů.
- [ ] Generování kontextových odpovědí a řízení videí (lip-syncing).

## 5. Integrace prvků rozšířené reality (ARG) a rébusů
- [ ] Logika ověřování fyzických objevů v reálném světě.
- [ ] Propojení modulárních virtuálních rébusů s herním dějem.

## 6. Vizuální a zvukové efekty (GL Shadery)
- [x] Atmosférické efekty přes hardwarovou akceleraci (CRT, glitching, odlesky).
- [ ] Synchronizace zvukového designu s akcemi hráče.

## 7. Vizuální editor her (Produkční nástroje)
- [ ] Nodové rozhraní (desktop Qt/C++) pro návrh příběhových větví a stavového automatu.
- [ ] Export scénářů a správa multimediálních assetů.

## 8. Námět na první scénář: Ztracená v jiné dimenzi
- [ ] **Koncept**: Hráč se přes interkom spojí s "Kapitánkou" (první postava). Ta mu dá úkol zachránit "Ztracenou" (druhá postava v jiné dimenzi). Hra obsahuje umělé výpadky spojení pro prodloužení a zvýšení napětí.
- [ ] **Fáze 1 - Spojení s Kapitánkou**: Zprovoznění interkomu a navázání komunikace s Kapitánkou. Přijetí úkolu a indicií.
- [ ] **Fáze 2 - Hledání Ztracené**: Pomocí šifer a hádanek najít správnou frekvenci/souřadnice pro spojení s druhou (ztracenou) postavou.
- [ ] **Fáze 3 - Neúspěšné pokusy a výpadky**: Ztracená je nalezena, ale spojení je nestabilní. Záměrné chybné přenosy, ztráta spojení a nutnost jeho opětovného (a složitějšího) navázání.
- [ ] **Fáze 4 - Záchranná mise**: Komunikace se Ztracenou. Pomocí dalších hádanek a šifer ji přemisťovat správným směrem až k záchrannému portálu.

## 9. Zjednodušení architektury (Pivot k webu a hardwaru)
- [ ] **Webový interkom (Hlavní klient)**: Opustit nutnost složitého QML klienta a přesunout hlavní komunikační rozhraní do webové aplikace (např. PWA).
- [ ] **Virtuální záložky pro rébusy (Fallback)**: Pokud není k dispozici vyhrazený HW nebo počítač pro konkrétní hádanku (či celou místnost), bude tato hádanka simulována ve formě samostatné záložky (tabu) v hlavním webovém klientovi. Výchozí a hlavní záložkou bude vždy Interkom.
- [ ] **Rozšířený interkom (Kanály)**: Vytvořit v interkomu oddělené komunikační kanály (např. #general, #kapitanka, #ztracena), aby byl děj přehlednější a více připomínal skutečný terminál.
- [ ] **Interaktivní mapa (Hybridní ARG navigace)**: Přidat záložku s mapou (např. hotelu), která propojuje herní děj s reálným světem. Mapa bude hráče navigovat na skutečná fyzická místa (např. konkrétní pokoje), kde najdou reálné schránky na kód, QR kódy ke skenování, nebo vyhrazené počítače s dílčími rébusy.
- [ ] **Klientský framework (Vlastní prohlížeč na míru)**: Pro PC vytvořit speciální prohlížeč/wrapper (např. pomocí Tauri či Electronu), který webovou aplikaci obalí a zajistí komunikaci s lokálním hardwarem, pokud standardní webové cesty nebudou stačit.
- [ ] **Jednoúčelové webovky pro rébusy**: Vytvořit speciální oddělené webové stránky určené výhradně pro vyhrazené počítače/tablety v únikovce, které budou sloužit k řešení specifických dílčích rébusů.
- [ ] **Hardwaroví klienti (Mikrokontroléry)**: Připravit architekturu pro dedikované klienty na mikrokontrolérech (např. ESP32), kteří budou s hrou komunikovat buď napřímo (WebSocket/MQTT), nebo přes zmiňovaný PC framework.
- [ ] **Přístupové panely a zámky místností**: Blokovat vstup do konkrétních virtuálních/fyzických místností. Virtuální místnost nejprve zobrazí číselník; vyhrazený PC poslouží jako "přihlašovací okno"; fyzický HW panel po správném zadání otevře dveře a odošle signál hře.

## 10. Backend jako centrální uzel (Orchestrace a Multitasking)
- [ ] **Webserver a orchestrátor**: Backend bude sloužit jako hlavní přístupový bod (webserver pro klientské aplikace) a postará se o orchestraci všech ostatních služeb (AI modely, HW zprávy).
- [x] **Perzistence a obnova relací (Wi-Fi stabilita)**: Session tokeny fungují. Stav všech her se automaticky ukládá do `sessions.json` a obnovuje i po tvrdém restartu serveru.
- [ ] **Správa více hráčů (Multiplayer)**: Zajištění synchronizace stavu hry mezi vícero klienty (telefony/tablety/PC) v rámci jedné herní relace.
- [ ] **Multitasking a více instancí (Multitenancy)**: Přepracování správy stavu tak, aby backend dokázal obsluhovat více nezávislých her (místností nebo různých scénářů) naprosto paralelně a bez ovlivňování.
- [ ] **Centrální správa hry (Game Master panel)**: (Odloženo) Využívat JSON soubor jako dočasnou admin konzoli. Později připravit plnohodnotné webové rozhraní pro obsluhu únikovky.
- [ ] **Captive portál (Vstupní bod hry)**: Zprovoznit captive portál (např. úpravou DNS pro přesměrování po připojení na herní Wi-Fi), který automaticky načte klientům webové rozhraní hry.

## 11. Herní engine, nápovědy a skórování
- [x] **Oddělení scénáře od enginu**: Přesunout hardcodovanou logiku, fáze a texty z backendu (např. `state_machine.py`) do externích konfiguračních souborů (JSON/YAML scénáře), aby engine zůstal plně univerzální.
- [x] **Inteligentní reakce na vstupy**: Nahradit jednoduché kontroly (např. if "734" in text) robustnějším systémem, případně s napojením na lokální AI (Ollama) pro interaktivní a variabilní reakce na hráčské podměty.
- [x] **Systém postupných nápověd (Hint systém)**: Nápovědy jsou integrovány přímo do chatu. AI analyzuje záměr hráče z jeho zpráv, a pokud detekuje bezradnost či prosbu o pomoc, uvolní další nápovědu k aktuální fázi.
- [x] **Bodování a penalizace**: Zaveden výchozí stav bodů (Skóre) pro hru. Za každé uvolnění nápovědy AI systémem se odečte specifikovaný počet negativních bodů.
- [x] **Síň slávy (Leaderboard)**: Na konci scénáře vyhodnotit úspěšnost, zobrazit výsledné skóre, vyzvat hráče k zadání jména týmu a zapsat výsledek do trvalé Síně slávy.

## 12. Inkrementální vývoj scénáře: Ztracená v jiné dimenzi

### Inkrement 1 – Funkční prototyp komunikátoru
**Cíl:** hráč si může zahrát celý příběh bez pohybu po hotelu.
- [ ] Vytvořit scénář Kapitánka → Ztracená → Záchrana.
- [ ] Implementovat fáze scénáře ve stavovém automatu.
- [ ] Přidat kanály:
  - `#general`
  - `#kapitanka`
  - `#ztracena`
- [ ] Připravit 3–5 jednoduchých textových rébusů.
- [ ] Implementovat přechody mezi fázemi pomocí správných odpovědí.
- [ ] Implementovat výpadky spojení.
- [ ] Implementovat závěrečné skóre.

### Inkrement 2 – Modulární komunikátor
**Cíl:** hráč postupně opravuje zařízení.
- [ ] Definovat seznam modulů komunikátoru:
  - Kamera
  - Mapa
  - Analýza signálu
  - Překladač
  - Archiv záznamů
- [ ] Přidat systém odemykání modulů.
- [ ] Zobrazovat neaktivní moduly v UI.
- [ ] Přidat backendovou evidenci získaných modulů.
- [ ] Přidat zprávy Kapitánky reagující na obnovu modulů.

### Inkrement 3 – QR infrastruktura
**Cíl:** první propojení virtuální a fyzické hry.
- [ ] Implementovat QR scanner v klientovi.
- [ ] Definovat formát QR payloadů.
- [ ] Implementovat registraci nalezených QR.
- [ ] Přidat ochranu proti opakovanému použití.
- [ ] Přidat reakce scénáře na nalezení QR.

### Inkrement 4 – Hledání dílů komunikátoru
**Cíl:** hráč se pohybuje po hotelu.
- [ ] Vytvořit systém "fyzických modulů".
- [ ] Připravit QR pro:
  - Kameru
  - Mapu
  - Analýzu signálu
- [ ] Vytvořit hádanky vedoucí k umístění QR.
- [ ] Ověřit průchodnost pouze přes společné prostory hotelu.
- [ ] Přidat nápovědní systém pro hledání.

### Inkrement 5 – Hotelová navigace
**Cíl:** hráč získává indicie a orientuje se v budově.
- [ ] Přidat interní mapu hotelu.
- [ ] Vytvořit databázi zajímavých míst:
  - recepce
  - výtah
  - schodiště
  - lobby
  - chodby
  - okna
- [ ] Implementovat rébusy typu:
  - patro
  - směr
  - orientační bod
- [ ] Přidat systém lokalizačních indicií.

### Inkrement 6 – Venkovní GPS mise
**Cíl:** rozšíření mimo budovu.
- [ ] Přidat GPS geofencing.
- [ ] Přidat ověření dosažení lokace.
- [ ] Připravit první venkovní checkpoint.
- [ ] Přidat QR na venkovní lokaci.
- [ ] Implementovat GPS založené nápovědy.

### Inkrement 7 – Stopy Ztracené
**Cíl:** budování příběhu.
- [ ] Navrhnout časovou osu pohybu Ztracené.
- [ ] Připravit sérii nalezených záznamů.
- [ ] Přidat hlasové zprávy.
- [ ] Přidat fotografie z "jiné dimenze".
- [ ] Implementovat skládání příběhu z nalezených stop.

### Inkrement 8 – Anomálie a falešné stopy
**Cíl:** zvýšit nejistotu a atmosféru.
- [ ] Přidat falešné QR.
- [ ] Přidat poškozené přenosy.
- [ ] Přidat alternativní dimenze.
- [ ] Přidat glitch efekty.
- [ ] Přidat náhodné rušení komunikace.

### Inkrement 9 – Navigace Ztracené
**Cíl:** hráč aktivně pomáhá postavě.
- [ ] Vytvořit systém virtuální mapy.
- [ ] Implementovat rozhodování:
  - vlevo
  - vpravo
  - vpřed
  - zpět
- [ ] Přidat slepé cesty.
- [ ] Přidat nebezpečné oblasti.
- [ ] Přidat více možných tras.

### Inkrement 10 – Finále
**Cíl:** záchrana Ztracené.
- [ ] Stabilizace portálu.
- [ ] Poslední série rébusů.
- [ ] Spojení informací od Kapitánky a Ztracené.
- [ ] Otevření portálu.
- [ ] Závěrečné video.
- [ ] Vyhodnocení skóre.
- [ ] Zápis do síně slávy.

### Inkrement 11 – Produkční připravenost
**Cíl:** scénář použitelný pro více hotelů.
- [ ] Oddělit lokace od scénáře.
- [ ] Přidat editor lokací.
- [ ] Generování QR kódů.
- [ ] Import mapy objektu.
- [ ] Konfigurovatelné GPS body.
- [ ] Export kompletní hry jako balíčku.

## 13. Produkční scénář – Ztracená v čase: Hotel Kraskov

### 13.1 Příběhové zasazení
**Cíl:** převést současný prototyp z obecného hotelu a jiné dimenze do konkrétního příběhu o poruše stroje času v Hotelu Kraskov.
- [x] Přejmenovat a upravit znalostní bázi scénáře pro Hotel Kraskov.
- [ ] Zachovat úvodní spojení s Kapitánkou a nalezení frekvence `734`.
- [x] Upravit roli Elary na věkyni ztracenou v jiné časové vrstvě stejného hotelu.
- [x] Po prvním spojení odhalit, že experiment rozptýlil součásti stroje času po hotelu a okolí.
- [x] Přejmenovat herní mapu na `CHRONOMAPA` a QR checkpointy na `časové kotvy`.
- [ ] Definovat pravidla cestování časem, aby byly konzistentní v dialozích i hádankách.
- [ ] Napsat časovou osu Elařina experimentu, havárie a návratu.
- [x] Nahradit odkazy na Hotel Overlook, dimenzionální krystaly a portál terminologií stroje času.

### 13.2 Trasa a dostupné prostory
**Cíl:** vytvořit bezpečnou trasu přes skutečné, předem schválené prostory Hotelu Kraskov.
- [ ] Získat půdorys nebo jednoduchý plánek hotelu a venkovního areálu.
- [ ] Potvrdit startovní a finální konferenční místnost.
- [ ] S hotelem potvrdit použití recepce, schodiště, lobby, bowlingu, terasy a venkovního sportovního areálu.
- [ ] Určit místa, kam lze bezpečně umístit QR kódy, obálky a fyzické artefakty.
- [ ] Vyhnout se pokojům hostů, mokrým prostorům wellness, provozním zónám a nebezpečným venkovním místům.
- [ ] Připravit suchou/vnitřní variantu venkovního checkpointu pro špatné počasí.
- [ ] Ověřit dostupnost celé trasy pro zamýšlený počet týmů.
- [ ] Stanovit cílovou délku hry a časový limit.

### 13.3 Checkpoint 0 – Havárie experimentu
**Místo:** startovní konferenční místnost.
- [ ] Dokončit hádanku vedoucí k frekvenci `734`.
- [ ] Zachovat první výpadek spojení a příkaz `restart`.
- [x] Napsat Elařino odhalení, že se nachází ve stejném hotelu, ale v jiném čase.
- [x] Po restartu odemknout modul `CHRONOMAPA`.
- [x] Zpřístupnit první indicii vedoucí na recepci.

### 13.4 Checkpoint 1 – Recepční archiv
**Typ:** logická dedukční tabulka.
- [x] Navrhnout čtveřici vědců, pokojů, archivních pozic a převážených součástek.
- [x] Sepsat jednoznačné indicie a ověřit jediné správné řešení.
- [x] Získat z tabulky čtyřmístný PIN virtuálního archivu.
- [ ] Umístit první časovou kotvu poblíž recepce bez omezení jejího provozu.
- [x] Po vyřešení zpřístupnit archivní záznam a navigaci ke schodišti.

### 13.5 Checkpoint 2 – Schodiště
**Typ:** praporová abeceda zamaskovaná jako polohy hodinových ručiček.
- [x] Připravit zašifrovanou zprávu vedoucí k bowlingu.
- [x] Připravit tematickou tabulku praporové abecedy.
- [x] Rozhodnout, že digitální tabulku odemkne QR checkpoint na schodišti.
- [x] Zajistit jednoznačnou orientaci levé a pravé paže z pohledu pozorovatele.
- [x] Po skenu zaznamenat dosažení schodiště a po vyřešení odemknout bowling.
- [x] Nahradit textový popis šifry jedinou koláží sedmi dovolenkových fotografií Elary u slavných hodin.
- [x] Zakódovat slovo `BOWLING` polohami modré a červené ručičky a neposkytovat u hádanky slovní návod.

### 13.6 Checkpoint 3 – Bowling
**Typ:** binární diagnostika pomocí stojících a spadlých kuželek.
- [x] Navrhnout vizuální binární zprávu s jednoznačným směrem čtení.
- [x] Použít pět sedmibitových znaků ASCII s výsledným slovem `MOTOR`.
- [ ] Umístit QR kotvu a fyzickou schránku mimo aktivní hrací dráhu.
- [ ] Vyrobit první fyzický díl stroje: `TEMPORÁLNÍ MOTOR`.
- [x] Zapsat součást do digitálního inventáře až po vyřešení hádanky.
- [x] Vytvořit jediný obrazový artefakt s pěti fotografiemi Elary při hodu a samostatným PIP v každé fotografii.
- [x] V každém PIP zobrazit kompletní trojúhelník 4–3–2–1; označené řady 4+3 kódují sedm bitů a řady 2+1 jsou obrazový šum.
- [x] Ve všech deseti pozicích použít stojící kuželku jako `1` a prázdnou obrysovou pozici jako `0`.

### 13.7 Checkpoint 4 – Terasa nebo okolí rybníka
**Typ:** Morseova abeceda a navigační zpráva.
- [ ] Vybrat konkrétní bezpečné venkovní místo.
- [x] Vytvořit poškozený přenos složený z krátkých a dlouhých impulzů.
- [x] Zpřístupnit Morseovu tabulku od začátku jako součást nouzového manuálu.
- [ ] Navrhnout navigační text bez nejednoznačných orientačních bodů.
- [ ] Umístit druhý fyzický díl stroje: `FÁZOVÝ STABILIZÁTOR`.
- [ ] Připravit alternativní umístění pro déšť, tmu nebo uzavření areálu.
- [x] Vytvořit noční obrazový artefakt Elary u rybníka s kočičí Morseovkou: kotě = tečka, dospělá kočka = čárka; sekvence `.... / .-. / .. / ... / - / .` vede na `HŘIŠTĚ`.
- [x] Po správném řešení přidat `FÁZOVÝ STABILIZÁTOR` do digitálního inventáře a odemknout sportovní checkpoint.

### 13.8 Checkpoint 5 – Sportovní areál
**Typ:** polský kříž a skládání šifrovací tabulky.
- [ ] Připravit dvě části tabulky nebo průhledné fólie získané na předchozích stanovištích.
- [ ] Zakódovat zprávu odkazující na konkrétní hodiny nebo jiný výrazný objekt v hotelu.
- [ ] Ověřit, že bez obou fyzických částí nelze řešení snadno odhadnout.
- [ ] Umístit třetí fyzický díl stroje: `KRYSTAL ČASOVÉ KOTVY`.
- [ ] Zpřístupnit vstup do virtuálního archivu budoucnosti.

### 13.9 Checkpoint 6 – Archiv budoucnosti
**Typ:** kombinace fyzické skládačky a klasické šifry.
- [ ] Navrhnout tři díly tak, aby po složení vytvořily šifrovací kotouč nebo tabulku.
- [ ] Umístit na díly symboly, barvy a části číselné stupnice určující správné pořadí.
- [ ] Vybrat finální klasickou šifru, např. Caesarovu nebo Vigenèrovu.
- [ ] Zajistit, aby klíč k šifře vznikl až správným složením fyzických dílů.
- [ ] Nechat hráče získat rok, přesný čas a pořadí modulů pro návrat Elary.

### 13.10 Checkpoint 7 – Finále stroje času
**Místo:** startovní/finální konferenční místnost.
- [ ] Vyrobit základnu, do které lze vložit tři fyzické díly stroje.
- [ ] Implementovat zadání roku, času a pořadí modulů do terminálu.
- [ ] Před spuštěním ověřit všechny povinné QR checkpointy a inventář.
- [ ] Připravit odpočet, zvuk stroje, glitch efekt a zprávu o návratu Elary.
- [ ] Dokončit výpočet skóre, penalizace za nápovědy a zápis do Síně slávy.

### 13.10.1 Interkomová navigace – Minové pole / Robot Karel
**Cíl:** spojit logické odhalování bezpečných polí ve stylu Min s programováním pohybu postavy ve stylu Robota Karla. Hráči navigují Elaru přes interkom a její polohu sledují na šachovnici.

#### Herní princip
- [ ] Určit vhodné zasazení do příběhu, např. nestabilní časové pole mezi Elarou a strojem času.
- [ ] Navrhnout obdélníkovou nebo čtvercovou herní mřížku s jasně označeným startem a cílem.
- [ ] Rozmístit skryté časové anomálie fungující jako miny.
- [ ] Na odkrytých polích zobrazovat počet anomálií v sousedních polích.
- [ ] Zvolit, zda se počítají čtyři ortogonální, nebo všech osm okolních polí.
- [ ] Zajistit alespoň jednu logicky odvoditelnou bezpečnou trasu bez nutnosti náhodného hádání.
- [ ] Určit, zda je cílem pouze dojít do cíle, nebo cestou sebrat klíč, artefakt či aktivovat spínače.
- [ ] Navázat dokončení úkolu na konkrétní odměnu, checkpoint nebo součást stroje času.

#### Ovládání ve stylu Robota Karla
- [ ] Definovat základní příkazy `KROK`, `VLEVO`, `VPRAVO` a `ZPET`.
- [ ] Rozhodnout, zda Elara stojí natočená určitým směrem, nebo se pohybuje přímo pomocí `NAHORU`, `DOLU`, `VLEVO`, `VPRAVO`.
- [ ] Umožnit zadat jeden příkaz nebo celou sekvenci příkazů najednou.
- [ ] Zvažit jednoduché programové konstrukce `OPAKUJ n`, podmínku nebo pojmenovanou sekvenci.
- [ ] Definovat maximální délku programu a způsob jeho potvrzení před spuštěním.
- [ ] Zobrazit náhled naplánované sekvence před jejím vykonáním.
- [ ] Umožnit krokové provedení, pozastavení a bezpečné zrušení nevykonané části sekvence.
- [ ] Rozlišit neplatný příkaz, náraz do stěny a vstup na nebezpečné pole.

#### Interkom a odezva Elary
- [ ] Přijímat navigační příkazy v samostatném strukturovaném vstupu nebo v kanálu Elary.
- [ ] Nepoužívat volné AI vyhodnocení pro samotný pohyb; příkazy parsovat deterministicky.
- [ ] Nechat Elaru před pohybem zopakovat pochopenou sekvenci.
- [ ] Po každém kroku odeslat krátkou reakci odpovídající novému okolí.
- [ ] Při odhalení čísla sdělit počet okolních anomálií i textově kvůli přístupnosti.
- [ ] Připravit reakce na slepou cestu, opakované pole, chybný příkaz a blízkost anomálie.
- [ ] Při úspěchu spustit příběhovou zprávu a odemknout navazující uzel scénáře.

#### Vizualizace šachovnice
- [ ] Přidat samostatný panel nebo záložku s responzivní šachovnicí.
- [ ] Zobrazit Elaru jako postavu se zřetelnou orientací.
- [ ] Rozlišit skryté, odkryté, navštívené, označené a cílové pole.
- [ ] Zobrazit čísla okolních anomálií podobně jako ve hře Miny.
- [ ] Animovat pohyb krok po kroku tak, aby hráči viděli, který příkaz se právě provádí.
- [ ] Umožnit na mobilu současně sledovat šachovnici a posloupnost příkazů.
- [ ] Vizuálně odlišit potvrzená bezpečná pole od pouhých hráčských odhadů.
- [ ] Připravit alternativní textové zobrazení mřížky pro přístupnost a nouzový provoz.

#### Chyby, penalizace a obnovení
- [ ] Rozhodnout, zda vstup na anomálii znamená okamžitý neúspěch, odečet bodů, návrat na poslední kotvu nebo změnu mapy.
- [ ] Zabránit nevratnému zablokování hry po chybném pohybu.
- [ ] Ukládat aktuální pozici, orientaci, odkrytá pole a historii příkazů do stavu relace.
- [ ] Připravit omezený počet bezpečnostních skenů nebo možnost jejich zakoupení za body.
- [ ] Připravit volitelné nápovědy: upozornění na bezpečné pole, odhalení čísla nebo zobrazení dalšího správného kroku.
- [ ] Umožnit Game Masterovi vrátit postavu na poslední bezpečné pole nebo úkol ručně dokončit.

#### Demo a budoucí admin panel
- [ ] V demo režimu zobrazit celé rozmístění anomálií a správnou bezpečnou trasu.
- [ ] Umožnit v demo režimu simulovat příkazy tlačítky bez psaní do interkomu.
- [ ] V admin snapshotu zobrazit pozici, orientaci, poslední příkaz, odkrytá pole a počet chyb.
- [ ] Umožnit administrátorovi sledovat animaci pohybu aktivního týmu v reálném čase.
- [ ] Zaznamenat celou historii příkazů pro pozdější vyhodnocení obtížnosti.

#### Implementace a testování
- [ ] Definovat mapu, start, cíl, anomálie a pravidla v datech scénáře, ne v UI.
- [ ] Implementovat deterministický simulátor pohybu nezávislý na WebSocketu a vykreslení.
- [ ] Přidat protokolové zprávy pro naplánování, potvrzení a vykonání příkazů.
- [ ] Ošetřit souběžné povely z více klientů stejného týmu.
- [ ] Otestovat hranice mapy, rotaci, kolize, anomálie, opakování a obnovení uložené relace.
- [ ] Automaticky ověřit, že navržená mapa má alespoň jednu bezpečnou trasu a není řešitelná náhodným jedním krokem.
- [ ] Udělat stolní test s hráči bez znalosti programování.
- [ ] Změřit, zda je srozumitelná kombinace dedukce Min a sekvenčních příkazů Karla.

### 13.10.2 Interkomový Sokoban
**Cíl:** navigovat Elaru v uzavřeném prostoru a správným pořadím pohybů přesunout energetické články na cílové pozice. Hráči dávají pokyny přes interkom a sledují jejich provedení na herní mřížce.

- [x] Příběhově zasadit úkol jako opravu napájení servisní sítě sportovního archivu.
- [x] Připravit tři aktivní mapy se stěnami, Elarou, energetickými články a cílovými poli.
- [x] Připravit dvě další validní a řešitelné mapy jako rezervu pro obměnu nebo zvýšení délky hry.
- [x] Zajistit možnost návratu posledního kroku a úplného restartu proti nevratnému zablokování.
- [x] Implementovat deterministické příkazy `NAHORU`, `DOLŮ`, `VLEVO`, `VPRAVO`, opakování a sekvence oddělené čárkou.
- [x] Zpracovávat navigační povely z kanálu `# ztracená_sig` bez volného AI vyhodnocení.
- [x] Nechat Elaru potvrdit provedené kroky, zatlačení a místo zastavení zablokované sekvence.
- [x] Zobrazit responzivní mřížku s Elarou, stěnami, články, cíli a články správně usazenými na cíli.
- [x] Umožnit vrácení posledního tahu a restart mapy; v demo režimu doplnit směrová tlačítka.
- [x] Omezit každou úroveň na dvě minuty a po vypršení umožnit restart pouze aktuální úrovně.
- [x] Za každou poprvé dokončenou aktivní úroveň přičíst 30 bodů bez možnosti opakovaného získávání.
- [x] Ukládat aktuální úroveň, mapu, čas, dokončené sektory, historii kroků, sekvence, počet zatlačení a restartů do relace.
- [x] Po vyřešení přidělit `KRYSTAL ČASOVÉ KOTVY`, odemknout polský kříž a dokončit sportovní checkpoint.
- [x] Definovat mapu znaky ve scénáři a při načtení ověřit hráče, články, cíle a obdélníkový tvar.
- [x] Otestovat český parser, řešení všech aktivních i rezervních map, bodování, zablokovanou sekvenci, undo a obnovení relace.
- [x] Posílat z backendu autoritativní mezistav každého skutečně provedeného kroku a zatlačení.
- [x] Animovat sekvenci krok po kroku, zvýraznit aktuální povel a neproveditelný krok při překážce.
- [x] Umožnit pozastavit a znovu spustit přehrávání sekvence; během přehrávání blokovat další povely z téhož klienta.
- [ ] V budoucí víceklientské verzi vysílat průběh animace synchronně všem zařízením týmu.
- [ ] V budoucím admin panelu zobrazit správné řešení, optimální počet tahů a aktuální odchylku týmu.
- [ ] Po uživatelském testu doladit dvě minuty na úroveň, bodovou odměnu a obtížnost aktivních map.

### 13.10.3 Interaktivní Had – sběr časových fragmentů
**Cíl:** nabídnout krátkou akční mezihru ovládanou přímo hráčem. Had představuje proud energie nebo časovou stopu, která sbírá fragmenty potřebné ke stabilizaci stroje času.

- [ ] Navrhnout hru jako samostatný interaktivní panel bez ovládání přes interkom.
- [ ] Připravit ovládání šipkami, `WASD` a velkými dotykovými tlačítky pro mobilní zařízení.
- [ ] Zabránit okamžitému otočení do protisměru a sjednotit rychlost hry mezi různými zařízeními.
- [ ] Nahradit běžné jídlo časovými fragmenty, energetickými částicemi nebo ztracenými daty Elary.
- [ ] Přidat překážky či nestabilní pole až ve vyšší obtížnosti; základní varianta musí být rychle pochopitelná.
- [ ] Určit jasnou podmínku splnění, například sesbírat stanovený počet fragmentů nebo vydržet určitý čas.
- [ ] Nastavit omezený počet pokusů, případně bodovou penalizaci, ale nezablokovat kvůli neúspěchu celý scénář.
- [ ] Nabídnout pauzu, restart a sníženou rychlost jako přístupnější variantu nebo placenou nápovědu.
- [ ] Ukládat nejlepší výsledek, počet pokusů, dosaženou délku a stav dokončení do relace.
- [ ] V demo režimu umožnit okamžité splnění a změnu rychlosti; v admin panelu sledovat aktuální skóre hráče.
- [ ] Po dosažení cíle udělit fragment, součást stroje nebo kód pro následující checkpoint.
- [ ] Otestovat klávesnici, dotykové ovládání, změnu orientace telefonu, ztrátu připojení a obnovení hry.

### 13.10.4 Logická variace na Tři v řadě
**Cíl:** v klasickém pětibarevném puzzle prohazovat sousední kameny a pomocí dvou aktivních časových barev splnit v libovolném pořadí cíle 5× trojice, 3× čtveřice a 1× pětice.

- [x] Zvolit pětibarevnou mřížku 7×7 s výměnou dvou ortogonálně sousedících kamenů.
- [x] Příběhově označit azurovou a jantarovou jako aktivní proudy minulosti a budoucnosti.
- [x] Použít zbývající tři barvy jako neutrální výplň, jejíž řady se odstraní, ale nezapočítají.
- [x] Po platné výměně odstranit vodorovné a svislé řady, nechat kameny propadnout a deterministicky doplnit nové.
- [x] Podporovat a započítávat navazující kaskády.
- [x] Implementovat cíle 5× řada délky 3, 3× řada délky 4 a 1× řada délky 5 v libovolném pořadí.
- [x] Nahradit limit tahů společným pětiminutovým limitem kontrolovaným backendem.
- [x] Při dokončení před třetí minutou přičítat 5 bodů za každých 10 sekund; po třetí minutě stejným tempem body odečítat až do limitu.
- [x] Umožnit nový pokus, který obnoví mřížku, cíle i časovač.
- [x] Implementovat deterministické vyhodnocení výměn na backendu bez závislosti na AI.
- [x] Zobrazit vybraný kámen, obě bodované barvy, počet platných výměn, čas a průběh všech cílů.
- [x] Napojit výhru na příběhovou kalibraci časové osy a odemčení sportovního archivu.
- [x] Ukládat celou rozehranou mřížku a průběh etap do stavu relace.
- [x] Zařadit samostatný QR checkpoint mezi terasu a sportovní archiv.
- [x] Otestovat pořadí checkpointů, neplatnou výměnu, volné pořadí cílů, časový limit, kladné i záporné časové skóre, restart a obnovení relace.
- [ ] Po uživatelském testu doladit časový limit, četnost kombinací a obtížnost náhodně doplňované mřížky.
- [ ] V budoucím admin panelu přidat živý náhled mřížky a možnost dokončit či restartovat pokus.

### 13.11 QR checkpointy a ochrana postupu
**Cíl:** QR kódy musí potvrzovat průchod trasou a bezpečně odemykat obsah.
- [x] Nahradit volný formát `escapebot://clue/<id>` seznamem povolených checkpointů ze scénáře.
- [x] Pro každý QR vytvořit neprůhledný náhodný token, který neprozrazuje řešení ani pořadí.
- [x] Definovat pro každý checkpoint povinné předchůdce.
- [x] Odmítnout QR naskenovaný před splněním předchozího kroku.
- [x] Zabránit opakovanému přidělování odměny a bodů za stejný QR.
- [ ] U klíčových míst doplnit lokální kontrolní otázku nebo kód z fyzického okolí.
- [x] Evidovat čas prvního skenu každého checkpointu.
- [ ] Rozlišit stavy `nalezeno`, `ověřeno`, `vyřešeno` a `odměna vyzvednuta`.
- [x] Odemknout virtuální místnost jen při splnění všech podmínek, ne pouze znalostí PINu.
- [ ] Připravit jednorázové nebo rotující kódy pro checkpointy vyžadující silnější kontrolu přítomnosti.
- [ ] Připravit Game Masterovi možnost ručně potvrdit nebo přeskočit porouchaný checkpoint.

### 13.12 Hádanky, nápovědy a testování
- [ ] U každé hádanky napsat zadání, řešení, mezikroky a akceptované varianty odpovědi.
- [ ] U vybraných hádanek připravit a otestovat stupňované nápovědy; obtížnější checkpointy mohou být záměrně bez nápověd.
- [ ] Střídat logické úlohy, klasické šifry, pohyb a manipulaci s artefakty.
- [ ] Nevkládat za sebe více než dvě substituční šifry.
- [ ] U každé použité šifry vysvětlit její existenci v rámci příběhu.
- [ ] Určit, které funkce Šifrovacích pomůcek Absolutno potřebujeme v herním panelu a které by již příliš automatizovaly řešení.
- [ ] Udělat stolní test všech hádanek bez pohybu po hotelu.
- [ ] Udělat technický průchod s jedním testovacím týmem přímo v hotelu.
- [ ] Udělat zátěžový test více týmů a odhalit kolize na stanovištích.
- [ ] Změřit reálnou obtížnost, dobu řešení a celkovou délku trasy.
- [ ] Připravit obálku s nouzovým řešením a provozní checklist pro Game Mastera.

### 13.13 Produkční podklady
- [ ] Vytvořit kartu každého checkpointu: lokace, QR ID, rekvizita, hádanka, řešení, odměna a nápovědy.
- [ ] Vygenerovat tisknutelné QR kódy s interním označením pro organizátora.
- [ ] Vytvořit tisknutelné šifrovací tabulky pro prapory, Morseovu abecedu a polský kříž.
- [ ] Vytvořit hráčskou mapu Kraskova bez vyznačených řešení.
- [ ] Vytvořit organizační mapu se všemi checkpointy, záložními QR a nouzovými trasami.
- [ ] Sepsat seznam všech fyzických dílů, schránek, obálek a spotřebního materiálu.
- [ ] Připravit instalační a deinstalační checklist pro hotel.
- [ ] Připravit záložní papírovou variantu pro výpadek Wi-Fi, serveru nebo telefonu.

### 13.13.1 Vývojový demo režim
- [x] Přidat explicitní spuštění backendu pomocí `--demo`.
- [x] Aktivovat demo rozhraní klienta parametrem `?demo=1`.
- [x] V demo režimu nevyžadovat kameru.
- [x] Zobrazit v záložce skeneru tlačítka všech QR checkpointů.
- [x] Simulovat tlačítkem stejnou zprávu `qr.detected` jako při skutečném skenu.
- [x] Zachovat v demo režimu kontrolu pořadí, duplicit, odměn a podmínek.
- [x] Nevydávat katalog QR tokenů, pokud backend nebyl explicitně spuštěn v demo režimu.
- [x] Definovat datový graf fází, checkpointů, virtuálních místností a finále ve scénáři.
- [x] V demo režimu zobrazit živý stav uzlů `hotovo`, `právě probíhá`, `dostupné` a `uzamčeno`.
- [x] Ve vizualizaci zobrazit aktuální fázi, skóre, inventář a odemčené pomůcky.
- [x] Ve vývojové/admin vizualizaci zobrazit správné řešení každého uzlu bez odeslání do běžného hráčského stavu.
- [x] Oddělit datový snapshot postupu od vykreslení pro pozdější použití v admin panelu.
- [ ] Vytvořit samostatnou autentizovanou admin stránku se seznamem všech aktivních relací.
- [ ] Přidat do admin stránky detail týmu založený na stejné vizualizaci `scenario.progress`.

### 13.14 Šifrovací pomůcky v aplikaci
**Cíl:** nabídnout hráčům pasivní referenční pomůcku inspirovanou způsobem použití aplikace Šifrovací pomůcky Absolutno, aniž aplikace sama vyřeší zadanou hádanku.
- [ ] Ověřit licenci, souhlas autora a možnosti přímého použití názvu, obrazovek nebo obsahu aplikace Absolutno.
- [ ] Bez licence nekopírovat zdrojový kód, grafiku ani konkrétní zpracování; vytvořit vlastní panel ze standardních veřejně známých abeced a šifer.
- [x] Přidat tlačítko `ŠIFROVACÍ POMŮCKY` dostupné z komunikátoru, mapy i obrazovek hádanek.
- [x] Zobrazovat pomůcky v plovoucím panelu nad aktuální obrazovkou bez ztráty rozeřešeného zadání.
- [x] Přizpůsobit panel mobilu, tabletu i desktopu a umožnit jeho minimalizaci a přesouvání.
- [x] Umožnit současně zobrazit zadání a vybranou tabulku.
- [ ] Připravit pasivní referenční listy minimálně pro Morseovu abecedu, praporovou/semaforovou abecedu, vlajkovou abecedu, malý a velký polský kříž, Braillovo písmo, A1Z26, binární zápis, ASCII a římské číslice.
- [ ] Zvážit pasivní přehled Caesarova posunu a šifrovacího čtverce bez automatického dešifrování.
- [ ] Nepřidávat v první verzi automatické luštění, frekvenční analýzu, OCR ani slovníkové hledání.
- [ ] Označit u každé pomůcky její název, princip čtení, směr a jeden neutrální příklad, který neprozrazuje herní řešení.
- [x] Zajistit plnou funkčnost pomůcek offline bez odkazů na externí web nebo CDN.

#### Režimy zpřístupnění pomůcek
- [ ] Definovat stav každé pomůcky: `skrytá`, `odemčená`, `dočasně zapůjčená` nebo `dostupná za body`.
- [x] Rozhodnout, které základní tabulky budou dostupné od začátku jako standardní výbava výzkumného týmu.
- [x] Navázat tematické pomůcky na bonusové QR checkpointy nebo nalezené moduly stroje času.
- [x] U bonusového checkpointu trvale odemknout pomůcku pro danou herní relaci bez bodové penalizace.
- [x] Nabídnout zamčenou pomůcku na vyžádání za předem zobrazenou bodovou cenu.
- [x] Před odečtením bodů vyžadovat potvrzení hráče a jasně ukázat, zda jde o trvalé nebo dočasné odemčení.
- [x] Za stejné odemčení v jedné relaci strhnout body pouze jednou.
- [x] Rozlišit otevření pasivní tabulky od použití stupňované nápovědy ke konkrétní hádance.
- [x] Zahrnout odemčené pomůcky a zaplacené penalizace do uloženého stavu relace.
- [ ] Zaznamenávat použití pomůcek pro pozdější vyhodnocení obtížnosti hádanek.

#### První navržené vazby na checkpointy
- [x] Po startu zpřístupnit základní Morseovu tabulku jako součást nouzového manuálu komunikátoru.
- [x] Bonusový QR u schodiště může odemknout praporovou/semaforovou tabulku bez penalizace.
- [x] Nalezení `TEMPORÁLNÍHO MOTORU` může odemknout binární a ASCII referenci.
- [x] Nalezení archivního checkpointu odemkne polský kříž.
- [ ] U každé povinné šifry ověřit, že existuje dosažitelná cesta k potřebné pomůcce i při přehlédnutí bonusového QR.

### 13.15 Sólo a týmové lobby
**Cíl:** před začátkem zvolit sólo nebo sdílenou týmovou relaci a synchronizovat průběh mezi telefony.

- [x] Přidat úvodní obrazovku s volbou `SÓLO` a `ZALOŽIT TÝM`.
- [x] U týmové relace zobrazit unikátní připojovací QR, kód, seznam zařízení a aktuální počet hráčů.
- [x] Umožnit zakladateli spustit příběh až po připojení týmu.
- [x] Připojit další zařízení pomocí URL z QR do stejného herního stavu.
- [x] Umožnit reverzní připojení: hráčské zařízení zobrazí vlastní ID/QR a zakladatel ho načte nebo opíše.
- [x] Reverzně přidané zařízení započítat jako regulérního hráče do maxima i bodové úpravy.
- [x] Doporučit, aby jeden hráč používal týmový notebook a každý člen měl právě jedno započítané zařízení.
- [x] Vysílat herní odpovědi a změny stavu všem aktivním zařízením relace.
- [x] Uchovat lobby, připojovací kód, hráče, maximum hráčů a bodovou úpravu při restartu backendu.
- [x] Nastavit úpravu skóre: sólo `+20`, tým 2 hráčů `+10`, 3 hráči `0`, každý další hráč `−30`.
- [x] Počítat maximum registrovaných hráčů, aby odpojením nešlo získat zpět bonus.
- [x] Nezamykat panely ani pevné role; organizaci pozorovatele a navigátora ponechat týmu.
- [x] V každé úrovni Sokobanu evidovat unikátní mluvčí a při střídání zařízení nechat Elaru tým napomenout.
- [x] Přidat příběhové vysvětlení, že Elara je ve tmě a mřížku vidí pouze týmový terminál.
- [ ] Doplnit odolnější obnovu lobby po smazání dat prohlížeče pomocí administrátorského kódu.
- [ ] Přidat možnost dobrovolně změnit přezdívku hráče během čekání.
- [ ] Přidat speech-to-text jako alternativní vstup do stejného deterministického parseru interkomových povelů.
- [ ] Otestovat synchronizaci a souběžné povely na třech a více fyzických telefonech.
