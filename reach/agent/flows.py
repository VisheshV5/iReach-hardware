"""Deterministic task flows composed from agent tools.

PRD section 13: run fixed sequences before adding LLM choice. A future planner should produce the
same tool calls these flows make. Each flow stops at the first stop/failure and reports it.
"""

from __future__ import annotations

from collections.abc import Callable

from reach.agent.tools import ReachTools
from reach.memory.store import normalize
from reach.results import ActionResult, ReasonCode, Status

RETRYABLE = {ReasonCode.VERIFICATION_FAILED, ReasonCode.DRAWER_BLOCKED}

# Allowlisted caretaker suggestions -> the normal flow that performs them (P1).
SUGGESTION_FLOWS: dict[str, tuple[str, str]] = {
    "bring_pill_bottle": ("pill bottle", "bring your pill bottle"),
    "bring_water": ("water bottle", "bring your water"),
}


def _yours(object_name: str) -> str:
    """Speak the user's words back from Reach's side: "my pill bottle" -> "your pill bottle"."""
    name = object_name.strip()
    if name.lower().startswith("my "):
        return "your " + name[3:]
    return name if name.lower().startswith(("the ", "your ")) else f"the {normalize(name)}"


def _once_more(step: Callable[[], ActionResult]) -> ActionResult:
    """One skill-specific retry, then report (FR-02)."""
    result = step()
    if result.status is Status.FAILED and result.reason_code in RETRYABLE:
        result = step()
    return result


def _finish(t: ReachTools, summary: str, result: ActionResult, say: str | None = None) -> ActionResult:
    t.events.emit("task_finished", "agent", summary=summary, status=result.status.value,
                  verified=result.ok, reason=result.reason_code.value if result.reason_code else None)
    if say or result.message:
        t.say(say or result.message)
    return result


def remember(t: ReachTools, object_name: str, place: str) -> ActionResult:
    """"My pill bottle is in the drawer." Stores the statement without claiming it was seen."""
    location_id = t.locations.resolve(place) or place
    result = t.remember_location(object_name, location_id)
    if result.ok:
        t.say(f"Okay, I'll remember {_yours(object_name)} is in {t.locations.display_name(location_id)}.")
    else:
        t.say(result.message)
    return result


def retrieve_object(t: ReachTools, object_name: str, destination: str = "handoff_pad") -> ActionResult:
    """Memory-driven retrieval (PRD 2.1): lookup -> open drawer with hook -> gripper -> find -> pick -> place."""
    spoken = _yours(object_name)
    summary = f"getting the {normalize(object_name)}"
    t.events.emit("task_started", "agent", summary=summary)

    found_memory = t.lookup_location(object_name)
    if not found_memory.ok:
        return _finish(t, summary, found_memory)
    location_id = found_memory.observations["location_id"]
    where = t.locations.display_name(location_id)

    if location_id == destination:
        here = t.find_object(object_name, location_id)
        if here.ok:
            return _finish(t, summary, here, say=f"{spoken.capitalize()} is already on {where}.")

    if t.locations.kind(location_id) == "drawer":
        state = t.inspect(location_id).observations.get("drawer_state")
        if state == "open":
            t.events.emit("task_step", "agent", step="open_drawer", skipped=True, reason="already open")
        else:
            t.say(f"Opening {where}.")
            for step in (lambda: t.select_tool("drawer_hook"),
                         lambda: _once_more(lambda: t.open_drawer(location_id)),
                         t.return_tool):
                result = step()
                if not result.ok:
                    return _finish(t, summary, result)

    result = t.select_tool("gripper")
    if not result.ok:
        return _finish(t, summary, result)

    found = t.find_object(object_name, location_id)
    if not found.ok:
        if found.reason_code is ReasonCode.OBJECT_NOT_FOUND:
            t.memory.mark_contradicted(object_name, evidence_event_id=found.evidence_event_ids[0])
        return _finish(t, summary, found)

    picked = t.pick_object(found.observations["detection_id"])
    if picked.status is Status.FAILED and picked.reason_code in RETRYABLE:
        # Retry from a fresh observation, never a stale detection.
        found = t.find_object(object_name, location_id)
        picked = t.pick_object(found.observations["detection_id"]) if found.ok else found
    if not picked.ok:
        return _finish(t, summary, picked)

    placed = t.place_object(destination)
    if not placed.ok:
        return _finish(t, summary, placed)
    t.memory.mark_observed(object_name, destination, evidence_event_id=placed.evidence_event_ids[-1])
    return _finish(t, summary, placed, say=f"Here's {spoken}. It's on {t.locations.display_name(destination)}.")


def serve_food(t: ReachTools, source_id: str = "bowl_01", presentation_id: str = "presentation_pad") -> ActionResult:
    """Spoon acquisition and transfer to a fixed presentation point (PRD 2.2). Never near a face in P0."""
    summary = "a spoonful of food"
    t.events.emit("task_started", "agent", summary=summary)
    for step in (lambda: t.select_tool("spoon"),
                 lambda: _once_more(lambda: t.acquire_food(source_id)),
                 lambda: t.present_food(presentation_id)):
        result = step()
        if result.status is not Status.SUCCEEDED:
            return _finish(t, summary, result)
        if not result.verified:
            t.say(result.message)
    return _finish(t, summary, result, say="The spoon is ready at the presentation point.")


def call_caretaker(t: ReachTools, caretaker: str = "caretaker", user_message: str | None = None) -> ActionResult:
    """Preview -> user approval -> one call. Never dials without approval, never retries."""
    preview = t.caller.preview(caretaker, user_message)
    if preview.reason_code is ReasonCode.CARETAKER_NOT_REGISTERED:
        t.say(preview.message)
        return preview
    answer = t.ask_user(preview.message)
    if answer is None or answer.strip().lower() in {"no", "cancel", "don't", "stop"}:
        t.say("Okay, I won't call.")
        return ActionResult.needs_user("call_caretaker", ReasonCode.NOT_CONFIRMED, "Call cancelled.")
    extra = None if answer.strip().lower() in {"yes", "yes please", "call", "go ahead", "ok", "okay"} else answer
    message = " ".join(m for m in (user_message, extra) if m) or None
    t.say("Calling now.")
    result = t.call_caretaker(caretaker, message, user_approved=True)
    if not result.ok:
        t.say(result.message)
    return result


def deliver_relays(t: ReachTools, offer_tasks: bool = False) -> list[ActionResult]:
    """Announce caretaker replies (P0). With offer_tasks (P1), offer an allowlisted task; only the local
    user's "yes" can turn it into motion, through the normal flow."""
    outcomes: list[ActionResult] = []
    for relay in t.get_pending_relays():
        caretaker = t.caller.registry.resolve(relay.caretaker_id)
        name = caretaker.display_name if caretaker else "Your caretaker"
        t.say(f"{name} says: \"{relay.caretaker_message}\"")
        response = None
        flow = SUGGESTION_FLOWS.get(relay.task_suggestion or "")
        if offer_tasks and flow:
            object_name, phrase = flow
            answer = t.ask_user(f"Want me to {phrase}?")
            if answer is not None and answer.strip().lower() in {"yes", "yes please", "sure", "ok", "okay"}:
                response = "accepted"
                result = retrieve_object(t, object_name)
                if result.ok:
                    t.say(f"{name} said to take these.")
                outcomes.append(result)
            else:
                response = "declined" if answer else "no_response"
        t.mark_relay_delivered(relay.relay_id, response)
    return outcomes
