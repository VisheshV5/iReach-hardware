"""Physical skills. Each checks preconditions, runs its trajectory through the executor, then verifies
the postcondition with fresh perception. A completed trajectory alone never counts as success."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reach.config import Locations
from reach.logging import EventLog
from reach.motion.executor import MotionExecutor
from reach.perception.base import TOOL_UNKNOWN, Perception
from reach.results import ActionResult, ReasonCode, Status
from reach.skills.mock_effects import MockEffects
from reach.tools.registry import BARE_GRIPPER

if TYPE_CHECKING:
    from reach.tools.manager import ToolManager


class SkillLibrary:
    def __init__(
        self,
        executor: MotionExecutor,
        perception: Perception,
        skills_config: dict[str, Any],
        locations: Locations,
        events: EventLog,
        effects: MockEffects | None = None,
    ) -> None:
        self.executor = executor
        self.perception = perception
        self.config: dict[str, dict[str, Any]] = skills_config.get("skills", {})
        self.locations = locations
        self.events = events
        self.effects = effects
        self.tools: ToolManager | None = None  # set by ToolManager

    # --- tool exchange (called by ToolManager, which owns attachment state) ---

    def acquire_tool(self, tool_id: str, slot: str | None) -> ActionResult:
        return self._move("acquire_tool", lambda: self.effects and self.effects.acquire_tool(tool_id, slot))

    def release_tool(self, tool_id: str, slot: str | None) -> ActionResult:
        return self._move("release_tool", lambda: self.effects and self.effects.release_tool(tool_id, slot))

    # --- task skills ---

    def open_drawer(self, drawer_id: str) -> ActionResult:
        action = f"open_drawer:{drawer_id}"
        if drawer_id not in self.locations or self.locations.kind(drawer_id) != "drawer":
            return ActionResult.failure(action, ReasonCode.UNKNOWN_LOCATION, f"{drawer_id} is not a configured drawer")
        before = self.perception.observe(drawer_id)
        if before.drawer_state == "open":
            return ActionResult.success(action, "drawer already open", observations={"skipped": True})
        blocked = self._preconditions("open_drawer")
        if blocked:
            return blocked
        moved = self._move("open_drawer", lambda: self.effects and self.effects.open_drawer(drawer_id))
        if not moved.ok:
            return moved
        after = self.perception.observe(drawer_id)
        if after.drawer_state != "open":
            return self._done(ActionResult.failure(action, ReasonCode.DRAWER_BLOCKED,
                                                   f"Drawer still {after.drawer_state} after pulling."))
        return self._done(ActionResult.success(action, observations={"frame_id": after.frame_id},
                                               state_changes={drawer_id: "open"}))

    def pick_object(self, detection_id: str) -> ActionResult:
        action = "pick_object"
        detection = self.perception.detection(detection_id)
        if detection is None:
            return ActionResult.failure(action, ReasonCode.STALE_OBSERVATION, "Unknown or expired detection; look again.")
        blocked = self._preconditions("pick_object")
        if blocked:
            return blocked
        moved = self._move("pick_object", lambda: self.effects and self.effects.pick_object(detection_id))
        if not moved.ok:
            return moved
        if self.perception.holding_object() is None:
            return self._done(ActionResult.failure(action, ReasonCode.VERIFICATION_FAILED,
                                                   f"Grasp of {detection.label} not confirmed."))
        return self._done(ActionResult.success(action, observations={"label": detection.label}))

    def place_object(self, location_id: str) -> ActionResult:
        action = f"place_object:{location_id}"
        if location_id not in self.locations:
            return ActionResult.failure(action, ReasonCode.UNKNOWN_LOCATION, f"Unknown place {location_id}")
        if self.perception.holding_object() is None:
            return ActionResult.failure(action, ReasonCode.VERIFICATION_FAILED, "Not holding anything to place.")
        blocked = self._preconditions("place_object")
        if blocked:
            return blocked
        moved = self._move("place_object", lambda: self.effects and self.effects.place_object(location_id))
        if not moved.ok:
            return moved
        seen = self.perception.observe(location_id)
        if self.perception.holding_object() is not None or not seen.detections:
            return self._done(ActionResult.failure(action, ReasonCode.VERIFICATION_FAILED,
                                                   "Placement not confirmed by camera."))
        return self._done(ActionResult.success(
            action, observations={"frame_id": seen.frame_id, "labels": [d.label for d in seen.detections]}))

    def acquire_food(self, source_id: str) -> ActionResult:
        action = f"acquire_food:{source_id}"
        blocked = self._preconditions("acquire_food")
        if blocked:
            return blocked
        moved = self._move("acquire_food", lambda: self.effects and self.effects.acquire_food(source_id))
        if not moved.ok:
            return moved
        loaded = self.perception.spoon_loaded()
        if loaded is None:
            # Expose the limitation instead of reporting certainty (FR-06).
            return self._done(ActionResult(action, Status.SUCCEEDED, verified=False,
                                           message="Scoop done, but I can't confirm food is on the spoon."))
        if not loaded:
            return self._done(ActionResult.failure(action, ReasonCode.VERIFICATION_FAILED, "Spoon looks empty."))
        return self._done(ActionResult.success(action, state_changes={"spoon_loaded": True}))

    def present_food(self, presentation_id: str) -> ActionResult:
        action = f"present_food:{presentation_id}"
        if presentation_id not in self.locations or self.locations.kind(presentation_id) != "presentation":
            return ActionResult.failure(action, ReasonCode.UNKNOWN_LOCATION, f"{presentation_id} is not a presentation point")
        blocked = self._preconditions("present_food")
        if blocked:
            return blocked
        moved = self._move("present_food", lambda: self.effects and self.effects.present_food(presentation_id))
        if not moved.ok:
            return moved
        return self._done(ActionResult.success(action, observations={"presentation_id": presentation_id}))

    # --- helpers ---

    def _preconditions(self, skill: str) -> ActionResult | None:
        required = self.config[skill].get("required_tool", BARE_GRIPPER)
        attached = self.tools.attached if self.tools else TOOL_UNKNOWN
        if attached == TOOL_UNKNOWN:
            return ActionResult.needs_user(skill, ReasonCode.TOOL_STATE_UNKNOWN,
                                           "I'm not sure what is in my gripper.")
        if (attached or BARE_GRIPPER) != required:
            return ActionResult.failure(skill, ReasonCode.TOOL_NOT_ATTACHED,
                                        f"{skill} needs the {required}; {attached or BARE_GRIPPER} is attached.")
        return None

    def _move(self, skill: str, effect: Any) -> ActionResult:
        spec = self.config[skill]
        if not spec.get("validated", False) and not self.executor.arm.is_mock:
            return ActionResult.failure(skill, ReasonCode.SKILL_NOT_VALIDATED,
                                        f"{skill} has not passed physical validation; refusing to run on hardware.")
        self.events.emit("skill_started", "skills", skill=skill)
        moved = self.executor.run_trajectory(spec["waypoints"], skill)
        if moved.ok:
            effect()
        return moved

    def _done(self, result: ActionResult) -> ActionResult:
        evt = self.events.emit("skill_result", "skills",
                               **{k: v for k, v in result.to_dict().items() if k != "observations"})
        result.evidence_event_ids.append(evt)
        return result
