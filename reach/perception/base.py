"""Perception interface. Observations are fresh evidence; memory is only a search hint."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Detection:
    detection_id: str
    label: str
    location_id: str
    confidence: float
    frame_id: str
    captured_at: str
    # Surface/frame the coordinates are expressed in (e.g. "drawer_01.interior", "table").
    surface_frame: str
    # Position on that surface in cm once calibration exists; None in the mock.
    position_cm: tuple[float, float] | None = None


@dataclass
class Observation:
    location_id: str
    frame_id: str
    captured_at: str
    detections: list[Detection] = field(default_factory=list)
    # For drawers: "open" | "closed" | "unknown".
    drawer_state: str | None = None


class Perception(Protocol):
    def observe(self, location_id: str) -> Observation: ...

    def detection(self, detection_id: str) -> Detection | None:
        """Look up a detection from a recent observation."""
        ...

    def attached_tool(self) -> str | None:
        """Tool seen in the gripper (wrist camera), None for bare gripper, or TOOL_UNKNOWN."""
        ...

    def holding_object(self) -> str | None: ...

    def spoon_loaded(self) -> bool | None:
        """None when acquisition cannot be verified reliably."""
        ...


TOOL_UNKNOWN = "unknown"
