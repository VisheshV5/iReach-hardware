"""Structured JSONL event log. Every module reports verified events and state changes here (PRD FR-08)."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reach.results import new_id

Event = dict[str, Any]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._events: list[Event] = []
        self._subscribers: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, kind: str, source: str, **data: Any) -> str:
        event: Event = {"event_id": new_id("evt"), "ts": now_iso(), "kind": kind, "source": source, "data": data}
        with self._lock:
            self._events.append(event)
            if self.path:
                with self.path.open("a") as f:
                    f.write(json.dumps(event, default=str) + "\n")
            subscribers = list(self._subscribers)
        for callback in subscribers:
            callback(event)
        return event["event_id"]

    def events(self, kind: str | None = None) -> list[Event]:
        with self._lock:
            return [e for e in self._events if kind is None or e["kind"] == kind]

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)
