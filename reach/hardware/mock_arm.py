"""Simulated follower arm: reaches each commanded target exactly, records every write."""

from __future__ import annotations

from collections.abc import Callable

from reach.hardware.base import JOINTS, JointPositions


class MockArm:
    is_mock = True

    def __init__(self, initial: JointPositions | None = None) -> None:
        self.joints: JointPositions = {j: 0.0 for j in JOINTS}
        self.joints["gripper"] = 50.0
        if initial:
            self.joints.update(initial)
        self.connected = False
        self.torque_enabled = False
        self.writes: list[JointPositions] = []
        # Test hooks, called after each write with the write index.
        self.on_write: list[Callable[[int], None]] = []
        # Joints that ignore commands, e.g. to simulate a servo in overload protection.
        self.stuck_joints: set[str] = set()

    def connect(self) -> None:
        self.connected = True
        self.torque_enabled = True

    def disconnect(self) -> None:
        self.connected = False
        self.torque_enabled = False

    def read_joints(self) -> JointPositions:
        self._require_connected()
        return dict(self.joints)

    def write_joint_targets(self, targets: JointPositions) -> None:
        self._require_connected()
        self.writes.append(dict(targets))
        if self.torque_enabled:
            for joint, value in targets.items():
                if joint not in self.stuck_joints:
                    self.joints[joint] = value
        for hook in list(self.on_write):
            hook(len(self.writes))

    def hold(self) -> None:
        self.write_joint_targets(dict(self.joints))

    def disable_torque(self) -> None:
        self.torque_enabled = False

    def _require_connected(self) -> None:
        if not self.connected:
            raise ConnectionError("MockArm is not connected")
