"""
Group 28 — Analyse-path prompts must pass per-car min/max ranges to the AI

Background
----------
The from-scratch "Build Setup" prompt already injects a full min–max block for
every field. The telemetry/feeling "Analyse / Get Setup Fix" prompts in
strategy/driving_advisor.py listed only field NAMES, so the AI never saw the
car's real bounds. As a result it suggested values blind to the limits and —
because it had no signal that a part like aero was adjustable on this car — it
declined to recommend aero changes even when aero was an allowed tuning category.

Fix: a shared `_valid_ranges_block(car_name)` helper, built from the same
resolve_ranges() data the parser clamps against, injected into all three
analyse-path prompt builders (combined, setup-advice, feeling).

All tests are source-scan or in-memory only (no Qt widgets, no real API calls).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strategy.setup_ranges as sr
from strategy import driving_advisor as da

DA_SOURCE = (ROOT / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helper behaviour
# ---------------------------------------------------------------------------
class TestValidRangesBlockContent:
    def test_block_lists_aero_front_and_rear(self):
        block = da._valid_ranges_block("")  # empty car -> generic defaults
        assert "aero_front:" in block
        assert "aero_rear:" in block

    def test_block_notes_parts_are_adjustable(self):
        block = da._valid_ranges_block("")
        low = block.lower()
        assert "adjustable" in low
        assert "aero" in low

    def test_block_covers_core_suspension_fields(self):
        block = da._valid_ranges_block("")
        for field in (
            "ride_height_front", "springs_rear", "arb_front",
            "camber_front", "toe_rear", "brake_bias", "power_restrictor",
        ):
            assert f"{field}:" in block, f"{field} missing from ranges block"

    def test_generic_aero_range_shown_when_no_override(self):
        block = da._valid_ranges_block("")
        aero_line = next(l for l in block.splitlines() if l.strip().startswith("aero_front:"))
        # GENERIC_DEFAULTS aero_front is (0, 1000)
        assert "0" in aero_line and "1000" in aero_line


# ---------------------------------------------------------------------------
# Per-car overrides flow through to the block
# ---------------------------------------------------------------------------
class TestPerCarRangesFlowThrough:
    @pytest.fixture(autouse=True)
    def _stub_loader(self, monkeypatch):
        # Custom per-car ranges with DIFFERENT aero front/rear bounds.
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Test Car": {
                "aero_front": {"min": 50, "max": 250},
                "aero_rear": {"min": 150, "max": 500},
                "arb_front": {"min": 2, "max": 5},
            }
        })
        yield

    def test_custom_aero_front_in_block(self):
        block = da._valid_ranges_block("Test Car")
        line = next(l for l in block.splitlines() if l.strip().startswith("aero_front:"))
        assert "50" in line and "250" in line

    def test_custom_aero_rear_in_block(self):
        block = da._valid_ranges_block("Test Car")
        line = next(l for l in block.splitlines() if l.strip().startswith("aero_rear:"))
        assert "150" in line and "500" in line

    def test_custom_arb_front_in_block(self):
        block = da._valid_ranges_block("Test Car")
        line = next(l for l in block.splitlines() if l.strip().startswith("arb_front:"))
        assert "2" in line and "5" in line

    def test_unspecified_field_falls_back_to_generic(self):
        block = da._valid_ranges_block("Test Car")
        # power_restrictor has no override -> generic (0, 100)
        line = next(l for l in block.splitlines() if l.strip().startswith("power_restrictor:"))
        assert "0" in line and "100" in line


# ---------------------------------------------------------------------------
# Wiring: every analyse-path prompt builder injects the block
# ---------------------------------------------------------------------------
class TestPromptBuildersInjectRanges:
    def test_helper_is_defined(self):
        assert "def _valid_ranges_block(" in DA_SOURCE

    def test_three_prompts_assign_ranges_block(self):
        # combined, setup-advice and feeling builders each compute ranges_block
        assert DA_SOURCE.count("_valid_ranges_block(car_name)") >= 3

    def test_three_prompts_interpolate_ranges_block(self):
        # each f-string includes {ranges_block}
        assert DA_SOURCE.count("{ranges_block}") >= 3


# ---------------------------------------------------------------------------
# End-to-end: a rendered combined prompt contains the per-car aero range
# ---------------------------------------------------------------------------
class TestRenderedCombinedPromptHasRanges:
    def test_combined_prompt_includes_custom_aero_range(self, monkeypatch):
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Render Car": {
                "aero_front": {"min": 75, "max": 300},
                "aero_rear": {"min": 200, "max": 650},
            }
        })

        # Minimal fake LapStats with the attributes the prompt reads.
        class _Lap:
            lock_up_count = 1
            wheelspin_count = 1
            brake_consistency_m = 5.0
            oversteer_count = 1
            oversteer_throttle_on_count = 0
            kerb_count = 0
            bottoming_count = 0
            snap_throttle_count = 0
            max_lat_g = 1.0
            max_speed_kmh = 200.0

        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        # Stub every collaborator the prompt builder touches.
        adv._summarize_new_telemetry = lambda laps: ""
        adv._car_track_header = lambda *a, **k: ""
        adv._get_event_context_block = lambda: ""
        adv._get_driver_feedback_context = lambda: ""
        adv._get_previous_ai_context = lambda *a, **k: ""
        adv._get_track_intelligence_context = lambda: ""
        adv._get_enriched_issue_context = lambda laps: ""
        adv._get_live_segment_context = lambda live: ""
        adv._DATA_QUALITY_NOTE = ""

        prompt = adv._build_combined_prompt(
            [_Lap(), _Lap()], setup={}, history_str="",
            car_name="Render Car", car_specs={},
        )
        assert "Valid setup ranges for THIS car" in prompt
        assert "aero_front:" in prompt and "75" in prompt and "300" in prompt
        assert "aero_rear:" in prompt and "200" in prompt and "650" in prompt


# ---------------------------------------------------------------------------
# "tyres" must NOT appear in the lockable tuning categories — there is no
# tyres checkbox in the event setup, so it was always reported as LOCKED.
# ---------------------------------------------------------------------------
class TestTyresNotInLockableCategories:
    def test_driving_advisor_all_cats_excludes_tyres(self):
        assert "tyres" not in da._ALL_TUNING_CATS

    def test_ai_planner_all_cats_excludes_tyres(self):
        from strategy import ai_planner as ap
        assert "tyres" not in ap._ALL_TUNING_CATS

    def test_both_modules_agree_on_categories(self):
        from strategy import ai_planner as ap
        assert da._ALL_TUNING_CATS == ap._ALL_TUNING_CATS

    def test_partial_allowed_tuning_does_not_lock_tyres(self):
        # With aero allowed, the rendered restriction block must not list tyres.
        block = da._tuning_constraint_block(
            ["brake_balance", "suspension", "differential", "aero"],
            tuning_locked=False,
        )
        assert "LOCKED" in block
        locked_line = next(l for l in block.splitlines() if "LOCKED" in l)
        assert "tyres" not in locked_line

    def test_categories_match_dashboard_checkboxes(self):
        # Every lockable category must be a real selectable checkbox code in the
        # dashboard's _TUNING_CATEGORIES list (source-scan to avoid importing Qt).
        import re
        dash_src = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
        m = re.search(r"_TUNING_CATEGORIES[^=]*=\s*\[(.*?)\]", dash_src, re.DOTALL)
        assert m, "_TUNING_CATEGORIES list not found in dashboard.py"
        checkbox_codes = set(re.findall(r'\(\s*"([a-z_]+)"', m.group(1)))
        assert "tyres" not in checkbox_codes, "there is no tyres checkbox"
        assert set(da._ALL_TUNING_CATS) <= checkbox_codes, (
            "lockable categories must all be selectable in the event setup"
        )


# ---------------------------------------------------------------------------
# Build Setup path must pass each side's OWN min/max — never collapse front/rear
# to one side's range (per-car ranges can be set independently per side).
# ---------------------------------------------------------------------------
class TestBuildPromptPerSideRanges:
    @pytest.fixture(autouse=True)
    def _stub_loader(self, monkeypatch):
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Split Car": {
                "aero_front": {"min": 100, "max": 500},
                "aero_rear": {"min": 200, "max": 850},
                "ride_height_front": {"min": 60, "max": 90},
                "ride_height_rear": {"min": 70, "max": 110},
            }
        })
        yield

    def _build_prompt(self):
        from strategy import ai_planner as ap
        return ap._build_setup_from_scratch_prompt(
            "Split Car", "Daytona", "race", 1, 1030, 670,
            ranges=sr.resolve_ranges("Split Car"),
        )

    def test_aero_shows_both_sides_when_different(self):
        prompt = self._build_prompt()
        line = next(l for l in prompt.splitlines() if l.strip().startswith("aero_front"))
        assert "front 100" in line and "500" in line
        assert "rear 200" in line and "850" in line

    def test_ride_height_shows_both_sides_when_different(self):
        prompt = self._build_prompt()
        line = next(l for l in prompt.splitlines() if l.strip().startswith("ride_height_front"))
        assert "90" in line and "110" in line, "rear ride-height range must appear"

    def test_every_generic_default_field_named_in_build_block(self):
        from strategy.setup_ranges import GENERIC_DEFAULTS
        prompt = self._build_prompt()
        # The valid-ranges block names every adjustable parameter key.
        for field in GENERIC_DEFAULTS:
            assert field in prompt, f"{field} missing from build-setup ranges block"

    def test_equal_ranges_stay_compact(self):
        # springs F/R use generic defaults (equal) -> single compact range, no "front .../ rear ..."
        prompt = self._build_prompt()
        line = next(l for l in prompt.splitlines() if l.strip().startswith("springs_front"))
        assert "front" not in line.split(":", 1)[1].split("←")[0].lower()
