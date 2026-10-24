"""Caretaker registry. Configured at setup; not editable by voice in P0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Global ceiling on what a caretaker reply may suggest; each caretaker may allow a subset.
TASK_ALLOWLIST: frozenset[str] = frozenset({"bring_pill_bottle", "bring_water", "open_drawer"})


@dataclass
class Caretaker:
    caretaker_id: str
    display_name: str
    relationship: str
    phone_e164: str
    allowed_task_suggestions: list[str] = field(default_factory=list)

    def allows(self, task: str | None) -> bool:
        return task is not None and task in TASK_ALLOWLIST and task in self.allowed_task_suggestions


class CaretakerRegistry:
    def __init__(self, data: dict[str, Any]) -> None:
        self.user_name: str = data.get("user", {}).get("display_name", "the user")
        self._caretakers = {
            cid: Caretaker(
                caretaker_id=cid,
                display_name=spec["display_name"],
                relationship=spec.get("relationship", ""),
                phone_e164=str(spec["phone_e164"]),
                allowed_task_suggestions=list(spec.get("allowed_task_suggestions", [])),
            )
            for cid, spec in data.get("caretakers", {}).items()
        }

    def resolve(self, name_or_id: str) -> Caretaker | None:
        """Match a registered caretaker by id, name or relationship. Never accepts a phone number."""
        key = name_or_id.lower().strip().removeprefix("my ").strip()
        for c in self._caretakers.values():
            if key in {c.caretaker_id.lower(), c.display_name.lower(), c.relationship.lower(), "caretaker"}:
                return c
        return None
