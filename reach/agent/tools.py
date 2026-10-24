"""Agent-facing tools (PRD 7.2). The LLM planner will call these; it never writes joint commands.

Every method returns an `ActionResult` and logs an event so the dashboard shows what actually happened.
"""

from __future__ import annotations

from reach.comms.caller import CaretakerCaller
from reach.comms.relay import RelayRecord, RelayStore
from reach.config import Locations
from reach.logging import EventLog
from reach.memory.store import LocationMemory, normalize
from reach.perception.base import Perception
from reach.results import ActionResult, ReasonCode
from reach.skills.library import SkillLibrary
from reach.tools.manager import ToolManager
from reach.voice.speaker import Speaker

MIN_CONFIDENCE = 0.6


class ReachTools:
    def __init__(
        self,
        memory: LocationMemory,
        perception: Perception,
        tool_manager: ToolManager,
        skills: SkillLibrary,
        speaker: Speaker,
        caller: CaretakerCaller,
        relays: RelayStore,
        locations: Locations,
        events: EventLog,
    ) -> None:
        self.memory = memory
        self.perception = perception
        self.tool_manager = tool_manager
        self.skills = skills
        self.speaker = speaker
        self.caller = caller
        self.relays = relays
        self.locations = locations
        self.events = events

    # --- memory ---

    def lookup_location(self, object_name: str) -> ActionResult:
        matches = self.memory.find(object_name)
        if not matches:
            return ActionResult.needs_user("lookup_location", ReasonCode.NO_MEMORY,
                                           f"I don't know where {object_name} is. Where should I look?")
        if len(matches) > 1:
            names = ", ".join(m.display_name for m in matches)
            return ActionResult.needs_user("lookup_location", ReasonCode.AMBIGUOUS_OBJECT,
                                           f"Which one do you mean: {names}?")
        return ActionResult.success("lookup_location", observations=matches[0].to_dict())

    def remember_location(self, object_name: str, location_id: str) -> ActionResult:
        if location_id not in self.locations:
            return ActionResult.failure("remember_location", ReasonCode.UNKNOWN_LOCATION,
                                        f"I don't know the place {location_id!r}.")
        if len(self.memory.find(object_name)) > 1:
            return self.lookup_location(object_name)
        evt = self.events.emit("user_statement", "memory", object=object_name, location_id=location_id)
        record = self.memory.remember(object_name, location_id, evidence_event_id=evt)
        self.events.emit("memory_updated", "memory", record=record.to_dict())
        return ActionResult.success("remember_location", observations=record.to_dict(), evidence_event_ids=[evt])

    def forget_location(self, object_name: str) -> ActionResult:
        if not self.memory.forget(object_name):
            return ActionResult.failure("forget_location", ReasonCode.NO_MEMORY, f"I had nothing saved for {object_name}.")
        evt = self.events.emit("memory_forgotten", "memory", object=object_name)
        return ActionResult.success("forget_location", evidence_event_ids=[evt])

    # --- perception ---

    def inspect(self, location_id: str) -> ActionResult:
        if location_id not in self.locations:
            return ActionResult.failure("inspect", ReasonCode.UNKNOWN_LOCATION, f"Unknown place {location_id}")
        obs = self.perception.observe(location_id)
        evt = self.events.emit("observation", "perception", location_id=location_id, frame_id=obs.frame_id,
                               drawer_state=obs.drawer_state, labels=[d.label for d in obs.detections])
        return ActionResult.success("inspect", observations={
            "frame_id": obs.frame_id, "captured_at": obs.captured_at, "drawer_state": obs.drawer_state,
            "detections": [d.__dict__ for d in obs.detections]}, evidence_event_ids=[evt])

    def find_object(self, object_name: str, location_id: str) -> ActionResult:
        """Search a fresh view. Refuses ambiguous or low-confidence targets rather than guessing."""
        obs = self.perception.observe(location_id)
        names = {normalize(object_name)}
        record = self.memory.lookup(object_name)
        if record:
            names |= set(record.aliases) | {normalize(record.display_name)}
        matches = [d for d in obs.detections if normalize(d.label) in names]
        evt = self.events.emit("find_object", "perception", object=object_name, location_id=location_id,
                               frame_id=obs.frame_id, matches=len(matches))
        where = self.locations.display_name(location_id) if location_id in self.locations else location_id
        if obs.drawer_state == "closed":
            return ActionResult.failure("find_object", ReasonCode.VERIFICATION_FAILED,
                                        f"{where} is closed; I can't see inside.", evidence_event_ids=[evt])
        if not matches:
            return ActionResult.failure("find_object", ReasonCode.OBJECT_NOT_FOUND,
                                        f"I don't see {object_name} in {where}.", evidence_event_ids=[evt])
        if len(matches) > 1:
            return ActionResult.needs_user("find_object", ReasonCode.AMBIGUOUS_OBJECT,
                                           f"I see {len(matches)} things that look like {object_name}. Which one?",
                                           evidence_event_ids=[evt])
        det = matches[0]
        if det.confidence < MIN_CONFIDENCE:
            return ActionResult.needs_user("find_object", ReasonCode.LOW_CONFIDENCE,
                                           f"I'm not sure that's {object_name}.", evidence_event_ids=[evt])
        return ActionResult.success("find_object", observations=det.__dict__, evidence_event_ids=[evt])

    # --- tools and skills ---

    def select_tool(self, tool_id: str) -> ActionResult:
        return self.tool_manager.select_tool(tool_id)

    def return_tool(self) -> ActionResult:
        return self.tool_manager.return_tool()

    def open_drawer(self, drawer_id: str) -> ActionResult:
        return self.skills.open_drawer(drawer_id)

    def pick_object(self, detection_id: str) -> ActionResult:
        return self.skills.pick_object(detection_id)

    def place_object(self, location_id: str) -> ActionResult:
        return self.skills.place_object(location_id)

    def acquire_food(self, source_id: str) -> ActionResult:
        return self.skills.acquire_food(source_id)

    def present_food(self, presentation_id: str) -> ActionResult:
        return self.skills.present_food(presentation_id)

    # --- user interaction ---

    def say(self, message: str) -> None:
        self.events.emit("say", "voice", message=message)
        self.speaker.say(message)

    def ask_user(self, question: str) -> str | None:
        self.events.emit("ask_user", "voice", question=question)
        answer = self.speaker.ask_user(question)
        self.events.emit("user_answer", "voice", answer=answer)
        return answer

    # --- caretaker ---

    def call_caretaker(self, caretaker: str, user_message: str | None, user_approved: bool) -> ActionResult:
        return self.caller.call(caretaker, user_message, user_approved)

    def get_pending_relays(self) -> list[RelayRecord]:
        return self.relays.pending()

    def mark_relay_delivered(self, relay_id: str, user_response: str | None) -> RelayRecord:
        record = self.relays.mark_delivered(relay_id, user_response)
        self.events.emit("relay_delivered", "comms", relay_id=relay_id, user_response=user_response)
        return record
