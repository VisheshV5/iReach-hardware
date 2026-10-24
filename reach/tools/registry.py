"""Tool registry from tools.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BARE_GRIPPER = "gripper"


@dataclass
class ToolSpec:
    tool_id: str
    kind: str
    rack_slot: str | None
    skills: list[str] = field(default_factory=list)
    tip_transform: Any = None
    food_safe: bool = False


class ToolRegistry:
    def __init__(self, data: dict[str, Any]) -> None:
        self.tools: dict[str, ToolSpec] = {
            tool_id: ToolSpec(
                tool_id=tool_id,
                kind=spec["kind"],
                rack_slot=spec.get("rack_slot"),
                skills=list(spec.get("skills", [])),
                tip_transform=spec.get("tip_transform"),
                food_safe=bool(spec.get("food_safe", False)),
            )
            for tool_id, spec in data.get("tools", {}).items()
        }

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self.tools

    def get(self, tool_id: str) -> ToolSpec:
        return self.tools[tool_id]

    def tool_for_skill(self, skill: str) -> str | None:
        for spec in self.tools.values():
            if skill in spec.skills:
                return spec.tool_id
        return None
