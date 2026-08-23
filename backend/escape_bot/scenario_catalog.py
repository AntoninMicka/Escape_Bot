from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .scenario import Scenario, ScenarioLoader


@dataclass(frozen=True)
class ScenarioCatalogEntry:
    id: str
    title: str
    template_id: str
    template_version: str
    realization_version: str
    modes: tuple[str, ...]
    scenario: Scenario
    template: dict[str, Any]
    realization: dict[str, Any]
    template_path: str
    realization_path: str

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "realization_version": self.realization_version,
            "modes": list(self.modes),
        }


@dataclass
class ScenarioCatalog:
    entries: dict[str, ScenarioCatalogEntry] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)

    def public(self) -> list[dict[str, Any]]:
        return [entry.public() for entry in self.entries.values()]


def _read_document(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Kořen dokumentu musí být objekt JSON.")
    return value


def load_scenario_catalog(template_dir: str | Path, realization_dir: str | Path) -> ScenarioCatalog:
    catalog = ScenarioCatalog()
    templates: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
    for path in sorted(Path(template_dir).glob("*.json")):
        try:
            document = _read_document(path)
            key = (str(document.get("id", "")), str(document.get("version", "")))
            if not all(key):
                raise ValueError("Šabloně chybí ID nebo verze.")
            templates[key] = (path, document)
        except Exception as error:
            catalog.errors.append({"kind": "template", "path": str(path), "message": str(error)})

    for path in sorted(Path(realization_dir).glob("*.json")):
        try:
            realization = _read_document(path)
            reference = realization.get("template", {})
            if not isinstance(reference, dict):
                raise ValueError("Pole template musí být objekt.")
            key = (str(reference.get("id", "")), str(reference.get("version", "")))
            source = templates.get(key)
            if source is None:
                raise ValueError(f"Chybí šablona {key[0]} ve verzi {key[1]}.")
            template_path, template = source
            scenario = ScenarioLoader.load_composed(str(template_path), str(path))
            realization_id = str(realization.get("id", ""))
            if not realization_id:
                raise ValueError("Realizaci chybí ID.")
            if realization_id in catalog.entries:
                raise ValueError(f"Duplicitní ID realizace {realization_id}.")
            catalog.entries[realization_id] = ScenarioCatalogEntry(
                id=realization_id,
                title=str(realization.get("title", scenario.data.get("title", realization_id))),
                template_id=key[0],
                template_version=key[1],
                realization_version=str(realization.get("version", "")),
                modes=tuple(str(mode) for mode in realization.get("modes", [])),
                scenario=scenario,
                template=template,
                realization=realization,
                template_path=str(template_path),
                realization_path=str(path),
            )
        except Exception as error:
            catalog.errors.append({"kind": "realization", "path": str(path), "message": str(error)})
    return catalog
