"""Group 49 — Race Strategy Brain Phase 3: build-evidence-from-session tests.

Covers strategy/race_strategy_from_session.py against a REAL in-memory SessionDB:
  • builds RaceStrategyEvidence from stored session samples
  • preserves event settings; uses measured data; fabricates nothing
  • confidence drops when fuel/tyre data is missing
  • INSUFFICIENT_EVIDENCE when critical data is absent
  • source summary identifies SessionDB as the evidence source
  • EventContext bridge sources canonical event settings

All tests are pure/offline (SQLite `:memory:`); no disk-backed runtime files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_evidence import RaceStrategyEvidence, StrategyConfidence  # noqa: E402
from strategy.race_strategy_from_session import (  # noqa: E402
    SessionEvidenceResult,
    build_strategy_evidence_from_session,
    build_strategy_evidence_from_event_context,
)


def _seed(db, *, car_id=911, track="Fuji Speedway", n=12, fuel=4.0,
          compound="RM", base_ms=100000, drift_ms=80):
    sid = db.open_session(car_id=car_id, track=track, session_type="Practice",
                          car_name="RSR")
    remaining = 100.0
    for i in range(n):
        db.write_lap(
            session_id=sid, lap_num=i + 1, lap_time_ms=base_ms + i * drift_ms,
            fuel_used=fuel, stats=None, compound=compound,
            fuel_start=remaining, fuel_end=remaining - fuel,
        )
        remaining -= fuel
    return sid


@pytest.fixture()
def db():
    d = SessionDB(":memory:")
    yield d


def _event_kwargs(**over):
    kw = dict(
        car_id=911, track="Fuji Speedway", layout_id="fuji__full",
        race_duration_minutes=50.0, race_laps=0,
        fuel_multiplier=3.0, tyre_multiplier=8.0,
        refuel_rate_lps=1.0, pit_loss_seconds=22.0,
        available_compounds=("RM", "RH"), required_compounds=(),
        mandatory_pit_stops=0, weather_context="dry_stable",
    )
    kw.update(over)
    return kw


class TestBuild:
    def test_builds_evidence_from_session(self, db):
        sid = _seed(db)
        res = build_strategy_evidence_from_session(db, session_id=sid, **_event_kwargs())
        assert isinstance(res, SessionEvidenceResult)
        assert isinstance(res.evidence, RaceStrategyEvidence)
        assert res.evidence.has_lap_data()
        assert res.evidence.mean_fuel_per_lap() == pytest.approx(4.0)

    def test_preserves_event_settings(self, db):
        sid = _seed(db)
        ev = build_strategy_evidence_from_session(db, session_id=sid, **_event_kwargs()).evidence
        assert ev.tyre_multiplier == 8.0
        assert ev.fuel_multiplier == 3.0
        assert ev.refuel_rate_lps == 1.0
        assert ev.pit_loss_seconds == 22.0
        assert ev.available_compounds == ("RM", "RH")

    def test_uses_measured_session_data(self, db):
        sid = _seed(db, n=12)
        ev = build_strategy_evidence_from_session(db, session_id=sid, **_event_kwargs()).evidence
        assert len(ev.lap_time_samples) == 12
        assert ev.representative_lap_s() > 0
        assert len(ev.tyre_wear_samples) == 11  # derived increments

    def test_source_summary_identifies_sessiondb(self, db):
        sid = _seed(db)
        res = build_strategy_evidence_from_session(db, session_id=sid, **_event_kwargs())
        assert res.source_summary.get("source") == "SessionDB"
        assert res.source_summary["fields"]["race_pace"].startswith("SessionDB measured")
        assert res.source_summary["fields"]["refuel_rate"] == "event setting"


class TestNoFabrication:
    def test_confidence_drops_when_fuel_missing(self, db):
        sid = _seed(db, fuel=0.0)  # no fuel signal at all
        res = build_strategy_evidence_from_session(db, session_id=sid, **_event_kwargs())
        # No fuel → cannot estimate total race time → INSUFFICIENT_EVIDENCE.
        assert res.confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE
        assert "no_fuel_use_samples" in res.evidence.missing_evidence

    def test_confidence_drops_when_tyre_missing(self, db):
        # Only 2 laps → no long-run tyre derivation, but enough for lap+fuel.
        sid = _seed(db, n=2)
        res = build_strategy_evidence_from_session(db, session_id=sid, **_event_kwargs())
        assert res.confidence.rank <= StrategyConfidence.MEDIUM.rank
        assert res.confidence != StrategyConfidence.HIGH

    def test_no_session_is_insufficient(self, db):
        res = build_strategy_evidence_from_session(db, session_id=999, **_event_kwargs())
        assert res.confidence == StrategyConfidence.INSUFFICIENT_EVIDENCE
        assert res.evidence.representative_lap_s() == 0.0

    def test_pit_loss_unknown_recorded(self, db):
        sid = _seed(db)
        kw = _event_kwargs(pit_loss_seconds=0.0)
        res = build_strategy_evidence_from_session(db, session_id=sid, **kw)
        assert "pit_loss_unknown" in res.evidence.missing_evidence
        assert res.source_summary["fields"]["pit_loss"] == "default/missing"

    def test_unknown_event_fields_not_invented(self, db):
        sid = _seed(db)
        kw = _event_kwargs(refuel_rate_lps=0.0, tyre_multiplier=0.0)
        ev = build_strategy_evidence_from_session(db, session_id=sid, **kw).evidence
        assert ev.refuel_rate_lps == 0.0
        assert ev.tyre_multiplier == 0.0


class TestEventContextBridge:
    def test_builds_from_event_context(self, db):
        sid = _seed(db)

        class _EC:
            track = "Fuji Speedway"
            layout_id = "fuji__full"
            is_lap_race = False
            is_timed = True
            laps = 0
            race_duration_minutes = 50
            tyre_wear_multiplier = 8.0
            fuel_multiplier = 3.0
            refuel_rate_lps = 1.0
            mandatory_stops = 0
            available_tyres = ("RM", "RH")
            required_tyres = ()
            weather = "Fixed Dry"

        res = build_strategy_evidence_from_event_context(
            db, session_id=sid, event_context=_EC(), pit_loss_seconds=22.0
        )
        ev = res.evidence
        assert ev.tyre_multiplier == 8.0
        assert ev.fuel_multiplier == 3.0
        assert ev.refuel_rate_lps == 1.0
        assert ev.race_duration_minutes == 50.0
        assert ev.available_compounds == ("RM", "RH")
        assert ev.has_lap_data()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
