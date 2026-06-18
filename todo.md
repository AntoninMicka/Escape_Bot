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
