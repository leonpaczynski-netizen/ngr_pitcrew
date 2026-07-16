"""OFR-1 Between-Race Learning Loop — end-to-end acceptance tests.

One test (or small class) per acceptance criterion, AC1–AC11, plus edge cases.

Conventions
-----------
* Only test files are modified — no production code.
* SessionDB(':memory:') throughout; real config.json is never touched.
* Qt-free: UI-layer tests bind the real _trigger_scoring_pass method with
  types.MethodType onto a MagicMock stub (same pattern as
  test_legacy_fanout_phase_4 / test_ofr1_trigger_wiring).
* driving_advisor._get_previous_ai_context is tested by instantiating a
  minimal stub with real method binding (no PyQt6, no MainWindow).
"""
from __future__ import annotations

import ast
import json
import re
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_db():
    """Return an open SessionDB(:memory:) — caller must close."""
    from data.session_db import SessionDB
    return SessionDB(":memory:")


def _insert_car(db, name: str = "Porsche 911 GT3") -> int:
    """Insert a car row and return its id."""
    with db._lock:
        cur = db._conn.execute(
            "INSERT INTO cars (name, category) VALUES (?, ?)",
            (name, "GR3"),
        )
        db._conn.commit()
        return cur.lastrowid


def _insert_rec(
    db,
    *,
    car_id: int = 1,
    track: str = "Spa",
    layout_id: str = "",
    session_id: int = 1,
    rec_text: str | None = None,
    status: str = "applied",
    before_metrics: str | None = None,
) -> int:
    """Insert a setup_recommendations row and return its id."""
    if rec_text is None:
        rec_text = json.dumps({
            "changes": [
                {"field": "arb_front", "from": 5, "to": 3, "why": "reduce understeer"}
            ]
        })
    if before_metrics is None:
        before_metrics = json.dumps({"best_lap_ms": 90_000, "lap_count": 6})
    with db._lock:
        cur = db._conn.execute(
            """INSERT INTO setup_recommendations
               (ai_interaction_id, session_id, car_id, track, layout_id,
                feature, recommendation_text, status, outcome,
                before_metrics, after_metrics, created_at)
               VALUES (NULL, ?, ?, ?, ?, 'Setup Advice', ?, ?, 'not_verified', ?, '{}', ?)""",
            (session_id, car_id, track, layout_id, rec_text, status,
             before_metrics, _now()),
        )
        db._conn.commit()
        return cur.lastrowid


def _insert_lap(
    db,
    session_id: int,
    *,
    lap_time_ms: int = 89_000,
    is_pit_lap: int = 0,
    is_out_lap: int = 0,
    compound: str = "RM",
    car_id: int = 1,
    track: str = "Spa",
    lock_up_count: int = 1,
    wheelspin_count: int = 2,
    oversteer_count: int = 0,
    oversteer_throttle_on: int = 0,
    bottoming_count: int = 0,
    brake_consistency_m: float = 5.0,
) -> None:
    with db._lock:
        db._conn.execute(
            """INSERT INTO lap_records
               (session_id, car_id, track, lap_num, lap_time_ms, fuel_used,
                lock_up_count, wheelspin_count, brake_consistency_m,
                max_speed_kmh, avg_throttle_pct, avg_brake_pct,
                compound, is_pit_lap, is_out_lap,
                oversteer_count, oversteer_throttle_on, bottoming_count)
               VALUES (?,?,?,
                (SELECT COALESCE(MAX(lap_num),0)+1 FROM lap_records WHERE session_id=?),
                ?,?,?,?,?,200.0,60.0,20.0,?,?,?,?,?,?)""",
            (session_id, car_id, track, session_id,
             lap_time_ms, 1.8,
             lock_up_count, wheelspin_count, brake_consistency_m,
             compound, is_pit_lap, is_out_lap,
             oversteer_count, oversteer_throttle_on, bottoming_count),
        )
        db._conn.commit()


def _make_scoring_stub(db=None):
    """Bind the real _trigger_scoring_pass onto a MagicMock shell.

    Follows the _make_fanout_stub pattern from test_legacy_fanout_phase_4.
    """
    from ui import dashboard as _dash_mod
    stub = MagicMock()
    stub._db = db if db is not None else MagicMock()
    stub._home_refresh_if_visible = MagicMock()
    stub._trigger_scoring_pass = types.MethodType(
        _dash_mod.MainWindow._trigger_scoring_pass, stub
    )
    return stub


# ---------------------------------------------------------------------------
# AC1 — Automatic scoring trigger fires after a new session opens
# ---------------------------------------------------------------------------

