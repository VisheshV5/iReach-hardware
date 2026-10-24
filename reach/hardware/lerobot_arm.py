"""Real SO-101 follower through the Seeed LeRobot fork.

Never constructed by tests or the mock demo. Connecting does not move the arm, but every
`write_joint_targets` does: PRD section 8 requires explicit human approval for each run that moves
hardware, and all writes must come through `MotionExecutor`.
"""

from __future__ import annotations

from typing import Any

from reach.hardware.base import JointPositions


class LeRobotArm:
    is_mock = False

    def __init__(self, port: str, robot_id: str, max_relative_target: float | None = 10.0) -> None:
        self.port = port
        self.robot_id = robot_id
        self.max_relative_target = max_relative_target
        self._robot: Any = None

    def connect(self) -> None:
        # Imported lazily so the package works without LeRobot installed.
        from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

        config = SO101FollowerConfig(
            port=self.port, id=self.robot_id, max_relative_target=self.max_relative_target, use_degrees=True
        )
        self._robot = SO101Follower(config)
        # calibrate=False: refuse to start an interactive calibration from application code.
        self._robot.connect(calibrate=False)

    def disconnect(self) -> None:
        if self._robot is not None:
            self._robot.disconnect()

    def read_joints(self) -> JointPositions:
        observation = self._robot.get_observation()
        return {k.removesuffix(".pos"): float(v) for k, v in observation.items() if k.endswith(".pos")}

    def write_joint_targets(self, targets: JointPositions) -> None:
        self._robot.send_action({f"{joint}.pos": value for joint, value in targets.items()})

    def hold(self) -> None:
        self.write_joint_targets(self.read_joints())

    def disable_torque(self) -> None:
        self._robot.bus.disable_torque()
