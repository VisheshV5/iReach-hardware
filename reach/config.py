"""YAML configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_yaml(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or CONFIG_DIR) / name
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_caretakers(config_dir: Path | None = None) -> dict[str, Any]:
    """Real registry if present, otherwise the committed example."""
    base = config_dir or CONFIG_DIR
    name = "caretakers.yaml" if (base / "caretakers.yaml").exists() else "caretakers.example.yaml"
    return load_yaml(name, base)


class Locations:
    """Configured semantic places (locations.yaml)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._places: dict[str, dict[str, Any]] = data.get("locations", {})

    def __contains__(self, location_id: str) -> bool:
        return location_id in self._places

    def ids(self) -> set[str]:
        return set(self._places)

    def kind(self, location_id: str) -> str:
        return self._places[location_id]["kind"]

    def display_name(self, location_id: str) -> str:
        return self._places[location_id].get("display_name", location_id)

    def resolve(self, text: str) -> str | None:
        """Map a spoken place ("the tray") to a location id, or None if unknown."""
        t = text.lower().strip().removeprefix("the ").strip()
        for location_id, place in self._places.items():
            names = {location_id.lower(), place.get("display_name", "").lower().removeprefix("the ")}
            names |= {a.lower() for a in place.get("aliases", [])}
            if t in names:
                return location_id
        return None