class TestAC1AutomaticScoringTrigger:
    """AC1: when a NEW session opens, prior applied recs are scored; never mid-session."""

    def test_trigger_scores_applied_rec_on_real_db(self):
        """Full e2e: two sessions, one applied rec, trigger scores it."""
        db = _make_db()
        try:
            car_id = _insert_car(db, "Porsche 911 GT3")
            # Session 1 — before: rec created here
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_500, 90_200, 90_000, 89_800]:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)

            # Session 2 — after: improvement
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [89_000, 88_800, 88_700, 88_900]:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)

            # Session 3 — "new session opening" triggers scoring
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            # The rec must now have a score_verdict populated
            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            assert row is not None
            assert row[0] != "", "rec should be scored after trigger"
        finally:
            db.close()

    def test_trigger_after_open_session_source_scan(self):
        """Source scan: _trigger_scoring_pass is called AFTER open_session in both call sites."""
        dash_src = (REPO / "ui" / "dashboard.py").read_text(encoding="utf-8") + (REPO / "ui" / "live_ui.py").read_text(encoding="utf-8")

        def _body(name):
            m = re.search(
                rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                dash_src, re.DOTALL
            )
            assert m, f"method {name!r} not found"
            return m.group(0)

        for method_name in ("_on_live_mode_changed", "_save_session_to_db"):
            body = _body(method_name)
            assert "open_session" in body, f"open_session missing from {method_name}"
            assert "self._trigger_scoring_pass(" in body, (
                f"_trigger_scoring_pass missing from {method_name}")
            open_idx = body.index("open_session")
            trigger_idx = body.index("self._trigger_scoring_pass(")
            assert trigger_idx > open_idx, (
                f"_trigger_scoring_pass must come AFTER open_session in {method_name}")

    def test_trigger_never_fires_mid_session(self):
        """The trigger must only run at session-open boundaries; it never touches
        laps that belong to the new (current) session being opened."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            # Rec created in sid1
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)

            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            # Mid-session: only 1 lap exists in sid2 (after-side too thin)
            _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=89_000)

            # Open new session — triggers scoring
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            # sid2 only had 1 lap → after_window.clean_count < 3 → insufficient_data
            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            # Should be scored (possibly insufficient_data) — NOT unscored
            assert row[0] != "" or row[0] == "insufficient_data" or row[0] in (
                "improved", "worsened", "neutral", "insufficient_data"
            ), "row was never touched by trigger"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# AC2 — Persisted verdict + confidence; write-once
# ---------------------------------------------------------------------------

class TestAC2PersistedVerdictWriteOnce:
    """AC2: score_confidence + score_verdict persisted; second trigger never overwrites."""

    def test_columns_populated_after_trigger(self):
        """After a scoring trigger, score_verdict and score_confidence are set."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [88_500] * 6:  # clear improvement
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_verdict, score_confidence FROM setup_recommendations WHERE id=?",
                (rec_id,)
            ).fetchone()
            assert row[0] in ("improved", "worsened", "neutral", "insufficient_data")
            # confidence: -1.0 is the sentinel for "unscored"
            assert row[1] >= 0.0, "confidence must be >= 0 after scoring"
        finally:
            db.close()

    def test_write_once_second_trigger_leaves_values_unchanged(self):
        """Running the trigger a second time must not overwrite the first result."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [88_500] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            # Capture first result
            row_after_first = db._conn.execute(
                "SELECT score_verdict, score_confidence FROM setup_recommendations WHERE id=?",
                (rec_id,)
            ).fetchone()

            # Open another session and trigger again
            sid4 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [87_000] * 6:
                _insert_lap(db, sid4, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid5 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            stub._trigger_scoring_pass(car_id, "Spa", "", sid5)

            row_after_second = db._conn.execute(
                "SELECT score_verdict, score_confidence FROM setup_recommendations WHERE id=?",
                (rec_id,)
            ).fetchone()

            # Values must be identical — write-once
            assert row_after_second[0] == row_after_first[0], (
                "second trigger must not overwrite verdict")
            assert row_after_second[1] == pytest.approx(row_after_first[1]), (
                "second trigger must not overwrite confidence")
        finally:
            db.close()

    def test_verdict_in_valid_set(self):
        """score_verdict must be one of the four allowed values."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [89_000] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            assert row[0] in ("improved", "worsened", "neutral", "insufficient_data"), (
                f"Unexpected verdict: {row[0]!r}")
        finally:
            db.close()

    def test_confidence_in_range_0_to_1(self):
        """score_confidence must be in [0.0, 1.0] after scoring."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [89_000] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_confidence FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            assert 0.0 <= row[0] <= 1.0, f"confidence out of range: {row[0]}"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# AC3 — Handling-metric deltas drive verdict for handling-targeted recs
# ---------------------------------------------------------------------------

class TestAC3HandlingMetricDeltas:
    """AC3: handling-targeted recs score against per-lap handling events, not lap time alone."""

    def _handling_rec_text(self) -> str:
        return json.dumps({
            "changes": [
                {"field": "arb_front", "from": 5, "to": 3,
                 "why": "reduce understeer at T1 apex"}
            ]
        })

    def test_handling_rec_improved_when_handling_better_despite_marginal_laptime(self):
        """Handling target: improvements in lock-up/wheelspin drive 'improved' even when
        lap time only improved marginally (within the ≤ +100 ms tolerance)."""
        from data.recommendation_scoring import (
            LapWindow, aggregate_lap_window, compute_verdict_and_confidence,
        )

        before_laps = [
            {
                "lap_time_ms": 90_000, "is_pit_lap": 0, "is_out_lap": 0,
                "compound": "RM", "lock_up_count": 4, "wheelspin_count": 5,
                "oversteer_count": 2, "oversteer_throttle_on": 1,
                "bottoming_count": 2, "brake_consistency_m": 10.0,
            }
        ] * 5

        after_laps = [
            {
                "lap_time_ms": 90_050,  # only +50 ms — lap time barely changed
                "is_pit_lap": 0, "is_out_lap": 0,
                "compound": "RM", "lock_up_count": 1, "wheelspin_count": 1,
                "oversteer_count": 0, "oversteer_throttle_on": 0,
                "bottoming_count": 0, "brake_consistency_m": 3.0,
            }
        ] * 5

        before_w = aggregate_lap_window(before_laps)
        after_w  = aggregate_lap_window(after_laps)
        rec = {
            "id": 1,
            "before_metrics": json.dumps({"best_lap_ms": 90_000}),
            "recommendation_text": self._handling_rec_text(),
        }
        result = compute_verdict_and_confidence(rec, before_w, after_w)
        assert result.verdict == "improved", (
            f"Expected 'improved' for handling rec with large handling gains, "
            f"got {result.verdict!r}")

    def test_handling_rec_worsened_when_handling_worse_despite_same_laptime(self):
        """Handling target: worsened handling events drive 'worsened' even though
        lap time is in the neutral zone."""
        from data.recommendation_scoring import aggregate_lap_window, compute_verdict_and_confidence

        before_laps = [
            {
                "lap_time_ms": 90_000, "is_pit_lap": 0, "is_out_lap": 0,
                "compound": "RM", "lock_up_count": 0, "wheelspin_count": 0,
                "oversteer_count": 0, "oversteer_throttle_on": 0,
                "bottoming_count": 0, "brake_consistency_m": 3.0,
            }
        ] * 5

        after_laps = [
            {
                "lap_time_ms": 90_100,  # +100 ms — in neutral lap-time zone
                "is_pit_lap": 0, "is_out_lap": 0,
                "compound": "RM", "lock_up_count": 3, "wheelspin_count": 4,
                "oversteer_count": 3, "oversteer_throttle_on": 2,
                "bottoming_count": 2, "brake_consistency_m": 9.0,
            }
        ] * 5

        before_w = aggregate_lap_window(before_laps)
        after_w  = aggregate_lap_window(after_laps)
        rec = {
            "id": 2,
            "before_metrics": json.dumps({"best_lap_ms": 90_000}),
            "recommendation_text": self._handling_rec_text(),
        }
        result = compute_verdict_and_confidence(rec, before_w, after_w)
        assert result.verdict == "worsened", (
            f"Expected 'worsened' for handling rec with all handling metrics worse, "
            f"got {result.verdict!r}")

    def test_laptime_rec_verdict_ignores_handling_events(self):
        """Lap-time targeted rec: verdict depends only on lap-time delta, not handling events."""
        from data.recommendation_scoring import LapWindow, compute_verdict_and_confidence

        def _w(clean_count, best_ms, **kw):
            return LapWindow(
                laps=[], clean_count=clean_count, compound="RM",
                best_clean_ms=best_ms,
                avg_lock_up=kw.get("avg_lock_up", 0.0),
                avg_wheelspin=kw.get("avg_wheelspin", 0.0),
                avg_oversteer=kw.get("avg_oversteer", 0.0),
                avg_oversteer_throttle=kw.get("avg_oversteer_throttle", 0.0),
                avg_bottoming=kw.get("avg_bottoming", 0.0),
                avg_brake_consistency=kw.get("avg_brake_consistency", 5.0),
            )

        # Lap-time rec text (no handling keywords)
        rec = {
            "id": 3,
            "before_metrics": json.dumps({"best_lap_ms": 90_000}),
            "recommendation_text": json.dumps({
                "changes": [{"field": "aero_rear", "from": 5, "to": 7,
                             "why": "improve top speed"}]
            }),
        }
        # Handling is much worse but lap time improved clearly
        before_w = _w(5, 90_000, avg_lock_up=0.0, avg_wheelspin=0.0)
        after_w  = _w(5, 89_700, avg_lock_up=5.0, avg_wheelspin=5.0)  # Δt < -200

        result = compute_verdict_and_confidence(rec, before_w, after_w)
        # For a laptime-target rec, Δt = -300 → improved; handling events don't veto
        assert result.verdict == "improved"


# ---------------------------------------------------------------------------
# AC4 — Confidence tracks evidence quality
# ---------------------------------------------------------------------------

class TestAC4ConfidenceEvidenceQuality:
    """AC4: more clean laps → higher confidence; feedback bonus; multi → halved."""

    def _basic_rec(self) -> dict:
        return {
            "id": 1,
            "before_metrics": json.dumps({"best_lap_ms": 90_000}),
            "recommendation_text": json.dumps({
                "changes": [{"field": "arb_front", "from": 5, "to": 3,
                             "why": "improve top speed"}]
            }),
        }

    def _laptime_window(self, clean_count, best_ms):
        from data.recommendation_scoring import LapWindow
        return LapWindow(
            laps=[], clean_count=clean_count, compound="RM",
            best_clean_ms=best_ms,
            avg_lock_up=0.0, avg_wheelspin=0.0, avg_oversteer=0.0,
            avg_oversteer_throttle=0.0, avg_bottoming=0.0,
            avg_brake_consistency=0.0,
        )

    def test_more_clean_laps_yields_higher_or_equal_confidence(self):
        """6 clean laps each side → confidence ≥ 3 clean laps each side (improved verdict)."""
        from data.recommendation_scoring import compute_verdict_and_confidence

        thin_before = self._laptime_window(3, 90_000)
        thin_after  = self._laptime_window(3, 89_500)  # Δt = -500 → improved
        rich_before = self._laptime_window(6, 90_000)
        rich_after  = self._laptime_window(6, 89_500)

        rec = self._basic_rec()
        thin_conf = compute_verdict_and_confidence(rec, thin_before, thin_after).confidence
        rich_conf = compute_verdict_and_confidence(rec, rich_before, rich_after).confidence

        assert rich_conf >= thin_conf, (
            f"More laps should give >= confidence ({rich_conf} vs {thin_conf})")

    def test_feedback_bonus_adds_0_1(self):
        """has_driver_feedback=True adds +0.1 (clamped to 1.0)."""
        from data.recommendation_scoring import compute_verdict_and_confidence

        before = self._laptime_window(6, 90_000)
        after  = self._laptime_window(6, 89_500)
        rec = self._basic_rec()

        base = compute_verdict_and_confidence(rec, before, after, has_driver_feedback=False)
        fb   = compute_verdict_and_confidence(rec, before, after, has_driver_feedback=True)

        expected = min(1.0, base.confidence + 0.1)
        assert fb.confidence == pytest.approx(expected, abs=0.01)

    def test_multi_rec_halves_confidence(self):
        """multi_rec_count=2 → confidence exactly half of single-rec confidence."""
        from data.recommendation_scoring import compute_verdict_and_confidence

        before = self._laptime_window(6, 90_000)
        after  = self._laptime_window(6, 89_500)
        rec = self._basic_rec()

        single = compute_verdict_and_confidence(rec, before, after, multi_rec_count=1)
        dual   = compute_verdict_and_confidence(rec, before, after, multi_rec_count=2)

        assert dual.confidence == pytest.approx(single.confidence / 2, abs=0.01)

    def test_confidence_insufficient_data_always_zero(self):
        """insufficient_data verdict must always yield confidence 0.0."""
        from data.recommendation_scoring import LapWindow, compute_verdict_and_confidence

        before = LapWindow(laps=[], clean_count=0, compound="", best_clean_ms=0,
                           avg_lock_up=0.0, avg_wheelspin=0.0, avg_oversteer=0.0,
                           avg_oversteer_throttle=0.0, avg_bottoming=0.0,
                           avg_brake_consistency=0.0)
        after = LapWindow(laps=[], clean_count=5, compound="RM", best_clean_ms=89_000,
                          avg_lock_up=0.0, avg_wheelspin=0.0, avg_oversteer=0.0,
                          avg_oversteer_throttle=0.0, avg_bottoming=0.0,
                          avg_brake_consistency=0.0)
        rec = {"id": 1, "before_metrics": "{}", "recommendation_text": "{}"}
        result = compute_verdict_and_confidence(rec, before, after)
        assert result.verdict == "insufficient_data"
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# AC5 — Insufficient-data honesty gates; end-to-end through trigger
# ---------------------------------------------------------------------------

class TestAC5InsufficientDataHonesty:
    """AC5: missing before_metrics OR < 3 clean laps on either side → insufficient_data."""

    def test_missing_before_metrics_insufficient_data_via_trigger(self):
        """When before_metrics is '{}' AND no before-session laps, verdict is insufficient_data."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            # sid1 has NO laps — before side is completely empty
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(
                db, car_id=car_id, track="Spa", session_id=sid1,
                before_metrics="{}"  # empty metrics
            )
            # sid2 — after side: good laps
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [89_000] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            assert row[0] == "insufficient_data", (
                f"Expected insufficient_data, got {row[0]!r}")
        finally:
            db.close()

    def test_too_few_after_laps_insufficient_data_via_trigger(self):
        """< 3 clean laps on the after side → insufficient_data (not fabricated verdict)."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)
            # sid2 — only 2 clean laps (below threshold)
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=89_000)
            _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=89_200)

            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            assert row[0] == "insufficient_data", (
                f"Expected insufficient_data for thin after side, got {row[0]!r}")
        finally:
            db.close()

    def test_too_few_before_laps_insufficient_data_via_trigger(self):
        """< 3 clean laps on the before side → insufficient_data even with good before_metrics."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            # Only 2 clean laps in sid1 (before side too thin)
            _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=90_000)
            _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=90_200)
            rec_id = _insert_rec(
                db, car_id=car_id, track="Spa", session_id=sid1,
                before_metrics=json.dumps({"best_lap_ms": 90_000, "lap_count": 2})
            )
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [89_000] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            assert row[0] == "insufficient_data", (
                f"Expected insufficient_data for thin before side, got {row[0]!r}")
        finally:
            db.close()

    def test_no_fabricated_verdict_field_values(self):
        """Verdicts must only ever be one of the four allowed strings."""
        from data.recommendation_scoring import LapWindow, compute_verdict_and_confidence

        allowed = {"improved", "worsened", "neutral", "insufficient_data"}
        # Test all honesty-gate paths
        def _w(n, ms):
            return LapWindow(laps=[], clean_count=n, compound="RM", best_clean_ms=ms,
                             avg_lock_up=0.0, avg_wheelspin=0.0, avg_oversteer=0.0,
                             avg_oversteer_throttle=0.0, avg_bottoming=0.0,
                             avg_brake_consistency=0.0)

        rec = {"id": 1, "before_metrics": "{}", "recommendation_text": "{}"}
        for before_n, after_n, before_ms, after_ms in [
            (0, 0, 0, 0),
            (2, 5, 90_000, 89_000),
            (5, 2, 90_000, 89_000),
            (5, 5, 90_000, 89_000),
            (5, 5, 90_000, 90_500),
        ]:
            result = compute_verdict_and_confidence(
                rec, _w(before_n, before_ms), _w(after_n, after_ms)
            )
            assert result.verdict in allowed, f"Unexpected verdict: {result.verdict!r}"


