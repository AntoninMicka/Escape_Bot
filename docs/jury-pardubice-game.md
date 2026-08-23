# Dvanáct pochybností — Pardubice

Originální detektivní porotní hra používá motiv hledání rozumné pochybnosti. Nejde
o přepis filmu ani o převzetí jeho postav a dialogů. Tým prověřuje rozpory ve
výpovědích, časovou osu, viditelnost svědků, digitální stopu, motiv a manipulaci s
důkazy.

## Společná šablona

`backend/content/templates/jury_deliberation.json` obsahuje příběh, šifry, minihry a
pořadí jedenácti mapových checkpointů. Obě realizace používají stejné kontrakty a
stejné herní mechanismy:

Klasické šifry jsou během návrhu označené jako vývojové placeholdery. Neobsahují
obrázky, zadání ani řešení převzatá ze scénáře Ztracena v čase; testovací průchod
jimi používá odpověď `PLACEHOLDER`. Interaktivní minihry zatím zůstávají zapojené
pro ověření celého herního toku.

- `pardubice_jury_geo.json` — fyzický okruh od Zelené brány přes historické centrum,
  zámecké okolí a Automatické mlýny;
- `pardubice_jury_doom.json` — online virtuální okruh nad stejnými souřadnicemi.

## GEO režim

Každý checkpoint má WGS‑84 polohu, pořadí a aktivační poloměr 24 metrů. Zařízení musí
dodat polohu s přesností nejvýše 35 metrů. Vzdálenost i pořadí ověřuje server;
odeslané souřadnice proto nejsou pouze klientská simulace. QR fallback zůstává v
datovém modelu povolený pro místa se slabým GNSS signálem.

Web zobrazuje vloženou OSM mapu a po výslovném stisku tlačítka začne sledovat polohu.
Používá se `Permissions-Policy: geolocation=(self)` a prohlížeč stále vyžádá souhlas
uživatele.

## Doom režim

Klient vykresluje metrickou OSM geometrii z pohledu první osoby. Budovy tvoří
perspektivní stěny a kolizní obálku hráče, aktivní checkpointy mají prostorové
značky a orientaci doplňuje lokální minimapa. Pohyb je relativní ke směru pohledu;
checkpoint se aktivuje až po fyzickém přiblížení ve virtuálním prostoru, nikoli
tlačítkem v seznamu online checkpointů.

Virtuální mapa používá lokální metrickou projekci s počátkem u Zelené brány.
`meters_per_unit` je `1`, takže polohy checkpointů a délky úseků odpovídají reálným
vzdálenostem. První renderer nabízí klávesové ovládání, trasu, hráče a aktivaci
důkazních bodů podle virtuální vzdálenosti.

Aktuální `geometry_status` je `osm_geometry_v2`. Lokální výřez obsahuje 350 půdorysů
budov, 563 komunikací a parkové či vodní plochy. Budovy tvoří kolizní vrstvu,
komunikace zachovávají typ, šířku a povrch a výška budov se bere z OSM nebo odhaduje
z počtu podlaží. Renderer používá procedurální barvy a povrchy pro zdivo, dlažbu,
asfalt, park a vodu. Neobsahuje cizí fotografie ani jejich autorská práva.

Jde stále o venkovní herní model, nikoli fotorealistický digitální dvojník fasád a
interiérů. OSM data jsou při distribuci opatřena atribucí `© OpenStreetMap
contributors` a licencí ODbL.

## Obnova zdrojových souborů

Datové soubory první verze lze konzistentně znovu vytvořit:

```bash
python3 backend/tools/build_jury_scenarios.py
python3 backend/tools/build_osm_geometry.py
```

Zdrojový Overpass export je uložen v `backend/content/maps/pardubice_center.osm.json`;
odvozená kompaktní geometrie v `pardubice_center.geometry.json`. Server ji poskytuje
přes `/api/world-geometry/pardubice_center` s hodinovou cache.
