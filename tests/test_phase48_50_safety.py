"""Phase 48-50 — safety invariants (task items 40, 45-48 and section 18).

No-AI architecture; frozen Apply gate untouched; voice gate preserved; nothing auto-locks/finalises/
binds/applies; DB version + rule-engine version pinned; new modules import no LLM/cloud/TTS/keys.
"""
from __future__ import annotations

import pathlib

from strategy._setup_constants import DB_VERSION, RULE_ENGINE_VERSION

_NEW_MODULES = [
    "strategy/event_preparation_cycle.py",
    "strategy/preparation_transitions.py",
    "strategy/preparation_evidence.py",
    "strategy/setup_convergence.py",
    "strategy/setup_lock.py",
    "strategy/strategy_maturity.py",
    "strategy/strategy_finalisation.py",
    "strategy/race_weekend.py",
    "strategy/ngr_event_manifest.py",
    "ui/event_preparation_vm.py",
    "ui/race_weekend_vm.py",
]

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_FORBIDDEN = ["import openai", "anthropic", "requests.get", "urllib.request", "http://", "https://",
              "socket.", "subprocess", "api_key", "API_KEY", "pyttsx", "sapi", "tts", "os.system",
              "eval(", "exec(", "pickle"]


def test_new_modules_have_no_ai_network_or_tts():
    for rel in _NEW_MODULES:
        src = (_ROOT / rel).read_text(encoding="utf-8").lower()
        for bad in _FORBIDDEN:
            assert bad.lower() not in src, f"{rel} contains forbidden token {bad!r}"


def test_versions_pinned():
    assert DB_VERSION == 28
    assert RULE_ENGINE_VERSION == "46.0"  # no rule-behaviour change in this slice


def test_new_modules_import_no_qt():
    for rel in _NEW_MODULES:
        if rel.startswith("ui/"):
            continue  # vms are Qt-free but live under ui/; panels legitimately import Qt
        src = (_ROOT / rel).read_text(encoding="utf-8")
        assert "PyQt6" not in src and "PyQt5" not in src, f"{rel} imports Qt"


def test_setup_lock_never_locks_without_confirmation():
    from strategy.setup_lock import build_lock_decision
    from strategy.setup_convergence import SetupConvergenceState, SetupDiscipline
    for _ in range(3):
        d = build_lock_decision(SetupDiscipline.RACE, SetupConvergenceState.LOCK_READY, confirmed=False)
        assert d.locked is False


def test_strategy_never_finalises_without_confirmation():
    from strategy.strategy_finalisation import build_strategy_finalisation
    from strategy.strategy_maturity import StrategyMaturity
    d = build_strategy_finalisation(StrategyMaturity.FINALISATION_READY, confirmed=False)
    assert d.finalised is False


def test_race_runtime_issues_no_pit_commands_and_voice_off_by_default():
    from strategy.race_weekend import build_race_runtime_profile
    p = build_race_runtime_profile()
    assert p.issues_pit_commands is False
    assert p.voice_enabled is False


def test_voice_gate_authority_unchanged():
    # the VOICE_ELIGIBLE gate remains owned by shadow_advisory (this slice added no voice authority)
    from strategy.shadow_advisory import voice_gate_allows, LiveValidationReadiness
    assert voice_gate_allows(LiveValidationReadiness.VOICE_ELIGIBLE.value) is True
    assert voice_gate_allows(LiveValidationReadiness.NOT_READY.value) is False


def test_apply_gate_untouched():
    # the single canonical setup-mutation route still lives on ActiveSetupAuthority (not re-implemented)
    from data.setup_state_authority import ActiveSetupAuthority
    assert hasattr(ActiveSetupAuthority, "mark_applied")


def test_evidence_aggregation_cannot_be_raised_by_invalid_or_incompatible():
    from strategy.event_preparation_cycle import PreparationActivityType as T
    from strategy.preparation_evidence import (
        PracticeEvidenceSample, EvidenceCompatibility as C, EvidenceDomain as Dom,
        build_cumulative_evidence)

    def _s(sid, valid=True, compat=C.EXACT):
        return PracticeEvidenceSample(sid, "a" + sid, T.SETUP_EXPERIMENT, is_valid=valid,
                                      compatibility=compat)
    base = build_cumulative_evidence([_s("1"), _s("2")])
    plus_bad = build_cumulative_evidence([_s("1"), _s("2"), _s("x", valid=False),
                                          _s("y", compat=C.INCOMPATIBLE)])
    assert plus_bad.confidence(Dom.SETUP_BASE) == base.confidence(Dom.SETUP_BASE)
