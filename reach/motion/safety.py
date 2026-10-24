"""Target validation and step limiting applied to every motion."""

from __future__ import annotations

import math
from dataclasses import dataclass

from reach.calibration.limits import JointLimits
from reach.hardware.base import JointPositions
from reach.results import ReasonCode


@dataclass
class SafetyConfig:
    joint_limits: JointLimits
    limit_margin: float = 3.0
    max_step: float = 5.0
    step_period_s: float = 0.02
    verify_tolerance: float = 2.0
    on_stop: str = "hold"


class SafetyGate:
    def __init__(self, config: SafetyConfig) -> None:
        self.config = config

    def allowed_range(self, joint: str) -> tuple[float, float]:
        lo, hi = self.config.joint_limits[joint]
        return lo + self.config.limit_margin, hi - self.config.limit_margin

    def check_target(self, target: JointPositions) -> tuple[ReasonCode, str] | None:
        """Reject (never silently clamp) targets outside the calibrated limits minus the margin."""
        for joint, value in target.items():
            if joint not in self.config.joint_limits:
                return ReasonCode.OUT_OF_BOUNDS, f"unknown joint {joint!r}"
            lo, hi = self.allowed_range(joint)
            if not lo <= value <= hi:
                return ReasonCode.OUT_OF_BOUNDS, f"{joint}={value:.1f} outside [{lo:.1f}, {hi:.1f}]"
        return None

    def interpolate(self, current: JointPositions, target: JointPositions) -> list[JointPositions]:
        """Split a move into steps no joint exceeds `max_step` in."""
        largest = max((abs(target[j] - current[j]) for j in target), default=0.0)
        n = max(1, math.ceil(largest / self.config.max_step))
        return [{j: current[j] + (target[j] - current[j]) * i / n for j in target} for i in range(1, n + 1)]
