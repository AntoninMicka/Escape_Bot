# Eventová platforma – roadmapa

## Cílový model

Event je provozní obálka s termínem, stavem, časovou zónou a brandingem. Obsahuje právě jednu hlavní hru, libovolný počet dalších soutěžních her a doplňkové hry mimo soutěž.

Hlavní a soutěžní hry mohou mít vlastní frontu, kapacitu, interval startů a žebříčky. Doplňkové online nebo 3D hry slouží typicky jako volný program a promo obsah; do pořadí se nezapočítávají, pokud je správce výslovně nepřeklasifikuje.

Oznámení mají tři úrovně dosahu:

1. globální – viditelné na všech nástěnkách,
2. eventová – pouze v aktivním eventu,
3. herní – pouze při zobrazení konkrétní hry.

## Aktuálně realizováno

- jednotný eventový model a zpětná kompatibilita se starším seznamem her,
- role hlavní / soutěžní / doplňková,
- individuální pravidla fronty a žebříčku,
- stavy koncept, připraven, otevřen, pozastaven, ukončen a archivován,
- branding, časová zóna a herně zaměřený odkaz i QR vstupní lobby,
- filtrování fronty, výsledků a oznámení na veřejné nástěnce,
- správa rozsahu oznámení v administraci.

## Další etapy

### 1. Katalog a životní cyklus eventů

Převést jediný aktivní event na katalog. Umožnit klonování konfigurace, archiv pouze pro čtení a bezpečné přepnutí aktivního eventu. Výsledky, fronty a QR identifikátory musí zůstat mezi eventy oddělené.

### 2. Celkové soutěžní pořadí

Nejdřív každá hra musí deklarovat maximální dosažitelné skóre nebo jinou normalizační funkci. Potom lze počítat vážený součet soutěžních her bez zvýhodnění hry s větší bodovou škálou. Chybějící výsledek a nedokončení musejí mít předem definované chování.

### 3. Více nástěnek

Každá fyzická obrazovka dostane profil s výchozí hrou, rozsahem obsahu a rotačním plánem. Jedna může zobrazovat hlavní frontu, jiná doplňkové hry nebo pouze organizační feed.

### 4. Provozní jistota

Před otevřením eventu proběhne preflight kontrola scénářů, časů, kapacit a QR odkazů. Změny se budou auditovat. Správcovské účty, role a více současných správců zůstávají plánovanou samostatnou etapou, nikoli součástí současné implementace.
