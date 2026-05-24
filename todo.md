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
- [ ] **Koncept**: Dvě dívky, jedna v naší realitě, druhá ztracená v jiné dimenzi. Cílem je dostat ztracenou dívku zpět pomocí komunikace přes "interkom".
- [ ] **Fáze 1 - Zprovoznění komunikace**: Vyřešit úvodní rébus k fyzickému zprovoznění interkomu, aby bylo vůbec možné zachytit signál.
- [ ] **Fáze 2 - Zaměření dimenze**: Rozluštit a zadat správné speciální "telefonní číslo" nebo dimenzionální souřadnice, čímž dojde ke stabilnímu propojení obou světů.
- [ ] **Fáze 3 - Navigace k portálu**: Řešit navazující hádanky a postupně ztracenou dívku přes interkom přemisťovat a navigovat v její dimenzi až na bezpečné místo, odkud se může vrátit domů.