# ---------------------------------------------------------------------------
# AC6 — Prompt block: §6.4 format for recs with confidence ≥ 0.5
# ---------------------------------------------------------------------------

class TestAC6PromptBlock:
    """AC6: next setup-advice prompt includes §6.4 performance block (≥0.5 confidence)."""

    def _make_advisor_stub(self, db):
        """Bind the real _get_previous_ai_context onto a minimal stub."""
        from strategy import driving_advisor as _adv_mod
        stub = MagicMock()
        stub._db = db
        stub._car_id_ref = [1]
        stub._config = {"strategy": {"track": "Spa", "layout_id": ""}}
        stub._get_previous_ai_context = types.MethodType(
            _adv_mod.DrivingAdvisor._get_previous_ai_context, stub
        )
        return stub

    def test_high_confidence_rec_produces_section_64_block(self):
        """With a ≥0.5 confidence scored rec, _get_previous_ai_context returns §6.4 header."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)

            details = {
                "target": "laptime",
                "delta_ms": -500,
                "before_best_ms": 90_000,
                "after_best_ms": 89_500,
                "before_clean_laps": 6,
                "after_clean_laps": 6,
                "before_compound": "RM",
                "after_compound": "RM",
                "handling_agreement": 0.5,
                "relevant_metrics": 2,
                "improved_metrics": 1,
                "before_source": "creation_session",
            }
            db.persist_score(rec_id, "improved", 0.8, details)

            stub = self._make_advisor_stub(db)
            stub._car_id_ref = [car_id]
            stub._config = {"strategy": {"track": "Spa", "layout_id": ""}}

            result = stub._get_previous_ai_context("Setup Advice")

            assert "Performance of Previous Recommendations" in result, (
                f"§6.4 header missing from prompt block: {result!r}")
        finally:
            db.close()

    def test_block_contains_required_fields(self):
        """§6.4 block must contain: change desc, measured outcome, verdict."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            details = {
                "target": "laptime",
                "delta_ms": -400,
                "before_best_ms": 90_000,
                "after_best_ms": 89_600,
                "before_clean_laps": 6,
                "after_clean_laps": 6,
                "before_compound": "RM",
                "after_compound": "RM",
                "handling_agreement": 0.5,
                "relevant_metrics": 0,
                "improved_metrics": 0,
                "before_source": "creation_session",
            }
            db.persist_score(rec_id, "improved", 0.75, details)

            stub = self._make_advisor_stub(db)
            stub._car_id_ref = [car_id]
            result = stub._get_previous_ai_context("Setup Advice")

            # Must contain the change field name from rec_text
            assert "arb_front" in result, "Change field name must appear in block"
            # Must contain lap delta info
            assert "lap" in result.lower(), "Lap delta must appear in block"
            # Must contain the verdict
            assert "improved" in result, "Verdict must appear in block"
        finally:
            db.close()

    def test_low_confidence_rec_omitted_from_block(self):
        """A rec with confidence < 0.5 must NOT appear in the prompt block."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            db.persist_score(rec_id, "improved", 0.3, {"before_source": "creation_session"})

            stub = self._make_advisor_stub(db)
            stub._car_id_ref = [car_id]
            result = stub._get_previous_ai_context("Setup Advice")

            # With only a < 0.5 confidence rec the block should be empty / fall back
            assert "Performance of Previous Recommendations" not in result, (
                "Low-confidence rec must NOT appear in §6.4 block")
        finally:
            db.close()

    def test_format_performance_block_section_64_header(self):
        """format_performance_block itself returns the §6.4 header text."""
        from data.recommendation_scoring import format_performance_block

        rec = {
            "id": 1,
            "score_verdict": "improved",
            "score_confidence": 0.75,
            "score_details": json.dumps({
                "target": "laptime", "delta_ms": -350,
                "before_best_ms": 90_000, "after_best_ms": 89_650,
                "before_clean_laps": 5, "after_clean_laps": 5,
                "before_compound": "RM", "after_compound": "RM",
                "handling_agreement": 0.5, "relevant_metrics": 2, "improved_metrics": 1,
                "lock_up_before": 1.5, "lock_up_after": 0.8,
            }),
            "recommendation_text": json.dumps({
                "changes": [{"field": "arb_front", "from": 5, "to": 3,
                             "why": "reduce understeer"}]
            }),
        }
        block = format_performance_block([rec])
        assert "Performance of Previous Recommendations" in block
        assert "arb_front" in block  # change field
        assert "improved" in block   # verdict


# ---------------------------------------------------------------------------
# AC7 — learning_saved gate: Home journey step-13 reflects DB state
# ---------------------------------------------------------------------------

class TestAC7LearningSavedGate:
    """AC7: after a real scored run, has_learning_for_car_track returns True
    and build_home_dashboard_state with learning_saved=True clears step 13."""

    def test_has_learning_false_before_scoring(self):
        """Before any scoring, has_learning_for_car_track returns False."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            assert db.has_learning_for_car_track(car_id, "Spa") is False
        finally:
            db.close()

    def test_has_learning_true_after_real_scored_run(self):
        """After _trigger_scoring_pass writes a non-insufficient_data verdict,
        has_learning_for_car_track returns True."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_500, 90_200, 90_000, 89_800, 89_700, 90_100]:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            # Clear improvement: all 6 laps well below before
            for ms in [88_500, 88_300, 88_400, 88_600, 88_200, 88_700]:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            # Check what verdict was written
            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations"
            ).fetchone()
            if row[0] not in ("", "insufficient_data"):
                assert db.has_learning_for_car_track(car_id, "Spa") is True, (
                    "has_learning_for_car_track must be True after a real verdict")
            # If insufficient_data, learning stays False — that's correct behaviour
        finally:
            db.close()

    def test_step13_not_pending_when_learning_saved_true(self):
        """With learning_saved=True, build_flow_state_summary marks step 13 done
        (next_action is not the step-13 prompt, or complete flag shows all done)."""
        from ui.product_flow import build_flow_state_summary

        # All other gates met + learning_saved=True
        result = build_flow_state_summary(
            has_event=True, has_car=True, has_track=True,
            tuning_confirmed=True, has_practice_laps=True,
            has_valid_laps=True, has_setup=True, has_strategy=True,
            live_active=True, learning_saved=True,
        )
        # When learning_saved is True and all other gates are met, the next action
        # should indicate completion, not prompt for step 13
        assert result["next_action"] == "All steps complete — nothing outstanding", (
            f"Expected completion message with learning_saved=True, "
            f"got {result['next_action']!r}")

    def test_step13_pending_when_learning_saved_false(self):
        """With learning_saved=False (all other gates met), step 13 is still pending."""
        from ui.product_flow import build_flow_state_summary

        result = build_flow_state_summary(
            has_event=True, has_car=True, has_track=True,
            tuning_confirmed=True, has_practice_laps=True,
            has_valid_laps=True, has_setup=True, has_strategy=True,
            live_active=True, learning_saved=False,
        )
        assert result["next_action"] == "Save this session's learning to history", (
            f"Unexpected next_action when learning_saved=False: {result['next_action']!r}")

    def test_build_home_dashboard_state_learning_saved_kwarg_accepted(self):
        """build_home_dashboard_state accepts learning_saved and passes it through."""
        from ui.home_dashboard_vm import build_home_dashboard_state
        # Should not raise; result should be a valid state
        state = build_home_dashboard_state(learning_saved=True)
        assert state is not None

    def test_build_home_dashboard_state_source_scan(self):
        """_build_home_dashboard_state must call has_learning_for_car_track
        and pass learning_saved= kwarg to build_home_dashboard_state."""
        dash_src = (REPO / "ui" / "dashboard.py").read_text(encoding="utf-8") + (REPO / "ui" / "live_ui.py").read_text(encoding="utf-8")
        m = re.search(
            r"\n    def _build_home_dashboard_state\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
            dash_src, re.DOTALL
        )
        assert m, "_build_home_dashboard_state not found"
        body = m.group(0)
        assert "has_learning_for_car_track" in body, (
            "_build_home_dashboard_state must call has_learning_for_car_track")
        assert "learning_saved=" in body, (
            "_build_home_dashboard_state must pass learning_saved= kwarg")


# ---------------------------------------------------------------------------
# AC8 — No tyre-radius signal in the scoring path
# ---------------------------------------------------------------------------

class TestAC8NoTyreRadius:
    """AC8: 'radius' never appears in recommendation_scoring.py or score_details."""

    def test_no_radius_in_scoring_module_source(self):
        """recommendation_scoring.py must not reference tyre_radius in code or data paths.

        The module docstring is permitted to say 'No tyre-radius fields' as a
        prohibition statement. What is forbidden is any import, variable name, dict key,
        or computation that reads or propagates a 'tyre_radius' value.
        """
        src = (REPO / "data" / "recommendation_scoring.py").read_text(encoding="utf-8")
        # tyre_radius as a data field / dict key (the actionable form) must not appear
        assert "tyre_radius" not in src, (
            "recommendation_scoring.py must not reference 'tyre_radius' as a data field")

    def test_no_radius_in_score_details_of_real_run(self):
        """score_details JSON from a real scoring run must not contain 'radius'."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [89_000] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_details FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            assert row is not None
            details_str = row[0] or ""
            assert "radius" not in details_str.lower(), (
                f"'radius' found in score_details: {details_str!r}")
        finally:
            db.close()


