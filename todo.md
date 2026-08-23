# Kompletní checklist projektu "Escape Bot"

> **Audit aktuálnosti 2026-08-05:** Do dokončení a prvního ostrého ověření Kraskova, plánovaného na konec září 2026, tvoří aktivní roadmapu pouze produkční scénář v oddílu 13. Cloudová migrace, sdílený 3D svět, komerční provoz více her a obecné příběhové šablony v oddílech 14–17 jsou návrhy pro období po Kraskovu a do té doby se neimplementují. Oddíly 8 a 12 jsou pouze historie původního konceptu. QML/WASM byl nahrazen webovou PWA a AI/Ollama není podmínkou herního průchodu.

## Aktuální milník – Kraskov do konce září 2026

**Cíl:** první verzi hry opakovaně projít v reálných podmínkách, odstranit technická a herní třecí místa a připravit ji k bezpečnému provozu. Nové platformní směry z oddílů 14–17 se do tohoto milníku nepřidávají, pokud neřeší konkrétní blokující problém Kraskova.

- [ ] Potvrdit s hotelem finální trasu, povolená stanoviště, startovní/finální místnost, vnitřní variantu pro špatné počasí a cílovou délku hry.
- [ ] Dokončit a zkontrolovat všechny fyzické rekvizity, QR, šifrovací tabulky, organizační mapu, nouzové obálky a instalační checklist.
- [ ] Udělat stolní průchod všech hádanek bez pohybu a zaznamenat čas, chyby zadání, počet nápověd a místa, kde tester neví, co dělat dál.
- [ ] Udělat technický průchod celé trasy v Hotelu Kraskov alespoň s jedním kompletním týmem a bez zásahu autora, pokud nejde o skutečnou provozní závadu.
- [ ] Otestovat tři a více fyzických telefonů, uspání aplikace, reconnect, ztrátu Wi-Fi, opakovaný QR, souběžné povely a obnovu po restartu backendu.
- [ ] Ověřit mobilní čitelnost, hlasitost, titulky, ovládání jednou rukou, venkovní světlo, slabší zařízení a bezpečný návrat z každé obrazovky.
- [ ] Změřit obtížnost a délku jednotlivých etap, upravit nápovědy, časové limity a bodování podle dat, ne pouze podle autorského průchodu.
- [ ] Udělat zátěžový/provozní test více týmů se startovními rozestupy a ověřit, že se nepotkávají u úzkých stanovišť ani si neprozrazují řešení.
- [ ] Projít s Game Masterem administraci, podporu, technický skip, obnovu hráče, diskvalifikaci či ukončení hry a nouzové postupy při výpadku.
- [ ] Před ostrým během uzavřít obsahový freeze; po něm přijímat pouze opravy chyb, bezpečnosti, nejasností a provozních blokátorů.
- [ ] Po prvním ostrém běhu udělat retrospektivu a teprve poté seřadit oddíly 14–17 podle skutečné obchodní a hráčské hodnoty.

### Odložená produktová roadmapa po stabilizaci Kraskova

- [ ] Přidat validátor připravenosti scénáře: chybějící návaznost na další stanoviště, nedostupná média, checkpoint bez pokračování, chybějící řešení a nedosažitelné větve či finále.
- [ ] Zobrazovat verzi klienta v hráčském rozhraní i administraci, evidovat verze připojených zařízení a po vydání nabídnout řízené načtení nové PWA cache.
- [ ] Doplnit volitelné týmové role a sdílené poznámky; zobrazit, kdo právě zadává odpověď nebo ovládá společnou minihru, bez pevného zamykání zařízení.
- [ ] Přidat provozní diagnostiku relace ke stažení, předherní kontrolu QR a médií a auditovaný nouzový skip rozbité fáze.

## 1. Návrh komunikačního protokolu (Frontend <-> Backend)
- [x] Definice formátu zpráv (JSON přes WebSockets).
- [x] Správa stavu hry a relací (State Machine v Pythonu).

## 2. Šablona pro QML rozhraní (Klientská aplikace)
- [x] Základní layout komunikátoru a interaktivní widgety.
- [x] Logika pro obsluhu kamery (extrakce snímků) a integrace čtečky QR kódů (přesunuto na WebRTC/JS).

