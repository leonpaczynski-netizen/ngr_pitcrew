"""Group 49 — Race Strategy Brain Phase 3: SessionDB adapter tests.

Covers strategy/race_strategy_session_adapter.py:
  • reads clean lap / fuel / tyre-proxy / compound samples from SessionDB
  • records missing fuel/tyre/compound as missing evidence
  • handles no-session, no-laps, and car/track mismatch safely
  • is strictly read-only (the mock exposes ONLY the two read methods it needs)

All tests are pure/offline — a lightweight duck-typed mock DB (and, where useful,
an in-memory SessionDB). No disk-backed runtime files are touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.race_strategy_session_adapter import (  # noqa: E402
    SessionStrategySamples,
    extract_session_strategy_samples,
    MISS_SESSION, MISS_LAPS, MISS_FUEL, MISS_TYRE, MISS_COMPOUND,
    MISS_CAR_TRACK_MISMATCH, MIN_STINT_LAPS_FOR_WEAR,
)


def _lap(n, ms, *, fuel_used=0.0, compound="RM", is_pit=0, is_out=0,
         fuel_start=0.0, fuel_end=0.0):
    return {
        "lap_num": n, "lap_time_ms": ms, "fuel_used": fuel_used,
        "compound": compound, "is_pit_lap": is_pit, "is_out_lap": is_out,
        "fuel_start": fuel_start, "fuel_end": fuel_end,
    }


class MockDB:
    """Duck-typed SessionDB exposing ONLY the two read methods the adapter uses.

    If the adapter ever tried to call a write method it would AttributeError —
    which is exactly the read-only guarantee we want to hold.
    """

    def __init__(self, meta, laps):
        self._meta = meta
        self._laps = laps

    def get_session_meta(self, session_id):
        if not self._meta or session_id != self._meta.get("id"):
            return None
        return dict(self._meta)

    def get_session_laps(self, session_id, exclude_pit=False, exclude_out=False):
        rows = list(self._laps)
        if exclude_pit:
            rows = [r for r in rows if not r.get("is_pit_lap")]
        if exclude_out:
            rows = [r for r in rows if not r.get("is_out_lap")]
        return [dict(r) for r in rows]


def _good_db(session_id=1, car_id=911, track="Fuji"):
    meta = {"id": session_id, "car_id": car_id, "car_name": "RSR", "config_id": "cfg1",
            "track": track, "session_type": "Practice", "total_laps": 10, "event_id": 0}
    laps = [
        _lap(1, 100000, fuel_used=4.0),
        _lap(2, 100080, fuel_used=4.0),
        _lap(3, 100160, fuel_used=4.0),
        _lap(4, 100240, fuel_used=4.0),
        _lap(5, 100320, fuel_used=4.0),
    ]
    return MockDB(meta, laps), session_id


class TestReads:
    def test_reads_clean_lap_samples(self):
        db, sid = _good_db()
        s = extract_session_strategy_samples(db, sid)
        assert isinstance(s, SessionStrategySamples)
        assert s.clean_lap_count == 5
        assert s.lap_samples[0] == pytest.approx(100.0)

    def test_reads_fuel_samples(self):
        db, sid = _good_db()
        s = extract_session_strategy_samples(db, sid)
        assert len(s.fuel_samples) == 5
        assert s.fuel_samples[0] == pytest.approx(4.0)

    def test_reads_compound_samples(self):
        db, sid = _good_db()
        s = extract_session_strategy_samples(db, sid)
        assert "RM" in s.compound_samples
        assert len(s.compound_samples["RM"]) == 5

    def test_derives_tyre_wear_from_lap_drift(self):
        db, sid = _good_db()
        s = extract_session_strategy_samples(db, sid)
        # 5 rising laps → 4 positive +0.08s increments.
        assert s.tyre_wear_derived
        assert len(s.tyre_samples) == 4
        assert all(x == pytest.approx(0.08, abs=1e-3) for x in s.tyre_samples)

    def test_fuel_from_start_minus_end_when_used_absent(self):
        meta = {"id": 1, "car_id": 911, "track": "Fuji", "config_id": ""}
        laps = [_lap(i, 100000, fuel_used=0.0, fuel_start=100.0 - i * 4, fuel_end=100.0 - (i + 1) * 4)
                for i in range(1, 5)]
        s = extract_session_strategy_samples(MockDB(meta, laps), 1)
        assert len(s.fuel_samples) == 4
        assert s.fuel_samples[0] == pytest.approx(4.0)

    def test_source_summary_names_sessiondb(self):
        db, sid = _good_db()
        s = extract_session_strategy_samples(db, sid)
        assert s.source_summary.get("source") == "SessionDB"
        assert s.source_summary.get("clean_lap_count") == 5


class TestMissing:
    def test_missing_fuel_recorded(self):
        meta = {"id": 1, "car_id": 911, "track": "Fuji", "config_id": ""}
        laps = [_lap(i, 100000 + i * 80, fuel_used=0.0) for i in range(1, 6)]
        s = extract_session_strategy_samples(MockDB(meta, laps), 1)
        assert MISS_FUEL in s.missing_fields
        assert s.fuel_samples == ()

    def test_missing_tyre_recorded_when_too_few_consecutive(self):
        meta = {"id": 1, "car_id": 911, "track": "Fuji", "config_id": ""}
        # Only 2 laps → below MIN_STINT_LAPS_FOR_WEAR → no derivation.
        laps = [_lap(1, 100000, fuel_used=4.0), _lap(2, 100080, fuel_used=4.0)]
        assert MIN_STINT_LAPS_FOR_WEAR >= 3
        s = extract_session_strategy_samples(MockDB(meta, laps), 1)
        assert MISS_TYRE in s.missing_fields
        assert s.tyre_samples == ()

    def test_missing_compound_recorded(self):
        meta = {"id": 1, "car_id": 911, "track": "Fuji", "config_id": ""}
        laps = [_lap(i, 100000 + i * 80, fuel_used=4.0, compound="") for i in range(1, 6)]
        s = extract_session_strategy_samples(MockDB(meta, laps), 1)
        assert MISS_COMPOUND in s.missing_fields

    def test_derive_tyre_wear_can_be_disabled(self):
        db, sid = _good_db()
        s = extract_session_strategy_samples(db, sid, derive_tyre_wear=False)
        assert s.tyre_samples == ()
        assert MISS_TYRE in s.missing_fields


class TestSafeEdgeCases:
    def test_no_db_safe(self):
        s = extract_session_strategy_samples(None, 5)
        assert MISS_SESSION in s.missing_fields
        assert s.lap_samples == ()

    def test_no_session_safe(self):
        db = MockDB(None, [])
        s = extract_session_strategy_samples(db, 99)
        assert MISS_SESSION in s.missing_fields

    def test_zero_session_id_safe(self):
        db, _ = _good_db()
        s = extract_session_strategy_samples(db, 0)
        assert MISS_SESSION in s.missing_fields

    def test_no_laps_safe(self):
        meta = {"id": 1, "car_id": 911, "track": "Fuji", "config_id": ""}
        s = extract_session_strategy_samples(MockDB(meta, []), 1)
        assert MISS_LAPS in s.missing_fields
        assert s.lap_samples == ()

    def test_car_mismatch_returns_no_samples(self):
        db, sid = _good_db(car_id=911)
        s = extract_session_strategy_samples(db, sid, expected_car_id=222)
        assert MISS_CAR_TRACK_MISMATCH in s.missing_fields
        assert s.lap_samples == ()
        assert any("does not match" in w for w in s.warnings)

    def test_track_mismatch_returns_no_samples(self):
        db, sid = _good_db(track="Fuji")
        s = extract_session_strategy_samples(db, sid, expected_track="Suzuka")
        assert MISS_CAR_TRACK_MISMATCH in s.missing_fields
        assert s.lap_samples == ()

    def test_matching_car_track_not_flagged(self):
        db, sid = _good_db(car_id=911, track="Fuji")
        s = extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji")
        assert MISS_CAR_TRACK_MISMATCH not in s.missing_fields
        assert s.clean_lap_count == 5


class TestReadOnly:
    def test_adapter_uses_only_read_methods(self):
        # MockDB has no write methods; a successful extract proves the adapter
        # never attempts a write (it would AttributeError otherwise).
        db, sid = _good_db()
        s = extract_session_strategy_samples(db, sid)
        assert s.clean_lap_count == 5
        assert not hasattr(db, "write_lap")

    def test_pit_laps_collected_from_all_rows(self):
        meta = {"id": 1, "car_id": 911, "track": "Fuji", "config_id": ""}
        laps = [
            _lap(1, 100000, fuel_used=4.0),
            _lap(2, 100080, fuel_used=4.0),
            _lap(3, 100160, fuel_used=4.0, is_pit=1),  # pit lap excluded from clean
            _lap(4, 100240, fuel_used=4.0),
        ]
        s = extract_session_strategy_samples(MockDB(meta, laps), 1)
        assert 3 in s.pit_samples
        assert s.clean_lap_count == 3  # pit lap excluded


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
