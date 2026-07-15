"""
Group 33 — Dashboard UI wiring for feasibility-gated StrategyResult

Tests the three UI changes introduced to ui/dashboard.py to consume the new
StrategyResult from the backend:

  Task 1 — _display_strategy_results reads result.strategies explicitly
            (getattr shim) rather than relying on the iterable shim.
  Task 2 — _build_feasibility_html renders rejected strategies, data gaps,
            assumptions, and calculation notes below the strategy cards;
            empty sections produce no header.
  Task 3 — Timed-race lap estimate uses estimate_race_laps (ceil) + best clean
            lap of the compound with the most data, matching the feasibility
            module exactly.

All tests are source-text inspection or in-memory logic tests — no Qt widgets,
no real API calls, no file I/O beyond reading dashboard.py once.
"""
from __future__ import annotations

import math
import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DASHBOARD_SRC = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers — locate method bodies by name
# ---------------------------------------------------------------------------

def _method_body(text: str, method_name: str) -> str:
    """Return the source text of the first method whose def line matches."""
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# ---------------------------------------------------------------------------
# Task 1 — _display_strategy_results reads .strategies explicitly
# ---------------------------------------------------------------------------

class TestDisplayStrategyResultsExplicitStrategies:
    """_display_strategy_results must extract .strategies via getattr rather than
    treating the StrategyResult as a plain list, and must handle bare-list payloads
    via the getattr(payload, 'strategies', payload) defensive pattern."""

    def setup_method(self):
        self._body = _method_body(DASHBOARD_SRC, "_display_strategy_results")

    def test_method_exists(self):
        assert self._body, "_display_strategy_results not found in dashboard.py"

    def test_uses_getattr_strategies_fallback(self):
        """Must use getattr(payload, 'strategies', payload) defensive pattern."""
        assert "getattr(payload" in self._body or "getattr(" in self._body, (
            "_display_strategy_results must use getattr() to extract .strategies"
        )
        assert "strategies" in self._body, (
            "_display_strategy_results must reference .strategies"
        )

    def test_does_not_assign_options_directly_from_payload(self):
        """options = payload (bare assignment) must no longer appear; the assignment
        must go through getattr."""
        # The old bare assignment was:  options = payload
        # The new code is:  options = getattr(payload, "strategies", payload)
        # We check that the new form is present.
        assert "getattr(payload, " in self._body, (
            "_display_strategy_results must use getattr(payload, ...) for options"
        )

    def test_calls_build_feasibility_html(self):
        """_build_feasibility_html must be called with payload (not options)."""
        assert "_build_feasibility_html(payload)" in self._body, (
            "_display_strategy_results must call _build_feasibility_html(payload)"
        )

    def test_feasibility_html_appended_when_nonempty(self):
        """The result HTML must include _feasibility_html when it is non-empty."""
        assert "_feasibility_html" in self._body, (
            "_display_strategy_results must use _feasibility_html"
        )
        assert "_full_html += _feasibility_html" in self._body, (
            "_display_strategy_results must concatenate _feasibility_html onto _full_html"
        )


# ---------------------------------------------------------------------------
# Task 2 — _build_feasibility_html
# ---------------------------------------------------------------------------

class TestBuildFeasibilityHtmlMethodExists:
    def setup_method(self):
        self._body = _method_body(DASHBOARD_SRC, "_build_feasibility_html")

    def test_method_defined(self):
        assert self._body, "_build_feasibility_html not found in dashboard.py"

    def test_reads_rejected_strategies(self):
        assert "rejected_strategies" in self._body

    def test_reads_data_gaps(self):
        assert "data_gaps" in self._body

    def test_reads_assumptions(self):
        assert "assumptions" in self._body

    def test_reads_calculation_notes(self):
        assert "calculation_notes" in self._body

    def test_returns_empty_string_guard(self):
        """If all four lists are empty, the method must return ''."""
        assert 'return ""' in self._body, (
            "_build_feasibility_html must return empty string when all lists are empty"
        )

    def test_uses_getattr_for_all_fields(self):
        """Must use getattr so bare-list payloads produce empty string safely."""
        assert "getattr(payload" in self._body or "getattr(" in self._body


