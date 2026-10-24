"""Relay records (PRD 5.3): the only channel from a phone call back to the station."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from reach.logging import now_iso
from reach.results import new_id


@dataclass
class RelayRecord:
    caretaker_id: str
    call_id: str | None
    call_outcome: str  # answered | no_answer | voicemail | failed
    update_sent: str
    caretaker_message: str | None = None
    task_suggestion: str | None = None
    confirmed_on_call: bool = False
    delivered_to_user_at: str | None = None
    user_response: str | None = None  # accepted | declined | no_response
    relay_id: str = ""

    def __post_init__(self) -> None:
        if not self.relay_id:
            self.relay_id = new_id("relay")


class RelayStore:
    """Small JSON store with atomic writes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._records: dict[str, RelayRecord] = {}
        if path and path.exists():
            for item in json.loads(path.read_text()):
                record = RelayRecord(**item)
                self._records[record.relay_id] = record

    def add(self, record: RelayRecord) -> None:
        self._records[record.relay_id] = record
        self._flush()

    def get(self, relay_id: str) -> RelayRecord | None:
        return self._records.get(relay_id)

    def pending(self) -> list[RelayRecord]:
        """Answered calls with a message not yet announced to the user."""
        return [r for r in self._records.values()
                if r.call_outcome == "answered" and r.caretaker_message and r.delivered_to_user_at is None]

    def mark_delivered(self, relay_id: str, user_response: str | None) -> RelayRecord:
        record = self._records[relay_id]
        record.delivered_to_user_at = now_iso()
        record.user_response = user_response
        self._flush()
        return record

    def _flush(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(r) for r in self._records.values()], indent=2))
        os.replace(tmp, self.path)
