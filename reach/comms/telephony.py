"""Outbound call interface, the phone agent's narrow toolset, and a scripted mock.

The phone agent may only use `PhoneAgentTools`: read the prepared update, record the reply, end the call.
It has no robot, memory or dialing tools. Provider is unresolved (PRD section 14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from reach.results import new_id


class PhoneAgentTools:
    def __init__(self, update: str, user_name: str, caretaker_name: str) -> None:
        self._update = update
        self.user_name = user_name
        self.caretaker_name = caretaker_name
        self.reply_message: str | None = None
        self.task_suggestion: str | None = None
        self.confirmed = False
        self.ended = False

    def opening_line(self) -> str:
        # AI disclosure at the start of every call.
        return (f"Hi {self.caretaker_name}, this is Reach, an AI assistant calling on behalf of "
                f"{self.user_name}.")

    def get_update_summary(self) -> str:
        return self._update

    def record_reply(self, message: str, task_suggestion: str | None = None, confirmed: bool = False) -> None:
        self.reply_message = message.strip()
        self.task_suggestion = task_suggestion
        self.confirmed = confirmed

    def end_call(self) -> None:
        self.ended = True


@dataclass
class CallResult:
    call_id: str | None
    outcome: str  # answered | no_answer | voicemail | busy | failed
    transcript: list[str] = field(default_factory=list)


class Telephony(Protocol):
    def place_call(self, to_e164: str, agent_tools: PhoneAgentTools) -> CallResult: ...


@dataclass
class ScriptedCaretaker:
    outcome: str = "answered"
    reply: str | None = None
    task_suggestion: str | None = None
    confirms: bool = True


class MockTelephony:
    """Plays scripted caretaker responses in order. Records every dial so tests can check for retries."""

    def __init__(self, scripts: list[ScriptedCaretaker] | None = None) -> None:
        self.scripts = list(scripts or [])
        self.dialed: list[str] = []

    def place_call(self, to_e164: str, agent_tools: PhoneAgentTools) -> CallResult:
        self.dialed.append(to_e164)
        script = self.scripts.pop(0) if self.scripts else ScriptedCaretaker(outcome="no_answer")
        call_id = new_id("call")
        if script.outcome == "failed":
            raise ConnectionError("mock telephony failure")
        if script.outcome != "answered":
            return CallResult(call_id, script.outcome)
        transcript = [
            f"agent: {agent_tools.opening_line()}",
            f"agent: {agent_tools.get_update_summary()}",
            f"agent: Is there anything you'd like me to pass on to {agent_tools.user_name}?",
            f"caretaker: {script.reply}",
            f"agent: I'll tell {agent_tools.user_name}: \"{script.reply}\". Is that right?",
            f"caretaker: {'Yes.' if script.confirms else 'No.'}",
        ]
        if script.reply:
            agent_tools.record_reply(script.reply, script.task_suggestion, confirmed=script.confirms)
        agent_tools.end_call()
        return CallResult(call_id, "answered", transcript)
