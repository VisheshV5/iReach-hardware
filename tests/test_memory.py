from pathlib import Path

import pytest

from reach.memory.store import LocationMemory
from reach.results import ReasonCode

PLACES = {"drawer_01", "tray_01", "handoff_pad"}


def test_statement_survives_restart(tmp_path: Path):
    db = tmp_path / "memory.db"
    memory = LocationMemory(db, PLACES)
    memory.remember("my pill bottle", "drawer_01")
    memory.close()

    record = LocationMemory(db, PLACES).lookup("pill bottle")
    assert record is not None
    assert record.location_id == "drawer_01"
    assert record.source == "user_statement"
    assert record.verification_status == "unverified"
    assert record.last_verified_at is None


def test_correction_keeps_provenance(tmp_path: Path):
    memory = LocationMemory(tmp_path / "m.db", PLACES)
    memory.remember("my pill bottle", "drawer_01")
    memory.remember("the pill bottle", "tray_01")  # "Actually, it's on the tray."

    record = memory.lookup("pill bottle")
    assert record.location_id == "tray_01"
    assert [h["location_id"] for h in memory.history(record.object_id)] == ["drawer_01", "tray_01"]


def test_forget(tmp_path: Path):
    memory = LocationMemory(tmp_path / "m.db", PLACES)
    memory.remember("pill bottle", "drawer_01")
    assert memory.forget("my pill bottle")
    assert memory.lookup("pill bottle") is None
    assert not memory.forget("pill bottle")


def test_unknown_location_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        LocationMemory(tmp_path / "m.db", PLACES).remember("keys", "kitchen")


def test_contradiction_does_not_overwrite_location(tmp_path: Path):
    memory = LocationMemory(tmp_path / "m.db", PLACES)
    memory.remember("pill bottle", "drawer_01")
    memory.mark_contradicted("pill bottle")
    record = memory.lookup("pill bottle")
    assert record.location_id == "drawer_01"
    assert record.verification_status == "contradicted"


def test_observation_marks_verified(tmp_path: Path):
    memory = LocationMemory(tmp_path / "m.db", PLACES)
    memory.remember("pill bottle", "drawer_01")
    record = memory.mark_observed("pill bottle", "handoff_pad")
    assert (record.location_id, record.source, record.verification_status) == ("handoff_pad", "observation", "verified")
    assert record.last_verified_at is not None


def test_ambiguous_identity_asks(make_system):
    system = make_system()
    system.memory.remember("red cup", "tray_01")
    system.memory.remember("blue cup", "drawer_01")
    system.memory.add_alias("red cup", "cup")
    system.memory.add_alias("blue cup", "cup")

    result = system.agent.lookup_location("cup")
    assert result.reason_code is ReasonCode.AMBIGUOUS_OBJECT
    assert "red cup" in result.message and "blue cup" in result.message
