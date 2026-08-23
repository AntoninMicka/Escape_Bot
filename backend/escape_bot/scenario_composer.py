from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


class ScenarioCompositionError(ValueError):
    """Raised when source layers cannot produce a safe runtime scenario."""


@dataclass(frozen=True)
class CompiledScenario:
    data: dict[str, Any]
    provenance: dict[str, str | int]


def _load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScenarioCompositionError(f"Nelze načíst {source}: {error}") from error
    if not isinstance(value, dict):
        raise ScenarioCompositionError(f"Kořen {source} musí být objekt JSON.")
    return value


def _require_document(document: dict[str, Any], kind: str, source: str) -> None:
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ScenarioCompositionError(f"{source}: nepodporovaná verze schématu.")
    if document.get("kind") != kind:
        raise ScenarioCompositionError(f"{source}: očekáván dokument typu {kind}.")
    required_fields = ("id", "version", "runtime") if kind == "story_template" else ("id", "version", "variables")
    for field in required_fields:
        if not document.get(field):
            raise ScenarioCompositionError(f"{source}: chybí povinné pole {field}.")
    if kind == "story_template" and not isinstance(document["runtime"], dict):
        raise ScenarioCompositionError(f"{source}: runtime musí být objekt.")
    if kind == "realization" and not isinstance(document["variables"], dict):
        raise ScenarioCompositionError(f"{source}: variables musí být objekt.")


_INTERPOLATION = re.compile(r"\$\{([a-zA-Z0-9_.-]+)\}")


def _resolve_variable(variables: dict[str, Any], path: str) -> Any:
    value: Any = variables
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ScenarioCompositionError(f"Realizaci chybí proměnná {path}.")
        value = value[part]
    return value


def _render_string(value: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        path = match.group(1)
        replacement = _resolve_variable(variables, path)
        if isinstance(replacement, (dict, list)) or replacement is None:
            raise ScenarioCompositionError(f"Proměnnou {path} nelze vložit do textu nebo klíče.")
        return str(replacement)

    return _INTERPOLATION.sub(replace, value)


def _render(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$var"}:
            path = value["$var"]
            if not isinstance(path, str):
                raise ScenarioCompositionError("Hodnota $var musí být cesta k proměnné.")
            return deepcopy(_resolve_variable(variables, path))
        result: dict[str, Any] = {}
        for key, child in value.items():
            rendered_key = _render_string(key, variables)
            if rendered_key in result:
                raise ScenarioCompositionError(f"Dosazení vytvořilo duplicitní klíč {rendered_key}.")
            result[rendered_key] = _render(child, variables)
        return result
    if isinstance(value, list):
        return [_render(item, variables) for item in value]
    if isinstance(value, str):
        return _render_string(value, variables)
    return deepcopy(value)


def _validate_variables(schema: dict[str, Any], variables: dict[str, Any]) -> None:
    supported_types = {
        "string": str, "number": (int, float), "boolean": bool,
        "object": dict, "array": list, "any": object,
    }
    for path, declaration in schema.items():
        if not isinstance(declaration, dict):
            raise ScenarioCompositionError(f"Deklarace proměnné {path} musí být objekt.")
        try:
            value = _resolve_variable(variables, path)
        except ScenarioCompositionError:
            if declaration.get("required", True):
                raise
            continue
        expected = declaration.get("type", "any")
        if expected not in supported_types:
            raise ScenarioCompositionError(f"Proměnná {path} má neznámý typ {expected}.")
        if expected == "number" and isinstance(value, bool):
            valid = False
        else:
            valid = isinstance(value, supported_types[expected])
        if not valid:
            raise ScenarioCompositionError(f"Proměnná {path} musí mít typ {expected}.")


def compose_documents(template: dict[str, Any], realization: dict[str, Any]) -> CompiledScenario:
    _require_document(template, "story_template", "story_template")
    _require_document(realization, "realization", "realization")
    expected = realization.get("template")
    if not isinstance(expected, dict):
        raise ScenarioCompositionError("Realizace musí obsahovat objekt template.")
    if expected.get("id") != template["id"] or expected.get("version") != template["version"]:
        raise ScenarioCompositionError("Realizace odkazuje na jinou šablonu nebo její verzi.")

    variables = realization["variables"]
    variable_schema = template.get("variable_schema", {})
    if not isinstance(variable_schema, dict):
        raise ScenarioCompositionError("variable_schema musí být objekt.")
    _validate_variables(variable_schema, variables)

    contracts = template.get("node_contracts", {})
    bindings = _render(template.get("node_bindings", {}), variables)
    if not isinstance(contracts, dict) or not isinstance(bindings, dict):
        raise ScenarioCompositionError("node_contracts a node_bindings musí být objekty.")
    missing = sorted(set(contracts) - set(bindings))
    unknown = sorted(set(bindings) - set(contracts))
    if missing or unknown:
        details = []
        if missing: details.append("chybí vazby: " + ", ".join(missing))
        if unknown: details.append("neznámé vazby: " + ", ".join(unknown))
        raise ScenarioCompositionError("Neúplné mapování realizace; " + "; ".join(details))

    runtime = _render(template["runtime"], variables)
    flow_items = runtime.get("scenario_flow", [])
    if not isinstance(flow_items, list):
        raise ScenarioCompositionError("Složený runtime musí obsahovat pole scenario_flow.")
    flow = {str(node.get("id")): node for node in flow_items if isinstance(node, dict)}
    for contract_id, contract in contracts.items():
        binding = bindings[contract_id]
        if not isinstance(contract, dict) or not isinstance(binding, dict):
            raise ScenarioCompositionError(f"Kontrakt a vazba {contract_id} musí být objekty.")
        runtime_node_id = str(binding.get("runtime_node_id", ""))
        node = flow.get(runtime_node_id)
        if node is None:
            raise ScenarioCompositionError(f"Vazba {contract_id} míří na neexistující uzel {runtime_node_id}.")
        expected_kind = str(contract.get("kind", ""))
        if expected_kind and node.get("kind") != expected_kind:
            raise ScenarioCompositionError(f"Uzel {runtime_node_id} neodpovídá typu {expected_kind} kontraktu {contract_id}.")
        required_capabilities = set(contract.get("requires_capabilities", []))
        capabilities = set(binding.get("capabilities", []))
        if not required_capabilities.issubset(capabilities):
            absent = ", ".join(sorted(required_capabilities - capabilities))
            raise ScenarioCompositionError(f"Vazbě {contract_id} chybí schopnosti: {absent}.")

    provenance: dict[str, str | int] = {
        "schema_version": SCHEMA_VERSION,
        "template_id": str(template["id"]),
        "template_version": str(template["version"]),
        "realization_id": str(realization["id"]),
        "realization_version": str(realization["version"]),
    }
    return CompiledScenario(runtime, provenance)


def compose_files(template_path: str | Path, realization_path: str | Path) -> CompiledScenario:
    return compose_documents(_load_json(template_path), _load_json(realization_path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile an Escape Bot story template and realization.")
    parser.add_argument("template", type=Path)
    parser.add_argument("realization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    compiled = compose_files(args.template, args.realization)
    encoded = json.dumps(compiled.data, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
