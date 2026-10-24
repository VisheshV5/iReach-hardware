"""SQLite location memory.

Records are search hints, not visual truth. User statements, observations and contradictions are kept
distinct, and every change is appended to `location_history` so provenance survives corrections.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

from reach.logging import now_iso

_FILLER = re.compile(r"^(my|the|a|an|our)\s+")

SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    object_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    aliases TEXT NOT NULL,
    location_id TEXT NOT NULL,
    source TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    last_verified_at TEXT,
    verification_status TEXT NOT NULL,
    evidence_event_id TEXT
);
CREATE TABLE IF NOT EXISTS location_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id TEXT NOT NULL,
    change TEXT NOT NULL,
    location_id TEXT,
    source TEXT,
    verification_status TEXT,
    at TEXT NOT NULL,
    evidence_event_id TEXT
);
"""


def normalize(name: str) -> str:
    return _FILLER.sub("", name.lower().strip()).strip()


@dataclass
class LocationRecord:
    object_id: str
    display_name: str
    location_id: str
    source: str  # user_statement | observation
    recorded_at: str
    verification_status: str  # unverified | verified | contradicted
    aliases: list[str] = field(default_factory=list)
    last_verified_at: str | None = None
    evidence_event_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class LocationMemory:
    def __init__(self, path: Path | str, known_locations: set[str] | None = None) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self.known_locations = known_locations

    def close(self) -> None:
        self._db.close()

    def find(self, name: str) -> list[LocationRecord]:
        """All records whose id, display name or alias matches; more than one means ask the user."""
        key = normalize(name)
        return [r for r in self.all() if key in {r.object_id, normalize(r.display_name), *r.aliases}]

    def lookup(self, name: str) -> LocationRecord | None:
        matches = self.find(name)
        return matches[0] if len(matches) == 1 else None

    def all(self) -> list[LocationRecord]:
        rows = self._db.execute("SELECT * FROM locations ORDER BY object_id").fetchall()
        return [self._record(row) for row in rows]

    def remember(self, name: str, location_id: str, evidence_event_id: str | None = None) -> LocationRecord:
        """Store a user statement. Replaces the active expectation but keeps history."""
        self._check_location(location_id)
        existing = self.lookup(name)
        now = now_iso()
        if existing:
            record = existing
            record.location_id = location_id
        else:
            key = normalize(name)
            record = LocationRecord(object_id=re.sub(r"\W+", "_", key), display_name=name.strip(),
                                    location_id=location_id, source="", recorded_at=now,
                                    verification_status="", aliases=[key])
        record.source = "user_statement"
        record.recorded_at = now
        record.verification_status = "unverified"
        record.evidence_event_id = evidence_event_id
        self._save(record, "user_statement")
        return record

    def mark_observed(self, name: str, location_id: str, evidence_event_id: str | None = None) -> LocationRecord:
        """Record a verified observation, e.g. after a confirmed placement."""
        self._check_location(location_id)
        record = self.lookup(name)
        now = now_iso()
        if record is None:
            key = normalize(name)
            record = LocationRecord(object_id=re.sub(r"\W+", "_", key), display_name=name.strip(),
                                    location_id=location_id, source="observation", recorded_at=now,
                                    verification_status="verified", aliases=[key])
        record.location_id = location_id
        record.source = "observation"
        record.recorded_at = now
        record.last_verified_at = now
        record.verification_status = "verified"
        record.evidence_event_id = evidence_event_id
        self._save(record, "observation")
        return record

    def mark_contradicted(self, name: str, evidence_event_id: str | None = None) -> LocationRecord | None:
        """The object was not where expected. Keep the location (no invented replacement), flag it."""
        record = self.lookup(name)
        if record is None:
            return None
        record.verification_status = "contradicted"
        record.evidence_event_id = evidence_event_id
        self._save(record, "contradicted")
        return record

    def add_alias(self, name: str, alias: str) -> None:
        record = self.lookup(name)
        if record and normalize(alias) not in record.aliases:
            record.aliases.append(normalize(alias))
            self._save(record, "alias_added")

    def forget(self, name: str) -> bool:
        record = self.lookup(name)
        if record is None:
            return False
        self._db.execute("DELETE FROM locations WHERE object_id = ?", (record.object_id,))
        self._history(record, "forgotten")
        self._db.commit()
        return True

    def history(self, object_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM location_history WHERE object_id = ? ORDER BY id", (object_id,))
        return [dict(row) for row in rows.fetchall()]

    def _check_location(self, location_id: str) -> None:
        if self.known_locations is not None and location_id not in self.known_locations:
            raise ValueError(f"unknown location {location_id!r}")

    def _save(self, record: LocationRecord, change: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO locations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record.object_id, record.display_name, json.dumps(record.aliases), record.location_id, record.source,
             record.recorded_at, record.last_verified_at, record.verification_status, record.evidence_event_id),
        )
        self._history(record, change)
        self._db.commit()

    def _history(self, record: LocationRecord, change: str) -> None:
        self._db.execute(
            "INSERT INTO location_history (object_id, change, location_id, source, verification_status, at, "
            "evidence_event_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record.object_id, change, record.location_id, record.source, record.verification_status, now_iso(),
             record.evidence_event_id),
        )

    @staticmethod
    def _record(row: sqlite3.Row) -> LocationRecord:
        data = dict(row)
        data["aliases"] = json.loads(data["aliases"])
        return LocationRecord(**data)
