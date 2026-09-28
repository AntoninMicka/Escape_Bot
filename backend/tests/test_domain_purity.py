import ast
from pathlib import Path


DOMAIN_FILES = (
    "game_engine.py",
    "state_machine.py",
    "line_game.py",
    "sokoban.py",
    "mine_karel.py",
    "triad_game.py",
    "puzzle_components.py",
    "protocol.py",
)
PACKAGE = Path(__file__).resolve().parents[1] / "escape_bot"
BANNED_IMPORTS = {"os", "pathlib", "socket", "subprocess", "threading", "urllib.request"}


def test_domain_path_has_no_runtime_or_io_dependencies() -> None:
    violations: list[str] = []

    for filename in DOMAIN_FILES:
        path = PACKAGE / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in BANNED_IMPORTS:
                        violations.append(f"{filename}:{node.lineno} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in BANNED_IMPORTS or module == "ollama_adapter":
                    violations.append(f"{filename}:{node.lineno} imports {module}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    violations.append(f"{filename}:{node.lineno} calls open")
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "datetime"
                    and node.func.attr in {"now", "utcnow"}
                ):
                    violations.append(f"{filename}:{node.lineno} reads the system clock")

    assert violations == []
