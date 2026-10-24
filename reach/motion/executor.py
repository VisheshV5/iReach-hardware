"""The only path to `ArmDriver.write_joint_targets`. Owns motion, checks the stop latch every step."""

from __future__ import annotations

import threading
import time

from reach.hardware.base import ArmDriver, JointPositions
from reach.logging import EventLog
from reach.motion.safety import SafetyGate
from reach.motion.stop import StopLatch
from reach.results import ActionResult, ReasonCode


class MotionExecutor:
    def __init__(self, arm: ArmDriver, gate: SafetyGate, stop: StopLatch, events: EventLog) -> None:
        self.arm = arm
        self.gate = gate
        self.stop = stop
        self.events = events
        self._owner = threading.Lock()

    def run_trajectory(self, waypoints: list[JointPositions], label: str) -> ActionResult:
        """Move through joint-space waypoints. Partial waypoints keep unlisted joints in place."""
        if self.stop.is_set:
            return ActionResult.stopped(label, "Stop is latched; explicit recovery required.")
        if not self._owner.acquire(blocking=False):
            return ActionResult.failure(label, ReasonCode.MOTION_BUSY, "Another motion owns the arm.")
        try:
            return self._run(waypoints, label)
        finally:
            self._owner.release()

    def _run(self, waypoints: list[JointPositions], label: str) -> ActionResult:
        current = self.arm.read_joints()
        planned: list[JointPositions] = []
        for waypoint in waypoints:
            full = {**current, **waypoint} if not planned else {**planned[-1], **waypoint}
            rejection = self.gate.check_target(full)
            if rejection:
                reason, detail = rejection
                evt = self.events.emit("motion_rejected", "executor", label=label, reason=reason.value, detail=detail)
                return ActionResult.failure(label, reason, detail, evidence_event_ids=[evt])
            planned.append(full)

        self.events.emit("motion_started", "executor", label=label, waypoints=len(planned))
        for target in planned:
            for step in self.gate.interpolate(current, target):
                if self.stop.is_set:
                    self._on_stop()
                    evt = self.events.emit("motion_stopped", "executor", label=label)
                    return ActionResult.stopped(label, evidence_event_ids=[evt])
                self.arm.write_joint_targets(step)
                if self.gate.config.step_period_s:
                    time.sleep(self.gate.config.step_period_s)
            current = self.arm.read_joints()
            off = {j: round(current[j] - target[j], 2) for j in target
                   if abs(current[j] - target[j]) > self.gate.config.verify_tolerance}
            if off:
                evt = self.events.emit("motion_not_reached", "executor", label=label, error=off)
                return ActionResult.failure(label, ReasonCode.VERIFICATION_FAILED,
                                            f"Joints did not reach target: {off}", evidence_event_ids=[evt])
        evt = self.events.emit("motion_completed", "executor", label=label)
        return ActionResult.success(label, observations={"joints": current}, evidence_event_ids=[evt])

    def _on_stop(self) -> None:
        if self.gate.config.on_stop == "disable_torque":
            self.arm.disable_torque()
        else:
            self.arm.hold()
