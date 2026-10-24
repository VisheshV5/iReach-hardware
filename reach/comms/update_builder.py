"""Builds the caretaker update from verified events only: no images, audio or unverified claims."""

from __future__ import annotations

from datetime import datetime

from reach.logging import Event

MAX_ITEMS = 3


def _clock(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone().strftime("%-I:%M %p")


def build_update(events: list[Event], user_name: str, user_message: str | None = None) -> str:
    lines: list[str] = []
    tasks = [e for e in events if e["kind"] == "task_finished"][-MAX_ITEMS:]
    for e in tasks:
        d = e["data"]
        if d.get("verified"):
            lines.append(f"{user_name} got help with {d['summary']} at {_clock(e['ts'])}.")
        elif d.get("status") == "failed":
            lines.append(f"Reach could not finish {d['summary']} at {_clock(e['ts'])}.")
    if not lines:
        lines.append(f"No tasks have been completed for {user_name} recently.")
    if user_message:
        lines.append(f"{user_name} says: {user_message.strip()}")
    return " ".join(lines)
