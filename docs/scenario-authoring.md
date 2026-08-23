# Šablony a konkrétní provedení her

Scénář se od verze schématu 1 skládá ze dvou zdrojů:

- `story_template` vlastní příběh, šifry, herní objekty, pravidla postupu a kontrakty uzlů;
- `realization` obsahuje pouze konkrétní hodnoty místa: názvy, ID a tokeny checkpointů,
  čísla místností a další lokální obsah.

První dvojici tvoří `backend/content/templates/lost_in_time.json` a
`backend/content/realizations/hotel_kraskov.json`. Server ji skládá při startu. Původní
`backend/scenario.json` zatím zůstává jako kompatibilní referenční soubor a test hlídá,
že zkompilovaný výsledek je přesně shodný.

## Pravidla formátu

Oba dokumenty mají `schema_version`, `kind`, stabilní `id` a sémantickou `version`.
Šablona obsahuje `runtime`, `variable_schema`, kontrakty a jejich vazby. Realizace
přesně odkazuje na ID a verzi šablony a dodává objekt `variables`.

Každý `node_contract` musí mít v šabloně právě jednu položku v `node_bindings`.
Po dosazení proměnných musí vazba ukazovat na existující uzel správného typu a mít
všechny požadované schopnosti. Změna kontraktu vyžaduje novou verzi šablony a
vědomou aktualizaci realizace.

## Proměnné

Šablona deklaruje očekávané proměnné pomocí tečkovaných cest:

```json
"variable_schema": {
  "location.name": {"type": "string"},
  "checkpoints.public_archive.id": {"type": "string"},
  "map.initial_view": {"type": "object", "required": false}
}
```

Podporované typy jsou `string`, `number`, `boolean`, `object`, `array` a `any`.
`required` je ve výchozím stavu zapnuté.

Řetězcová interpolace funguje v hodnotách i klíčích JSON. Díky dynamickému klíči se
přejmenování checkpointu propíše do mapy checkpointů i všech návazností:

```json
"${checkpoints.public_archive.id}": {
  "label": "${checkpoints.public_archive.name}"
}
```

Celou hodnotu libovolného typu, například mapový objekt, checkpoint nebo seznam,
lze vložit beze změny konstrukcí:

```json
"initial_view": {"$var": "map.initial_view"}
```

Chybějící proměnná, špatný typ, objekt vložený doprostřed textu nebo kolize dvou
dynamických klíčů zastaví kompilaci před spuštěním serveru.

## Kontrola a kompilace

Výsledek lze vypsat bez změny zdrojových souborů:

```bash
PYTHONPATH=backend python3 -m escape_bot.scenario_composer \
  backend/content/templates/lost_in_time.json \
  backend/content/realizations/hotel_kraskov.json
```

Volba `--output cesta.json` výsledek uloží. Server podporuje výběr jiné dvojice přes
adresáře `ESCAPEBOT_TEMPLATE_DIR` a `ESCAPEBOT_REALIZATION_DIR` a výchozí realizaci
`ESCAPEBOT_SCENARIO_ID`. V produkci se vždy ověří úplnost vazeb, schopnosti a
návaznost checkpointů ještě před zpřístupněním hry.

## Katalog a odolnost serveru

Server načítá každou realizaci samostatně. Chyba JSON, chybějící šablona, neplatná
proměnná nebo porušená trasa vyřadí pouze dotčenou realizaci. Ostatní hry i
administrace zůstanou dostupné. Pokud není platná žádná hra, server nastartuje v
servisním režimu a odmítne pouze pokus o zahájení herní relace.

Každá realizace deklaruje podporované `modes`. Lobby je rozděluje do tří nezávislých
větví:

- `online_doom` pro čistě online hry;
- `on_site_qr` pro hry na místě s QR checkpointy;
- `geo` pro OSM/GEO/GNSS hry odemykané polohou.

Jedna větev může nabídnout více realizací, včetně více her ve stejné lokalitě.
Konkrétní `scenario_id` i typ lobby se ukládají do relace a zachovají se po restartu.

## První verze editoru

Administrace obsahuje kartu **Editor her**. Z katalogu načte zdrojovou šablonu a
realizaci, umožní je upravit jako JSON a spustí stejnou serverovou validaci jako při
startu. V této fázi editor záměrně nezapisuje na disk; slouží k bezpečné přípravě a
ověření datového modelu před doplněním verzovaného publikování.

Toto je základ pro editor: šablonový editor bude upravovat herní logiku a deklarace
proměnných, zatímco editor realizace nabídne formulář vygenerovaný z
`variable_schema`. Doom může vzniknout jako jiná herní šablona; geo/mapová varianta
může sdílet příběhovou šablonu a dodat polohy, mapový objekt a checkpointy pomocí
proměnných.
