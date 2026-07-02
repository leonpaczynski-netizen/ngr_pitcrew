"""Tests for Group 40: Strategy-card outcome-comparison rendering.

Covers _build_strategy_html in ui/dashboard.py:

Deliverable 1  — head-to-head delta:
  * When deterministic_time_s > 0, app time is shown prefixed "App:".
  * The fastest option (delta_vs_fastest_s == 0.0) shows "fastest".
  * Slower options show "+X.Xs vs fastest".
  * AI estimate is always shown, labeled "AI est:" when app time is present.
  * When deterministic_time_s == 0, only "AI est:" is shown and no delta line.

Deliverable 2  — outcome_confidence:
  * "high"   => green colour #8BC34A.
  * "medium" => amber colour #F5C542.
  * "low"    => red colour #F55.
  * Empty/absent => no "(confidence:" text.

Deliverable 3  — risk chips and confidence_score:
  * tyre_risk, fuel_risk, undercut_risk appear when non-empty.
  * Absent/empty fields are omitted.
  * confidence_score > 0 shown as "AI conf: XX%".
  * confidence_score == 0 omitted.

Deliverable 4  — pit time label:
  * "pit time" appears; the old "pit loss" label must be absent.

Deliverable 5  — rank badge:
  * rank_by_time > 0 => "#N by time" badge.
  * rank_by_time == 0 / absent => no badge.

Backwards-compatibility:
  * StrategyOption without the new fields (legacy objects) must not raise
    AttributeError.
"""
from __future__ import annotations

import pathlib
import types
import unittest

_SRC = pathlib.Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Minimal stub for StrategyOption that mirrors the full dataclass but
# lives entirely in-process so the test never imports Qt.
# ---------------------------------------------------------------------------

def _make_opt(**kwargs) -> object:
    """Create a minimal StrategyOption-like namespace for HTML rendering tests."""
    defaults = dict(
        rank=1,
        name="One-stop",
        stints=[{"compound": "Medium", "laps": 30}],
        estimated_time_s=3600.0,
        pit_time_s=22.0,
        summary="One-stop strategy",
        positives="Fewer stops",
        negatives="",
        risks="Tyre wear risk",
        # new fields
        deterministic_time_s=0.0,
        delta_vs_fastest_s=0.0,
        outcome_confidence="",
        rank_by_time=0,
        tyre_risk="",
        fuel_risk="",
        undercut_risk="",
        confidence_score=0.0,
    )
    defaults.update(kwargs)
    ns = types.SimpleNamespace(**defaults)
    return ns


# ---------------------------------------------------------------------------
# Extract just the _build_strategy_html method from dashboard.py and exec it
# into a throwaway class so we can call it without importing PyQt6.
# ---------------------------------------------------------------------------

