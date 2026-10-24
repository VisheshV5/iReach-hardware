"""Tracks the attached tool (including unknown state) and performs verified exchanges."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reach.logging import EventLog
from reach.perception.base import TOOL_UNKNOWN, Perception
from reach.results import ActionResult, ReasonCode
from reach.tools.registry import BARE_GRIPPER, ToolRegistry

if TYPE_CHECKING:
    from reach.skills.library import SkillLibrary


class ToolManager:
    def __init__(self, registry: ToolRegistry, skills: SkillLibrary, perception: Perception, events: EventLog) -> None:
        self.registry = registry
        self.skills = skills
        self.perception = perception
        self.events = events
        # None = bare gripper; TOOL_UNKNOWN when identity or retention is uncertain.
        self.attached: str | None = TOOL_UNKNOWN
        skills.tools = self

    @property
    def effective_tool(self) -> str:
        return self.attached or BARE_GRIPPER

    def refresh(self) -> str | None:
        """Re-observe the attachment, e.g. at startup or after a stop."""
        self._set(self.perception.attached_tool(), "observed")
        return self.attached

    def select_tool(self, tool_id: str) -> ActionResult:
        action = f"select_tool:{tool_id}"
        if tool_id not in self.registry:
            return ActionResult.failure(action, ReasonCode.UNKNOWN_TOOL, f"No tool {tool_id!r} in the registry.")
        if self.attached == TOOL_UNKNOWN:
            return ActionResult.needs_user(action, ReasonCode.TOOL_STATE_UNKNOWN,
                                           "I'm not sure what is in my gripper. Please check it.")
        if self.effective_tool == tool_id:
            return ActionResult.success(action, f"{tool_id} already in use", observations={"skipped": True})

        if self.attached is not None:
            returned = self.return_tool()
            if not returned.ok:
                return returned
        if tool_id == BARE_GRIPPER:
            return ActionResult.success(action, "bare gripper ready")

        slot = self.registry.get(tool_id).rack_slot
        moved = self.skills.acquire_tool(tool_id, slot)
        if not moved.ok:
            self._set(TOOL_UNKNOWN, f"acquire {tool_id} interrupted")
            return moved
        seen = self.perception.attached_tool()
        if seen != tool_id:
            self._set(TOOL_UNKNOWN, f"expected {tool_id}, saw {seen}")
            return ActionResult.failure(action, ReasonCode.TOOL_NOT_ATTACHED,
                                        f"Could not verify the {tool_id} is attached.")
        evt = self._set(tool_id, "acquired and verified")
        return ActionResult.success(action, state_changes={"attached_tool": tool_id}, evidence_event_ids=[evt])

    def return_tool(self) -> ActionResult:
        if self.attached is None:
            return ActionResult.success("return_tool", "nothing to return", observations={"skipped": True})
        if self.attached == TOOL_UNKNOWN:
            return ActionResult.needs_user("return_tool", ReasonCode.TOOL_STATE_UNKNOWN,
                                           "I'm not sure what is in my gripper. Please check it.")
        tool_id = self.attached
        moved = self.skills.release_tool(tool_id, self.registry.get(tool_id).rack_slot)
        if not moved.ok:
            self._set(TOOL_UNKNOWN, f"return {tool_id} interrupted")
            return moved
        seen = self.perception.attached_tool()
        if seen is not None:
            self._set(TOOL_UNKNOWN, f"after return saw {seen}")
            return ActionResult.failure("return_tool", ReasonCode.VERIFICATION_FAILED,
                                        f"The {tool_id} still seems attached.")
        evt = self._set(None, f"returned {tool_id}")
        return ActionResult.success("return_tool", state_changes={"attached_tool": None}, evidence_event_ids=[evt])

    def _set(self, attached: str | None, why: str) -> str:
        self.attached = attached
        return self.events.emit("tool_state", "tools", attached=attached, reason=why)
