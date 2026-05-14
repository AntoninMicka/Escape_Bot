# Kompletní Checklist Projektu "Escape Bot"

## 1. Návrh Komunikačního Protokolu

- [x] Definovat JSON zprávy přes WebSocket.
- [x] Připravit datové typy zpráv v Pythonu.
- [x] Připravit základní state machine v Pythonu.
- [ ] Doplnit autentizaci/session token pro produkční build.
- [ ] Přidat replay log pro ladění průchodu hrou.

## 2. QML Rozhraní A Nativní Klient

- [x] Připravit základní layout komunikátoru.
- [x] Připravit C++ bridge pro kameru a QR události.
- [ ] Napojit reálné dekódování QR kódů.
- [ ] Doplnit lokální cache médií a videí.
- [ ] Přidat packaging profil pro Linux/Windows.

## 3. Dynamické Napojení Na AI

- [x] Připravit adaptér pro Ollama.
- [x] Připravit adaptér pro ComfyUI.
- [ ] Napojit vizuální analýzu snímků z lokace.
- [ ] Navrhnout prompt kontrakty pro textové odpovědi.
- [ ] Vybrat pipeline pro lip-syncing videí.

## 4. ARG Prvky

- [x] Založit strukturu pro ověřování fyzických objevů.
- [ ] Definovat první sadu QR/fyzických stop.
- [ ] Přidat pravidla pro virtuální a hardwarové rébusy.
- [ ] Přidat audit, aby AI sama neodemkla stav bez verifikace.

## 5. Vizuální A Zvukové Efekty

- [x] Připravit CRT shader.
- [x] Připravit glitch shader.
- [ ] Doplnit audio cue systém.
- [ ] Propojit efekty se stavy hry.
- [ ] Přidat nastavení intenzity efektů pro přístupnost.

