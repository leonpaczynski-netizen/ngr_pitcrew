"""Driver-profile evolution (Phase 3) — the profile learns the driver's style from
observed driving, deterministically, add-only, and never on a single session.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_driver_profile import build_driver_profile
from strategy.driver_profile_evolution import (
    observe_feedback, evolve_profile, build_evolved_driver_profile,
    ObservedTendencies, _MIN_SESSIONS,
)


def _us(n):
    return [{"corner_entry": "understeer"} for _ in range(n)]


def _os(n):
    return [{"exit_stability": "oversteer"} for _ in range(n)]


class TestObserve:
    def test_counts_understeer_and_oversteer_sessions(self):
        t = observe_feedback(_us(4) + _os(2))
        assert t.sessions == 6 and t.understeer_sessions == 4 and t.oversteer_sessions == 2

    def test_strong_grades_count(self):
        t = observe_feedback([{"mid_corner": "strong understeer"},
                              {"exit_stability": "strong oversteer"}])
        assert t.understeer_sessions == 1 and t.oversteer_sessions == 1


class TestEvolve:
    def test_below_min_sessions_is_no_change(self):
        base = build_driver_profile()
        evolved, why = evolve_profile(base, observe_feedback(_us(_MIN_SESSIONS - 1)))
        assert evolved == base and why == []

    def test_a_single_session_never_flips_the_profile(self):
        base = build_driver_profile()
        evolved, why = evolve_profile(base, observe_feedback(_us(1)))
        assert evolved == base and why == []

    def test_persistent_understeer_adds_front_bite(self):
        base = build_driver_profile()
        evolved, why = evolve_profile(base, observe_feedback(_us(5) + _os(0)))
        assert evolved.prefers_front_bite and evolved.dislikes_floaty_front
        assert "prefers_front_bite" in evolved.style_tags
        assert evolved.profile_version.endswith("+obs-fb")
        assert why and "front-bite" in why[0]

    def test_persistent_oversteer_adds_rear_stability(self):
        base = build_driver_profile()
        evolved, why = evolve_profile(base, observe_feedback(_os(5)))
        assert evolved.dislikes_snap_exit and evolved.prefers_rear_stability
        assert "-rs" in evolved.profile_version

    def test_mixed_signal_without_dominance_is_no_change(self):
        # 3 understeer vs 3 oversteer — neither dominates → profile unchanged.
        base = build_driver_profile()
        evolved, why = evolve_profile(base, observe_feedback(_us(3) + _os(3)))
        assert evolved == base and why == []

    def test_add_only_never_removes_base_tags(self):
        base = build_driver_profile()
        evolved, _ = evolve_profile(base, observe_feedback(_us(5)))
        # Every baseline tag survives; evolution only adds.
        assert set(base.style_tags).issubset(set(evolved.style_tags))


class TestEndToEnd:
    def test_evolves_from_persisted_feedback(self):
        from data.session_db import SessionDB
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = SessionDB(os.path.join(tmp, "s.db"))
            try:
                car_id = db.upsert_car({"name": "Test Car"})
                for i in range(5):
                    sid = db.open_session(car_id, "T", "Practice", "Test Car")
                    db.write_feedback(sid, 0, {"corner_entry": "understeer",
                                               "mid_corner": "understeer"})
                profile, why = build_evolved_driver_profile(db)
                assert profile.prefers_front_bite is True
                assert why
            finally:
                db.close()

    def test_no_db_returns_static_baseline(self):
        profile, why = build_evolved_driver_profile(None)
        assert profile == build_driver_profile() and why == []
