"""End-to-end mock rehearsal: no robot, no network.

    python3 scripts/run_mock_demo.py

1. "My pill bottle is in the drawer."  -> stored as a user statement
2. Restart (new process state, same memory db)
3. "Get my pill bottle."                -> hook, open drawer, return hook, gripper, find, pick, place
4. "Call my caretaker."                 -> preview, approval, one mock call, relay record
5. Relay announced; P1 offer accepted   -> pill bottle already on the pad, so retrieval reports where it is
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reach.agent import flows  # noqa: E402
from reach.app import build_mock_system  # noqa: E402
from reach.comms.telephony import MockTelephony, ScriptedCaretaker  # noqa: E402
from reach.hardware.mock_world import MockWorld  # noqa: E402
from reach.voice.speaker import ScriptedSpeaker  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data" / "mock_demo"


class EchoSpeaker(ScriptedSpeaker):
    def say(self, message: str) -> None:
        super().say(message)
        print(f"  Reach: {message}")

    def ask_user(self, question: str) -> str | None:
        answer = super().ask_user(question)
        print(f"  Reach: {question}\n  User:  {answer}")
        return answer


def main() -> None:
    shutil.rmtree(DATA, ignore_errors=True)
    world = MockWorld()
    world.add_object("pill_bottle_01", "pill bottle", "drawer_01")

    print("\n== 1. User states a location")
    system = build_mock_system(DATA, world=world, speaker=EchoSpeaker())
    print("  User:  My pill bottle is in the drawer.")
    flows.remember(system.agent, "my pill bottle", "the drawer")
    system.memory.close()

    print("\n== 2. Restart; memory reloaded from disk")
    telephony = MockTelephony([ScriptedCaretaker(reply="Ask her to take her pill.", task_suggestion="bring_pill_bottle")])
    speaker = EchoSpeaker(answers=["yes", "yes"])
    system = build_mock_system(DATA, world=world, speaker=speaker, telephony=telephony)
    print(f"  memory: {[(r.display_name, r.location_id, r.verification_status) for r in system.memory.all()]}")

    print("\n== 3. User: Get my pill bottle.")
    result = flows.retrieve_object(system.agent, "my pill bottle")
    print(f"  result: {result.status.value} verified={result.verified}")
    print(f"  world: drawer={world.drawers['drawer_01']} bottle_at={world.objects['pill_bottle_01'].location_id} "
          f"attached={world.attached_tool}")

    print("\n== 4. User: Call my caretaker.")
    flows.call_caretaker(system.agent, "my caretaker")
    print(f"  dialed: {telephony.dialed}")

    print("\n== 5. Relay announced at the station (P1 offer on)")
    flows.deliver_relays(system.agent, offer_tasks=True)

    print(f"\n== Events: {len(system.events.events())} written to {DATA / 'events.jsonl'}")
    for e in system.events.events():
        if e["kind"] in {"task_started", "task_finished", "tool_state", "skill_result", "call_status", "memory_updated"}:
            print(f"  {e['kind']:15s} {e['data']}")


if __name__ == "__main__":
    main()
