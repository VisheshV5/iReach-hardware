"""Local software stop latch.

This is a keyboard/software stop, not a hardware emergency stop. It must not depend on the network,
speech transcription or the LLM: anything local (a key handler, the push-to-talk button) calls `trigger`.
"""

from __future__ import annotations

import threading

from reach.logging import EventLog


class StopLatch:
    def __init__(self, events: EventLog) -> None:
        self._flag = threading.Event()
        self._events = events

    @property
    def is_set(self) -> bool:
        return self._flag.is_set()

    def trigger(self, source: str) -> None:
        if not self._flag.is_set():
            self._flag.set()
            self._events.emit("stop_triggered", "stop", trigger_source=source)

    def reset(self, confirmed_by: str) -> None:
        """Explicit recovery only. The caller must re-evaluate scene and state before moving again;
        nothing replays the interrupted motion."""
        if self._flag.is_set():
            self._flag.clear()
            self._events.emit("stop_reset", "stop", confirmed_by=confirmed_by)