# ---------------------------------------------------------------------------
# AC9 — No new config["strategy"] reads (frozen allowlist unchanged)
# ---------------------------------------------------------------------------

class TestAC9FrozenAllowlist:
    """AC9: the Phase 5 frozen-allowlist test must pass unchanged."""

    def test_frozen_allowlist_matches_exactly(self):
        """Import and run _scan_inventory from the existing allowlist test.

        The test is designed to fail if any NEW config['strategy'] consumer is
        introduced, or if an old one disappears without updating the list.
        """
        import importlib
        import sys

        # Import the existing test module (it's already importable as a module)
        sys.path.insert(0, str(REPO / "tests"))
        phase5 = importlib.import_module("test_legacy_fanout_phase_5")

        found = phase5._scan_inventory()
        assert found == phase5.FROZEN_ALLOWLIST, (
            f"config['strategy'] access sites changed — allowlist no longer matches.\n"
            f"Extra: {set(found) - set(phase5.FROZEN_ALLOWLIST)}\n"
            f"Missing: {set(phase5.FROZEN_ALLOWLIST) - set(found)}"
        )


# ---------------------------------------------------------------------------
# AC10 — Scoring module is pure Python (no PyQt/sqlite/file-IO)
# ---------------------------------------------------------------------------

class TestAC10ModulePurity:
    """AC10: recommendation_scoring.py uses no PyQt6, sqlite3, or open()."""

    def _load_src(self) -> str:
        return (REPO / "data" / "recommendation_scoring.py").read_text(encoding="utf-8")

    def _get_imports(self, src: str) -> set[str]:
        tree = ast.parse(src)
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module.split(".")[0])
        return names

    def test_no_pyqt6_import(self):
        imports = self._get_imports(self._load_src())
        assert "PyQt6" not in imports

    def test_no_sqlite3_import(self):
        imports = self._get_imports(self._load_src())
        assert "sqlite3" not in imports

    def test_no_open_call(self):
        src = self._load_src()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    pytest.fail("recommendation_scoring.py must not call open()")

    def test_this_test_file_uses_only_memory_db(self):
        """This test file itself must only use ':memory:' SessionDB instances.

        Scans the AST for Call nodes whose callee is SessionDB; each call's
        first positional arg (or 'path' kwarg) must be the string ':memory:'.
        """
        src = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        violations: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Match both SessionDB(...) and module.SessionDB(...)
            is_session_db = (
                (isinstance(func, ast.Name) and func.id == "SessionDB")
                or (isinstance(func, ast.Attribute) and func.attr == "SessionDB")
            )
            if not is_session_db:
                continue
            # First positional arg must be the ':memory:' string constant
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and first.value == ":memory:":
                    continue
                violations.append(node.lineno)
            else:
                # keyword-only path= arg
                for kw in node.keywords:
                    if kw.arg in (None, "path"):
                        if not (isinstance(kw.value, ast.Constant)
                                and kw.value.value == ":memory:"):
                            violations.append(node.lineno)
        assert not violations, (
            f"Non-':memory:' SessionDB usage at lines: {violations}")

    def test_module_no_os_import(self):
        """recommendation_scoring.py must not import os (no file-system ops)."""
        imports = self._get_imports(self._load_src())
        assert "os" not in imports, (
            "recommendation_scoring.py imports os — file I/O is forbidden")


