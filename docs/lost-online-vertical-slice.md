# Ztracená online – první vertikální řez

## Cíl

Ověřit během 5–10 minut skutečné webové 3D, orientaci v autorském prostoru a
jednu příběhovou interakci. Řez není zmenšená hotová hra; musí bezpečně skončit
návratem do komunikátoru a nesmí blokovat stávající scénář.

## Průchod

1. Hráč vstoupí na recepci Ústavu CHRONOS a uvidí uzamčený výtah.
2. Na recepčním terminálu obnoví napájení výtahu.
3. Výtah jej přesune do podzemní chronální laboratoře.
4. V laboratoři aktivuje první stopu Elary: poškozený nouzový záznam.
5. Záznam otevře návratový portál a hráč se vrátí do komunikátoru.

## Rozsah první implementace

- skutečná perspektivní WebGL scéna s hloubkou, světly a objekty;
- recepce a jedna laboratoř jako dvě oddělené zóny;
- klávesnice, myš a základní dotykové ovládání;
- kolize s hranicemi místností a interakce v dosahu;
- stabilní ID objektů `reception_terminal`, `lab_elevator`, `elara_log` a
  `return_portal`;
- lokální stav řezu a bezpečné opuštění modulu;
- původní canvasový Ústav zůstává dostupným fallbackem.

## Mimo rozsah

- finální modely a textury, fyzika, inventář a ukládání pozice;
- synchronizace avatarů a serverově autoritativní pohyb;
- hlasový chat, editor map a další podlaží;
- přepis produkčního scénáře Hotelu Kraskov.

## Akceptační brána

- modul se načte bez CDN a lze jej kdykoliv opustit;
- průchod funguje na klávesnici i dotykem;
- hráč nemůže projít obvodovou stěnou ani se přesunout výtahem před aktivací;
- skrytá karta zastaví vstupy a po návratu pokračuje bez ztráty lokálního stavu;
- na nepodporovaném zařízení zůstane přístupný původní 2D/raycast fallback.

