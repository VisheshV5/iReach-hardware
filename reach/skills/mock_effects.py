"""What each skill does to the simulated world once its trajectory completes.

On hardware there is no equivalent: physics produces the effect and perception observes it.
"""

from __future__ import annotations

from reach.hardware.mock_world import MockWorld
from reach.perception.mock import MockPerception


class MockEffects:
    def __init__(self, world: MockWorld, perception: MockPerception) -> None:
        self.world = world
        self.perception = perception

    def acquire_tool(self, tool_id: str, slot: str | None) -> None:
        if "tool_slips" in self.world.faults:
            return
        if slot:
            self.world.rack[slot] = None
        self.world.attached_tool = tool_id

    def release_tool(self, tool_id: str, slot: str | None) -> None:
        if slot:
            self.world.rack[slot] = tool_id
        self.world.attached_tool = None

    def open_drawer(self, drawer_id: str) -> None:
        if "drawer_blocked" not in self.world.faults:
            self.world.drawers[drawer_id] = "open"

    def pick_object(self, detection_id: str) -> None:
        if "grasp_fails" not in self.world.faults:
            self.world.held_object = self.perception.object_id_for(detection_id)

    def place_object(self, location_id: str) -> None:
        held = self.world.held_object
        if held:
            self.world.objects[held].location_id = location_id
            self.world.held_object = None

    def acquire_food(self, source_id: str) -> None:
        if "acquire_fails" not in self.world.faults and self.world.food_portions.get(source_id, 0) > 0:
            self.world.food_portions[source_id] -= 1
            self.world.spoon_loaded = True

    def present_food(self, presentation_id: str) -> None:
        self.world.presented = True
