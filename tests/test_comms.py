from reach.agent import flows
from reach.comms.relay import RelayStore
from reach.comms.telephony import ScriptedCaretaker
from reach.comms.update_builder import build_update
from reach.results import ReasonCode


def setup_bottle(system):
    flows.remember(system.agent, "pill bottle", "drawer_01")


def test_call_delivers_update_and_relays_reply(make_system):
    system = make_system(answers=["yes"], scripts=[ScriptedCaretaker(reply="Ask her to take her pill.")])
    setup_bottle(system)
    assert flows.retrieve_object(system.agent, "pill bottle").ok

    result = flows.call_caretaker(system.agent, "my caretaker")

    assert result.ok
    assert system.telephony.dialed == ["+15555550100"]
    assert "got help with getting the pill bottle" in system.speaker.asked[0]
    relay = system.relays.pending()[0]
    assert relay.caretaker_message == "Ask her to take her pill." and relay.confirmed_on_call

    flows.deliver_relays(system.agent)
    assert system.speaker.said[-1] == 'Priya says: "Ask her to take her pill."'
    assert system.relays.pending() == []


def test_user_can_add_a_message(make_system):
    system = make_system(answers=["Tell her I miss her"], scripts=[ScriptedCaretaker(reply="Love you too.")])
    flows.call_caretaker(system.agent, "Priya")
    assert "Asha says: Tell her I miss her" in system.relays.get(system.relays.pending()[0].relay_id).update_sent


def test_declined_preview_never_dials(make_system):
    system = make_system(answers=["no"])
    flows.call_caretaker(system.agent, "Priya")
    assert system.telephony.dialed == []


def test_no_answer_tells_user_and_does_not_redial(make_system):
    system = make_system(answers=["yes"], scripts=[ScriptedCaretaker(outcome="no_answer")])
    result = flows.call_caretaker(system.agent, "Priya")
    assert result.reason_code is ReasonCode.CALL_NO_ANSWER
    assert len(system.telephony.dialed) == 1
    assert system.speaker.said[-1] == "I couldn't reach Priya."
    assert system.relays.pending() == []


def test_api_failure_reported(make_system):
    system = make_system(answers=["yes"], scripts=[ScriptedCaretaker(outcome="failed")])
    result = flows.call_caretaker(system.agent, "Priya")
    assert result.reason_code is ReasonCode.CALL_FAILED
    assert len(system.telephony.dialed) == 1


def test_unregistered_caretaker_never_dialed(make_system):
    system = make_system(answers=["yes"])
    result = flows.call_caretaker(system.agent, "Bob")
    assert result.reason_code is ReasonCode.CARETAKER_NOT_REGISTERED
    assert system.telephony.dialed == []
    assert system.agent.call_caretaker("+15551234567", None, user_approved=True).reason_code \
        is ReasonCode.CARETAKER_NOT_REGISTERED


def test_reply_without_task_is_words_only(make_system):
    system = make_system(answers=["yes"], scripts=[ScriptedCaretaker(reply="Tell her I'll visit Sunday.")])
    flows.call_caretaker(system.agent, "Priya")
    writes = len(system.arm.writes)
    flows.deliver_relays(system.agent, offer_tasks=True)
    assert system.speaker.said[-1] == "Priya says: \"Tell her I'll visit Sunday.\""
    assert system.speaker.asked == [system.speaker.asked[0]]  # only the pre-call preview
    assert len(system.arm.writes) == writes


def test_allowlisted_task_accepted_runs_retrieval(make_system):
    system = make_system(answers=["yes", "yes"],
                         scripts=[ScriptedCaretaker(reply="Ask her to take her pill.", task_suggestion="bring_pill_bottle")])
    setup_bottle(system)
    flows.call_caretaker(system.agent, "Priya")
    assert len(system.arm.writes) == 0  # the call itself moved nothing

    outcomes = flows.deliver_relays(system.agent, offer_tasks=True)

    assert outcomes[0].ok
    assert system.world.objects["pill_bottle_01"].location_id == "handoff_pad"
    assert system.speaker.said[-1] == "Priya said to take these."
    assert system.relays.get(outcomes and system.relays._records and list(system.relays._records)[0]).user_response \
        == "accepted"


def test_allowlisted_task_declined_or_silence_does_nothing(make_system):
    for answer, expected in [("no", "declined"), (None, "no_response")]:
        system = make_system(answers=["yes", answer],
                             scripts=[ScriptedCaretaker(reply="Take your pill.", task_suggestion="bring_pill_bottle")])
        setup_bottle(system)
        flows.call_caretaker(system.agent, "Priya")
        relay_id = system.relays.pending()[0].relay_id
        assert flows.deliver_relays(system.agent, offer_tasks=True) == []
        assert system.arm.writes == []
        assert system.relays.get(relay_id).user_response == expected


def test_unsupported_suggestion_dropped_and_relayed_as_words(make_system):
    system = make_system(answers=["yes"],
                         scripts=[ScriptedCaretaker(reply="Give her two pills.", task_suggestion="give_two_pills")])
    flows.call_caretaker(system.agent, "Priya")
    relay = system.relays.pending()[0]
    assert relay.task_suggestion is None
    assert "relay_suggestion_dropped" in [e["kind"] for e in system.events.events()]
    flows.deliver_relays(system.agent, offer_tasks=True)
    assert system.speaker.said[-1] == 'Priya says: "Give her two pills."'
    assert system.arm.writes == []


def test_stop_works_while_call_in_progress(make_system):
    system = make_system(answers=["yes"])

    class StopDuringCall:
        dialed: list = []

        def place_call(self, to_e164, agent_tools):
            system.stop.trigger("keyboard")
            from reach.comms.telephony import CallResult
            return CallResult("c1", "no_answer")

    system.caller.telephony = StopDuringCall()
    flows.call_caretaker(system.agent, "Priya")
    assert system.stop.is_set
    setup_bottle(system)
    assert flows.retrieve_object(system.agent, "pill bottle").reason_code is ReasonCode.STOP_LATCHED
    assert system.arm.writes == []


def test_relays_persist_across_restart(make_system, tmp_path):
    system = make_system(answers=["yes"], scripts=[ScriptedCaretaker(reply="Back at six.")])
    flows.call_caretaker(system.agent, "Priya")
    assert RelayStore(tmp_path / "relays.json").pending()[0].caretaker_message == "Back at six."


def test_update_uses_verified_events_only():
    events = [
        {"kind": "task_finished", "ts": "2026-10-23T14:00:00+00:00",
         "data": {"summary": "getting the pill bottle", "status": "succeeded", "verified": True}},
        {"kind": "task_finished", "ts": "2026-10-23T14:05:00+00:00",
         "data": {"summary": "a spoonful of food", "status": "succeeded", "verified": False}},
        {"kind": "observation", "ts": "2026-10-23T14:06:00+00:00", "data": {"frame_id": "frame_1"}},
    ]
    update = build_update(events, "Asha")
    assert "pill bottle" in update
    assert "spoonful" not in update and "frame" not in update