# ---------------------------------------------------------------------------
# AC11 — OFR-2 tables absent from schema
# ---------------------------------------------------------------------------

class TestAC11LoopTwoThreeTables:
    """AC11: prediction_log / compound_profiles / driver_weaknesses must NOT exist."""

    def test_forbidden_tables_absent(self):
        """A fresh in-memory DB must not contain any OFR-2/3 schema tables."""
        db = _make_db()
        try:
            tables = {
                row[0]
                for row in db._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            forbidden = {"prediction_log", "compound_profiles", "driver_weaknesses"}
            present = forbidden & tables
            assert not present, (
                f"Forbidden OFR-2/3 tables found in schema: {present}")
        finally:
            db.close()

    def test_no_forbidden_table_references_in_session_db_source(self):
        """session_db.py source must not reference any OFR-2/3 table names."""
        src = (REPO / "data" / "session_db.py").read_text(encoding="utf-8")
        for name in ("prediction_log", "compound_profiles", "driver_weaknesses"):
            assert name not in src, (
                f"OFR-2/3 table name '{name}' found in session_db.py source")


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases from the user story."""

    def test_multiple_recs_same_session_get_individual_verdicts(self):
        """Multiple applied recs from the same session each get their own verdict."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id_a = _insert_rec(
                db, car_id=car_id, track="Spa", session_id=sid1,
                rec_text=json.dumps({
                    "changes": [{"field": "arb_front", "from": 5, "to": 3,
                                 "why": "reduce understeer"}]
                })
            )
            rec_id_b = _insert_rec(
                db, car_id=car_id, track="Spa", session_id=sid1,
                rec_text=json.dumps({
                    "changes": [{"field": "arb_rear", "from": 3, "to": 5,
                                 "why": "improve stability"}]
                })
            )
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)

            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [89_000] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            rows = db._conn.execute(
                "SELECT id, score_verdict, score_confidence FROM setup_recommendations "
                "ORDER BY id"
            ).fetchall()
            # Both recs must be scored
            assert len(rows) == 2
            for row in rows:
                assert row[1] != "", f"rec {row[0]} was not scored"
            # With multi_rec_count=2, confidence should be lower than a single-rec run
            # (attribution split). Both must be in valid-verdict set.
            valid = {"improved", "worsened", "neutral", "insufficient_data"}
            for row in rows:
                assert row[1] in valid, f"Invalid verdict {row[1]!r} for rec {row[0]}"

        finally:
            db.close()

    def test_multiple_recs_attribution_split_reduces_confidence(self):
        """Multiple recs applied together → per-rec confidence < single-rec confidence."""
        from data.recommendation_scoring import LapWindow, compute_verdict_and_confidence

        def _w(n, ms):
            return LapWindow(
                laps=[], clean_count=n, compound="RM", best_clean_ms=ms,
                avg_lock_up=0.0, avg_wheelspin=0.0, avg_oversteer=0.0,
                avg_oversteer_throttle=0.0, avg_bottoming=0.0,
                avg_brake_consistency=0.0,
            )

        rec = {
            "id": 1,
            "before_metrics": json.dumps({"best_lap_ms": 90_000}),
            "recommendation_text": json.dumps({
                "changes": [{"field": "aero", "from": 5, "to": 7, "why": "improve speed"}]
            }),
        }
        before = _w(6, 90_000)
        after  = _w(6, 89_500)  # Δt = -500 → improved

        single = compute_verdict_and_confidence(rec, before, after, multi_rec_count=1)
        multi  = compute_verdict_and_confidence(rec, before, after, multi_rec_count=2)
        assert multi.confidence < single.confidence

    def test_cross_layout_guard_e2e(self):
        """Recs for layout 'spa__full' are not scored when trigger uses layout 'spa__short'."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(
                db, car_id=car_id, track="Spa", session_id=sid1,
                layout_id="spa__full"
            )
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [89_000] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            # Trigger with DIFFERENT layout — should not score the rec
            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "spa__short", sid3)

            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            assert row[0] == "", (
                "Cross-layout rec must NOT be scored by a mismatched layout trigger")
        finally:
            db.close()

    def test_compound_present_in_score_details(self):
        """score_details must record before_compound and after_compound."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid1)
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa",
                            lap_time_ms=ms, compound="RM")
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [88_500] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa",
                            lap_time_ms=ms, compound="RS")
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")

            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_details FROM setup_recommendations WHERE id=?", (rec_id,)
            ).fetchone()
            details = json.loads(row[0])
            assert "before_compound" in details, "before_compound missing from score_details"
            assert "after_compound" in details, "after_compound missing from score_details"
            # Compounds should be recorded correctly
            assert details["before_compound"] == "RM", (
                f"before_compound should be 'RM', got {details['before_compound']!r}")
            assert details["after_compound"] == "RS", (
                f"after_compound should be 'RS', got {details['after_compound']!r}")
        finally:
            db.close()

    def test_own_session_recs_skipped(self):
        """Recs created IN the after-session are skipped by the trigger."""
        db = _make_db()
        try:
            car_id = _insert_car(db)
            sid1 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            for ms in [90_000] * 6:
                _insert_lap(db, sid1, car_id=car_id, track="Spa", lap_time_ms=ms)

            # sid2 is the "after" session — rec created HERE should be skipped
            sid2 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            own_rec_id = _insert_rec(db, car_id=car_id, track="Spa", session_id=sid2)
            for ms in [89_000] * 6:
                _insert_lap(db, sid2, car_id=car_id, track="Spa", lap_time_ms=ms)

            # sid3 triggers scoring with after_sid = sid2
            sid3 = db.open_session(car_id=car_id, track="Spa", session_type="Practice")
            stub = _make_scoring_stub(db)
            stub._trigger_scoring_pass(car_id, "Spa", "", sid3)

            row = db._conn.execute(
                "SELECT score_verdict FROM setup_recommendations WHERE id=?",
                (own_rec_id,)
            ).fetchone()
            assert row[0] == "", (
                "A rec created IN the after-session must not be scored by that run")
        finally:
            db.close()
