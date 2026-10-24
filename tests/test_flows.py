from conftest import kinds

from reach.agent import flows
from reach.hardware.mock_world import MockWorld
from reach.perception.base import TOOL_UNKNOWN
from reach.results import ReasonCode, Status


def tool_events(system):
    return [e["data"]["attached"] for e in system.events.events("tool_state")]


def test_memory_driven_drawer_retrieval(make_system):
    system = make_system()
    flows.remember(system.agent, "my pill bottle", "the drawer")

    result = flows.retrieve_object(system.agent, "my pill bottle")

    assert result.ok
    assert system.world.drawers["drawer_01"] == "open"
    assert system.world.objects["pill_bottle_01"].location_id == "handoff_pad"
    assert system.world.attached_tool is None and system.world.rack["slot_1"] == "drawer_hook"
    # Hook fetched, verified, returned; then bare gripper for the pick.
    assert tool_events(system) == [None, "drawer_hook", None]
    record = system.memory.lookup("pill bottle")
    assert (record.location_id, record.verification_status) == ("handoff_pad", "verified")
    assert system.speaker.said[-1] == "Here's your pill bottle. It's on the handoff pad."


def test_statement_then_retrieval_after_restart(make_system, tmp_path):
    world = MockWorld()
    world.add_object("pill_bottle_01", "pill bottle", "drawer_01")
    first = make_system(world=world)
    flows.remember(first.agent, "my pill bottle", "drawer")
    first.memory.close()

    second = make_system(world=world)
    assert flows.retrieve_object(second.agent, "pill bottle").ok


def test_skip_opening_when_already_open(make_system):
    system = make_system()
    system.world.drawers["drawer_01"] = "open"
    flows.remember(system.agent, "pill bottle", "drawer_01")

    assert flows.retrieve_object(system.agent, "pill bottle").ok
    assert "drawer_hook" not in tool_events(system)


def test_object_absent_from_remembered_drawer(make_system):
    system = make_system(world=MockWorld())  # drawer is empty
    flows.remember(system.agent, "pill bottle", "drawer_01")

    result = flows.retrieve_object(system.agent, "pill bottle")

    assert result.reason_code is ReasonCode.OBJECT_NOT_FOUND
    record = system.memory.lookup("pill bottle")
    assert (record.location_id, record.verification_status) == ("drawer_01", "contradicted")
    assert "pick_object" not in [e["data"].get("skill") for e in system.events.events("skill_started")]


def test_two_matching_objects_asks(make_system):
    world = MockWorld()
    world.add_object("a", "pill bottle", "drawer_01")
    world.add_object("b", "pill bottle", "drawer_01")
    system = make_system(world=world)
    flows.remember(system.agent, "pill bottle", "drawer_01")

    result = flows.retrieve_object(system.agent, "pill bottle")
    assert result.status is Status.NEEDS_USER
    assert result.reason_code is ReasonCode.AMBIGUOUS_OBJECT
    assert system.world.held_object is None


def test_low_confidence_target_refused(make_system):
    world = MockWorld()
    world.add_object("a", "pill bottle", "drawer_01", confidence=0.3)
    system = make_system(world=world)
    flows.remember(system.agent, "pill bottle", "drawer_01")
    assert flows.retrieve_object(system.agent, "pill bottle").reason_code is ReasonCode.LOW_CONFIDENCE


def test_tool_that_fails_to_attach_blocks_dependent_actions(make_system):
    system = make_system()
    system.world.faults.add("tool_slips")
    flows.remember(system.agent, "pill bottle", "drawer_01")

    result = flows.retrieve_object(system.agent, "pill bottle")

    assert result.reason_code is ReasonCode.TOOL_NOT_ATTACHED
    assert system.tool_manager.attached == TOOL_UNKNOWN
    assert system.world.drawers["drawer_01"] == "closed"
    assert system.agent.select_tool("spoon").reason_code is ReasonCode.TOOL_STATE_UNKNOWN


def test_blocked_drawer_retries_once_then_reports(make_system):
    system = make_system()
    system.world.faults.add("drawer_blocked")
    flows.remember(system.agent, "pill bottle", "drawer_01")

    result = flows.retrieve_object(system.agent, "pill bottle")

    assert result.reason_code is ReasonCode.DRAWER_BLOCKED
    opens = [e for e in system.events.events("skill_started") if e["data"]["skill"] == "open_drawer"]
    assert len(opens) == 2


def stop_when_skill_starts(system, skill):
    fired = []

    def hook(event):
        if not fired and event["kind"] == "skill_started" and event["data"]["skill"] == skill:
            fired.append(True)
            system.stop.trigger("keyboard")
    system.events.subscribe(hook)


def test_stop_during_docking_leaves_tool_state_unknown(make_system):
    system = make_system()
    flows.remember(system.agent, "pill bottle", "drawer_01")
    stop_when_skill_starts(system, "acquire_tool")

    result = flows.retrieve_object(system.agent, "pill bottle")

    assert result.status is Status.STOPPED
    assert system.tool_manager.attached == TOOL_UNKNOWN
    # Recovery is explicit and re-evaluates state; it does not replay the interrupted motion.
    system.stop.reset(confirmed_by="user")
    assert flows.retrieve_object(system.agent, "pill bottle").reason_code is ReasonCode.TOOL_STATE_UNKNOWN
    system.tool_manager.refresh()
    assert flows.retrieve_object(system.agent, "pill bottle").ok


def test_stop_during_drawer_grasp_and_spoon(make_system):
    for skill, flow in [("open_drawer", lambda s: flows.retrieve_object(s.agent, "pill bottle")),
                        ("pick_object", lambda s: flows.retrieve_object(s.agent, "pill bottle")),
                        ("present_food", lambda s: flows.serve_food(s.agent))]:
        system = make_system()
        flows.remember(system.agent, "pill bottle", "drawer_01")
        stop_when_skill_starts(system, skill)
        assert flow(system).status is Status.STOPPED, skill
        assert "motion_completed" not in kinds(system)[kinds(system).index("stop_triggered"):]


def test_spoon_acquisition_and_presentation(make_system):
    system = make_system()
    result = flows.serve_food(system.agent)
    assert result.ok
    assert system.world.attached_tool == "spoon" and system.world.presented
    assert system.world.food_portions["bowl_01"] == 4


def test_spoon_acquisition_failure_retries_once(make_system):
    system = make_system()
    system.world.faults.add("acquire_fails")
    result = flows.serve_food(system.agent)
    assert result.reason_code is ReasonCode.VERIFICATION_FAILED
    acquires = [e for e in system.events.events("skill_started") if e["data"]["skill"] == "acquire_food"]
    assert len(acquires) == 2
    assert not system.world.presented


def test_unverifiable_spoon_acquisition_is_reported_not_claimed(make_system):
    system = make_system()
    system.perception.spoon_loaded = lambda: None
    result = flows.serve_food(system.agent)
    assert any("can't confirm" in line for line in system.speaker.said)
    finished = system.events.events("task_finished")[-1]["data"]
    assert finished["status"] == "succeeded" and finished["verified"] is True
    # The acquisition step itself was not counted as verified.
    acquired = [e["data"] for e in system.events.events("skill_result") if e["data"]["action"].startswith("acquire")]
    assert acquired[-1]["verified"] is False
