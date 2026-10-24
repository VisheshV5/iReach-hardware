"""Joint limits in executor units, derived from a LeRobot calibration file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# STS3215 resolution minus one, as LeRobot uses in its degree normalization.
_MAX_RES = 4095

JointLimits = dict[str, tuple[float, float]]


def limits_from_lerobot_calibration(path: Path) -> JointLimits:
    """LeRobot maps raw ticks to degrees about the range midpoint: (raw - mid) * 360 / 4095.

    The gripper uses 0-100 normalization instead of degrees.
    """
    data: dict[str, Any] = json.loads(path.expanduser().read_text())
    limits: JointLimits = {}
    for joint, cal in data.items():
        if joint == "gripper":
            limits[joint] = (0.0, 100.0)
            continue
        half = (cal["range_max"] - cal["range_min"]) / 2 * 360 / _MAX_RES
        limits[joint] = (-half, half)
    return limits


def load_joint_limits(robot_config: dict[str, Any]) -> JointLimits:
    cal_file = robot_config.get("follower", {}).get("calibration_file")
    if cal_file and Path(cal_file).expanduser().exists():
        return limits_from_lerobot_calibration(Path(cal_file))
    return {joint: (float(lo), float(hi)) for joint, (lo, hi) in robot_config["joint_limits"].items()}
