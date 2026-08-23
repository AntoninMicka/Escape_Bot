"""Build the shared jury story and its Pardubice GEO/Doom realizations."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any


BACKEND = Path(__file__).resolve().parents[1]
SOURCE_TEMPLATE = BACKEND / "content" / "templates" / "lost_in_time.json"
SOURCE_REALIZATION = BACKEND / "content" / "realizations" / "hotel_kraskov.json"
OUTPUT_TEMPLATE = BACKEND / "content" / "templates" / "jury_deliberation.json"
OUTPUT_GEO = BACKEND / "content" / "realizations" / "pardubice_jury_geo.json"
OUTPUT_DOOM = BACKEND / "content" / "realizations" / "pardubice_jury_doom.json"


POINTS = {
    "public_archive": ("Zelená brána", 50.0379962, 15.7779363),
    "signal_transition": ("Pernštýnské náměstí", 50.0383643, 15.7790772),
    "hazard_navigation": ("Příhrádek", 50.0391760, 15.7793180),
    "machine_part_one": ("Zámecké valy", 50.0398569, 15.7771889),
    "timeline_calibration": ("Tyršovy sady", 50.0425081, 15.7748017),
    "machine_part_two": ("Lávka přes Chrudimku", 50.0410820, 15.7801250),
    "alignment_game": ("Automatické mlýny", 50.0416769, 15.7815900),
    "spatial_archive": ("Komenského náměstí", 50.0392300, 15.7810500),
    "machine_part_three": ("Bělobranské náměstí", 50.0401150, 15.7830350),
    "return_archive": ("Wernerovo nábřeží", 50.0387900, 15.7822600),
    "final_console": ("Pernštýnské náměstí – radnice", 50.0384200, 15.7793100),
}


# These story beats intentionally have no production puzzle yet. Keeping a
# visible, solvable placeholder makes the GEO/Doom route testable without
# silently shipping ciphers and artwork copied from Lost in Time.
PLACEHOLDER_CIPHERS = {
    "reception_deduction": ("Rozpory ve výpovědích", "Budoucí dedukční úloha nad výpověďmi porotců a časovou osou případu."),
    "staircase_semaphore": ("Viditelnost svědka", "Budoucí obrazová šifra ověřující, co mohl klíčový svědek skutečně vidět."),
    "bowling_binary": ("Digitální stopa telefonu", "Budoucí datová šifra nad časovými údaji z telefonu a vysílačů."),
    "terrace_morse": ("Zvuk kroků v noci", "Budoucí zvuková nebo rytmická šifra porovnávající svědecké výpovědi."),
    "sports_pigpen": ("Zašifrovaná poznámka", "Budoucí samostatná šifra založená na poznámce nalezené ve spise."),
    "future_archive_cipher": ("Sestavení alternativní verze", "Budoucí závěrečná šifra, která spojí rozpory do alternativní verze událostí."),
}


def placeholder_cipher(puzzle: dict[str, Any], title: str, brief: str) -> dict[str, Any]:
    """Replace inherited cipher content while preserving its route binding."""
    return {
        "title": title,
        "type": "placeholder",
        "development_status": "placeholder",
        "checkpoint_id": puzzle["checkpoint_id"],
        "instructions": (
            f"{brief}\n\nToto stanoviště zatím používá vývojový placeholder. "
            "Pro otestování průchodu zadejte PLACEHOLDER."
        ),
        "answer": "PLACEHOLDER",
        "admin_solution": "PLACEHOLDER – dočasný průchod; finální šifra ještě není navržena.",
        "success_message": {
            "text": "Vývojový placeholder splněn. Stanoviště bude před vydáním nahrazeno původní šifrou.",
            "mood": "focused",
            "channel": "captain",
        },
        "failure_message": {
            "text": "Jde o vývojový placeholder. Pro pokračování zadejte PLACEHOLDER.",
            "mood": "error",
            "channel": "general",
        },
        "hints": [],
    }


def rewrite_story(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: rewrite_story(child) for key, child in value.items()}
    if isinstance(value, list):
        return [rewrite_story(child) for child in value]
    if not isinstance(value, str):
        return value
    replacements = (
        ("doktorka Elara", "porotkyně Nora"), ("Doktorka Elara", "Porotkyně Nora"),
        ("Elara", "Nora"), ("časové vrstvy", "vzájemně rozporné výpovědi"),
        ("časová vrstva", "verze případu"), ("časové kotvy", "důkazní body"),
        ("časovou kotvu", "důkazní bod"), ("Časová kotva", "Důkazní bod"),
        ("časová kotva", "důkazní bod"), ("časový proud", "řetězec důkazů"),
        ("stroj času", "rekonstrukce případu"), ("stroje času", "rekonstrukce případu"),
        ("Temporální motor", "ČASOVÁ OSA"), ("Fázový stabilizátor", "MOTIV"),
        ("Krystal časové kotvy", "ROZHODUJÍCÍ SVĚDECTVÍ"),
        ("CHRONOMAPA", "MAPA DŮKAZŮ"), ("Chronomapa", "Mapa důkazů"),
        ("chronální", "forenzní"), ("temporální", "důkazní"), ("časových", "důkazních"),
    )
    for source, target in replacements:
        value = value.replace(source, target)
    return value


def local_xy(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    north = math.radians(lat - origin_lat) * 6_371_000
    east = math.radians(lon - origin_lon) * 6_371_000 * math.cos(math.radians(origin_lat))
    return round(east, 2), round(north, 2)


def checkpoint_values(prefix: str) -> dict[str, Any]:
    values = {}
    for contract, (name, lat, lon) in POINTS.items():
        node_id = f"jury_{contract}"
        values[contract] = {
            "id": node_id,
            "name": name,
            "route_name": name,
            "token": hashlib.sha256(f"{prefix}:{contract}".encode()).hexdigest()[:32],
        }
    return values


def world(mode: str) -> dict[str, Any]:
    origin_lat, origin_lon = POINTS["public_archive"][1:]
    checkpoints = []
    route = []
    for order, (contract, (name, lat, lon)) in enumerate(POINTS.items(), 1):
        x, y = local_xy(lat, lon, origin_lat, origin_lon)
        checkpoints.append({
            "contract": contract, "node_id": f"jury_{contract}", "name": name, "lat": lat, "lon": lon,
            "radius_m": 24, "order": order, "x_m": x, "y_m": y, "z_m": 0,
        })
        route.append([x, y])
    common = {
        "mode": mode,
        "location_id": "pardubice_center",
        "coordinate_system": "WGS84",
        "center": {"lat": 50.03965, "lon": 15.77955, "zoom": 16},
        "bounds": {"south": 50.03755, "west": 15.77390, "north": 50.04300, "east": 15.78355},
        "checkpoints": checkpoints,
        "map_source": {
            "name": "OpenStreetMap", "url": "https://www.openstreetmap.org/copyright",
            "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
            "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        },
    }
    if mode == "geo":
        common["position_unlock"] = {"accuracy_required_m": 35, "dwell_seconds": 3, "allow_qr_fallback": True}
    else:
        common["virtual_map"] = {
            "projection": "local_equirectangular", "origin": {"lat": origin_lat, "lon": origin_lon},
            "units": "meters", "meters_per_unit": 1, "route_width_m": 5,
            "building_height_scale": 1.0,
            "route_centerline_m": route, "wall_height_m": 3.2,
            "spawn": {"x_m": route[0][0], "y_m": route[0][1], "z_m": 1.7, "heading_deg": 35},
            "geometry_status": "osm_geometry_v2",
            "geometry_asset": "/api/world-geometry/pardubice_center",
            "collision_layer": "buildings",
            "textures": {"masonry": "brick", "roof": "dark_tile", "path": "paving", "park": "grass", "water": "water"},
        }
    return common


def realization(mode: str, realization_id: str, title: str) -> dict[str, Any]:
    source = json.loads(SOURCE_REALIZATION.read_text(encoding="utf-8"))
    variables = deepcopy(source["variables"])
    variables["game"]["id"] = realization_id
    variables["location"] = {
        "name": "centrum Pardubic",
        "name_locative": "centru Pardubic",
        "knowledge_base": "Dvanáctičlenná porota posuzuje případ smrti nočního hlídače. Jedenáct hlasů míří k vině, Nora však upozorní na rozpory. Tým znovu prověří časovou osu, viditelnost svědků, původ nástroje, motiv a manipulaci se záznamem. Cílem není určit pachatele, ale rozhodnout, zda obžaloba odstranila rozumnou pochybnost.",
    }
    variables["checkpoints"] = checkpoint_values(realization_id)
    # The current generic runtime still exposes its optional keypad through the
    # legacy room-104 protocol; the editor can migrate this contract later.
    variables["rooms"] = {"optional_archive": {"node_id": "room_104", "number": "104", "pin": "1104"}}
    variables["world"] = world(mode)
    return {
        "schema_version": 1, "kind": "realization", "id": realization_id, "version": "1.0.0",
        "title": title, "template": {"id": "jury_deliberation", "version": "1.0.0"},
        "modes": ["geo", "osm", "gnss"] if mode == "geo" else ["online_doom", "doom", "online"],
        "variables": variables,
    }


def main() -> None:
    template = rewrite_story(json.loads(SOURCE_TEMPLATE.read_text(encoding="utf-8")))
    template.update({
        "id": "jury_deliberation", "version": "1.0.0", "title": "Dvanáct pochybností",
        "description": "Originální porotní drama o hledání rozumné pochybnosti skrze dvanáct důkazních stanovišť.",
    })
    template["variable_schema"]["world"] = {"type": "object"}
    template["runtime"]["title"] = "Dvanáct pochybností: ${location.name}"
    template["runtime"]["world"] = {"$var": "world"}
    template["runtime"]["time_travel_rules"] = [
        "Porota rozhoduje pouze podle ověřených důkazů a musí oddělit fakt od domněnky.",
        "Každý důkazní bod odhalí rozpor, který je nutné zanést do společné mapy případu.",
        "Cílem není dokázat jiného pachatele, ale zjistit, zda přetrvává rozumná pochybnost.",
        "Závěrečné rozhodnutí se odemkne až po prověření celého řetězce důkazů.",
    ]
    template["runtime"]["story_timeline"] = [
        {"id": "incident", "when": "22:41", "text": "Noční hlídač je nalezen mrtvý v uzamčeném skladu."},
        {"id": "accusation", "when": "23:06", "text": "Vyšetřovatelé zadrží mladíka, kterého se skladem spojuje svědecká výpověď."},
        {"id": "deliberation", "when": "Nyní", "text": "Porota znovu skládá časovou osu a ověřuje, zda obžaloba unesla důkazní břemeno."},
    ]
    template["runtime"]["characters"]["captain"]["avatar_prompt"] = "experienced Czech judge, neutral expression, modern courtroom, realistic portrait"
    template["runtime"]["characters"]["lost"]["avatar_prompt"] = "thoughtful female juror and investigator, rainy city at night, realistic portrait"
    template["runtime"]["phases"]["comms_offline"]["enter_message"].update({
        "text": "Tady předsedkyně senátu. Porada byla přerušena: jeden hlas odmítá rychlý verdikt. Potvrďte příjem a otevřeme zapečetěný spis.",
        "channel": "captain", "mood": "alert",
    })
    searching = template["runtime"]["phases"]["searching_lost"]
    searching["enter_message"]["text"] = "Nouzový export spisu poškodil číslo případu. Tři skupiny krátkých a dlouhých pulzů ukrývají číslice. Rozluštěte je a odešlete tříciferný kód:\n\n━━  ━━  ●  ●  ●   /   ●  ●  ●  ━━  ━━   /   ●  ●  ●  ●  ━━"
    searching["success_messages"] = [
        {"text": "Spis 734 ověřen. Přepojuji vás k porotkyni, která vznesla pochybnost.", "mood": "focused", "channel": "captain"},
        {"text": "Tady Nora. Jedenáct lidí chtělo hlasovat pro vinu, ale časová osa a výpovědi si odporují. Projděte se mnou všech dvanáct důkazních bodů.", "mood": "tense", "channel": "lost"},
        {"text": "Mapa důkazů je aktivní. Začněte prvním bodem a nic nepovažujte za fakt, dokud to neověříte.", "mood": "alert", "channel": "lost"},
    ]
    navigating = template["runtime"]["phases"]["navigating"]
    navigating["default_message"]["text"] = "Prověřujte důkazy v pořadí mapy. U každého rozporu rozhodněte, zda oslabuje jistotu obžaloby."
    navigating["ai_system_prompt"] = "Jsi Nora, pečlivá členka poroty v českém detektivním dramatu. Pomáháš týmu hledat rozpory v důkazech, nikdy nepředjímáš vinu a neprozrazuješ řešení šifer. Odpovídej česky a nejvýše třemi větami."
    puzzle_titles = {
        "reception_deduction": "Rozpory ve výpovědích", "staircase_semaphore": "Viditelnost svědka",
        "bowling_binary": "Digitální stopa telefonu", "terrace_morse": "Zvuk kroků v noci",
        "timeline_lines": "Rekonstrukce časové osy", "courtyard_karel": "Bezpečná cesta hlídače",
        "temporal_triad": "Shoda tří svědectví", "sports_sokoban": "Přesuny důkazů ve skladu",
        "sports_pigpen": "Zašifrovaná poznámka", "future_archive_cipher": "Sestavení alternativní verze",
        "time_machine_finale": "Závěrečné hlasování poroty",
    }
    for puzzle_id, title in puzzle_titles.items():
        template["runtime"]["puzzles"][puzzle_id]["title"] = title
    for puzzle_id, (title, brief) in PLACEHOLDER_CIPHERS.items():
        inherited = template["runtime"]["puzzles"][puzzle_id]
        template["runtime"]["puzzles"][puzzle_id] = placeholder_cipher(inherited, title, brief)
    template["runtime"]["puzzle_components"]["placeholder"] = {"adapter": "answer"}
    checkpoint_texts = {
        contract: (f"Důkazní bod {index} potvrzen: {POINTS[contract][0]}.",
                   "Pokračujte k dalšímu bodu mapy a porovnejte novou stopu s dosavadní časovou osou.")
        for index, contract in enumerate(POINTS, 1)
    }
    for contract, (message_text, navigation_text) in checkpoint_texts.items():
        checkpoint = template["runtime"]["checkpoints"]["${checkpoints." + contract + ".id}"]
        checkpoint["message"] = {"text": message_text, "mood": "focused", "channel": "lost"}
        if checkpoint.get("next_checkpoint"):
            checkpoint["navigation_message"] = {"text": navigation_text, "mood": "focused", "channel": "captain"}
    OUTPUT_TEMPLATE.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_GEO.write_text(json.dumps(realization("geo", "pardubice_jury_geo", "Dvanáct pochybností — Pardubice GEO"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_DOOM.write_text(json.dumps(realization("doom", "pardubice_jury_doom", "Dvanáct pochybností — Pardubice Doom"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
