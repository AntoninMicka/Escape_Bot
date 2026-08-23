# Šablony a konkrétní provedení her

Scénář se od verze schématu 1 skládá ze dvou zdrojů:

- `story_template` popisuje přenositelný příběhový kontrakt, povinné uzly a sdílené herní nástroje;
- `realization` váže kontrakty na konkrétní stanoviště, schopnosti a kompletní runtime daného místa.

První dvojici tvoří `backend/content/templates/lost_in_time.json` a
`backend/content/realizations/hotel_kraskov.json`. Server ji skládá při startu. Původní
`backend/scenario.json` zatím zůstává jako kompatibilní referenční soubor a test hlídá,
že zkompilovaný výsledek je přesně shodný.

## Pravidla formátu

Oba dokumenty mají `schema_version`, `kind`, stabilní `id`, sémantickou `version` a
objekt `runtime`. Realizace navíc přesně odkazuje na ID a verzi šablony.

Každý `node_contract` musí mít právě jednu položku v `node_bindings`. Vazba určuje
existující `runtime_node_id`, odpovídající typ uzlu a deklaruje všechny požadované
schopnosti. Překryv stejně pojmenovaných částí `runtime` je odmítnut, aby nebylo
nejasné, která vrstva data vlastní. Změna kontraktu proto vyžaduje novou verzi
šablony a vědomou aktualizaci realizace.

## Kontrola a kompilace

Výsledek lze vypsat bez změny zdrojových souborů:

```bash
PYTHONPATH=backend python3 -m escape_bot.scenario_composer \
  backend/content/templates/lost_in_time.json \
  backend/content/realizations/hotel_kraskov.json
```

Volba `--output cesta.json` výsledek uloží. Server podporuje výběr jiné dvojice přes
`ESCAPEBOT_SCENARIO_TEMPLATE` a `ESCAPEBOT_SCENARIO_REALIZATION`. V produkci se vždy
ověří úplnost vazeb, schopnosti a návaznost checkpointů ještě před spuštěním hry.

Toto je základ pro editor: ten bude upravovat zdrojové vrstvy, zobrazovat jejich
původ a před publikací spustí stejnou validaci. Doom a geo/mapový mód budou nové
realizace a schopnosti nad tímto společným kontraktem, nikoli podmínky vložené do
jednoho monolitického scénáře.