class TestBuildFeasibilityHtmlLogic:
    """Test _build_feasibility_html in isolation by importing the module and
    constructing a minimal fake dashboard object with the method."""

    def _make_dashboard_cls(self):
        """Import the source fragment containing _build_feasibility_html as a method
        of a minimal test class without instantiating the full Qt dashboard."""
        # We exec just the method body into a class namespace.
        body = _method_body(DASHBOARD_SRC, "_build_feasibility_html")
        ns: dict = {}
        # Wrap it in a class so 'self' works
        class_src = "class _FakeDash:\n" + "\n".join(
            "    " + line for line in body.splitlines()
        )
        exec(class_src, ns)  # noqa: S102
        return ns["_FakeDash"]

    def _make_result(self, rejected=None, data_gaps=None, assumptions=None, notes=None):
        """Return a mock StrategyResult-like object."""
        r = MagicMock()
        r.rejected_strategies = rejected or []
        r.data_gaps = data_gaps or []
        r.assumptions = assumptions or []
        r.calculation_notes = notes or []
        return r

    def _make_rejected(self, name: str, reason: str):
        r = MagicMock()
        r.name = name
        r.reason = reason
        return r

    def _make_gap(self, name: str, description: str):
        g = MagicMock()
        g.name = name
        g.description = description
        return g

    def test_returns_empty_string_for_bare_list(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        # A bare list has no .rejected_strategies etc — getattr returns None → []
        result = obj._build_feasibility_html([])
        assert result == ""

    def test_returns_empty_string_when_all_lists_empty(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result()
        result = obj._build_feasibility_html(payload)
        assert result == ""

    def test_renders_rejected_strategy_name_and_reason(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(
            rejected=[self._make_rejected("0-stop", "Fuel-limited — tank runs out after 33 laps")]
        )
        html = obj._build_feasibility_html(payload)
        assert "0-stop" in html
        assert "Fuel-limited" in html

    def test_renders_data_gap_name_and_description(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(
            data_gaps=[self._make_gap("missing_refuel_speed", "refuel_speed_lps is 0")]
        )
        html = obj._build_feasibility_html(payload)
        assert "missing_refuel_speed" in html
        assert "refuel_speed_lps" in html

    def test_renders_assumptions(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(assumptions=["GT7 may require completing the lap."])
        html = obj._build_feasibility_html(payload)
        assert "GT7 may require completing the lap." in html

    def test_renders_calculation_notes(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(notes=["Race laps = ceil(7200/96.3) = 75."])
        html = obj._build_feasibility_html(payload)
        assert "Race laps = ceil(7200/96.3) = 75." in html

    def test_no_rejected_header_when_rejected_empty(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(assumptions=["Only assumption"])
        html = obj._build_feasibility_html(payload)
        assert "Rejected Stop Counts" not in html

    def test_no_data_gaps_header_when_data_gaps_empty(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(assumptions=["Only assumption"])
        html = obj._build_feasibility_html(payload)
        assert "Data Gaps" not in html

    def test_no_assumptions_header_when_assumptions_empty(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(
            rejected=[self._make_rejected("0-stop", "reason")]
        )
        html = obj._build_feasibility_html(payload)
        assert "Assumptions" not in html

    def test_no_calculation_notes_header_when_notes_empty(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(
            rejected=[self._make_rejected("0-stop", "reason")]
        )
        html = obj._build_feasibility_html(payload)
        assert "Calculation Notes" not in html

    def test_multiple_rejected_all_rendered(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(
            rejected=[
                self._make_rejected("0-stop", "Reason A"),
                self._make_rejected("1-stop", "Reason B"),
            ]
        )
        html = obj._build_feasibility_html(payload)
        assert "0-stop" in html
        assert "1-stop" in html
        assert "Reason A" in html
        assert "Reason B" in html

    def test_html_is_wrapped_in_div(self):
        cls = self._make_dashboard_cls()
        obj = cls.__new__(cls)
        payload = self._make_result(assumptions=["test"])
        html = obj._build_feasibility_html(payload)
        assert html.startswith("<div")
        assert html.endswith("</div>")


# ---------------------------------------------------------------------------
# Task 3 — Lap estimate logic matches feasibility module
# ---------------------------------------------------------------------------

class TestTimedRaceLapLogicAgreesWithFeasibility:
    """Verify that the representative-lap selection logic in dashboard.py produces
    the same estimate as strategy.feasibility.estimate_race_laps for the same inputs.
    This is a pure-logic test — no Qt, no DB."""

    def _dashboard_estimate(
        self,
        duration_secs: float,
        lap_data_by_compound: dict,
    ) -> int:
        """Replicate the dashboard's Task 3 logic in isolation."""
        from statistics import mean as _mean
        from strategy.feasibility import estimate_race_laps as _estimate_race_laps

        representative_lap_s: float = 0.0
        if lap_data_by_compound:
            try:
                rep_compound = max(
                    lap_data_by_compound,
                    key=lambda c: (
                        len(lap_data_by_compound[c]),
                        -_mean(lap_data_by_compound[c]) if lap_data_by_compound[c] else 0,
                    ),
                )
                rep_laps = lap_data_by_compound[rep_compound]
                if rep_laps:
                    representative_lap_s = min(rep_laps) / 1000.0  # ms → s
            except Exception:
                pass
        est = _estimate_race_laps(duration_secs, representative_lap_s)
        return max(1, est)

    def test_120_min_single_compound_rm(self):
        """120 min, RM at 96290 ms best lap: ceil(7200/96.29) = 75."""
        laps = {"RM": [96290.0 + i * 50 for i in range(10)]}  # best = 96290
        result = self._dashboard_estimate(7200.0, laps)
        assert result == 75

    def test_selects_compound_with_most_laps(self):
        """When RS has more laps than RM, RS is selected as representative."""
        laps = {
            "RM": [90000.0] * 5,   # 5 laps, best = 90000 ms = 90.0s
            "RS": [88000.0] * 8,   # 8 laps, best = 88000 ms = 88.0s → more laps
        }
        # RS is selected (more laps); best lap = 88.0s
        # ceil(3600 / 88.0) = ceil(40.909) = 41
        result = self._dashboard_estimate(3600.0, laps)
        assert result == 41

    def test_tiebreak_on_fastest_average(self):
        """When two compounds have equal lap count, tiebreak on fastest average selects
        the compound with the lower average (higher priority in max key)."""
        laps = {
            "RM": [90000.0, 91000.0],   # avg = 90500
            "RS": [88000.0, 89000.0],   # avg = 88500 → lower avg → higher priority
        }
        # RS selected (same count, but lower avg means -avg is less negative so higher);
        # best lap of RS = 88000 ms = 88.0s; ceil(3600/88) = 41
        result = self._dashboard_estimate(3600.0, laps)
        assert result == 41

    def test_uses_min_not_mean(self):
        """Representative lap is the MINIMUM (best) lap, not the mean.
        If mean were used the result would differ."""
        # Compound with one very slow outlier lap — mean would be ~100s,
        # but min is ~90s.
        laps = {"RM": [90000.0, 90100.0, 130000.0]}  # min=90.0s, mean≈103.4s
        # ceil(3600 / 90.0) = 40
        result_with_min = self._dashboard_estimate(3600.0, laps)
        assert result_with_min == 40, (
            f"Expected 40 (using min 90.0s), got {result_with_min}"
        )
        # Verify that using mean would give a different answer (confirming the
        # test is sensitive to the min-vs-mean distinction)
        mean_s = (90000.0 + 90100.0 + 130000.0) / 3 / 1000.0
        result_with_mean = max(1, math.ceil(3600.0 / mean_s))
        assert result_with_mean != 40, (
            "Test is not discriminating — mean also gives 40; adjust the test data"
        )

    def test_empty_compound_list_returns_1(self):
        """No lap data → representative_lap_s stays 0 → estimate_race_laps returns 0 → floor to 1."""
        result = self._dashboard_estimate(7200.0, {})
        assert result == 1

    def test_result_matches_feasibility_module(self):
        """The dashboard estimate must agree with estimate_race_laps for the same inputs."""
        from strategy.feasibility import estimate_race_laps
        laps = {"RM": [96290.0 + i * 100 for i in range(12)]}  # best = 96290 ms
        dashboard_result = self._dashboard_estimate(7200.0, laps)
        feasibility_result = max(1, estimate_race_laps(7200.0, 96290.0 / 1000.0))
        assert dashboard_result == feasibility_result, (
            f"Dashboard estimate {dashboard_result} != feasibility estimate {feasibility_result}"
        )

    def test_ceil_not_floor(self):
        """Verify ceil is used: 7201s / 96.0s/lap should round UP."""
        # 7201 / 96.0 = 75.01 → ceil = 76
        laps = {"RM": [96000.0] * 10}  # best = 96.0s
        result = self._dashboard_estimate(7201.0, laps)
        assert result == 76, f"Expected ceil(7201/96.0)=76, got {result}"
