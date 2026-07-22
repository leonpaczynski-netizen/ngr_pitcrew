"""Tests for the UI-rebuild design tokens added to ui/ngr_theme.py (F0.4).

These tokens are additive: existing tokens/builders are unchanged. Every state
descriptor must carry a `tone` that indexes STATUS_TONES and a human `label`, so
meaning is conveyed by colour + text (+ glyph) — never colour alone.
"""

import ui.ngr_theme as t


ALL_STATE_TABLES = [
    ("STAGE_STATES", t.STAGE_STATES),
    ("OUTCOME_TONES", t.OUTCOME_TONES),
    ("FRESHNESS_TONES", t.FRESHNESS_TONES),
    ("MATCH_TRUST", t.MATCH_TRUST),
]


class TestTokenIntegrity:
    def test_state_tables_reference_valid_tones_and_have_labels(self):
        for name, table in ALL_STATE_TABLES:
            for key, desc in table.items():
                assert desc.get("tone") in t.STATUS_TONES, f"{name}[{key}] bad tone"
                assert desc.get("label"), f"{name}[{key}] missing label"

    def test_confidence_levels_have_valid_tone_and_fill(self):
        for key, desc in t.CONFIDENCE_LEVELS.items():
            assert desc["tone"] in t.STATUS_TONES
            assert desc["label"]
            assert 0.0 <= desc["fill"] <= 1.0

    def test_worse_outcome_is_danger_and_prominent(self):
        # Negative feedback must be authoritative — DANGER tone, not softened.
        assert t.OUTCOME_TONES["worse"]["tone"] == "danger"

    def test_match_trust_tiers_are_visually_distinct(self):
        # approved vs fallback must differ so a fallback never looks high-confidence.
        assert t.MATCH_TRUST["approved"]["tone"] != t.MATCH_TRUST["fallback"]["tone"]

    def test_no_emoji_glyphs(self):
        # Glyphs must be plain typographic marks, not emoji (icon rule).
        glyphs = [d.get("glyph", "") for _, tbl in ALL_STATE_TABLES for d in tbl.values()]
        for g in glyphs:
            for ch in g:
                assert ord(ch) < 0x1F000, f"emoji-range glyph {g!r} not allowed"


class TestResolvers:
    def test_stage_state_defaults_to_available(self):
        assert t.stage_state("nonexistent") is t.STAGE_STATES[t.STAGE_AVAILABLE]
        assert t.stage_state(t.STAGE_COMPLETE)["glyph"] == "✓"

    def test_confidence_level_defaults_to_unknown_and_is_case_insensitive(self):
        assert t.confidence_level("HIGH")["fill"] == 1.0
        assert t.confidence_level("bogus") is t.CONFIDENCE_LEVELS["unknown"]

    def test_outcome_freshness_match_resolvers_never_raise(self):
        assert t.outcome_tone(None)["label"] == "Unchanged"
        assert t.freshness_tone("")["label"] == "NO SIGNAL"
        assert t.match_trust("nope")["label"] == "Position unavailable"


class TestFocusRing:
    def test_focus_ring_qss_uses_accent_and_removes_default_outline(self):
        qss = t.focus_ring_qss()
        assert t.NGR_GREEN in qss
        assert "outline: none" in qss

    def test_focus_ring_custom_width(self):
        assert "3px" in t.focus_ring_qss(width=3)
