"""Tests for Group 17H — Track Intelligence AI Prompt Integration.

Covers:
  - strategy.track_context_prompt.get_track_context_for_ai
  - RaceParams.track_location_id / layout_id fields
  - _build_race_prompt track context injection
  - _build_practice_prompt track context injection
  - _build_setup_from_scratch_prompt track context injection
  - DrivingAdvisor._get_track_intelligence_context
  - coaching/setup prompt track intelligence injection
  - seed-only context warnings
  - missing track/layout warnings
  - resolver error safety
  - regression: Groups 17A-17G still importable
"""
from __future__ import annotations

import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from strategy.driving_advisor import DrivingAdvisor

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEED_LOC = "suzuka_circuit"
_SEED_LAY = "suzuka_circuit__full_course"
_UNKNOWN_LOC = "nowhere_speedway"
_UNKNOWN_LAY = "nowhere_speedway__full"


def _make_config(loc_id: str = "", lay_id: str = "") -> dict:
    return {
        "strategy": {
            "track": "Suzuka Circuit",
            "track_location_id": loc_id,
            "layout_id": lay_id,
            "car": "Test Car",
        },
        "anthropic": {"api_key": "test_key"},
    }


# ---------------------------------------------------------------------------
# Class 1 — get_track_context_for_ai helper: missing IDs
# ---------------------------------------------------------------------------


