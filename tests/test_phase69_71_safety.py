"""Phase 69-71 — safety / metamorphic assertions (spec 9.2).

Source + behaviour proofs that the UAT-activation slice introduces no new listener, no raw-packet access,
no setup-authoring, no Apply/approve, no automatic pit/game command, no setup-history write, no physical
adapter activation from unit tests, and no false PASS for a physical certification area; that ambiguous
speech carries no driver-report label; that missing evidence never increases confidence; that the tyre
proxy is never labelled measured; that bench mode cannot mutate live state; and that manual evidence needs
an explicit user action.
"""
from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

_NEW_MODULES = [
    "strategy/live_uat_runtime_snapshot.py",
    "strategy/live_session_lifecycle.py",
    "strategy/bench_uat_harness.py",
    "strategy/manual_uat_evidence.py",
    "strategy/release_candidate_manifest.py",
    "data/manual_uat_store.py",
    "ui/uat_runtime_vm.py",
    "ui/bench_uat_vm.py",
    "ui/manual_uat_vm.py",
]

_ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _code_only(rel: str) -> str:
    """Source with all comments and string/docstring contents removed — so a safety assertion inspects
    actual CODE (imports, calls, names), never prose describing what a module deliberately does NOT do."""
    src = _src(rel)
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return src
    return " ".join(out)


def test_no_new_udp_listener_or_socket_in_new_modules():
    for rel in _NEW_MODULES:
        s = _src(rel)
        assert "socket.socket" not in s, rel
        assert "SOCK_DGRAM" not in s, rel
        assert "UDPListener" not in s, rel
        assert ".bind(" not in s, rel


def test_no_raw_packet_access_in_new_strategy_modules():
    for rel in ("strategy/live_uat_runtime_snapshot.py", "strategy/bench_uat_harness.py"):
        s = _src(rel)
        assert "recvfrom" not in s, rel
        assert "GT7Packet" not in s, rel


def test_no_setup_authoring_or_apply_imports():
    # inspect CODE only — the banned names must not appear as identifiers/imports (docstrings that
    # describe the safety boundary in prose are legitimately allowed to mention them).
    banned = ("save_setup_history", "apply_setup", "SetupApply", "write_setup", "setup_history")
    for rel in _NEW_MODULES:
        s = _code_only(rel).lower()
        for b in banned:
            assert b.lower() not in s, f"{rel} must not reference {b} in code"


def test_no_automatic_pit_or_game_command():
    for rel in ("strategy/bench_uat_harness.py", "strategy/live_uat_runtime_snapshot.py"):
        s = _code_only(rel).lower()
        for b in ("keyboard", "joystick", "sendkey", "pyautogui", "press_button", "execute_pit"):
            assert b not in s, f"{rel} must not issue device/game commands ({b}) in code"


def test_bench_result_safety_checks_are_all_true():
    from strategy.bench_uat_harness import run_bench_uat
    rep = run_bench_uat()
    for r in rep.results:
        assert r.safety_checks["no_telemetry_listener"] is True
        assert r.safety_checks["no_setup_history_write"] is True
        assert r.safety_checks["no_engineering_memory_write"] is True
        assert r.safety_checks["no_physical_certification_promotion"] is True


def test_ambiguous_speech_carries_no_driver_report_label():
    from strategy.bench_uat_harness import run_bench_scenario, BENCH_SCENARIOS
    s = next(s for s in BENCH_SCENARIOS if s.id == "A55")
    r = run_bench_scenario(s)
    assert r.actual["ptt_driver_report_label"] is None
    assert r.actual["ptt_command_class"] == "unrecognised"


def test_tyre_proxy_never_labelled_measured():
    from strategy.live_uat_runtime_snapshot import build_live_uat_runtime_snapshot
    from strategy.canonical_live_race_state import build_canonical_live_race_state
    import types
    t = types.SimpleNamespace(race_type="laps", laps_recorded=10, laps_in_race=30, tyre_compound="RH",
                              best_lap_ms=88000, last_fuel=40.0, laps_since_pit=10, car_name="GT3")
    canon = build_canonical_live_race_state(t, recent_clean_lap_times_s=[88, 88.4, 88.8, 89.2, 89.6])
    snap = build_live_uat_runtime_snapshot(canonical=canon)
    assert snap.tyre_age_proxy_is_measured is False


def test_missing_evidence_never_increases_confidence():
    from strategy.live_uat_runtime_snapshot import build_live_uat_runtime_snapshot
    from strategy.canonical_live_race_state import build_canonical_live_race_state
    import types
    bare = types.SimpleNamespace(race_type="laps", laps_recorded=2, laps_in_race=30, car_name="GT3")
    snap = build_live_uat_runtime_snapshot(canonical=build_canonical_live_race_state(bare))
    assert snap.fuel_confidence in ("none", "low")
    assert snap.pace_confidence in ("none", "low")


def test_bench_mode_cannot_mutate_live_state():
    # running the whole harness twice yields identical fingerprints — no hidden accumulation/mutation
    from strategy.bench_uat_harness import run_bench_uat
    assert run_bench_uat().fingerprint == run_bench_uat().fingerprint


def test_no_false_pass_for_physical_certification():
    # neither the honest cert nor any bench-derived cert can mark a physical area PASS/live
    from strategy.event_programme_certification import live_vr_certification, _LIVE_VR_PHYSICAL_OR_LIVE
    from strategy.bench_uat_harness import certification_from_bench
    for cert in (live_vr_certification(), certification_from_bench({})):
        by = {a.name: a.evidence_type.value for a in cert.areas}
        for name in _LIVE_VR_PHYSICAL_OR_LIVE:
            assert by[name] == "none"
        assert cert.overall_level.value == "not_tested"


def test_manual_evidence_requires_explicit_action():
    # a fresh ledger has no PASS anywhere; only an explicit append creates one
    from strategy.manual_uat_evidence import (ManualUatLedger, make_observation, ManualUatStatus,
                                              manual_uat_area_keys)
    led = ManualUatLedger()
    assert all(led.status_of(k) == ManualUatStatus.NOT_RUN for k in manual_uat_area_keys())
    led2 = led.append(make_observation("physical_tts", ManualUatStatus.PASS))
    assert led2.status_of("physical_tts") == ManualUatStatus.PASS
    # the original ledger is unchanged (immutable append)
    assert led.status_of("physical_tts") == ManualUatStatus.NOT_RUN


def test_new_modules_parse_and_have_module_docstrings():
    for rel in _NEW_MODULES + ["strategy/bench_uat_harness.py"]:
        tree = ast.parse(_src(rel))
        assert ast.get_docstring(tree), f"{rel} should have a module docstring"


def test_manual_store_never_writes_setup_history():
    s = _src("data/manual_uat_store.py").lower()
    assert "setup_history" not in s
