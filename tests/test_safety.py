import json
from pathlib import Path

from conftest import LIMITS

from reach.calibration.limits import limits_from_lerobot_calibration
from reach.hardware.mock_arm import MockArm
from reach.logging import EventLog
from reach.motion.executor import MotionExecutor
from reach.motion.safety import SafetyConfig, SafetyGate
from reach.motion.stop import StopLatch
from reach.results import ReasonCode, Status


def make_executor(max_step: float = 5.0) -> tuple[MotionExecutor, MockArm, StopLatch]:
    events = EventLog()
    arm = MockArm()
    arm.connect()
    stop = StopLatch(events)
    gate = SafetyGate(SafetyConfig(joint_limits=LIMITS, limit_margin=3.0, max_step=max_step, step_period_s=0))
    return MotionExecutor(arm, gate, stop, events), arm, stop


def test_target_inside_margin_is_rejected_without_motion():
    executor, arm, _ = make_executor()
    # 102 is inside the calibrated -103.8 limit but within the 3 deg margin.
    result = executor.run_trajectory([{"wrist_flex": -102.0}], "test")
    assert result.reason_code is ReasonCode.OUT_OF_BOUNDS
    assert arm.writes == []


def test_unreachable_later_waypoint_rejects_whole_trajectory():
    executor, arm, _ = make_executor()
    result = executor.run_trajectory([{"elbow_flex": 10.0}, {"elbow_flex": 200.0}], "test")
    assert result.reason_code is ReasonCode.OUT_OF_BOUNDS
    assert arm.writes == []


def test_steps_never_exceed_max_step():
    executor, arm, _ = make_executor(max_step=5.0)
    assert executor.run_trajectory([{"shoulder_pan": 40.0}], "test").ok
    previous = 0.0
    for write in arm.writes:
        assert abs(write["shoulder_pan"] - previous) <= 5.0 + 1e-9
        previous = write["shoulder_pan"]
    assert arm.joints["shoulder_pan"] == 40.0


def test_stop_mid_motion_holds_and_latches():
    executor, arm, stop = make_executor()
    arm.on_write.append(lambda n: stop.trigger("keyboard") if n == 3 else None)
    result = executor.run_trajectory([{"shoulder_pan": 60.0}], "test")
    assert result.status is Status.STOPPED
    assert arm.joints["shoulder_pan"] < 60.0
    writes_at_stop = len(arm.writes)

    # Latched: nothing moves until explicit recovery, and nothing is replayed after it.
    assert executor.run_trajectory([{"shoulder_pan": 0.0}], "test").status is Status.STOPPED
    assert len(arm.writes) == writes_at_stop
    stop.reset(confirmed_by="user")
    assert executor.run_trajectory([{"shoulder_pan": 0.0}], "test").ok


def test_stuck_joint_reports_verification_failure():
    # Same symptom as the 2026-10-23 wrist overload: commands sent, joint doesn't move.
    executor, arm, _ = make_executor()
    arm.stuck_joints.add("wrist_flex")
    result = executor.run_trajectory([{"wrist_flex": 30.0}], "test")
    assert result.reason_code is ReasonCode.VERIFICATION_FAILED
    assert "wrist_flex" in result.message


def test_single_motion_owner():
    executor, arm, _ = make_executor()
    executor._owner.acquire()
    try:
        assert executor.run_trajectory([{"shoulder_pan": 10.0}], "test").reason_code is ReasonCode.MOTION_BUSY
    finally:
        executor._owner.release()
    assert arm.writes == []


def test_limits_from_lerobot_calibration(tmp_path: Path):
    cal = {
        "shoulder_pan": {"id": 1, "drive_mode": 0, "homing_offset": 0, "range_min": 1101, "range_max": 3507},
        "wrist_roll": {"id": 5, "drive_mode": 0, "homing_offset": 0, "range_min": 0, "range_max": 4095},
        "gripper": {"id": 6, "drive_mode": 0, "homing_offset": 0, "range_min": 2003, "range_max": 3533},
    }
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(cal))
    limits = limits_from_lerobot_calibration(path)
    assert round(limits["shoulder_pan"][1], 1) == 105.8
    assert limits["wrist_roll"] == (-180.0, 180.0)
    assert limits["gripper"] == (0.0, 100.0)


def test_unvalidated_skill_refused_on_real_arm(make_system):
    system = make_system()
    system.arm.is_mock = False  # pretend this is the real follower
    result = system.agent.select_tool("drawer_hook")
    assert result.reason_code is ReasonCode.SKILL_NOT_VALIDATED
    assert system.arm.writes == []
