"""Group 52 — Race Plan UAT remediation / behaviour pins.

The Group 52 UAT harness found **no defects** in the Group 48-51 Race Plan surface
(the full and incomplete Porsche/Fuji scenarios both behave correctly). Rather than
add tests for fixes that were not needed, this file PINS the UAT-critical behaviours
as regression guards, so a future change that breaks one is caught immediately.

All tests are pure/offline (SQLite `:memory:`; UI wiring source-verified).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.session_db import SessionDB  # noqa: E402
from strategy.race_strategy_session_adapter import extract_session_strategy_samples  # noqa: E402
from strategy.race_strategy_pipeline import recommend_strategy_from_session  # noqa: E402
from ui.race_strategy_vm import build_race_plan_view_model, render_race_plan_html  # noqa: E402
from ui.race_strategy_readiness_vm import (  # noqa: E402
    build_race_plan_readiness, build_session_diagnostics,
    validate_event_settings, empty_state_messages,
    ReadinessLevel, CheckStatus,
)
from strategy.race_strategy_evidence import StrategyConfidence  # noqa: E402


def _seed(db, *, n=12, fuel=4.0, compound="RM", car_id=911, track="Fuji Speedway"):
    sid = db.open_session(car_id=car_id, track=track, session_type="Practice", car_name="RSR")
    rem = 100.0
    for i in range(n):
        db.write_lap(session_id=sid, lap_num=i + 1, lap_time_ms=100000 + i * 80,
                     fuel_used=fuel, stats=None, compound=compound,
                     fuel_start=rem, fuel_end=rem - fuel)
        rem -= fuel
    return sid


def _es(**over):
    es = dict(
        car_id=911, track="Fuji Speedway", layout_id="fuji__full",
        race_duration_minutes=50.0, race_laps=0, fuel_multiplier=3.0,
        tyre_multiplier=8.0, refuel_rate_lps=1.0, pit_loss_seconds=22.0,
        starting_fuel_pct=100.0, available_compounds=("RM", "RH"),
        required_compounds=(), mandatory_pit_stops=0,
    )
    es.update(over)
    return es


@pytest.fixture()
def db():
    yield SessionDB(":memory:")


class TestSelectedSessionDrivesBuild:
    def test_assemble_uses_selected_session_id(self):
        src = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
        # _assemble_race_plan_inputs resolves via the selector, not the raw active id.
        start = src.index("def _assemble_race_plan_inputs(self)")
        end = src.index("\n    def ", start + 1)
        body = src[start:end]
        assert "self._selected_race_plan_session_id()" in body


class TestReadinessAgreesWithEvidence:
    def test_ready_matches_high_confidence(self, db):
        sid = _seed(db)
        samples = extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji Speedway")
        readiness = build_race_plan_readiness(samples=samples, event_settings=_es())
        result = recommend_strategy_from_session(db, session_id=sid, **{
            k: _es()[k] for k in ("car_id", "track", "race_duration_minutes",
                                  "fuel_multiplier", "tyre_multiplier", "refuel_rate_lps",
                                  "pit_loss_seconds", "available_compounds")})
        assert readiness.overall_readiness == ReadinessLevel.READY
        assert result.confidence == StrategyConfidence.HIGH

    def test_insufficient_matches_no_recommendation(self, db):
        samples = extract_session_strategy_samples(db, 999)
        readiness = build_race_plan_readiness(samples=samples, event_settings=_es())
        result = recommend_strategy_from_session(db, session_id=999, **{
            k: _es()[k] for k in ("car_id", "track", "race_duration_minutes",
                                  "fuel_multiplier", "tyre_multiplier", "refuel_rate_lps",
                                  "pit_loss_seconds", "available_compounds")})
        assert readiness.overall_readiness == ReadinessLevel.INSUFFICIENT_EVIDENCE
        assert not result.recommendation.has_recommendation


class TestLabellingAndMissing:
    def test_manual_pit_loss_labelled_manual(self):
        v = validate_event_settings(_es(pit_loss_is_manual=True))
        assert v.field_status["pit_loss_seconds"] == CheckStatus.MANUAL

    def test_missing_refuel_in_missing_evidence(self, db):
        r = build_race_plan_readiness(samples=extract_session_strategy_samples(db, _seed(db), expected_car_id=911, expected_track="Fuji Speedway"),
                                      event_settings=_es(refuel_rate_lps=0.0))
        assert "refuel rate" in r.missing


class TestEmptyStatesDoNotCrash:
    def test_no_session_renders(self, db):
        result = recommend_strategy_from_session(db, session_id=0, car_id=911, track="Fuji Speedway",
                                                 race_duration_minutes=50.0, fuel_multiplier=3.0,
                                                 tyre_multiplier=8.0, refuel_rate_lps=1.0,
                                                 pit_loss_seconds=22.0, available_compounds=("RM", "RH"))
        vm = build_race_plan_view_model(result)
        assert render_race_plan_html(vm)  # no crash
        assert not vm.has_recommendation

    def test_no_clean_laps_message_actionable(self, db):
        sid = db.open_session(car_id=911, track="Fuji Speedway", session_type="Practice", car_name="RSR")
        db.write_lap(session_id=sid, lap_num=1, lap_time_ms=100000, fuel_used=4.0,
                     stats=None, compound="RM", is_pit_lap=True)
        s = extract_session_strategy_samples(db, sid, expected_car_id=911, expected_track="Fuji Speedway")
        d = build_session_diagnostics(s, event_car_id=911, event_track="Fuji Speedway")
        assert "no clean laps" in d.message.lower()
        msgs = empty_state_messages(s, _es())
        assert any("clean" in m.lower() and "record" in m.lower() for m in msgs)


class TestCandidateTableLegalOnly:
    def test_illegal_not_shown(self, db):
        # Heavy fuel makes no-stop illegal → excluded from scored rows.
        sid = _seed(db, fuel=6.0)
        vm = build_race_plan_view_model(recommend_strategy_from_session(
            db, session_id=sid, car_id=911, track="Fuji Speedway",
            race_duration_minutes=50.0, fuel_multiplier=3.0, tyre_multiplier=8.0,
            refuel_rate_lps=1.0, pit_loss_seconds=22.0, available_compounds=("RM", "RH")))
        ids = {r["candidate_id"] for r in vm.candidate_comparison_rows}
        assert "nostop" not in ids


class TestNoFalseCertainty:
    def test_absent(self, db):
        vm = build_race_plan_view_model(recommend_strategy_from_session(
            db, session_id=_seed(db), car_id=911, track="Fuji Speedway",
            race_duration_minutes=50.0, fuel_multiplier=3.0, tyre_multiplier=8.0,
            refuel_rate_lps=1.0, pit_loss_seconds=22.0, available_compounds=("RM", "RH")))
        text = render_race_plan_html(vm).lower()
        for banned in ("guaranteed", "perfect strategy", "the winning strategy"):
            assert banned not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
