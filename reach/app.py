"""Wires the system together. Only the mock build exists so far; hardware wiring comes after Gates 1-6."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reach.agent.tools import ReachTools
from reach.calibration.limits import JointLimits, load_joint_limits
from reach.comms.caller import CaretakerCaller
from reach.comms.registry import CaretakerRegistry
from reach.comms.relay import RelayStore
from reach.comms.telephony import MockTelephony, Telephony
from reach.config import Locations, load_caretakers, load_yaml
from reach.hardware.mock_arm import MockArm
from reach.hardware.mock_world import MockWorld
from reach.logging import EventLog
from reach.memory.store import LocationMemory
from reach.motion.executor import MotionExecutor
from reach.motion.safety import SafetyConfig, SafetyGate
from reach.motion.stop import StopLatch
from reach.perception.mock import MockPerception
from reach.skills.library import SkillLibrary
from reach.skills.mock_effects import MockEffects
from reach.tools.manager import ToolManager
from reach.tools.registry import ToolRegistry
from reach.voice.speaker import ConsoleSpeaker, Speaker


@dataclass
class ReachSystem:
    events: EventLog
    stop: StopLatch
    arm: MockArm
    executor: MotionExecutor
    world: MockWorld
    perception: MockPerception
    skills: SkillLibrary
    tool_manager: ToolManager
    memory: LocationMemory
    relays: RelayStore
    telephony: Telephony
    caller: CaretakerCaller
    speaker: Speaker
    locations: Locations
    agent: ReachTools


def build_mock_system(
    data_dir: Path,
    world: MockWorld | None = None,
    telephony: Telephony | None = None,
    speaker: Speaker | None = None,
    config_dir: Path | None = None,
    joint_limits: JointLimits | None = None,
) -> ReachSystem:
    robot_cfg = load_yaml("robot.yaml", config_dir)
    locations = Locations(load_yaml("locations.yaml", config_dir))
    events = EventLog(data_dir / "events.jsonl")
    stop = StopLatch(events)

    safety = robot_cfg["safety"]
    gate = SafetyGate(SafetyConfig(
        joint_limits=joint_limits or load_joint_limits(robot_cfg),
        limit_margin=safety["limit_margin"],
        max_step=safety["max_step"],
        step_period_s=0.0,  # mock: no real-time pacing
        verify_tolerance=safety["verify_tolerance"],
        on_stop=safety["on_stop"],
    ))
    arm = MockArm(robot_cfg.get("home_pose"))
    arm.connect()
    executor = MotionExecutor(arm, gate, stop, events)

    world = world or MockWorld()
    perception = MockPerception(world, locations)
    skills = SkillLibrary(executor, perception, load_yaml("skills.yaml", config_dir), locations, events,
                          effects=MockEffects(world, perception))
    tool_manager = ToolManager(ToolRegistry(load_yaml("tools.yaml", config_dir)), skills, perception, events)
    tool_manager.refresh()

    memory = LocationMemory(data_dir / "memory.db", known_locations=locations.ids())
    relays = RelayStore(data_dir / "relays.json")
    telephony = telephony or MockTelephony()
    caller = CaretakerCaller(CaretakerRegistry(load_caretakers(config_dir)), telephony, relays, events)
    speaker = speaker or ConsoleSpeaker()
    agent = ReachTools(memory, perception, tool_manager, skills, speaker, caller, relays, locations, events)
    return ReachSystem(events, stop, arm, executor, world, perception, skills, tool_manager, memory, relays,
                       telephony, caller, speaker, locations, agent)
