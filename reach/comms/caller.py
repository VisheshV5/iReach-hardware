"""`call_caretaker`: one confirmed, registry-only call that ends in a relay record."""

from __future__ import annotations

from reach.comms.registry import CaretakerRegistry
from reach.comms.relay import RelayRecord, RelayStore
from reach.comms.telephony import PhoneAgentTools, Telephony
from reach.comms.update_builder import build_update
from reach.logging import EventLog
from reach.results import ActionResult, ReasonCode


class CaretakerCaller:
    def __init__(self, registry: CaretakerRegistry, telephony: Telephony, relays: RelayStore, events: EventLog) -> None:
        self.registry = registry
        self.telephony = telephony
        self.relays = relays
        self.events = events

    def preview(self, who: str, user_message: str | None = None) -> ActionResult:
        """What the user approves before dialing (FR-09)."""
        caretaker = self.registry.resolve(who)
        if caretaker is None:
            return ActionResult.failure("call_caretaker", ReasonCode.CARETAKER_NOT_REGISTERED,
                                        f"{who} is not a registered caretaker.")
        update = build_update(self.events.events(), self.registry.user_name, user_message)
        return ActionResult.needs_user(
            "call_caretaker", ReasonCode.NOT_CONFIRMED,
            f"I'll call {caretaker.display_name} and say: \"{update}\" Should I call now, or add something?",
            observations={"caretaker_id": caretaker.caretaker_id, "update": update},
        )

    def call(self, who: str, user_message: str | None, user_approved: bool) -> ActionResult:
        caretaker = self.registry.resolve(who)
        if caretaker is None:
            return ActionResult.failure("call_caretaker", ReasonCode.CARETAKER_NOT_REGISTERED,
                                        f"{who} is not a registered caretaker.")
        if not user_approved:
            return self.preview(who, user_message)

        update = build_update(self.events.events(), self.registry.user_name, user_message)
        agent_tools = PhoneAgentTools(update, self.registry.user_name, caretaker.display_name)
        self.events.emit("call_status", "comms", status="dialing", caretaker_id=caretaker.caretaker_id)
        try:
            result = self.telephony.place_call(caretaker.phone_e164, agent_tools)
            outcome, call_id, transcript = result.outcome, result.call_id, result.transcript
        except Exception as exc:  # provider/API failure: report, never retry in a loop
            outcome, call_id, transcript = "failed", None, []
            self.events.emit("call_error", "comms", error=str(exc))

        suggestion = agent_tools.task_suggestion if caretaker.allows(agent_tools.task_suggestion) else None
        if agent_tools.task_suggestion and suggestion is None:
            self.events.emit("relay_suggestion_dropped", "comms", suggestion=agent_tools.task_suggestion)
        relay = RelayRecord(
            caretaker_id=caretaker.caretaker_id,
            call_id=call_id,
            call_outcome=outcome if outcome in {"answered", "no_answer", "voicemail", "failed"} else "no_answer",
            update_sent=update,
            caretaker_message=agent_tools.reply_message,
            task_suggestion=suggestion,
            confirmed_on_call=agent_tools.confirmed,
        )
        self.relays.add(relay)
        # Retention default: summary and relay only, not the full transcript.
        evt = self.events.emit("call_status", "comms", status="ended", outcome=relay.call_outcome,
                               relay_id=relay.relay_id, transcript_lines=len(transcript))

        if relay.call_outcome == "answered":
            return ActionResult.success("call_caretaker", f"Spoke with {caretaker.display_name}.",
                                        observations={"relay_id": relay.relay_id}, evidence_event_ids=[evt])
        reason = ReasonCode.CALL_FAILED if relay.call_outcome == "failed" else ReasonCode.CALL_NO_ANSWER
        return ActionResult.failure("call_caretaker", reason, f"I couldn't reach {caretaker.display_name}.",
                                    observations={"relay_id": relay.relay_id}, evidence_event_ids=[evt])
