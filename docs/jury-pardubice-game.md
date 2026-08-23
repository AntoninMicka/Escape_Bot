# Dvanáct pochybností — Pardubice

Originální detektivní porotní hra používá motiv hledání rozumné pochybnosti. Nejde
o přepis filmu ani o převzetí jeho postav a dialogů. Tým prověřuje rozpory ve
výpovědích, časovou osu, viditelnost svědků, digitální stopu, motiv a manipulaci s
důkazy.

## Společná šablona

`backend/content/templates/jury_deliberation.json` obsahuje příběh, šifry, minihry a
pořadí jedenácti mapových checkpointů. Obě realizace používají stejné kontrakty a
stejné herní mechanismy:

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

Virtuální mapa používá lokální metrickou projekci s počátkem u Zelené brány.
`meters_per_unit` je `1`, takže polohy checkpointů a délky úseků odpovídají reálným
vzdálenostem. První renderer nabízí klávesové ovládání, trasu, hráče a aktivaci
důkazních bodů podle virtuální vzdálenosti.

Aktuální `geometry_status` je `route_mesh_v1`: jde o hratelnou metrickou trasu, ne
ještě o detailní 3D rekonstrukci fasád a interiérů. Další stupeň importuje půdorysy
budov a průchodné cesty z OSM, vytvoří kolizní geometrii a doplní textury. OSM data
musí být při distribuci opatřena atribucí `© OpenStreetMap contributors` a dodržet
licenci ODbL.

## Obnova zdrojových souborů

Datové soubory první verze lze konzistentně znovu vytvořit:

```bash
python3 backend/tools/build_jury_scenarios.py
```
