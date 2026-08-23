"""Convert a bounded Overpass export into compact metric game geometry."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


BACKEND = Path(__file__).resolve().parents[1]
SOURCE = BACKEND / "content" / "maps" / "pardubice_center.osm.json"
TARGET = BACKEND / "content" / "maps" / "pardubice_center.geometry.json"
ORIGIN_LAT = 50.0379962
ORIGIN_LON = 15.7779363

PATH_WIDTHS = {
    "pedestrian": 8.0, "footway": 3.0, "path": 2.2, "steps": 2.5,
    "living_street": 7.0, "residential": 7.0, "service": 5.0,
    "tertiary": 9.0, "secondary": 11.0, "cycleway": 3.0,
}


def local_xy(lat: float, lon: float) -> list[float]:
    north = math.radians(lat - ORIGIN_LAT) * 6_371_000
    east = math.radians(lon - ORIGIN_LON) * 6_371_000 * math.cos(math.radians(ORIGIN_LAT))
    return [round(east, 2), round(north, 2)]


def geometry(element: dict[str, Any]) -> list[list[float]]:
    return [local_xy(float(point["lat"]), float(point["lon"])) for point in element.get("geometry", [])]


def numeric_height(tags: dict[str, str]) -> float:
    try:
        return max(2.5, min(80.0, float(str(tags.get("height", "")).split()[0])))
    except (ValueError, IndexError):
        try: return max(2.5, min(80.0, float(tags.get("building:levels", 3)) * 3.1))
        except ValueError: return 9.3


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    buildings = []
    paths = []
    surfaces = []
    for element in source.get("elements", []):
        tags = element.get("tags", {})
        points = geometry(element)
        if len(points) < 2:
            continue
        if tags.get("building"):
            if points[0] != points[-1]: points.append(points[0])
            buildings.append({
                "osm_id": element.get("id"), "polygon_m": points,
                "height_m": numeric_height(tags), "kind": tags.get("building", "yes"),
                "material": tags.get("building:material", "masonry"),
                "name": tags.get("name", ""),
            })
        highway = tags.get("highway")
        if highway:
            paths.append({
                "osm_id": element.get("id"), "line_m": points, "kind": highway,
                "width_m": PATH_WIDTHS.get(highway, 5.0), "surface": tags.get("surface", "paving_stones"),
                "name": tags.get("name", ""),
            })
        if tags.get("leisure") == "park" or tags.get("natural") == "water":
            if points[0] != points[-1]: points.append(points[0])
            surfaces.append({
                "osm_id": element.get("id"), "polygon_m": points,
                "kind": "water" if tags.get("natural") == "water" else "park",
                "name": tags.get("name", ""),
            })
    result = {
        "schema_version": 1,
        "id": "pardubice_center_osm_2026_08_23",
        "origin": {"lat": ORIGIN_LAT, "lon": ORIGIN_LON},
        "units": "meters", "meters_per_unit": 1,
        "source": {
            "name": "OpenStreetMap", "attribution": "© OpenStreetMap contributors",
            "license": "ODbL-1.0", "url": "https://www.openstreetmap.org/copyright",
            "retrieved_at": "2026-08-23",
        },
        "buildings": buildings, "paths": paths, "surfaces": surfaces,
        "stats": {"buildings": len(buildings), "paths": len(paths), "surfaces": len(surfaces)},
    }
    TARGET.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(result["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
