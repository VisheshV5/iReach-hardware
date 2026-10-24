"""Common result envelope returned by every skill and agent-facing tool (PRD 7.3)."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Status(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_USER = "needs_user"
    STOPPED = "stopped"


class ReasonCode(str, Enum):
    TOOL_NOT_ATTACHED = "TOOL_NOT_ATTACHED"
    OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
    DRAWER_BLOCKED = "DRAWER_BLOCKED"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    CALL_NO_ANSWER = "CALL_NO_ANSWER"
    CALL_FAILED = "CALL_FAILED"
    CARETAKER_NOT_REGISTERED = "CARETAKER_NOT_REGISTERED"
    # Additions used by the scaffold.
    STOP_LATCHED = "STOP_LATCHED"
    MOTION_BUSY = "MOTION_BUSY"
    UNKNOWN_LOCATION = "UNKNOWN_LOCATION"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    TOOL_STATE_UNKNOWN = "TOOL_STATE_UNKNOWN"
    INCOMPATIBLE_TOOL = "INCOMPATIBLE_TOOL"
    SKILL_NOT_VALIDATED = "SKILL_NOT_VALIDATED"
    AMBIGUOUS_OBJECT = "AMBIGUOUS_OBJECT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    NO_MEMORY = "NO_MEMORY"
    NOT_CONFIRMED = "NOT_CONFIRMED"


@dataclass
class ActionResult:
    action: str
    status: Status
    verified: bool = False
    reason_code: ReasonCode | None = None
    message: str = ""
    observations: dict[str, Any] = field(default_factory=dict)
    state_changes: dict[str, Any] = field(default_factory=dict)
    evidence_event_ids: list[str] = field(default_factory=list)
    action_id: str = field(default_factory=lambda: new_id("act"))

    @property
    def ok(self) -> bool:
        """True only for a verified success; an accepted command is not evidence of success."""
        return self.status is Status.SUCCEEDED and self.verified

    @classmethod
    def success(cls, action: str, message: str = "", **kw: Any) -> ActionResult:
        return cls(action=action, status=Status.SUCCEEDED, verified=True, message=message, **kw)

    @classmethod
    def failure(cls, action: str, reason: ReasonCode, message: str = "", **kw: Any) -> ActionResult:
        return cls(action=action, status=Status.FAILED, reason_code=reason, message=message, **kw)

    @classmethod
    def needs_user(cls, action: str, reason: ReasonCode, message: str, **kw: Any) -> ActionResult:
        return cls(action=action, status=Status.NEEDS_USER, reason_code=reason, message=message, **kw)

    @classmethod
    def stopped(cls, action: str, message: str = "Stopped.", **kw: Any) -> ActionResult:
        return cls(action=action, status=Status.STOPPED, reason_code=ReasonCode.STOP_LATCHED, message=message, **kw)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["reason_code"] = self.reason_code.value if self.reason_code else None
        return d
