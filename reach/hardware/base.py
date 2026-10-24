"""Arm driver interface.

Units follow LeRobot with `use_degrees=True`: body joints in degrees about the calibrated midpoint,
gripper in 0-100. Only `reach.motion.executor.MotionExecutor` may call `write_joint_targets`.
"""

from __future__ import annotations

from typing import Protocol

JOINTS: tuple[str, ...] = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")

JointPositions = dict[str, float]


class ArmDriver(Protocol):
    is_mock: bool

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def read_joints(self) -> JointPositions: ...

    def write_joint_targets(self, targets: JointPositions) -> None: ...

    def hold(self) -> None:
        """Command the present position as the goal (stop in place, torque on)."""
        ...

    def disable_torque(self) -> None: ...