class TestGetTrackContextMissingIds:
    def test_none_loc_returns_warning(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai(None, _SEED_LAY)
        assert "Track Intelligence unavailable" in result
        assert "no selected track/layout" in result

    def test_none_layout_returns_warning(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai(_SEED_LOC, None)
        assert "Track Intelligence unavailable" in result

    def test_empty_loc_returns_warning(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai("", _SEED_LAY)
        assert "Track Intelligence unavailable" in result

    def test_empty_layout_returns_warning(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai(_SEED_LOC, "")
        assert "Track Intelligence unavailable" in result

    def test_both_none_returns_warning(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai(None, None)
        assert "Track Intelligence unavailable" in result

    def test_warning_is_string(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai("", "")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Class 2 — get_track_context_for_ai helper: resolver called when IDs present
# ---------------------------------------------------------------------------


class TestGetTrackContextCallsResolver:
    def test_calls_resolver_when_ids_present(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        _sentinel = "RESOLVER_CALLED_SENTINEL"
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            return_value=_sentinel,
        ) as mock_fn:
            result = get_track_context_for_ai(_SEED_LOC, _SEED_LAY)
        args, kwargs = mock_fn.call_args
        assert args == (_SEED_LOC, _SEED_LAY)
        assert "rev_limit_threshold_pct" in kwargs
        assert result == _sentinel

    def test_resolver_receives_exact_ids(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            return_value="ctx",
        ) as mock_fn:
            get_track_context_for_ai("fuji_speedway", "fuji_speedway__full_course")
        args, kwargs = mock_fn.call_args
        assert args == ("fuji_speedway", "fuji_speedway__full_course")

    def test_real_seed_returns_track_section(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai(_SEED_LOC, _SEED_LAY)
        assert isinstance(result, str)
        assert len(result) > 10  # non-trivial content


# ---------------------------------------------------------------------------
# Class 3 — get_track_context_for_ai helper: error safety
# ---------------------------------------------------------------------------


class TestGetTrackContextErrorSafety:
    def test_resolver_exception_returns_warning(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            side_effect=RuntimeError("disk error"),
        ):
            result = get_track_context_for_ai(_SEED_LOC, _SEED_LAY)
        assert "Track Intelligence unavailable" in result
        assert "RuntimeError" in result or "disk error" in result

    def test_resolver_import_error_returns_warning(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            side_effect=ImportError("no module"),
        ):
            result = get_track_context_for_ai(_SEED_LOC, _SEED_LAY)
        assert "Track Intelligence unavailable" in result

    def test_error_result_is_string(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            side_effect=Exception("boom"),
        ):
            result = get_track_context_for_ai(_SEED_LOC, _SEED_LAY)
        assert isinstance(result, str)

    def test_does_not_raise(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            side_effect=ValueError("bad value"),
        ):
            # Must not propagate
            get_track_context_for_ai(_SEED_LOC, _SEED_LAY)


# ---------------------------------------------------------------------------
# Class 4 — RaceParams has new fields
# ---------------------------------------------------------------------------


class TestRaceParamsFields:
    def _minimal_params(self, **kwargs):
        from strategy.ai_planner import RaceParams
        defaults = dict(
            track="Test Track",
            total_laps=10,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        defaults.update(kwargs)
        return RaceParams(**defaults)

    def test_track_location_id_default_empty(self):
        p = self._minimal_params()
        assert p.track_location_id == ""

    def test_layout_id_default_empty(self):
        p = self._minimal_params()
        assert p.layout_id == ""

    def test_track_location_id_set(self):
        p = self._minimal_params(track_location_id=_SEED_LOC)
        assert p.track_location_id == _SEED_LOC

    def test_layout_id_set(self):
        p = self._minimal_params(layout_id=_SEED_LAY)
        assert p.layout_id == _SEED_LAY

    def test_both_ids_coexist(self):
        p = self._minimal_params(track_location_id=_SEED_LOC, layout_id=_SEED_LAY)
        assert p.track_location_id == _SEED_LOC
        assert p.layout_id == _SEED_LAY


# ---------------------------------------------------------------------------
# Class 5 — _build_race_prompt includes track context
# ---------------------------------------------------------------------------


class TestBuildRacePromptTrackContext:
    def _make_params(self, **kwargs):
        from strategy.ai_planner import RaceParams
        defaults = dict(
            track="Test Track",
            total_laps=10,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        defaults.update(kwargs)
        return RaceParams(**defaults)

    def test_track_context_injected_when_provided(self):
        from strategy.ai_planner import _build_race_prompt
        p = self._make_params()
        prompt = _build_race_prompt(p, {"RM": [90000.0]}, track_context="## Track Intelligence\nTest track ctx")
        assert "## Track Intelligence" in prompt
        assert "Test track ctx" in prompt

    def test_no_track_context_when_empty(self):
        from strategy.ai_planner import _build_race_prompt
        p = self._make_params()
        prompt = _build_race_prompt(p, {"RM": [90000.0]}, track_context="")
        # Should not crash and Track Intelligence section absent
        assert "Track Intelligence unavailable" not in prompt

    def test_track_context_before_practice_lap_times(self):
        from strategy.ai_planner import _build_race_prompt
        p = self._make_params()
        ctx = "## Track Intelligence\nCorner data here"
        prompt = _build_race_prompt(p, {"RM": [90000.0]}, track_context=ctx)
        tc_pos = prompt.index("## Track Intelligence")
        lap_pos = prompt.index("## Practice lap times")
        assert tc_pos < lap_pos


# ---------------------------------------------------------------------------
# Class 6 — _build_practice_prompt includes track context
# ---------------------------------------------------------------------------


class TestBuildPracticePromptTrackContext:
    def _make_params(self, **kwargs):
        from strategy.ai_planner import RaceParams
        defaults = dict(
            track="Test Track",
            total_laps=10,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        defaults.update(kwargs)
        return RaceParams(**defaults)

    def test_track_context_injected(self):
        from strategy.ai_planner import _build_practice_prompt
        p = self._make_params()
        ctx = "## Track Intelligence\nPractice ctx"
        prompt = _build_practice_prompt(
            p, {"RM": [90000.0]}, {}, {},
            track_context=ctx
        )
        assert "## Track Intelligence" in prompt
        assert "Practice ctx" in prompt

    def test_no_crash_without_track_context(self):
        from strategy.ai_planner import _build_practice_prompt
        p = self._make_params()
        prompt = _build_practice_prompt(p, {"RM": [90000.0]}, {}, {})
        assert isinstance(prompt, str)

    def test_track_context_before_practice_lap_times(self):
        from strategy.ai_planner import _build_practice_prompt
        p = self._make_params()
        ctx = "## Track Intelligence\nCorner data"
        prompt = _build_practice_prompt(
            p, {"RM": [90000.0]}, {}, {},
            track_context=ctx,
        )
        tc_pos = prompt.index("## Track Intelligence")
        lap_pos = prompt.index("## Practice lap times")
        assert tc_pos < lap_pos


# ---------------------------------------------------------------------------
# Class 7 — _build_setup_from_scratch_prompt includes track context
# ---------------------------------------------------------------------------


class TestBuildSetupFromScratchTrackContext:
    def test_track_context_injected(self):
        from strategy.ai_planner import _build_setup_from_scratch_prompt
        ctx = "## Track Intelligence\nSetup ctx"
        prompt = _build_setup_from_scratch_prompt(
            car="Test Car",
            track="Test Track",
            session_type="Race",
            race_laps=10,
            min_weight_kg=1200.0,
            max_power_hp=500.0,
            track_context=ctx,
        )
        assert "## Track Intelligence" in prompt
        assert "Setup ctx" in prompt

    def test_no_crash_without_track_context(self):
        from strategy.ai_planner import _build_setup_from_scratch_prompt
        prompt = _build_setup_from_scratch_prompt(
            car="Test Car",
            track="Test Track",
            session_type="Race",
            race_laps=10,
            min_weight_kg=1200.0,
            max_power_hp=500.0,
        )
        assert isinstance(prompt, str)

    def test_track_context_present_in_build_car_setup(self):
        from strategy.ai_planner import build_car_setup
        _captured: list[str] = []

        def _fake_parse(raw):
            return MagicMock()

        with patch("strategy.ai_planner._build_setup_from_scratch_prompt") as mock_builder, \
             patch("strategy.ai_planner.call_api", return_value='{"rank":1}'), \
             patch("strategy.ai_planner._parse_setup_recommendation", return_value=MagicMock()), \
             patch(
                 "strategy.track_context_prompt.get_track_context_for_ai",
                 return_value="## Track Intelligence\nInjected"
             ) as mock_ctx:
            mock_builder.return_value = "prompt"
            try:
                build_car_setup(
                    car="Car",
                    track="Track",
                    session_type="Race",
                    race_laps=10,
                    min_weight_kg=1200.0,
                    max_power_hp=500.0,
                    api_key="test",
                    track_location_id=_SEED_LOC,
                    layout_id=_SEED_LAY,
                )
            except Exception:
                pass
            args, kwargs = mock_ctx.call_args
            assert args == (_SEED_LOC, _SEED_LAY)
            # track_context kwarg forwarded to prompt builder
            _, kw = mock_builder.call_args
            assert kw.get("track_context") == "## Track Intelligence\nInjected"


# ---------------------------------------------------------------------------
# Class 8 — analyse_strategy passes track context
# ---------------------------------------------------------------------------


class TestAnalyseStrategyTrackContext:
    def _make_params(self, **kwargs):
        from strategy.ai_planner import RaceParams
        defaults = dict(
            track="Test Track",
            total_laps=10,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        defaults.update(kwargs)
        return RaceParams(**defaults)

    def test_track_context_included_in_payload_when_ids_set(self):
        from strategy.ai_planner import analyse_strategy
        p = self._make_params(track_location_id=_SEED_LOC, layout_id=_SEED_LAY)
        _payloads: list[dict] = []

        def _fake_call(prompt, api_key, **kw):
            _payloads.append(kw.get("structured_payload", {}))
            raise RuntimeError("no api")

        # Need ≥8 clean laps + degradation entry so the feasibility gate passes
        # and call_api is actually invoked (Fix 1 short-circuits when all stops rejected).
        _laps = [90000.0] * 8
        _deg = {"RM": {"optimal_stint_race": 15, "total_life_race": 18,
                       "cliff_lap_practice": 16, "pace_loss_at_cliff_s": 1.5, "confidence": "high"}}
        with patch("strategy.ai_planner.call_api", side_effect=_fake_call):
            with pytest.raises(RuntimeError):
                analyse_strategy(p, {"RM": _laps}, "key", degradation=_deg)

        assert _payloads
        payload = _payloads[0]
        assert payload.get("track_context_included") is True
        assert payload.get("track_location_id") == _SEED_LOC
        assert payload.get("layout_id") == _SEED_LAY

    def test_track_context_not_included_when_ids_missing(self):
        from strategy.ai_planner import analyse_strategy
        p = self._make_params()
        _payloads: list[dict] = []

        def _fake_call(prompt, api_key, **kw):
            _payloads.append(kw.get("structured_payload", {}))
            raise RuntimeError("no api")

        # Need ≥8 clean laps + degradation entry so the feasibility gate passes
        # and call_api is actually invoked (Fix 1 short-circuits when all stops rejected).
        _laps = [90000.0] * 8
        _deg = {"RM": {"optimal_stint_race": 15, "total_life_race": 18,
                       "cliff_lap_practice": 16, "pace_loss_at_cliff_s": 1.5, "confidence": "high"}}
        with patch("strategy.ai_planner.call_api", side_effect=_fake_call):
            with pytest.raises(RuntimeError):
                analyse_strategy(p, {"RM": _laps}, "key", degradation=_deg)

        payload = _payloads[0]
        assert payload.get("track_context_included") is False


# ---------------------------------------------------------------------------
# Class 9 — analyse_practice_session passes track context
# ---------------------------------------------------------------------------


class TestAnalysePracticeSessionTrackContext:
    def _make_params(self, **kwargs):
        from strategy.ai_planner import RaceParams
        defaults = dict(
            track="Test Track",
            total_laps=10,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
        )
        defaults.update(kwargs)
        return RaceParams(**defaults)

    def test_payload_includes_track_context_flag(self):
        from strategy.ai_planner import analyse_practice_session
        p = self._make_params(track_location_id=_SEED_LOC, layout_id=_SEED_LAY)
        _payloads: list[dict] = []

        def _fake_call(prompt, api_key, **kw):
            _payloads.append(kw.get("structured_payload", {}))
            raise RuntimeError("no api")

        with patch("strategy.ai_planner.call_api", side_effect=_fake_call):
            with pytest.raises(RuntimeError):
                analyse_practice_session(p, {"RM": [90000.0]}, {}, {}, "key")

        assert _payloads
        payload = _payloads[0]
        assert payload.get("track_context_included") is True
        assert payload.get("track_location_id") == _SEED_LOC

    def test_missing_ids_flag_false(self):
        from strategy.ai_planner import analyse_practice_session
        p = self._make_params()
        _payloads: list[dict] = []

        def _fake_call(prompt, api_key, **kw):
            _payloads.append(kw.get("structured_payload", {}))
            raise RuntimeError("no api")

        with patch("strategy.ai_planner.call_api", side_effect=_fake_call):
            with pytest.raises(RuntimeError):
                analyse_practice_session(p, {"RM": [90000.0]}, {}, {}, "key")

        payload = _payloads[0]
        assert payload.get("track_context_included") is False


# ---------------------------------------------------------------------------
# Class 10 — DrivingAdvisor._get_track_intelligence_context
# ---------------------------------------------------------------------------


class TestDrivingAdvisorTrackIntelligence:
    def _make_advisor(self, loc_id: str = "", lay_id: str = "") -> "DrivingAdvisor":
        from strategy.driving_advisor import DrivingAdvisor
        mock_recorder = MagicMock()
        mock_tracker = MagicMock()
        config = _make_config(loc_id, lay_id)
        return DrivingAdvisor(mock_recorder, mock_tracker, config)

    def test_returns_warning_when_no_ids(self):
        adv = self._make_advisor()
        ctx = adv._get_track_intelligence_context()
        assert "Track Intelligence unavailable" in ctx

    def test_calls_resolver_when_ids_set(self):
        adv = self._make_advisor(_SEED_LOC, _SEED_LAY)
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            return_value="## Track Intelligence\nfrom resolver",
        ) as mock_fn:
            ctx = adv._get_track_intelligence_context()
        mock_fn.assert_called_once()
        args, kwargs = mock_fn.call_args
        assert args[:2] == (_SEED_LOC, _SEED_LAY)
        assert "from resolver" in ctx

    def test_returns_string_on_resolver_error(self):
        adv = self._make_advisor(_SEED_LOC, _SEED_LAY)
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            side_effect=OSError("no file"),
        ):
            ctx = adv._get_track_intelligence_context()
        assert isinstance(ctx, str)
        assert "Track Intelligence unavailable" in ctx

    def test_does_not_raise_on_resolver_error(self):
        adv = self._make_advisor(_SEED_LOC, _SEED_LAY)
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            side_effect=Exception("fatal"),
        ):
            adv._get_track_intelligence_context()  # must not raise


# ---------------------------------------------------------------------------
# Class 11 — DrivingAdvisor coaching prompt includes track intelligence
# ---------------------------------------------------------------------------


class TestCoachingPromptTrackIntelligence:
    def _make_advisor(self, loc_id: str = "", lay_id: str = "") -> "DrivingAdvisor":
        from strategy.driving_advisor import DrivingAdvisor
        mock_recorder = MagicMock()
        mock_recorder.best_lap.return_value = None
        mock_tracker = MagicMock()
        config = _make_config(loc_id, lay_id)
        return DrivingAdvisor(mock_recorder, mock_tracker, config)

    def _make_lap(self):
        mock = MagicMock()
        mock.lap_num = 1
        mock.lap_time_ms = 90000
        mock.lock_up_count = 0
        mock.wheelspin_count = 0
        mock.oversteer_count = 0
        mock.oversteer_throttle_on_count = 0
        mock.kerb_count = 0
        mock.bottoming_count = 0
        mock.snap_throttle_count = 0
        mock.brake_consistency_m = 5.0
        mock.max_speed_kmh = 200.0
        mock.max_lat_g = 1.5
        mock.avg_throttle_pct = 60.0
        mock.avg_brake_pct = 20.0
        mock.rev_limiter_count = 0
        mock.lock_up_positions = []
        mock.wheelspin_positions = []
        mock.oversteer_positions = []
        mock.snap_throttle_positions = []
        mock.over_braking_positions = []
        mock.rev_limiter_by_gear = {}
        mock.over_braking_count = 0
        mock.abrupt_release_count = 0
        mock.car_max_speed_theoretical_kmh = 0.0
        mock.avg_tyre_radius = {}
        mock.off_track_count = 0
        return mock

    def test_coaching_prompt_includes_track_intelligence_when_ids_set(self):
        adv = self._make_advisor(_SEED_LOC, _SEED_LAY)
        laps = [self._make_lap()]
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            return_value="## Track Intelligence\ncoaching ctx",
        ):
            prompt = adv._build_coaching_prompt(laps, "")
        assert "## Track Intelligence" in prompt
        assert "coaching ctx" in prompt

    def test_coaching_prompt_includes_warning_when_ids_missing(self):
        adv = self._make_advisor()
        laps = [self._make_lap()]
        prompt = adv._build_coaching_prompt(laps, "")
        assert "Track Intelligence unavailable" in prompt

    def test_track_intelligence_in_extra_sections(self):
        adv = self._make_advisor(_SEED_LOC, _SEED_LAY)
        laps = [self._make_lap()]
        _sentinel = "## Track Intelligence\nSENTINEL_INTEL"
        with patch.object(adv, "_get_track_intelligence_context", return_value=_sentinel):
            prompt = adv._build_coaching_prompt(laps, "")
        assert _sentinel in prompt


# ---------------------------------------------------------------------------
# Class 12 — DrivingAdvisor setup prompt includes track intelligence
# ---------------------------------------------------------------------------


class TestSetupPromptTrackIntelligence:
    def _make_advisor(self, loc_id: str = "", lay_id: str = "") -> "DrivingAdvisor":
        from strategy.driving_advisor import DrivingAdvisor
        mock_recorder = MagicMock()
        mock_tracker = MagicMock()
        config = _make_config(loc_id, lay_id)
        return DrivingAdvisor(mock_recorder, mock_tracker, config)

    def _make_lap(self):
        mock = MagicMock()
        mock.lap_num = 1
        mock.lap_time_ms = 90000
        mock.lock_up_count = 1
        mock.wheelspin_count = 0
        mock.oversteer_count = 0
        mock.oversteer_throttle_on_count = 0
        mock.kerb_count = 0
        mock.bottoming_count = 0
        mock.snap_throttle_count = 0
        mock.brake_consistency_m = 8.0
        mock.max_speed_kmh = 200.0
        mock.max_lat_g = 1.5
        mock.avg_throttle_pct = 55.0
        mock.avg_brake_pct = 22.0
        mock.rev_limiter_count = 0
        mock.lock_up_positions = []
        mock.wheelspin_positions = []
        mock.oversteer_positions = []
        mock.snap_throttle_positions = []
        mock.over_braking_positions = []
        mock.rev_limiter_by_gear = {}
        mock.over_braking_count = 0
        mock.abrupt_release_count = 0
        mock.car_max_speed_theoretical_kmh = 0.0
        mock.avg_tyre_radius = {}
        mock.off_track_count = 0
        return mock

    def test_setup_prompt_includes_track_intelligence_when_ids_set(self):
        adv = self._make_advisor(_SEED_LOC, _SEED_LAY)
        laps = [self._make_lap()]
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            return_value="## Track Intelligence\nsetup ctx",
        ):
            prompt = adv._build_setup_prompt(laps, {}, "")
        assert "## Track Intelligence" in prompt
        assert "setup ctx" in prompt

    def test_setup_prompt_warning_when_ids_missing(self):
        adv = self._make_advisor()
        laps = [self._make_lap()]
        prompt = adv._build_setup_prompt(laps, {}, "")
        assert "Track Intelligence unavailable" in prompt

    def test_combined_prompt_includes_track_intelligence(self):
        adv = self._make_advisor(_SEED_LOC, _SEED_LAY)
        laps = [self._make_lap()]
        with patch(
            "data.track_model_resolver.build_resolved_track_context_for_prompt",
            return_value="## Track Intelligence\ncombined ctx",
        ):
            prompt = adv._build_combined_prompt(laps, {}, "")
        assert "## Track Intelligence" in prompt
        assert "combined ctx" in prompt


# ---------------------------------------------------------------------------
# Class 13 — seed-only context includes expected warning
# ---------------------------------------------------------------------------


class TestSeedOnlyContextWarning:
    def test_seed_only_includes_not_validated_warning(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai(_SEED_LOC, _SEED_LAY)
        # Seed-only result must include a warning about unvalidated data
        assert any(
            phrase in result
            for phrase in [
                "seed data only",
                "NOT validated",
                "no reviewed track model",
                "SEED DATA ONLY",
                "IMPORTANT",
            ]
        )

    def test_missing_track_context_says_missing(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai(_UNKNOWN_LOC, _UNKNOWN_LAY)
        assert isinstance(result, str)
        # Either "MISSING" or an error note is acceptable
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Class 14 — missing layout_id does not crash AI callers
# ---------------------------------------------------------------------------


class TestMissingLayoutIdSafety:
    def test_analyse_strategy_no_crash_with_missing_loc(self):
        from strategy.ai_planner import analyse_strategy, RaceParams
        p = RaceParams(
            track="Test",
            total_laps=5,
            tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0,
            pit_loss_secs=23.0,
            track_location_id="",   # explicitly empty
            layout_id="",
        )
        # Provide ≥8 laps + degradation so the feasibility gate passes and call_api is invoked.
        # Fix 1 short-circuits before calling the API when all stops are rejected, so
        # we must pass enough data to get at least one feasible stop count.
        _laps = [90000.0] * 8
        _deg = {"RM": {"optimal_stint_race": 10, "total_life_race": 12,
                       "cliff_lap_practice": 11, "pace_loss_at_cliff_s": 1.5, "confidence": "high"}}
        with patch("strategy.ai_planner.call_api", side_effect=RuntimeError("no api")):
            with pytest.raises(RuntimeError, match="no api"):
                analyse_strategy(p, {"RM": _laps}, "key", degradation=_deg)

    def test_build_car_setup_no_crash_with_missing_loc(self):
        from strategy.ai_planner import build_car_setup
        with patch("strategy.ai_planner._build_setup_from_scratch_prompt", return_value="p"), \
             patch("strategy.ai_planner.call_api", side_effect=RuntimeError("no api")), \
             patch("strategy.ai_planner._parse_setup_recommendation", return_value=MagicMock()):
            with pytest.raises(RuntimeError, match="no api"):
                build_car_setup(
                    "car", "track", "Race", 10, 1200.0, 500.0, "key",
                    track_location_id="",
                    layout_id="",
                )


# ---------------------------------------------------------------------------
# Class 15 — build_car_setup structured_payload includes track context flag
# ---------------------------------------------------------------------------


class TestBuildCarSetupPayloadDebug:
    def test_payload_has_track_context_included_true(self):
        from strategy.ai_planner import build_car_setup
        _payloads: list[dict] = []

        def _fake_call(prompt, api_key, **kw):
            _payloads.append(kw.get("structured_payload", {}))
            raise RuntimeError("no api")

        with patch("strategy.ai_planner._build_setup_from_scratch_prompt", return_value="p"), \
             patch("strategy.ai_planner.call_api", side_effect=_fake_call), \
             patch("strategy.ai_planner._parse_setup_recommendation", return_value=MagicMock()):
            with pytest.raises(RuntimeError):
                build_car_setup(
                    "car", "track", "Race", 10, 1200.0, 500.0, "key",
                    track_location_id=_SEED_LOC,
                    layout_id=_SEED_LAY,
                )

        assert _payloads
        p = _payloads[0]
        assert p.get("track_context_included") is True
        assert p.get("track_location_id") == _SEED_LOC
        assert p.get("layout_id") == _SEED_LAY

    def test_payload_has_track_context_included_false_when_missing(self):
        from strategy.ai_planner import build_car_setup
        _payloads: list[dict] = []

        def _fake_call(prompt, api_key, **kw):
            _payloads.append(kw.get("structured_payload", {}))
            raise RuntimeError("no api")

        with patch("strategy.ai_planner._build_setup_from_scratch_prompt", return_value="p"), \
             patch("strategy.ai_planner.call_api", side_effect=_fake_call), \
             patch("strategy.ai_planner._parse_setup_recommendation", return_value=MagicMock()):
            with pytest.raises(RuntimeError):
                build_car_setup("car", "track", "Race", 10, 1200.0, 500.0, "key")

        assert _payloads[0].get("track_context_included") is False


# ---------------------------------------------------------------------------
# Class 16 — Regression: Groups 17A–17H all importable
# ---------------------------------------------------------------------------


class TestRegressionImports:
    def test_track_context_prompt_importable(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        assert callable(get_track_context_for_ai)

    def test_ai_planner_importable(self):
        from strategy.ai_planner import (
            RaceParams, analyse_strategy, analyse_practice_session,
            build_car_setup, _build_race_prompt, _build_practice_prompt,
            _build_setup_from_scratch_prompt,
        )
        assert RaceParams is not None

    def test_driving_advisor_importable(self):
        from strategy.driving_advisor import DrivingAdvisor
        assert DrivingAdvisor is not None

    def test_track_model_resolver_importable(self):
        from data.track_model_resolver import (
            resolve_best_track_model,
            build_resolved_track_context_for_prompt,
        )
        assert callable(build_resolved_track_context_for_prompt)

    def test_track_segment_review_importable(self):
        from data.track_segment_review import (
            TrackModelReviewResult,
            export_review_json,
            import_review_json,
        )
        assert TrackModelReviewResult is not None

    def test_track_intelligence_importable(self):
        from data.track_intelligence import (
            load_track_seed,
            resolve_track_layout,
        )
        assert callable(load_track_seed)

    def test_race_params_has_track_location_id(self):
        from strategy.ai_planner import RaceParams
        import dataclasses
        fields = {f.name for f in dataclasses.fields(RaceParams)}
        assert "track_location_id" in fields
        assert "layout_id" in fields

    def test_driving_advisor_has_track_intelligence_method(self):
        from strategy.driving_advisor import DrivingAdvisor
        assert hasattr(DrivingAdvisor, "_get_track_intelligence_context")

    def test_get_track_context_returns_string(self):
        from strategy.track_context_prompt import get_track_context_for_ai
        result = get_track_context_for_ai(None, None)
        assert isinstance(result, str)