def _load_build_strategy_html():
    """Return a bound-free function equivalent to _build_strategy_html."""
    src = (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")
    start = src.find("    def _build_strategy_html(")
    assert start != -1, "_build_strategy_html not found in dashboard.py"
    # Find the next method at the same indent level
    end = src.find("\n    def ", start + 1)
    body = src[start:end] if end != -1 else src[start:]
    # Dedent one level (4 spaces) so it can be exec'd at module scope
    dedented = "\n".join(
        line[4:] if line.startswith("    ") else line
        for line in body.splitlines()
    )
    globs: dict = {}
    exec(dedented, globs)  # noqa: S102
    return globs["_build_strategy_html"]


_build_strategy_html = _load_build_strategy_html()


def _html(options, loaded_rank=0) -> str:
    """Call _build_strategy_html as an unbound function (pass None as self)."""
    return _build_strategy_html(None, options, loaded_rank)


# ---------------------------------------------------------------------------
# Group 40a — Deliverable 1: head-to-head delta
# ---------------------------------------------------------------------------

class TestHeadToHeadDelta(unittest.TestCase):

    def test_app_time_shown_when_deterministic_computed(self):
        """App-computed time appears as 'App: M:SS.ss' when deterministic_time_s > 0."""
        opt = _make_opt(deterministic_time_s=3720.5, delta_vs_fastest_s=0.0)
        html = _html([opt])
        self.assertIn("App:", html)

    def test_fastest_label_when_delta_zero(self):
        """The fastest option (delta == 0.0) shows 'fastest'."""
        opt = _make_opt(deterministic_time_s=3600.0, delta_vs_fastest_s=0.0)
        html = _html([opt])
        self.assertIn("fastest", html)

    def test_delta_shown_for_slower_option(self):
        """A slower option shows '+X.Xs vs fastest'."""
        opt = _make_opt(deterministic_time_s=3700.0, delta_vs_fastest_s=23.4)
        html = _html([opt])
        self.assertIn("+23.4s vs fastest", html)

    def test_ai_est_label_shown_alongside_app_time(self):
        """When app time is present, the AI estimate is still shown labeled 'AI est:'."""
        opt = _make_opt(deterministic_time_s=3600.0, delta_vs_fastest_s=0.0,
                        estimated_time_s=3650.0)
        html = _html([opt])
        self.assertIn("AI est:", html)

    def test_no_app_time_when_deterministic_zero(self):
        """When deterministic_time_s == 0, 'App:' label must not appear."""
        opt = _make_opt(deterministic_time_s=0.0)
        html = _html([opt])
        self.assertNotIn("App:", html)

    def test_no_delta_when_deterministic_zero(self):
        """When deterministic_time_s == 0, 'vs fastest' must not appear."""
        opt = _make_opt(deterministic_time_s=0.0)
        html = _html([opt])
        self.assertNotIn("vs fastest", html)

    def test_ai_est_shown_even_when_no_deterministic(self):
        """When deterministic_time_s == 0, AI estimate is still displayed."""
        opt = _make_opt(deterministic_time_s=0.0, estimated_time_s=3600.0)
        html = _html([opt])
        self.assertIn("AI est:", html)

    def test_delta_format_one_decimal(self):
        """Delta is formatted to one decimal place."""
        opt = _make_opt(deterministic_time_s=3700.0, delta_vs_fastest_s=5.678)
        html = _html([opt])
        self.assertIn("+5.7s vs fastest", html)


# ---------------------------------------------------------------------------
# Group 40b — Deliverable 2: outcome_confidence
# ---------------------------------------------------------------------------

class TestOutcomeConfidence(unittest.TestCase):

    def test_high_confidence_green(self):
        """'high' confidence uses green colour #8BC34A."""
        opt = _make_opt(deterministic_time_s=3600.0, outcome_confidence="high")
        html = _html([opt])
        self.assertIn("confidence: high", html)
        # The span wrapping the badge uses the green colour
        idx = html.find("confidence: high")
        snippet = html[max(0, idx - 80):idx]
        self.assertIn("#8BC34A", snippet)

    def test_medium_confidence_amber(self):
        """'medium' confidence uses amber colour #F5C542."""
        opt = _make_opt(deterministic_time_s=3600.0, outcome_confidence="medium")
        html = _html([opt])
        self.assertIn("confidence: medium", html)
        idx = html.find("confidence: medium")
        snippet = html[max(0, idx - 80):idx]
        self.assertIn("#F5C542", snippet)

    def test_low_confidence_red(self):
        """'low' confidence uses red colour #F55."""
        opt = _make_opt(deterministic_time_s=3600.0, outcome_confidence="low")
        html = _html([opt])
        self.assertIn("confidence: low", html)
        idx = html.find("confidence: low")
        snippet = html[max(0, idx - 80):idx]
        self.assertIn("#F55", snippet)

    def test_empty_confidence_no_badge(self):
        """Empty outcome_confidence produces no '(confidence:' text."""
        opt = _make_opt(deterministic_time_s=3600.0, outcome_confidence="")
        html = _html([opt])
        self.assertNotIn("confidence:", html)

    def test_no_confidence_when_no_deterministic(self):
        """When deterministic_time_s == 0, confidence badge is not shown."""
        opt = _make_opt(deterministic_time_s=0.0, outcome_confidence="high")
        html = _html([opt])
        self.assertNotIn("confidence: high", html)


# ---------------------------------------------------------------------------
# Group 40c — Deliverable 3: risk chips and confidence_score
# ---------------------------------------------------------------------------

class TestRiskChips(unittest.TestCase):

    def test_tyre_risk_shown_when_set(self):
        """tyre_risk non-empty produces 'tyre: <value>' chip."""
        opt = _make_opt(tyre_risk="medium")
        html = _html([opt])
        self.assertIn("tyre: medium", html)

    def test_fuel_risk_shown_when_set(self):
        """fuel_risk non-empty produces 'fuel: <value>' chip."""
        opt = _make_opt(fuel_risk="high")
        html = _html([opt])
        self.assertIn("fuel: high", html)

    def test_undercut_risk_shown_when_set(self):
        """undercut_risk non-empty produces 'undercut: <value>' chip."""
        opt = _make_opt(undercut_risk="low")
        html = _html([opt])
        self.assertIn("undercut: low", html)

    def test_tyre_risk_absent_when_empty(self):
        """Empty tyre_risk produces no 'tyre:' text in card."""
        opt = _make_opt(tyre_risk="")
        html = _html([opt])
        self.assertNotIn("tyre:", html)

    def test_fuel_risk_absent_when_empty(self):
        """Empty fuel_risk produces no 'fuel:' text in card."""
        opt = _make_opt(fuel_risk="")
        html = _html([opt])
        self.assertNotIn("fuel:", html)

    def test_undercut_risk_absent_when_empty(self):
        """Empty undercut_risk produces no 'undercut:' text in card."""
        opt = _make_opt(undercut_risk="")
        html = _html([opt])
        self.assertNotIn("undercut:", html)

    def test_confidence_score_shown_as_percentage(self):
        """confidence_score > 0 is rendered as 'AI conf: XX%'."""
        opt = _make_opt(confidence_score=0.85)
        html = _html([opt])
        self.assertIn("AI conf: 85%", html)

    def test_confidence_score_zero_omitted(self):
        """confidence_score == 0.0 must not produce an 'AI conf:' line."""
        opt = _make_opt(confidence_score=0.0)
        html = _html([opt])
        self.assertNotIn("AI conf:", html)

    def test_low_risk_chip_green(self):
        """'low' risk value uses green colour #8BC34A."""
        opt = _make_opt(tyre_risk="low")
        html = _html([opt])
        idx = html.find("tyre: low")
        # colour attribute sits ~90 chars before the label text
        snippet = html[max(0, idx - 120):idx]
        self.assertIn("#8BC34A", snippet)

    def test_high_risk_chip_red(self):
        """'high' risk value uses red colour #F55."""
        opt = _make_opt(fuel_risk="high")
        html = _html([opt])
        idx = html.find("fuel: high")
        snippet = html[max(0, idx - 120):idx]
        self.assertIn("#F55", snippet)


# ---------------------------------------------------------------------------
# Group 40d — Deliverable 4: pit time label fix
# ---------------------------------------------------------------------------

class TestPitTimeLabel(unittest.TestCase):

    def test_pit_time_label_present(self):
        """'pit time' label must appear in the rendered card."""
        opt = _make_opt()
        html = _html([opt])
        self.assertIn("pit time", html)

    def test_pit_loss_label_absent(self):
        """The old 'pit loss' mislabel must no longer appear."""
        opt = _make_opt()
        html = _html([opt])
        self.assertNotIn("pit loss", html)

    def test_pit_time_value_rendered(self):
        """The pit_time_s value is still rendered in the card."""
        opt = _make_opt(pit_time_s=25.0)
        html = _html([opt])
        self.assertIn("25.0s", html)


# ---------------------------------------------------------------------------
# Group 40e — Deliverable 5: rank badge
# ---------------------------------------------------------------------------

class TestRankBadge(unittest.TestCase):

    def test_rank_badge_shown_when_rank_by_time_set(self):
        """rank_by_time > 0 produces '#N by time' badge."""
        opt = _make_opt(rank_by_time=1)
        html = _html([opt])
        self.assertIn("#1 by time", html)

    def test_rank_badge_second_place(self):
        """rank_by_time == 2 produces '#2 by time'."""
        opt = _make_opt(rank_by_time=2)
        html = _html([opt])
        self.assertIn("#2 by time", html)

    def test_no_rank_badge_when_zero(self):
        """rank_by_time == 0 produces no 'by time' badge."""
        opt = _make_opt(rank_by_time=0)
        html = _html([opt])
        self.assertNotIn("by time", html)


# ---------------------------------------------------------------------------
# Group 40f — backwards-compatibility (legacy StrategyOption without new fields)
# ---------------------------------------------------------------------------

class TestLegacyCompatibility(unittest.TestCase):

    def _make_legacy_opt(self):
        """A StrategyOption-like object that lacks all new backend fields."""
        return types.SimpleNamespace(
            rank=1,
            name="Legacy",
            stints=[{"compound": "Hard", "laps": 40}],
            estimated_time_s=3700.0,
            pit_time_s=20.0,
            summary="Old cached option",
            positives="",
            negatives="",
            risks="",
        )

    def test_legacy_opt_does_not_raise(self):
        """Rendering a legacy StrategyOption (no new fields) must not raise AttributeError."""
        opt = self._make_legacy_opt()
        try:
            html = _html([opt])
        except AttributeError as exc:
            self.fail(f"AttributeError raised for legacy StrategyOption: {exc}")

    def test_legacy_opt_shows_ai_estimate(self):
        """Legacy options still render the AI estimate time."""
        opt = self._make_legacy_opt()
        html = _html([opt])
        self.assertIn("AI est:", html)

    def test_legacy_opt_no_delta(self):
        """Legacy options must not show 'vs fastest' (no deterministic data)."""
        opt = self._make_legacy_opt()
        html = _html([opt])
        self.assertNotIn("vs fastest", html)

    def test_legacy_opt_no_risk_chips(self):
        """Legacy options must not show any risk chip text."""
        opt = self._make_legacy_opt()
        html = _html([opt])
        for label in ("tyre:", "fuel:", "undercut:", "AI conf:"):
            self.assertNotIn(label, html)

    def test_legacy_opt_no_rank_badge(self):
        """Legacy options must not show 'by time' badge."""
        opt = self._make_legacy_opt()
        html = _html([opt])
        self.assertNotIn("by time", html)


# ---------------------------------------------------------------------------
# Group 40g — source-level guard assertions (static analysis)
# ---------------------------------------------------------------------------

class TestSourceGuards(unittest.TestCase):
    """Verify the implementation uses getattr guards for all new fields."""

    def setUp(self):
        src = (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")
        start = src.find("    def _build_strategy_html(")
        end = src.find("\n    def ", start + 1)
        self._body = src[start:end] if end != -1 else src[start:]

    def _assert_getattr_guard(self, field: str):
        self.assertIn(f'getattr(opt, "{field}"', self._body,
                      f'Missing getattr guard for field "{field}" in _build_strategy_html')

    def test_guard_deterministic_time_s(self):
        self._assert_getattr_guard("deterministic_time_s")

    def test_guard_delta_vs_fastest_s(self):
        self._assert_getattr_guard("delta_vs_fastest_s")

    def test_guard_outcome_confidence(self):
        self._assert_getattr_guard("outcome_confidence")

    def test_guard_rank_by_time(self):
        self._assert_getattr_guard("rank_by_time")

    def test_guard_tyre_risk(self):
        self._assert_getattr_guard("tyre_risk")

    def test_guard_fuel_risk(self):
        self._assert_getattr_guard("fuel_risk")

    def test_guard_undercut_risk(self):
        self._assert_getattr_guard("undercut_risk")

    def test_guard_confidence_score(self):
        self._assert_getattr_guard("confidence_score")

    def test_pit_loss_not_in_source(self):
        """The old 'pit loss' mislabel must not exist anywhere in _build_strategy_html."""
        self.assertNotIn("pit loss", self._body)

    def test_pit_time_in_source(self):
        """The corrected 'pit time' label must appear in _build_strategy_html."""
        self.assertIn("pit time", self._body)


if __name__ == "__main__":
    unittest.main()
