"""Mock perception reading `MockWorld`."""

from __future__ import annotations

from reach.config import Locations
from reach.hardware.mock_world import MockWorld
from reach.logging import now_iso
from reach.perception.base import Detection, Observation
from reach.results import new_id


class MockPerception:
    def __init__(self, world: MockWorld, locations: Locations) -> None:
        self.world = world
        self.locations = locations
        self._detections: dict[str, Detection] = {}
        self._detected_objects: dict[str, str] = {}

    def observe(self, location_id: str) -> Observation:
        frame_id, captured_at = new_id("frame"), now_iso()
        drawer_state = None
        visible = True
        if location_id in self.locations and self.locations.kind(location_id) == "drawer":
            drawer_state = self.world.drawers.get(location_id, "unknown")
            # Contents of a closed drawer are not visible.
            visible = drawer_state == "open"
        surface = f"{location_id}.interior" if drawer_state else location_id
        detections = []
        if visible:
            for obj in self.world.objects_at(location_id):
                det = Detection(new_id("det"), obj.label, location_id, obj.confidence, frame_id, captured_at, surface)
                self._detections[det.detection_id] = det
                self._detected_objects[det.detection_id] = obj.object_id
                detections.append(det)
        return Observation(location_id, frame_id, captured_at, detections, drawer_state)

    def detection(self, detection_id: str) -> Detection | None:
        return self._detections.get(detection_id)

    def attached_tool(self) -> str | None:
        return self.world.attached_tool

    def holding_object(self) -> str | None:
        return self.world.held_object

    def spoon_loaded(self) -> bool | None:
        return self.world.spoon_loaded

    def object_id_for(self, detection_id: str) -> str | None:
        """Mock-only: which simulated object a detection refers to."""
        return self._detected_objects.get(detection_id)
