from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from reach.app import ReachSystem, build_mock_system
from reach.comms.telephony import MockTelephony, ScriptedCaretaker
from reach.hardware.mock_world import MockWorld
from reach.voice.speaker import ScriptedSpeaker

# Fixed limits so tests don't depend on the calibration file in the user's home directory.
LIMITS = {
    "shoulder_pan": (-105.7, 105.7),
    "shoulder_lift": (-104.6, 104.6),
    "elbow_flex": (-97.8, 97.8),
    "wrist_flex": (-103.8, 103.8),
    "wrist_roll": (-180.0, 180.0),
    "gripper": (0.0, 100.0),
}

MakeSystem = Callable[..., ReachSystem]


@pytest.fixture
def make_system(tmp_path: Path) -> MakeSystem:
    def make(
        world: MockWorld | None = None,
        answers: list[str | None] | None = None,
        scripts: list[ScriptedCaretaker] | None = None,
        data_dir: Path | None = None,
    ) -> ReachSystem:
        if world is None:
            world = MockWorld()
            world.add_object("pill_bottle_01", "pill bottle", "drawer_01")
        return build_mock_system(
            data_dir or tmp_path,
            world=world,
            telephony=MockTelephony(scripts),
            speaker=ScriptedSpeaker(answers),
            joint_limits=LIMITS,
        )

    return make


def kinds(system: ReachSystem) -> list[str]:
    return [e["kind"] for e in system.events.events()]