## 3. Webová aplikace a infrastruktura (PWA / WASM)
- [x] Kompilaci C++/Qt frontendu do WebAssembly vyřadit; aktuální klient je nativní webová PWA bez QML.
- [x] Konfigurace PWA (Manifest, Service Workers) pro běh na mobilu ve fullscreenu bez instalace.
- [ ] Zajištění HTTPS a nastavení webového serveru (nutnost pro přístup prohlížeče ke kameře a bezpečné spojení). **Registrace certifikátu u autority (např. Let's Encrypt)**, protože plně důvěryhodný certifikát je vyžadován i pro lokální běh PWA aplikace v místnosti.

## 4. Dynamické napojení na AI (odloženo)
- [ ] **Odloženo mimo aktuální roadmapu:** zpracování vizuálního vstupu pomocí AI.
- [ ] **Odloženo mimo aktuální roadmapu:** generování volných odpovědí, videa a lip-sync. Produkční průchod musí fungovat deterministicky bez LLM.

## 5. Integrace prvků rozšířené reality (ARG) a rébusů
- [ ] Logika ověřování fyzických objevů v reálném světě.
- [ ] Propojení modulárních virtuálních rébusů s herním dějem.

## 6. Vizuální a zvukové efekty (GL Shadery)
- [x] Atmosférické efekty přes hardwarovou akceleraci (CRT, glitching, odlesky).
- [x] Synchronizace základního offline zvukového designu s interkomem, checkpointy, hádankami, Karlem, Sokobanem, jigsaw puzzle a finále; uživatelská hlasitost a mute.
- [x] Přidat přehrávač klíčových hlasových replik se samostatnou hlasitostí, textovým ekvivalentem, opakováním a lokálním syntetickým fallbackem pro budoucí nahrávky.
- [x] Dokončit ženské hlasové nahrávky Kapitánky a Elary pro všechny klíčové repliky interkomu; zachovat titulky, opakování a syntetický fallback.

## 7. Vizuální editor her (Produkční nástroje)
- [ ] Nodové rozhraní (desktop Qt/C++) pro návrh příběhových větví a stavového automatu.
- [ ] Export scénářů a správa multimediálních assetů.

## 8. Archivní námět: Ztracená v jiné dimenzi (nahrazen oddílem 13)
- [ ] **Koncept**: Hráč se přes interkom spojí s "Kapitánkou" (první postava). Ta mu dá úkol zachránit "Ztracenou" (druhá postava v jiné dimenzi). Hra obsahuje umělé výpadky spojení pro prodloužení a zvýšení napětí.
- [ ] **Fáze 1 - Spojení s Kapitánkou**: Zprovoznění interkomu a navázání komunikace s Kapitánkou. Přijetí úkolu a indicií.
- [ ] **Fáze 2 - Hledání Ztracené**: Pomocí šifer a hádanek najít správnou frekvenci/souřadnice pro spojení s druhou (ztracenou) postavou.
- [ ] **Fáze 3 - Neúspěšné pokusy a výpadky**: Ztracená je nalezena, ale spojení je nestabilní. Záměrné chybné přenosy, ztráta spojení a nutnost jeho opětovného (a složitějšího) navázání.
- [ ] **Fáze 4 - Záchranná mise**: Komunikace se Ztracenou. Pomocí dalších hádanek a šifer ji přemisťovat správným směrem až k záchrannému portálu.

## 9. Zjednodušení architektury (Pivot k webu a hardwaru)
- [x] **Webový interkom (Hlavní klient)**: Hlavní klient je webová PWA.
- [x] **Virtuální záložky pro rébusy (Fallback)**: Rébusy jsou součástí Archivu hádanek v hlavním klientovi.
- [x] **Rozšířený interkom (Kanály)**: Interkom má oddělené kanály systému, Kapitánky a Elary.
- [x] **Interaktivní mapa (Hybridní ARG navigace)**: CHRONOMAPA propojuje postup, lokace a checkpointy.
- [ ] **Klientský framework (Vlastní prohlížeč na míru)**: Pro PC vytvořit speciální prohlížeč/wrapper (např. pomocí Tauri či Electronu), který webovou aplikaci obalí a zajistí komunikaci s lokálním hardwarem, pokud standardní webové cesty nebudou stačit.
- [ ] **Jednoúčelové webovky pro rébusy**: Vytvořit speciální oddělené webové stránky určené výhradně pro vyhrazené počítače/tablety v únikovce, které budou sloužit k řešení specifických dílčích rébusů.
- [ ] **Hardwaroví klienti (Mikrokontroléry)**: Připravit architekturu pro dedikované klienty na mikrokontrolérech (např. ESP32), kteří budou s hrou komunikovat buď napřímo (WebSocket/MQTT), nebo přes zmiňovaný PC framework.
- [x] **Virtuální přístupové panely**: Číselník dveří je deterministicky ověřovaný a začleněný mezi hádanky. Fyzické zámky zůstávají budoucím rozšířením.

## 10. Backend jako centrální uzel (Orchestrace a Multitasking)
- [x] **Webserver a orchestrátor**: FastAPI backend obsluhuje klienta, WebSockety i herní logiku.
- [x] **Perzistence a obnova relací (Wi-Fi stabilita)**: Session tokeny fungují. Stav všech her se automaticky ukládá do `sessions.json` a obnovuje i po tvrdém restartu serveru.
- [x] **Správa více hráčů (Multiplayer)**: Stav týmu se synchronizuje mezi více klienty.
- [x] **Více nezávislých her (Multitenancy v jednom procesu)**: Relace mají oddělené lobby a stav. Horizontální škálování je součástí cloudové etapy.
- [x] **Centrální správa hry (Game Master panel)**: Webový admin spravuje týmy, postup, události a Síň slávy.
- [ ] **Captive portál (Vstupní bod hry)**: Zprovoznit captive portál (např. úpravou DNS pro přesměrování po připojení na herní Wi-Fi), který automaticky načte klientům webové rozhraní hry.

## 11. Herní engine, nápovědy a skórování
- [x] **Oddělení scénáře od enginu**: Přesunout hardcodovanou logiku, fáze a texty z backendu (např. `state_machine.py`) do externích konfiguračních souborů (JSON/YAML scénáře), aby engine zůstal plně univerzální.
- [x] **Deterministické vyhodnocení vstupů**: Povinný průchod, šifry, minihry a nápovědy nevyžadují LLM.
- [x] **Systém tří statických nápověd**: Hádanky mají tlačítka Nápověda 1–3; každý stupeň se platí pouze při prvním odemčení a poté jej lze opakovat zdarma.
- [x] **Bodování a penalizace**: Zaveden výchozí stav bodů (Skóre) pro hru. Za každé uvolnění nápovědy AI systémem se odečte specifikovaný počet negativních bodů.
- [x] **Síň slávy (Leaderboard)**: Na konci scénáře vyhodnotit úspěšnost, zobrazit výsledné skóre, vyzvat hráče k zadání jména týmu a zapsat výsledek do trvalé Síně slávy.

## 12. Archivní inkrementální plán (nahrazen produkčním scénářem v oddílu 13)

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
- [x] Zachovat úvodní spojení s Kapitánkou a nalezení frekvence `734`.
- [x] Upravit roli Elary na věkyni ztracenou v jiné časové vrstvě stejného hotelu.
- [x] Po prvním spojení odhalit, že experiment rozptýlil součásti stroje času po hotelu a okolí.
- [x] Přejmenovat herní mapu na `CHRONOMAPA` a QR checkpointy na `časové kotvy`.
- [x] Definovat pravidla cestování časem, aby byly konzistentní v dialozích i hádankách.
- [x] Napsat časovou osu Elařina experimentu, havárie a návratu.
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
- [ ] Až po potvrzení finálních stanovišť projít návaznosti všech hádanek, checkpointů a příběhových zpráv; aktualizovat odkazy, navigační texty a názvy následujících míst podle skutečné trasy v místě konání.

### 13.3 Checkpoint 0 – Havárie experimentu
**Místo:** startovní konferenční místnost.
- [x] Dokončit hádanku vedoucí k frekvenci `734`.
- [x] Zachovat první výpadek spojení a příkaz `restart`.
- [x] Napsat Elařino odhalení, že se nachází ve stejném hotelu, ale v jiném čase.
- [x] Po restartu odemknout modul `CHRONOMAPA`.
- [x] Zpřístupnit první indicii vedoucí na recepci.

### 13.4 Checkpoint 1 – Recepční archiv
**Typ:** logická dedukční tabulka.
- [x] Navrhnout čtveřici vědců, pokojů, archivních pozic a převážených součástek.
- [x] Sepsat jednoznačné indicie a ověřit jediné správné řešení.
- [x] Získat z tabulky čtyřmístný PIN virtuálního archivu.
- [x] Doplnit samostatnou stopu a stupňované nápovědy pro PIN dveří pokoje 104.
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
- [x] Zakódovat zprávu odkazující na konkrétní hodiny nebo jiný výrazný objekt v hotelu.
- [ ] Ověřit, že bez obou fyzických částí nelze řešení snadno odhadnout.
- [ ] Umístit třetí fyzický díl stroje: `KRYSTAL ČASOVÉ KOTVY`.
- [x] Zpřístupnit vstup do virtuálního archivu budoucnosti.

### 13.9 Checkpoint 6 – Archiv budoucnosti
**Typ:** kombinace fyzické skládačky a klasické šifry.
- [x] Navrhnout tři díly tak, aby po složení vytvořily šifrovací kotouč nebo tabulku.
- [x] Umístit na díly symboly, barvy a části číselné stupnice určující správné pořadí.
- [x] Vybrat finální klasickou šifru, např. Caesarovu nebo Vigenèrovu.
- [ ] Zajistit, aby klíč k šifře vznikl až správným složením fyzických dílů.
- [x] Nechat hráče získat rok, přesný čas a pořadí modulů pro návrat Elary.
- [x] Nahradit digitální řazení tří karet obrázkovým jigsaw puzzle 4×4 se serverovým ověřením a obnovou stavu.

### 13.10 Checkpoint 7 – Finále stroje času
**Místo:** startovní/finální konferenční místnost.
- [ ] Vyrobit základnu, do které lze vložit tři fyzické díly stroje.
- [x] Implementovat zadání roku, času a pořadí modulů do terminálu.
- [x] Před spuštěním ověřit všechny povinné QR checkpointy a inventář.
- [x] Připravit odpočet, zvuk stroje, glitch efekt a zprávu o návratu Elary.
- [ ] Doplnit animaci aktivace stroje času vizuálně odvozenou od sestaveného obrázku z puzzle; navázat ji na odpočet, zapojení modulů a potvrzení Elařina návratu.
- [x] Dokončit výpočet skóre, penalizace za nápovědy a zápis do Síně slávy.

### 13.10.1 Interkomová navigace – Minové pole / Robot Karel
**Cíl:** spojit logické odhalování bezpečných polí ve stylu Min s programováním pohybu postavy ve stylu Robota Karla. Hráči navigují Elaru přes interkom a její polohu sledují na šachovnici.

#### Herní princip
- [x] Příběhově zasadit úkol jako nestabilní časové pole, kterým Elara prochází.
- [x] Navrhnout obdélníkovou herní mřížku s jasně označeným startem a cílem.
- [x] Rozmístit skryté časové anomálie fungující jako miny.
- [x] Na odkrytých polích zobrazovat počet anomálií v sousedních polích.
- [x] Počítat anomálie ve všech osmi okolních polích.
- [x] Zajistit alespoň jednu bezpečnou trasu a její dosažitelnost automaticky validovat.
- [x] Stanovit jako cíl bezpečný přesun Elary ze startu k východu.
- [x] Navázat dokončení úkolu na body a odemčení navazujícího checkpointu.

#### Ovládání ve stylu Robota Karla
- [ ] Definovat základní příkazy `KROK`, `VLEVO`, `VPRAVO` a `ZPET`.
- [x] Použít přímý pohyb pomocí `NAHORU`, `DOLŮ`, `VLEVO`, `VPRAVO` bez orientace postavy.
- [x] Umožnit zadat jeden příkaz nebo celou sekvenci příkazů najednou.
- [ ] Zvažit jednoduché programové konstrukce `OPAKUJ n`, podmínku nebo pojmenovanou sekvenci.
- [ ] Definovat maximální délku programu a způsob jeho potvrzení před spuštěním.
- [ ] Zobrazit náhled naplánované sekvence před jejím vykonáním.
- [ ] Umožnit krokové provedení, pozastavení a bezpečné zrušení nevykonané části sekvence.
- [x] Rozlišit neplatný příkaz, opuštění hranice mapy a vstup na nebezpečné pole.

#### Interkom a odezva Elary
- [x] Přijímat navigační příkazy v kanálu Elary a v týmovém režimu zobrazit šipky pouze v interkomu.
- [x] Vložit úlohu mezi praporovou a binární šifru, aby se v hlavní ose pravidelně střídaly šifry a interaktivní hry.
- [x] Přidat číselné sondy, skryté miny, návrat na start, bodový malus, časový limit a obnovení stavu po reconnectu.
- [x] Připravit tři aktivní úrovně s rostoucí obtížností, body za každou dokončenou mapu a dvě rezervní mapy.
- [x] Zpřesnit rozdělení informací lokálním režimem zařízení `MAPA / INTERKOM / VOLNĚ`; role lze kdykoli měnit, mapové indicie se neposílají v odpovědích interkomu a mapový režim nemá ovládací šipky.
- [x] Rozšířit admin detail o poslední aktivitu, stav checkpointů, zásahy min, restarty, pohyby, nápovědy, pokusy, poslední zprávy a časovou osu událostí.
- [x] Umožnit adminovi obnovit identitu hráče na novém zařízení pomocí návratového QR.
- [x] Vložit časovanou variaci na tři v řadě mezi Morseovu úlohu a Sokoban: pole 6×6, dvě volitelné barvy, tahy blokujícího automatu a splnění dvou ze tří směrů.
- [x] Nepoužívat volné AI vyhodnocení pro samotný pohyb; příkazy parsovat deterministicky.
- [x] Nechat Elaru před pohybem zopakovat pochopenou sekvenci.
- [ ] Volitelně rozšířit souhrnnou reakci po sekvenci na samostatnou reakci po každém kroku; současná verze záměrně nezaplňuje interkom dlouhou dávkou zpráv.
- [x] Při odhalení čísla sdělit počet okolních anomálií i textově kvůli přístupnosti.
- [x] Připravit reakce na slepou cestu, opakované pole, chybný příkaz a blízkost anomálie.
- [x] Při úspěchu spustit příběhovou zprávu a odemknout navazující uzel scénáře.

#### Vizualizace šachovnice
- [ ] Přidat samostatný panel nebo záložku s responzivní šachovnicí.
- [ ] Zobrazit Elaru jako postavu se zřetelnou orientací.
- [ ] Rozlišit skryté, odkryté, navštívené, označené a cílové pole.
- [x] Zobrazit čísla okolních anomálií podobně jako ve hře Miny.
- [x] Animovat pohyb krok po kroku tak, aby hráči viděli, který příkaz se právě provádí.
- [ ] Umožnit na mobilu současně sledovat šachovnici a posloupnost příkazů.
- [ ] Vizuálně odlišit potvrzená bezpečná pole od pouhých hráčských odhadů.
- [x] Připravit alternativní textové zobrazení mřížky pro přístupnost a nouzový provoz.

#### Chyby, penalizace a obnovení
- [x] Při vstupu na anomálii odečíst body a vrátit Elaru na start aktuální mapy.
- [x] Zabránit nevratnému zablokování hry po chybném pohybu pomocí návratu na start a restartu mapy.
- [x] Ukládat aktuální pozici, orientaci, odkrytá pole a historii příkazů do stavu relace.
- [ ] Připravit omezený počet bezpečnostních skenů nebo možnost jejich zakoupení za body.
- [ ] Připravit volitelné nápovědy: upozornění na bezpečné pole, odhalení čísla nebo zobrazení dalšího správného kroku.
- [ ] Umožnit Game Masterovi vrátit postavu na poslední bezpečné pole nebo úkol ručně dokončit.

#### Demo a budoucí admin panel
- [ ] V demo režimu zobrazit celé rozmístění anomálií a správnou bezpečnou trasu.
- [x] Umožnit v demo režimu simulovat příkazy tlačítky bez psaní do interkomu.
- [x] V admin snapshotu zobrazit pozici, odkrytá pole, počet chyb, miny a bezpečnou trasu.
- [x] Umožnit administrátorovi sledovat animaci pohybu aktivního týmu v reálném čase.
- [x] Zaznamenat historii příkazů pro pozdější vyhodnocení obtížnosti.

#### Implementace a testování
- [x] Definovat mapu, start, cíl, anomálie a pravidla v datech scénáře, ne v UI.
- [x] Implementovat deterministický simulátor pohybu nezávislý na WebSocketu a vykreslení.
- [ ] Přidat protokolové zprávy pro naplánování, potvrzení a vykonání příkazů.
- [ ] Ošetřit souběžné povely z více klientů stejného týmu.
- [x] Otestovat hranice mapy, kolize, anomálie, opakování a obnovení uložené relace.
- [x] Automaticky ověřit, že každá navržená mapa má alespoň jednu bezpečnou trasu.
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

### 13.10.5 Redesign samostatné úlohy horizontální–vertikální–diagonální trojice
- [x] Přepracovat původní úlohu doplněním aktivního protihráče a mírnější podmínky dvou ze tří směrů.
- [x] Implementovat deterministického protihráče, který po každém tahu blokuje nejsilnější hrozbu a jinak obsadí strategické pole.
- [ ] Porovnat protihráče s alternativou bez soupeře: omezený počet kamenů, povinné střídání barev, posouvání již položených kamenů nebo měnící se blokovaná pole.
- [x] Zachovat tři sledované směry, vyžadovat dva z nich a zabránit řešení prostým naklikáním předem zřejmých čar.
- [x] Zajistit plně deterministický průběh bez AI a automaticky ověřenou vítěznou sekvenci.
- [ ] Připravit dvě až tři obtížnosti a v demo režimu zobrazit pravidlo protihráče, doporučený postup a možnost okamžitého restartu.
- [ ] Novou variantu implementovat až po výběru pravidel na základě stolního prototypu a krátkého domácího testu.

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
- [x] Připravit Game Masterovi možnost ručně potvrdit nebo přeskočit porouchaný checkpoint.

### 13.12 Hádanky, nápovědy a testování
- [x] Prověřit navigační odkazy mezi všemi checkpointy, doplnit postavám přechodové repliky a automaticky odmítnout scénář, který by přeskočil bezprostředně předchozí stanoviště.
- [x] Přidat automatický smoke průchod celé produkční cesty včetně lobby, obnovy relace, všech hlavních miniher, inventáře, skóre a finále bez GM přeskočení.
- [ ] U každé hádanky napsat zadání, řešení, mezikroky a akceptované varianty odpovědi.
- [x] U všech šifrovacích hádanek připravit tři statické stupně nápověd s jednorázovou penalizací.
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
- [x] Vytvořit samostatnou autentizovanou admin stránku se seznamem všech aktivních relací.
- [x] Přidat do admin stránky detail týmu založený na stejné vizualizaci `scenario.progress`.
- [x] Přidat telemetrii obtížnosti: celkový a aktivní čas hádanek, pokusy, nápovědy, akce, místa ukončení, filtrování období a CSV export.

### 13.14 Šifrovací pomůcky v aplikaci
**Cíl:** nabídnout hráčům pasivní referenční pomůcku inspirovanou způsobem použití aplikace Šifrovací pomůcky Absolutno, aniž aplikace sama vyřeší zadanou hádanku.
- [ ] Ověřit licenci, souhlas autora a možnosti přímého použití názvu, obrazovek nebo obsahu aplikace Absolutno.
- [ ] Bez licence nekopírovat zdrojový kód, grafiku ani konkrétní zpracování; vytvořit vlastní panel ze standardních veřejně známých abeced a šifer.
- [x] Přidat tlačítko `ŠIFROVACÍ POMŮCKY` dostupné z komunikátoru, mapy i obrazovek hádanek.
- [x] Zobrazovat pomůcky v plovoucím panelu nad aktuální obrazovkou bez ztráty rozeřešeného zadání.
- [x] Přizpůsobit panel mobilu, tabletu i desktopu a umožnit jeho minimalizaci a přesouvání.
- [x] Umožnit současně zobrazit zadání a vybranou tabulku.
- [x] Připravit pasivní referenční listy minimálně pro Morseovu abecedu, praporovou/semaforovou abecedu, vlajkovou abecedu, malý a velký polský kříž, Braillovo písmo, A1Z26, binární zápis, ASCII a římské číslice.
- [x] Zvážit pasivní přehled Caesarova posunu a šifrovacího čtverce bez automatického dešifrování.
- [x] Nepřidávat v první verzi automatické luštění, frekvenční analýzu, OCR ani slovníkové hledání.
- [x] Označit u každé pomůcky její název, princip čtení, směr a jeden neutrální příklad, který neprozrazuje herní řešení.
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
- [x] U každé povinné šifry ověřit, že existuje dosažitelná cesta k potřebné pomůcce i při přehlédnutí bonusového QR.

### 13.15 Sólo a týmové lobby
**Cíl:** před začátkem zvolit sólo nebo sdílenou týmovou relaci a synchronizovat průběh mezi telefony.

- [x] Přidat úvodní obrazovku s volbou `SÓLO` a `ZALOŽIT TÝM`.
- [x] U týmové relace zobrazit unikátní připojovací QR, kód, seznam zařízení a aktuální počet hráčů.
- [x] Umožnit zakladateli spustit příběh až po připojení týmu.
- [x] Připojit další zařízení pomocí URL z QR do stejného herního stavu.
- [x] Přidat v úvodní lobby explicitní volbu `PŘIPOJIT SE K TÝMU` s kamerovým načtením leaderova QR i ručním zadáním týmového kódu.
- [x] Umožnit reverzní připojení: hráčské zařízení zobrazí vlastní ID/QR a zakladatel ho načte nebo opíše.
- [x] Reverzně přidané zařízení započítat jako regulérního hráče do maxima i bodové úpravy.
- [x] Doporučit, aby jeden hráč používal týmový notebook a každý člen měl právě jedno započítané zařízení.
- [x] Vysílat herní odpovědi a změny stavu všem aktivním zařízením relace.
- [x] Uchovat lobby, připojovací kód, hráče, maximum hráčů a bodovou úpravu při restartu backendu.
- [x] Vyžadovat název týmu a jména všech hráčů, blokovat neúplné spuštění a kontrolovat unikátnost názvu týmu bez ohledu na velikost písmen a mezery.
- [x] Zachovat týmový režim při uspání nebo krátkém odpojení telefonu; rozlišovat registrované hráče od právě online zařízení.
- [x] Po probuzení či opětovném připojení zařízení obnovit kompletní historii, herní stav, postup scénářem a demo katalog; detekovat i zdánlivě otevřený mrtvý WebSocket.
- [x] V týmovém Sokobanu oddělit mapu od ovládání: šipky skrýt u mřížky a zobrazit je pouze v interkomu v kanálu Elary; sólo demo ponechat samostatně ovladatelné.
- [x] Nastavit úpravu skóre: sólo `+20`, tým 2 hráčů `+10`, 3 hráči `0`, každý další hráč `−30`.
- [x] Počítat maximum registrovaných hráčů, aby odpojením nešlo získat zpět bonus.
- [x] Nezamykat panely ani pevné role; organizaci pozorovatele a navigátora ponechat týmu.
- [x] V každé úrovni Sokobanu evidovat unikátní mluvčí a při střídání zařízení nechat Elaru tým napomenout.
- [x] Přidat příběhové vysvětlení, že Elara je ve tmě a mřížku vidí pouze týmový terminál.
- [ ] Doplnit odolnější obnovu lobby po smazání dat prohlížeče pomocí administrátorského kódu.
- [ ] Přidat možnost dobrovolně změnit přezdívku hráče během čekání.
- [ ] Přidat speech-to-text jako alternativní vstup do stejného deterministického parseru interkomových povelů.
- [ ] Otestovat synchronizaci a souběžné povely na třech a více fyzických telefonech.

### 13.16 Administrační dohled

- [x] Přidat heslem chráněný administrační režim se seznamem týmů, hráčů, online stavem, skóre a postupem scénářem.
- [x] Umožnit správci udělit bodový malus s povinným důvodem a zapsat jej do historie relace.
- [x] Umožnit po potvrzení odstranit tým, jeho uložený herní stav a ukončit aktivní připojení.
- [x] Doplnit filtrování týmů a detailní časovou osu administrátorských i herních událostí.
- [x] Generovat v admin režimu tiskovou A4 sadu startovního a checkpointových QR přímo z aktuálního scénářového datasetu.
- [x] Přidat globální přepínač fyzického/online režimu; v online režimu nahradit QR checkpointy akčními body v Chronomapě a nastavení uchovat po restartu.
- [x] Přidat týmový kanál podpory s perzistentní historií a trvale dostupnou odpovědí Game Mastera.
- [x] Oddělit trvale dostupné týmové chaty od dočasného read-only náhledu celé hry v hráčském rozhraní.
- [x] Rozdělit administrační záhlaví na Týmy, Chaty, Síň slávy a Nástroje.
- [x] Upozorňovat přihlášené administrátory na nové týmové zprávy badge počítadlem a obrazovkovou notifikací.
- [x] Aktualizovat podpůrné chaty samostatným WebSocket push přenosem a polling omezit pouze na právě otevřený přehled týmů.
- [x] Zobrazit v admin detailu správná řešení a serverem řízené předvolby postihů pro ruční dokončení či technický skip bez postihu.

### 13.17 Globální start, deadline a společné vyhodnocení
**Cíl:** umožnit registraci a sestavení týmů před prezentací, ale zpřístupnit samotnou hru všem až ručním povelem pořadatele nebo v předem nastavený čas. Stejným způsobem musí jít hru společně ukončit a uzavřít výsledky.

#### Stav globálního herního okna
- [ ] Zavést serverem řízené stavy `REGISTRACE`, `HRA_POVOLENA` a `HRA_UKONČENA` nezávislé na fázi jednotlivých týmů.
- [ ] Ve stavu `REGISTRACE` povolit vytvoření týmu, připojování hráčů, změny sestavy a čekárnu, ale nepovolit spuštění ani žádnou herní akci.
- [ ] Ve stavu `HRA_POVOLENA` povolit týmům zahájit nebo pokračovat ve hře podle jejich vlastního uloženého postupu.
- [ ] Ve stavu `HRA_UKONČENA` odmítat nové herní tahy, odpovědi, QR checkpointy a placené nápovědy; zachovat pouze prohlížení konečného stavu, výsledků a podpory.
- [ ] Globální stav, plánované časy a administrátorské změny ukládat perzistentně a obnovit je po restartu serveru.

#### Startovní čára
- [ ] Umožnit administrátorovi nastavit volitelný čas automatického startu `start_at` včetně časové zóny a srozumitelného lokálního zobrazení.
- [ ] Umožnit ruční povel `SPUSTIT HRU NYNÍ`, který okamžitě přepne čekající týmy do stavu `HRA_POVOLENA` bez čekání na `start_at`.
- [ ] Umožnit naplánovaný start změnit nebo zrušit, dokud hra nebyla spuštěna.
- [ ] V čekárně zobrazit stav „Registrace dokončena, čekáme na společný start“ a případně živý odpočet k `start_at`.
- [ ] Rozeslat změnu globálního stavu přes WebSocket všem připojeným lobby a herním klientům bez nutnosti obnovení stránky.
- [ ] Zabránit obejití startu přímým WebSocket/HTTP požadavkem; oprávnění kontrolovat autoritativně na backendu u všech herních akcí.

#### Deadline a ukončení
- [ ] Umožnit administrátorovi nastavit volitelný automatický konec `end_at` včetně časové zóny.
- [ ] Umožnit ruční povel `UKONČIT VŠECHNY HRY NYNÍ` s potvrzením a náhledem počtu aktivních týmů.
- [ ] Umožnit automatický konec před jeho dosažením odložit o zadaný počet minut, přesunout na konkrétní čas nebo úplně zrušit.
- [ ] Po automatickém či ručním konci atomicky uzavřít všechny dosud nedokončené relace se společným časem ukončení a důvodem `deadline` nebo `admin`.
- [ ] Před koncem zobrazit týmům serverem řízená varování, například 15, 5 a 1 minutu před deadline; po odložení přepočítat další upozornění.
- [ ] Rozlišit dokončení příběhu týmem od administrativního ukončení v čase, aby Síň slávy a vyhodnocení neoznačovaly nedokončenou hru jako úspěšně dohranou.

#### Vyhodnocení a správa výjimek
- [ ] Po uzavření her vytvořit neměnný výsledkový snapshot každého týmu: skóre, dosažený checkpoint, dokončení, počet nápověd, čas startu a čas ukončení.
- [ ] V administraci zobrazit společnou výsledkovou tabulku i nedokončené týmy a umožnit export do CSV.
- [ ] Určit pořadí výsledků: primárně dokončení příběhu, následně skóre a jako další kritérium čas dokončení; pravidlo viditelně uvést před startem.
- [ ] Evidovat audit každého nastavení, spuštění, odložení, zrušení deadline a ručního ukončení včetně administrátora a času.
- [ ] Připravit nouzovou výjimku pro konkrétní tým pouze jako explicitní administrátorský zásah; výchozí globální start a konec musí platit pro všechny stejně.
- [ ] Otestovat registraci před startem, souběžný automatický start, ruční předčasný start, odložení a zrušení konce, restart serveru před časem T a souběh deadline s právě zpracovávaným tahem.

#### Diskvalifikace týmu
- [ ] Zavést konečný stav týmu `DISKVALIFIKOVÁN`, který okamžitě ukončí jeho rozehranou hru a zablokuje všechny další herní akce, QR checkpointy, odpovědi a nápovědy.
- [ ] V administraci přidat akci `DISKVALIFIKOVAT TÝM` s povinným textovým důvodem, výrazným potvrzením a zobrazením dopadu před provedením.
- [ ] Diskvalifikovaný tým neodstraňovat; zachovat jeho lobby, hráče, kompletní herní stav, historii zpráv, postup, události a administrátorský audit.
- [ ] Při diskvalifikaci vytvořit výsledkový snapshot s časem, dosaženým checkpointem, důvodem a administrátorem, ale bez bodového ohodnocení.
- [ ] V Síně slávy zobrazit diskvalifikované týmy až za všemi řádně klasifikovanými týmy bez ohledu na jejich původní skóre; místo skóre uvést `DSQ`.
- [ ] Při více diskvalifikovaných týmech zachovat stabilní pořadí podle času diskvalifikace nebo registračního času a pravidlo uvést ve výsledcích.
- [ ] V běžném hráčském rozhraní zobrazit ukončení hry a neutrální informaci o diskvalifikaci; podrobný interní důvod zpřístupnit pouze administrátorům, pokud pořadatel nezvolí jeho zveřejnění.
- [ ] Oddělit diskvalifikaci od existujícího odstranění týmu: diskvalifikace je soutěžní výsledek se zachovanými záznamy, odstranění je pouze technická operace pro chybně založenou nebo testovací relaci.
- [ ] Umožnit zrušení chybné diskvalifikace pouze zvláštní administrátorskou akcí s povinným důvodem; obnovený tým se vrátí do hry jen tehdy, pokud globální herní okno stále dovoluje hraní.
- [ ] Otestovat diskvalifikaci čekajícího, aktivního i dokončeného týmu, souběžný tah během zásahu, pořadí v Síně slávy, restart serveru a případné administrátorské obnovení.

#### Indikativní detekce duplicitní registrace hráče nebo zařízení
- [ ] Při první návštěvě vytvořit náhodný identifikátor zařízení a uchovat jej v bezpečné cookie a/nebo `localStorage`; neposuzovat duplicitu pouze podle jména hráče nebo IP adresy.
- [ ] Při registraci porovnat identifikátor zařízení s aktivními a dřívějšími registracemi v jiných týmech a případnou shodu označit jako varovnou indicii pro Game Mastera.
- [ ] Shodu stejného zařízení ve více týmech nikdy automaticky neblokovat ani nepoužít k automatické diskvalifikaci; běžným legitimním případem může být sdílený rodinný notebook nebo tablet.
- [ ] V administraci zobrazit upozornění `MOŽNÁ DUPLICITA ZAŘÍZENÍ`, dotčené týmy, hráče, časy registrací a sílu signálu bez tvrzení, že došlo k podvodu.
- [ ] Umožnit Game Masterovi označit shodu jako `PROVĚŘIT`, `POTVRZENÁ DUPLICITA` nebo `LEGITIMNĚ SDÍLENÉ ZAŘÍZENÍ`; rozhodnutí a poznámku uložit do auditu.
- [ ] Po označení zařízení jako legitimně sdíleného potlačit opakované výstrahy pro stejnou kombinaci týmů, ale zachovat původní záznam.
- [ ] Volitelný otisk prohlížeče používat pouze jako doplňkový slabý signál při smazané cookie; sestavit jej z minimálního množství stabilních údajů a na server ukládat pouze osolený hash, ne surové parametry prohlížeče.
- [ ] Nepoužívat agresivní fingerprinting založený na canvasu, zvuku, fontových seznamech nebo jiných technikách, které nejsou pro provoz hry nezbytné.
- [ ] Definovat dobu uchování identifikátorů a fingerprintových hashů, po skončení akce je automaticky odstranit nebo anonymizovat a popsat jejich použití v informaci pro účastníky.
- [ ] Počítat s tím, že inkognito režim, jiný prohlížeč, smazaná data nebo více profilů detekci obejdou; funkci prezentovat pouze jako pomoc při dohledu, nikoli jako důkaz identity osoby.
- [ ] Otestovat stejné zařízení ve dvou týmech, více hráčů na jednom tabletu, smazání cookies, anonymní režim, obnovení identity a falešnou shodu doplňkového fingerprintu.

## 14. Migrace na cloud (odloženo po Kraskovu, nejdříve říjen 2026)

- [ ] Zmrazit deterministický produkční průchod bez povinné závislosti na Ollamě nebo ComfyUI.
- [ ] Kontejnerizovat FastAPI aplikaci a statický PWA klient; doplnit produkční ASGI konfiguraci.
- [ ] Nahradit soubory `sessions.json`, `lobbies.json`, `leaderboard.json` a `runtime_settings.json` transakční databází PostgreSQL.
- [ ] Zavést databázové migrace, zálohování, obnovu a retenční pravidla dokončených relací.
- [ ] Přesunout tajné hodnoty do cloudového secret manageru a vynutit silný admin token.
- [ ] Nasadit staging s HTTPS/WSS, health checky, strukturovanými logy a monitoringem chyb.
- [ ] První produkční verzi provozovat jako jedinou instanci; pro horizontální škálování doplnit Redis pub/sub, distribuované zámky a sdílenou evidenci WebSocketů.
- [ ] Otestovat reconnect, více týmů, souběžné povely, restart instance a obnovu databáze.
- [ ] Připravit DNS, reverzní proxy, bezpečnostní hlavičky, rate limiting a plán rollbacku.
- [ ] Provést zkušební migraci kopií lokálních dat, ověřit počty relací a Síň slávy a teprve potom přepnout produkční DNS.

## 15. Volitelný modul „Doomovka“ – sdílený alternativní svět (odloženo po Kraskovu)

**Vize:** hráči vstoupí z komunikátoru do stylizovaného prostoru vykresleného přímo v prohlížeči, vidí avatary ostatních členů týmu, společně se pohybují a aktivují úkoly. První verze má ověřit zábavu, ovládání a synchronizaci na běžných telefonech; nemá nahrazovat hlavní scénář ani z něj dělat akční střílečku. Do budoucna může stejný modul představovat jinou časovou vrstvu hotelu nebo samostatný alternativní svět.

### 15.1 Hranice modulu a technický prototyp

- [ ] Sepsat krátký design prototypu: příběhový vstup, cílová délka 5–10 minut, počet hráčů, jeden společný úkol a podmínka návratu do komunikátoru.
- [ ] Implementovat modul jako samostatnou obrazovku PWA načítanou pouze po odemčení scénářem; zachovat běžný interkom, mapu i fyzickou trasu beze změny.
- [ ] Zvolit styl první verze: jednoduchý 2.5D raycasting ve stylu raných FPS, nebo nízkopolygonové WebGL 3D. Předběžně preferovat WebGL 3D s lokálně uloženou knihovnou a bez CDN, pokud test na cílových telefonech potvrdí stabilní výkon.
- [ ] Vykreslovat svět kompletně na zařízení hráče; neposílat obraz ze serveru ani mezi hráči.
- [ ] Připravit jednu malou testovací mapu se starty, stěnami, dveřmi, jedním interaktivním objektem a návratovým portálem.
- [ ] Definovat rozpočty pro cílové zařízení: velikost assetů, počet trojúhelníků a světel, maximální počet avatarů a minimální stabilní snímkovou frekvenci.
- [ ] Přidat detekci nepodporovaného nebo pomalého zařízení a bezpečný 2D/mapový fallback, aby modul nikdy nezablokoval hlavní herní průchod.

### 15.2 Pohyb a ovládání v prohlížeči

- [ ] Přidat ovládání klávesnicí a myší na notebooku: `WASD`, otáčení myší, interakce a opuštění modulu.
- [ ] Přidat mobilní dotykové ovládání se dvěma zónami nebo virtuálními joysticky, velkým tlačítkem interakce a podporou orientace na šířku.
- [ ] Pointer Lock a pohybové senzory používat pouze po výslovném gestu hráče; hra musí zůstat ovladatelná bez gyroskopu.
- [ ] Přidat nastavení citlivosti, omezení rychlosti otáčení, redukci pohybu, vypnutí houpání kamery a režim s většími ovládacími prvky.
- [ ] Zabránit pádu mimo mapu, průchodu stěnou a uváznutí; nabídnout bezpečný návrat na poslední kontrolní bod.
- [ ] Pozastavit renderovací smyčku na skryté kartě a po návratu načíst autoritativní stav ze serveru.

### 15.3 Multiplayer – hráči se navzájem vidí

- [ ] Rozšířit identitu existující týmové relace o `player_id`, zobrazované jméno, barvu a jednoduchý avatar; nepřidávat druhé paralelní lobby.
- [ ] Definovat oddělené zprávy `world.join`, `world.input`, `world.snapshot`, `world.event`, `world.interact` a `world.leave` s verzí protokolu a `request_id` pro idempotentní interakce.
- [ ] Nechat server autoritativně řídit místnost, pozice, rychlost, kolize, interakce a stav úkolů. Klient posílá vstupy, nikoli důvěryhodnou výslednou pozici.
- [ ] Pro první lokální test rozesílat snapshoty přibližně 10–15× za sekundu a na klientovi použít interpolaci ostatních avatarů a krátkou predikci vlastního pohybu; hodnoty upravit podle měření.
- [ ] Při odpojení ponechat avatar krátce neaktivní, po reconnectu obnovit stejnou identitu a pozici a po delší prodlevě jej bezpečně odstranit ze světa.
- [ ] Zobrazit jméno, barvu, směr pohledu a jednoduchou animaci pohybu spoluhráče; nepřenášet kameru, video ani biometrická data.
- [ ] Omezit první verzi na členy stejného týmu a jednu instanci mapy na relaci; mezitýmové setkávání řešit až po cloudové migraci, moderaci a kapacitních testech.
- [ ] Přidat serverové limity frekvence zpráv, validaci čísel a hranic mapy a odmítnutí vstupů od hráče, který do světa nevstoupil.

### 15.4 První kooperativní vertikální řez

- [ ] Navrhnout úkol, který skutečně využije více hráčů, například současné držení dvou spínačů, navigaci podle rozdělených indicií nebo přenos energie přes několik stanovišť.
- [ ] Umožnit sólo průchod pomocí přepínání stanovišť, časové pojistky nebo pomocného hologramu; hlavní scénář nesmí být bez týmu nedohratelný.
- [ ] Ukládat stav dveří, spínačů, sebraných předmětů a dokončených cílů do autoritativního stavu relace.
- [ ] Napojit vstup do světa i jeho dokončení na scénářová data, inventář, skóre a události stejným způsobem jako současné minihry.
- [ ] Nechat komunikátor během modulu zobrazovat krátké cíle a textový přepis důležitých zvukových nebo prostorových indicií.
- [ ] Přidat Game Masterovi read-only 2D půdorys s pozicemi hráčů, stavem úkolu a možností bezpečně vrátit hráče na checkpoint nebo modul technicky přeskočit.

### 15.5 Datový formát map a tvorba obsahu

- [ ] Oddělit mapu od enginu do verzovaného balíčku: geometrie, spawn pointy, kolizní vrstvy, interaktivní entity, cíle, texty a odkazy na lokální assety.
- [ ] Pro první prototyp použít ručně udržovaný JSON a validaci při startu backendu; editor nezačínat dříve, než se ustálí datový formát na alespoň dvou mapách.
- [ ] U 3D varianty standardizovat assety na glTF/GLB, komprimované textury a předem vypočítané nebo velmi jednoduché osvětlení.
- [ ] Každému interaktivnímu objektu přidělit stabilní ID a jeho stav ukládat nezávisle na vizuálním modelu.
- [ ] Po ověření dvou map navrhnout jednoduchý webový editor spawnů, kolizí, dveří, spínačů a vazeb úkolů; export musí být čitelný a verzovatelný se scénářem.
- [ ] Připravit kontrolu chyb mapy: chybějící asset, spawn ve stěně, nedosažitelný cíl, duplicitní ID a chybějící návratová cesta.

### 15.6 Zvuk, komunikace a atmosféra

- [ ] Přidat prostorový zvuk jen pro atmosféru a herní indicie, vždy s titulkem nebo vizuálním ekvivalentem.
- [ ] V první verzi ponechat týmovou komunikaci mimo modul osobně nebo přes existující textový interkom; hlasový chat není podmínkou prototypu.
- [ ] WebRTC hlas zvažovat až pro vzdálené hráče a až po vyřešení oprávnění mikrofonu, signalizace, NAT/TURN, moderace a ochrany soukromí.
- [ ] Zachovat jednotný vizuální jazyk CRT/glitch efektů, ale omezit efekty, které zhoršují orientaci nebo mohou vyvolávat nevolnost.

### 15.7 Testovací brány a rozhodnutí o dalším rozvoji

- [ ] Brána A – sólo prototyp: na cílovém telefonu se lze pohybovat, interagovat a vrátit do hlavní hry bez ztráty stavu.
- [ ] Brána B – dva hráči v lokální Wi-Fi: navzájem se vidí, dokončí společný úkol a přežijí uspání či reconnect jednoho zařízení.
- [ ] Brána C – plný tým a slabší zařízení: změřit FPS, latenci vstupu, objem přenosu, spotřebu baterie, zahřívání a chování při ztrátě paketů.
- [ ] Provést krátký uživatelský test zaměřený na orientaci, nevolnost, dotykové ovládání, pochopení společného cíle a přínos oproti 2D minihře.
- [ ] Modul zapnout do produkčního scénáře až tehdy, když má bezpečný fallback, obnovu relace, administrátorský skip a neprodlužuje čekání ostatních týmů.
- [ ] Po vertikálním řezu rozhodnout mezi třemi směry: jednorázová 3D minihra, sada scénářových místností, nebo trvalejší alternativní svět. Teprve poslední varianta vyžaduje zónování, více serverových instancí, databázi světa, moderaci a provozní monitoring.

## 16. Provoz více her, rezervace a platební brána (odloženo po Kraskovu)

**Výchozí stav:** backend již drží více nezávislých týmových relací v `active_sessions`, ale všechny vznikají nad jedním scénářem načteným při startu procesu. Pro komerční provoz je proto nutné oddělit titul hry, konkrétní verzi scénáře, herní termín a týmovou relaci. Platba má vytvářet oprávnění ke vstupu, nikdy přímo měnit rozehraný herní stav.

### 16.1 Doménový model více her

- [ ] Zavést stabilní entity `game` (nabízený titul), `scenario_version` (neměnná publikovaná verze obsahu), `venue` (místo), `slot` (termín/kapacita), `booking` (rezervace) a `session` (rozehraná týmová relace).
- [ ] Přidat do každé relace povinné `game_id`, `scenario_version_id`, `venue_id` a volitelné `booking_id`; po spuštění hry nesmí aktualizace katalogu změnit její scénář.
- [ ] Načítat více validovaných scénářových balíčků současně a zakládat stavový automat z verze vybrané pro konkrétní termín, nikoli z jednoho globálního `scenario.json`.
- [ ] Oddělit assety, leaderboard, provozní nastavení a administrační oprávnění podle hry a místa; podporu a globální dohled ponechat dostupné centrálnímu správci.
- [ ] Zavést životní cyklus scénáře `draft`, `published`, `retired`; rozehrané relace musí umět dokončit i vyřazenou verzi.
- [ ] Připravit katalog her s názvem, popisem, délkou, doporučeným počtem hráčů, jazykem, věkovým omezením, dostupností a vazbou na publikovanou verzi scénáře.
- [ ] Zajistit, aby URL nebo vstupní QR jednoznačně určily hru a případně termín, ale neobsahovaly citlivé údaje rezervace.

### 16.2 Ověření souběžného provozu

- [ ] Doplnit integrační test, který současně založí několik týmů ve dvou různých hrách, provede v nich odlišné akce a ověří úplnou izolaci stavu, chatu, skóre, inventáře a leaderboardu.
- [ ] Otestovat dva termíny stejné hry nad různými verzemi scénáře a potvrdit, že publikace nové verze neovlivní již vytvořený ani rozehraný termín.
- [ ] Otestovat souběžné WebSocket broadcasty, reconnect, restart backendu, administrátorský dohled a ukončení jedné hry bez dopadu na ostatní.
- [ ] Definovat kapacitu termínu počtem týmů, hráčů a případně fyzických zdrojů; zabránit překročení kapacity transakčně, ne pouze kontrolou v klientovi.
- [ ] Vytvořit zátěžový profil pro běžný provoz a 3D modul: počet současných relací, zařízení na tým, zprávy za sekundu, paměť na relaci a cílová latence.
- [ ] Před horizontálním škálováním ověřit maximum jedné instance; poté test zopakovat s PostgreSQL, Redis pub/sub, distribuovanými zámky a více ASGI workery/instancemi.
- [ ] Zajistit per-game health metriky a upozornění: aktivní týmy, chybovost, latence zpráv, reconnecty, obsazenost termínů a nedokončené platby.

### 16.3 Termíny a rezervace

- [ ] Umožnit správci vypsat termíny s místem, začátkem, délkou, kapacitou, cenou, měnou a stavem `draft`, `open`, `sold_out`, `closed` nebo `cancelled`.
- [ ] Při zahájení objednávky vytvořit krátkodobou rezervaci kapacity s expirací; po úspěšné platbě ji potvrdit, po vypršení nebo neúspěchu kapacitu automaticky uvolnit.
- [ ] Zabránit dvojímu prodeji posledního místa databázovou transakcí nebo zámkem a unikátním omezením, nikoli pořadím HTTP požadavků.
- [ ] Podporovat jednorázový bezpečný vstupní token nebo QR navázaný na potvrzenou rezervaci; jeho použití vytvoří či otevře správnou lobby.
- [ ] Umožnit ruční rezervaci, nulovou cenu, promo kód a administrátorské pozvání bez obcházení stejné evidence kapacity a auditu.
- [ ] Posílat potvrzení rezervace odděleně od herních zpráv a nabídnout bezpečné znovuzobrazení vstupního odkazu bez ukládání citlivých platebních dat.
- [ ] Definovat pravidla změny termínu, storna, nedostavení se a zrušení akce provozovatelem ještě před implementací automatických refundací.

### 16.4 Integrace platební brány

- [ ] Vytvořit interní rozhraní poskytovatele plateb, aby šlo nasadit jednu bránu a později ji vyměnit nebo doplnit bez změn rezervací a herního enginu.
- [ ] Pro první verzi použít hostovanou platební stránku poskytovatele; čísla karet ani bezpečnostní kódy nikdy nepřijímat a neukládat v Escape Botu.
- [ ] Evidovat vlastní `order_id`, očekávanou částku, měnu a stav platby; identifikátor transakce poskytovatele ukládat odděleně a s unikátním omezením.
- [ ] Považovat platbu za potvrzenou pouze podle serverově ověřeného webhooku nebo následného serverového dotazu na API brány; návratová stránka v prohlížeči není důkaz zaplacení.
- [ ] Ověřovat podpis webhooku nad nezměněným tělem požadavku, kontrolovat částku, měnu a příjemce a zpracovávat opakované či opožděné události idempotentně.
- [ ] Navrhnout stavový automat platby minimálně `created`, `pending`, `paid`, `failed`, `expired`, `cancelled`, `partially_refunded`, `refunded` a uchovávat audit každého přechodu.
- [ ] Udržet webhook rychlý a odolný: událost bezpečně uložit, potvrdit přijetí a navazující e-mail, rezervaci či refundaci zpracovat opakovatelnou úlohou.
- [ ] Tajné klíče držet pouze na serveru v secret manageru, oddělit testovací a produkční prostředí a pravidelně rotovat webhooková tajemství.
- [ ] Výběr konkrétní brány provést až podle cílových zemí, měn, firemního subjektu, poplatků, podporovaných metod, refundací, účetnictví a kvality sandboxu/API.

### 16.5 Aktivace hry po zaplacení

- [ ] Po potvrzení platby vytvořit samostatné `entitlement` opravňující k určité hře/termínu; tím oddělit účetní událost od technického vstupu do hry.
- [ ] Uplatnění oprávnění provést atomicky a idempotentně, aby obnovení stránky ani opakovaný webhook nevytvořily více lobby nebo nevyčerpaly další kapacitu.
- [ ] Umožnit kupujícímu předat pozvánku zakladateli týmu bez zpřístupnění historie platby či osobních údajů ostatním hráčům.
- [ ] Při refundaci definovat, zda se pouze zruší budoucí oprávnění, nebo se ukončí již aktivovaná relace; rozehranou hru nikdy nevypínat automaticky bez explicitního provozního pravidla.
- [ ] Připravit administrátorský přehled vazby objednávka → platba → rezervace → oprávnění → herní relace s auditovanou ruční opravou chybného spárování.

### 16.6 Bezpečnost, soukromí a provoz

- [ ] Minimalizovat osobní údaje; oddělit kontaktní údaje kupujícího od přezdívek hráčů a určit retenční lhůty objednávek, herní telemetrie a technických logů.
- [ ] Nezapisovat tokeny, celé webhooky s osobními údaji ani platební návratové URL do běžných aplikačních logů; citlivá pole redigovat.
- [ ] Doplnit obchodní podmínky, informace o zpracování osobních údajů, storno/refundační pravidla a souhlasy podle skutečného provozovatele a cílového trhu.
- [ ] Vyřešit číslování objednávek a dokladů, DPH, účetní export a případné napojení na fakturační systém odděleně od platební brány.
- [ ] Přidat denní kontrolu nesouladů: zaplaceno bez rezervace, rezervace bez oprávnění, částka nebo měna nesouhlasí, refundace se nepropsala a webhook se opakovaně nezdařil.
- [ ] Připravit provozní postup pro výpadek brány: rezervace s časovým limitem, ruční ověření v administraci poskytovatele a auditované ruční vydání oprávnění.

### 16.7 Doporučené pořadí realizace

- [ ] Etapa A – více her bez plateb: katalog, verzované scénáře, termíny a integrační test izolace.
- [ ] Etapa B – rezervace bez peněz: kapacitní zámek, expirace, vstupní QR a ruční potvrzení administrátorem.
- [ ] Etapa C – sandbox platební brány: hostovaný checkout, podepsané webhooky, idempotence a testovací refundace.
- [ ] Etapa D – omezený produkční pilot jedné hry a několika termínů se souběžnou ruční kontrolou každé platby.
- [ ] Etapa E – více her a míst, automatizované refundace, účetní export a horizontální škálování až podle naměřené zátěže.

## 17. Obecné příběhy a konkrétní realizace v různých lokalitách (odloženo po Kraskovu)

**Cíl:** jeden příběh navrhnout pouze jednou a provozovat jej v několika městech, budovách, venkovních trasách nebo virtuálních světech. Obecný scénář určuje děj, role stanovišť, pravidla, návaznosti a výukové cíle. Konkrétní realizace určuje skutečná či virtuální místa, lokální navigaci, rekvizity, assety, bezpečnostní omezení a případné náhradní úkoly.

### 17.1 Vrstvy obsahu a jejich odpovědnosti

- [ ] Zavést vrstvu `story_template`: obecný příběh, postavy, kapitoly, abstraktní uzly, podmínky postupu, odměny, povinné schopnosti hráčů a význam jednotlivých úkolů v ději.
- [ ] Zavést vrstvu `realization`: konkrétní výběr a konfigurace uzlů pro určité město, objekt, akci nebo virtuální svět.
- [ ] Zavést vrstvu `deployment`: provozní nasazení realizace na konkrétní termín a místo, včetně aktivních QR tokenů, dostupných tras, počasí, kapacity a lokálních nastavení.
- [ ] Ponechat `session` jako rozehraný a neměnný snapshot konkrétního deploymentu; pozdější změna šablony ani realizace nesmí změnit běžící hru.
- [ ] Nepoužívat volné přepisování libovolných JSON polí. Každá vrstva musí mít vlastní explicitní schéma a jasně definovaná místa rozšíření.

### 17.2 Abstraktní role míst a úkolů

- [ ] Popisovat příběhová stanoviště rolí a požadovanými vlastnostmi místo konkrétního názvu, například `START_BASE`, `PUBLIC_ARCHIVE`, `VERTICAL_TRANSITION`, `SOCIAL_AREA`, `OUTDOOR_LANDMARK` a `FINAL_BASE`.
- [ ] U každé role určit povinné schopnosti: fyzická přítomnost, GPS, QR, kamera, zvuk, tma, schody, obsluha Game Masterem, více zařízení nebo vstup do 3D světa.
- [ ] Oddělit logický cíl úkolu od jeho prezentace. Například „získat čtyřmístný kód dedukcí“ může mít hotelovou, městskou, muzejní nebo virtuální grafiku a texty.
- [ ] Umožnit realizaci vybrat z několika kompatibilních variant úkolu, pokud konkrétní lokalita nepodporuje původní mechanismus.
- [ ] Definovat povinné příběhové informace, které musí každá varianta hráči předat, aby náhradní úkol nezpůsobil mezeru v ději.
- [ ] Rozlišit uzly `required`, `optional`, `bonus` a `fallback`; validátor musí potvrdit alespoň jednu průchodnou cestu od startu do finále.

### 17.3 Typy realizací

- [ ] Podporovat `physical_indoor`: budova nebo areál s QR, rekvizitami a lokální navigací.
- [ ] Podporovat `physical_outdoor`: městská či přírodní trasa s GPS/geofencingem, veřejnými orientačními body a nouzovou variantou při uzavírce nebo špatném počasí.
- [ ] Podporovat `virtual`: kompletní průchod přes webové obrazovky, 2D mapy nebo sdílený 3D svět bez fyzických checkpointů.
- [ ] Podporovat `hybrid`: část postupu v reálné lokalitě a část ve virtuálním světě, se společným stavem relace a inventářem.
- [ ] Umožnit jedné realizaci nabídnout více tras nebo režimů dostupnosti, například bezbariérovou, zkrácenou, deštivou a vzdálenou variantu.

### 17.4 Mapování do měst a konkrétních míst

- [ ] Vytvořit kartu lokace s názvem pro hráče, interním ID, souřadnicemi nebo virtuální mapou, přístupností, otevírací dobou, kapacitou, riziky a kontaktem provozovatele.
- [ ] Mapovat každou abstraktní roli scénáře na konkrétní lokaci a uvést lokální navigační text, checkpoint, rekvizitu, variantu úkolu a nouzovou náhradu.
- [ ] Nepoužívat jako povinnou stopu nestabilní detail veřejného prostoru bez záložní varianty; u soch, výloh, nápisů a podniků evidovat datum posledního ověření.
- [ ] U městských realizací zabránit vedení hráčů do soukromých, nebezpečných, dopravně exponovaných nebo časově nedostupných prostor.
- [ ] Počítat s více týmy na trase: určit kapacitu stanovišť, rozestupy startů, alternativní pořadí nezávislých uzlů a prevenci prozrazení řešení mezi týmy.
- [ ] Uchovávat organizační mapu s přesnými checkpointy odděleně od hráčské mapy, která nesmí předem prozrazovat trasu ani řešení.

### 17.5 Lokalizace jazyka a kulturní adaptace

- [ ] Oddělit všechny zobrazované texty, dialogy, titulky, nápovědy a názvy assetů od logiky do lokalizačních klíčů.
- [ ] Rozlišit jazykový překlad od lokální adaptace příběhu; jiné město může vyžadovat změnu reálií, ale nesmí svévolně porušit pravidla obecného příběhu.
- [ ] U slovních šifer deklarovat jazykovou závislost a pro každý podporovaný jazyk vyžadovat samostatně ověřenou variantu řešení a nápověd.
- [ ] Přidat fallback jazyka a validaci chybějících překladů; publikaci realizace zablokovat, pokud chybí povinný text nebo přístupnostní alternativa.

### 17.6 Balíčky assetů a konfigurace

- [ ] Rozdělit assety na společné příběhové, lokální a provozní; sdílené soubory neduplikovat do každé realizace.
- [ ] Používat stabilní logická ID assetů a manifest s hashem, typem, velikostí, licencí a offline dostupností.
- [ ] Umožnit realizaci nahradit pouze povolené prezentační assety, například mapu, fotografie, hlasové varianty a modely prostředí, bez změny serverové logiky.
- [ ] Při publikaci sestavit neměnný balíček obsahující přesné verze šablony, realizace, překladů, assetů a datového schématu.
- [ ] PWA musí před startem ověřit dostupnost povinných assetů pro danou realizaci a nabídnout řízený fallback místo částečně načtené hry.

### 17.7 Validace a automatické testování realizací

- [ ] Vytvořit validátor kompatibility `story_template` × `realization`: obsazené povinné role, podporované schopnosti, úplnost textů, existující assety a dosažitelnost finále.
- [ ] Generovat automatický deterministický smoke průchod pro každou publikovanou realizaci včetně všech zvolených variant a fallbackových tras.
- [ ] Ověřit, že žádný lokální QR, GPS bod, PIN, odpověď nebo asset nemůže omylem změnit jinou realizaci stejného příběhu.
- [ ] Přidat maticový test: jeden příběh ve dvou fyzických městech, jedné virtuální realizaci a jednom hybridu běží současně bez sdílení stavu.
- [ ] Před publikací fyzické realizace vyžadovat technický průchod na místě a datum schválení; po stanovené době nebo významné změně lokality ji označit k opětovnému ověření.
- [ ] Zobrazit v administraci přesnou provenienci relace: příběh, verzi šablony, realizaci, deployment, jazyk a všechny aktivní fallbacky.

### 17.8 Nástroj pro tvorbu nové realizace

- [ ] První dvě realizace vytvořit ručně v datových souborech, aby se ověřil model a odhalilo, co je skutečně společné a co lokální.
- [ ] Poté připravit průvodce: výběr příběhu → typ realizace → přiřazení rolí míst → varianty úkolů → navigace → assety → bezpečnost → test → publikace.
- [ ] U každého kroku zobrazit chybějící povinné prvky, kompatibilní varianty a náhled hráčské i organizační mapy.
- [ ] Umožnit realizaci klonovat pro další město, ale po klonování vyžadovat nové ověření všech lokací, navigace, QR tokenů, práv k assetům a bezpečnostních údajů.
- [ ] Zavést role `autor příběhu`, `editor realizace`, `lokální provozovatel`, `tester` a `schvalovatel`; publikace musí být auditovaná a oddělená od běžné editace.

### 17.9 Doporučený referenční experiment

- [ ] Nejprve vytáhnout z existujícího Kraskova obecnou šablonu `Ztracená v čase` bez názvů hotelových míst a konkrétních rekvizit.
- [ ] Zachovat současný Hotel Kraskov jako první fyzickou realizaci a porovnat její průchod se stávajícím smoke testem bez funkční změny.
- [ ] Vytvořit druhou malou virtuální realizaci stejného příběhu, ve které jsou fyzické role nahrazené 2D/3D místnostmi a digitálními checkpointy.
- [ ] Vytvořit papírový návrh realizace pro druhé město a ověřit, zda lze všechny obecné role obsadit bez změny společné dějové logiky.
- [ ] Teprve po těchto třech variantách zmrazit první verzi schématu a začít stavět editor realizací.

## 18. Lokační varianta hry s GPS a mapou (odloženo po Kraskovu)

**Cíl:** umožnit venkovní nebo městskou variantu, v níž se úkol zpřístupní až po skutečném příchodu týmu do určené oblasti. Hráčská mapa má podporovat orientaci a zobrazovat postup, ale nesmí předčasně odhalit celou trasu ani řešení. Tato varianta je samostatná vůči sdílenému 3D světu z oddílu 15 a může využít obecné realizace z oddílu 17.

### 18.1 Datový model lokačních checkpointů

- [ ] Doplnit ke checkpointu souřadnice, poloměr geofence, tolerovanou přesnost GPS, hráčský název, navigační text a volitelný mapový symbol.
- [ ] Rozlišit stav `hidden`, `revealed`, `approaching`, `available`, `completed` a `unavailable`; poloha smí odemknout pouze uzel, jehož příběhové podmínky už byly splněny.
- [ ] Podporovat bod, kruhovou oblast i volitelný polygon pro rozsáhlejší stanoviště.
- [ ] U každého lokačního uzlu definovat QR nebo administrátorský fallback pro zařízení bez GPS, slabý signál či dočasně nepřístupné místo.
- [ ] Uložit okamžik prvního příchodu, použitou přesnost, způsob ověření a případný zásah Game Mastera do auditní časové osy.

### 18.2 Hráčská mapa založená na OpenStreetMap

- [ ] Přidat mapový panel s podklady OpenStreetMap prostřednictvím zvoleného poskytovatele dlaždic nebo vlastního tile serveru; před produkcí ověřit licenci, atribuci, limity a možnost offline použití.
- [ ] Zobrazit aktuální polohu hráče, kruh přesnosti a stav dostupnosti lokalizační služby.
- [ ] Zobrazovat pouze checkpointy, které má hráč podle scénáře znát; budoucí skrytá stanoviště neposílat klientovi ani je pouze neschovávat pomocí CSS.
- [ ] Vizuálně rozlišit aktivní checkpoint, dostupné vedlejší úkoly, splněná stanoviště a dočasně nedostupné body.
- [ ] Po výběru aktivního bodu zobrazit vzdálenost, směr a bezpečný textový navigační pokyn; nepoužívat automaticky přímou trasu přes nepřístupný terén.
- [ ] Umožnit mapu vystředit na hráče, na aktivní úkol nebo na dosud odhalenou trasu a zachovat čitelnost na telefonu i na přímém slunci.

### 18.3 Ověření polohy a odemykání úkolů

- [ ] Sledovat polohu pouze během aktivní hry a pouze po výslovném udělení oprávnění prohlížeči.
- [ ] Odemknout checkpoint až po získání měření s přijatelnou přesností uvnitř geofence; jediné nepřesné měření nesmí samo potvrdit příchod.
- [ ] Zavést krátkou stabilizační podmínku, například dvě až tři vyhovující měření nebo setrvání v oblasti po stanovenou dobu.
- [ ] Provádět autoritativní kontrolu odemčení na backendu a neposílat klientovi tajná řešení ani skryté souřadnice před jejich odhalením.
- [ ] Zpracovat návrat do aplikace, uspání telefonu, změnu oprávnění, ztrátu signálu a přechod mezi Wi-Fi a mobilními daty bez dvojího odemčení.
- [ ] Neodemykat další úkol pouhým ručním posunem značky v mapě; případnou ochranu proti falešné poloze kombinovat s QR, časovou posloupností nebo fyzickou indicií podle rizika hry.

### 18.4 Soukromí, bezpečnost a offline provoz

- [ ] Neukládat průběžnou GPS stopu, pokud ji hra nepotřebuje; standardně uchovat pouze auditované příchody k checkpointům a nezbytnou diagnostiku přesnosti.
- [ ] Informovat hráče, kdy a proč se poloha používá, jak dlouho se data uchovávají a jak lze pokračovat bez udělení trvalého přístupu.
- [ ] Připravit nouzovou mapu a základní navigační data pro slabý mobilní signál; před startem ověřit dostupnost potřebných mapových podkladů a assetů.
- [ ] Zakázat vedení trasy přes silnice bez přechodu, soukromé pozemky, uzavřené areály a další nebezpečné nebo časově omezené oblasti.
- [ ] U každé venkovní realizace evidovat datum fyzické kontroly trasy, rizika, otevírací dobu a náhradní variantu pro počasí či uzavírku.

### 18.5 Administrace a testování

- [ ] V administraci zobrazit mapu týmů, jejich poslední známý stav polohy, aktivní checkpoint a důvod, proč se další úkol neodemkl; přesnou polohu zobrazovat pouze po dobu aktivní relace.
- [ ] Umožnit Game Masterovi auditovaně potvrdit příchod, změnit aktivní checkpoint nebo přepnout tým na nelokační fallback.
- [ ] Přidat simulátor polohy do demo režimu, aby šel celý scénář testovat bez fyzického obcházení trasy.
- [ ] Otestovat přesnost v zástavbě, pod stromy, uvnitř budov, na různých telefonech a při vypnutém přesném určování polohy.
- [ ] Otestovat překrývající se geofence, příchod ke stanovištím v nesprávném pořadí, více zařízení jednoho týmu a souběžný příchod více týmů.

### 18.6 Doporučený první vertikální řez

- [ ] Vytvořit malou trasu se třemi checkpointy: start, jeden povinný mezikrok a cíl.
- [ ] Zobrazit na mapě pouze aktuálně známý bod, hráčovu polohu, přesnost a vzdálenost.
- [ ] Odemknout každý krok kombinací geofence a QR fallbacku a propsat výsledek do společného scénářového postupu.
- [ ] Projít trasu alespoň na třech fyzických telefonech a teprve podle naměřené přesnosti stanovit výchozí poloměry geofence.
- [ ] Po ověření vertikálního řezu rozhodnout, zda přidat navigační trasu, offline dlaždice, bonusové body a paralelní větve checkpointů.
