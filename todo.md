# Kompletní checklist projektu "Escape Bot"

## 1. Návrh komunikačního protokolu (Frontend <-> Backend)
- [x] Definice formátu zpráv (JSON přes WebSockets).
- [x] Správa stavu hry a relací (State Machine v Pythonu).

## 2. Šablona pro QML rozhraní (Klientská aplikace)
- [x] Základní layout komunikátoru a interaktivní widgety.
- [ ] Logika pro obsluhu kamery (extrakce snímků) a integrace čtečky QR kódů.

## 3. Webová aplikace a infrastruktura (PWA / WASM)
- [ ] Kompilace C++/Qt frontendu do WebAssembly.
- [ ] Konfigurace PWA (Manifest, Service Workers) pro běh na mobilu ve fullscreenu bez instalace.
- [ ] Zajištění HTTPS a nastavení webového serveru (nutnost pro přístup prohlížeče ke kameře a bezpečné spojení).

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
- [ ] **Klientský framework (Vlastní prohlížeč na míru)**: Pro PC vytvořit speciální prohlížeč/wrapper (např. pomocí Tauri či Electronu), který webovou aplikaci obalí a zajistí komunikaci s lokálním hardwarem, pokud standardní webové cesty nebudou stačit.
- [ ] **Jednoúčelové webovky pro rébusy**: Vytvořit speciální oddělené webové stránky určené výhradně pro vyhrazené počítače/tablety v únikovce, které budou sloužit k řešení specifických dílčích rébusů.
- [ ] **Hardwaroví klienti (Mikrokontroléry)**: Připravit architekturu pro dedikované klienty na mikrokontrolérech (např. ESP32), kteří budou s hrou komunikovat buď napřímo (WebSocket/MQTT), nebo přes zmiňovaný PC framework.

## 10. Backend jako centrální uzel (Orchestrace a Multitasking)
- [ ] **Webserver a orchestrátor**: Backend bude sloužit jako hlavní přístupový bod (webserver pro klientské aplikace) a postará se o orchestraci všech ostatních služeb (AI modely, HW zprávy).
- [ ] **Správa více hráčů (Multiplayer)**: Zajištění synchronizace stavu hry mezi vícero klienty (telefony/tablety/PC) v rámci jedné herní relace.
- [ ] **Multitasking a více instancí (Multitenancy)**: Přepracování správy stavu tak, aby backend dokázal obsluhovat více nezávislých her (místností nebo různých scénářů) naprosto paralelně a bez ovlivňování.
- [ ] **Centrální správa hry (Game Master panel)**: Připravit rozhraní pro obsluhu únikovky, která zde uvidí stav všech běžících her, bude moci posílat nápovědy a řešit krizové situace.
- [ ] **Captive portál (Vstupní bod hry)**: Zprovoznit captive portál (např. úpravou DNS pro přesměrování po připojení na herní Wi-Fi), který automaticky načte klientům webové rozhraní hry.
