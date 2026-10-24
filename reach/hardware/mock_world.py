"""Simulated workspace state behind the mock skills, docking and perception.

Mock skills change this state after their trajectory runs; mock perception reads it back so
verification follows the same path it will on hardware. Faults let tests exercise failure handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MockObject:
    object_id: str
    label: str
    location_id: str
    confidence: float = 0.95


@dataclass
class MockWorld:
    drawers: dict[str, str] = field(default_factory=lambda: {"drawer_01": "closed"})
    objects: dict[str, MockObject] = field(default_factory=dict)
    rack: dict[str, str | None] = field(
        default_factory=lambda: {"slot_1": "drawer_hook", "slot_2": "spoon", "slot_3": "fork"}
    )
    attached_tool: str | None = None
    held_object: str | None = None
    spoon_loaded: bool = False
    food_portions: dict[str, int] = field(default_factory=lambda: {"bowl_01": 5})
    presented: bool = False
    # e.g. {"drawer_blocked", "tool_slips", "grasp_fails", "acquire_fails"}
    faults: set[str] = field(default_factory=set)

    def add_object(self, object_id: str, label: str, location_id: str, confidence: float = 0.95) -> None:
        self.objects[object_id] = MockObject(object_id, label, location_id, confidence)

    def objects_at(self, location_id: str) -> list[MockObject]:
        return [o for o in self.objects.values() if o.location_id == location_id and o.object_id != self.held_object]
