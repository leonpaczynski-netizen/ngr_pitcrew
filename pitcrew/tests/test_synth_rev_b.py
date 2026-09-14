"""Rev B - built on the masking check after Rev A failed in the seat.

Rev A passed a per-effect check (every effect over the driver's floor and under
the knock curve, ALONE) and was rejected on track on 13 Sep 2026: the traction
cue, the ripple strip and the gear change were buried under `chassis_load`.
`tools/rig_levels.py` now reports what each cue must beat at every instant it
is live; it reproduced that report from telemetry, and Rev B is the profile it
graded best over the 21 laps driven that night. The replay needs the lap store,
so what is pinned here is the construction the replay graded - not the replay.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pitcrew.rig import synth  # noqa: E402

DEFAULT = {s.name: s for s in synth.PORSCHE_RSR_17}
REV_A = {s.name: s for s in synth.PORSCHE_RSR_17_REV_A}
REV_B = {s.name: s for s in synth.PORSCHE_RSR_17_REV_B}


def test_chassis_load_is_off():
    """The masker. Continuous in every corner at 59-65 Hz, the most sensitive
    band on the rig, and 91% of the traction cue's burial even in the
    everyday profile. 0.01 because the spec guard forbids a zero trim."""
    assert REV_B["chassis_load"].felt_trim <= 0.01


def test_the_beds_and_gear_change_are_back_to_default():
    """Rev A lifted them; they were not felt as beds and became the next
    masker - `road` took 86% of the kerb strike's burial once chassis_load
    was gone."""
    for name in ("engine", "road", "driveline"):
        assert REV_B[name].felt_trim == DEFAULT[name].felt_trim, name


def test_the_cues_keep_the_levels_checked_in_the_seat():
    """Bench-checked at amp 35 on 13 Sep: kerb "no knock, still a kerb strike",
    traction "no knock, feels good". Nothing in Rev B is louder than a level
    already verified clean, which is what makes it knock-safe by construction."""
    for name in ("impact", "rear_traction", "brake_limit"):
        assert REV_B[name].felt_trim == REV_A[name].felt_trim, name
    for name, spec in REV_B.items():
        verified = max(DEFAULT[name].felt_trim, REV_A[name].felt_trim)
        if name == "impact":          # the old kerb knocked at amp 35
            verified = REV_A[name].felt_trim
        assert spec.felt_trim <= verified, name


def test_rev_b_changes_only_trims():
    for old, new in zip(synth.PORSCHE_RSR_17, synth.PORSCHE_RSR_17_REV_B):
        assert old.name == new.name
        assert (old.freq_lo, old.freq_hi) == (new.freq_lo, new.freq_hi)
        assert old.gain == new.gain
        assert old.priority == new.priority


def test_revision_selector(monkeypatch):
    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.delenv("PITCREW_RIG_REV", raising=False)
    assert synth.rig_revision() == synth.LOCKED_REVISION == "G"      # locked in
    assert synth.default_profile() is synth.PORSCHE_RSR_17_REV_G
    monkeypatch.setenv("PITCREW_RIG_REV", "original")
    assert synth.rig_revision() == ""                                  # the baseline
    assert synth.default_profile() is synth.PORSCHE_RSR_17

    monkeypatch.setenv("PITCREW_RIG_REV", "b")
    assert synth.rig_revision() == "B"
    assert synth.default_profile() is synth.PORSCHE_RSR_17_REV_B

    monkeypatch.delenv("PITCREW_RIG_REV", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV_A", "1")
    assert synth.default_profile() is synth.PORSCHE_RSR_17_REV_A


def test_the_live_engine_runs_rev_b_and_says_so(monkeypatch):
    from pitcrew.rig import haptics

    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV", "B")
    engine = haptics.HapticsEngine()
    assert engine._specs == tuple(synth.PORSCHE_RSR_17_REV_B)
    assert synth.profile_name(engine._specs) == "REV B"


def test_rev_c_turns_up_what_he_asked_for(monkeypatch):
    """Rev B in the seat: "everything could go up a bit but especially rear
    traction loss and kerb strikes"; gear change "could be stronger"; engine
    rumble missed. Rev C lifts exactly those, keeps chassis_load off, and the
    engine lift is held to +2 dB because the masking replay showed Rev A's
    engine level burying the gear change and brake cue a third of the time."""
    c = {s.name: s for s in synth.PORSCHE_RSR_17_REV_C}
    b = REV_B
    for name in ("rear_traction", "impact", "brake_limit",
                 "engine", "road"):
        assert c[name].felt_trim > b[name].felt_trim, name
    assert c["rear_traction"].felt_trim / b["rear_traction"].felt_trim >= 1.99
    assert c["chassis_load"].felt_trim <= 0.01
    assert c["driveline"].felt_trim == b["driveline"].felt_trim   # +7 blunt, +3 worse

    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV", "C")
    assert synth.default_profile() is synth.PORSCHE_RSR_17_REV_C
    assert synth.profile_name(synth.default_profile()) == "REV C"


def test_bumps_clear_the_impact_gate_and_stay_under_a_kerb():
    """Rev C lifts the compression event over the impact voice's 25% gate.

    Median real bump over the laps of 13 Sep was 0.16 - silent in every tune
    ever run. Lifted, the smallest live compression shapes above zero and the
    biggest stays below the lightest kerb thump, so a bump never reads as a kerb.
    """
    from pitcrew.rig import effects

    impact = {s.name: s for s in synth.PORSCHE_RSR_17_REV_C}["impact"]
    assert effects.bump_level(0.0) == 0.0
    assert impact.shape(0.16) == 0.0                      # the defect
    assert impact.shape(effects.bump_level(0.01)) > 0.0   # the fix
    assert (impact.shape(effects.bump_level(1.0))
            < impact.shape(effects.KERB_THUMP_FLOOR))


def test_bump_lift_follows_the_tune(monkeypatch):
    from pitcrew.rig import effects

    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV", "C")
    assert effects.EffectDeriver()._lift_bumps is True
    monkeypatch.setenv("PITCREW_RIG_REV", "B")
    assert effects.EffectDeriver()._lift_bumps is False
    monkeypatch.setenv("PITCREW_RIG_REV", "ORIGINAL")
    assert effects.EffectDeriver()._lift_bumps is False
    monkeypatch.delenv("PITCREW_RIG_REV")
    assert effects.EffectDeriver()._lift_bumps is True          # the locked tune


def test_a_bump_is_one_thud_not_a_rumble():
    """Bench, 14 Sep: tracking compression for as long as the spring stayed down
    felt "more like a rumble than a bump"; one decaying pulse per event, fired
    on the rising edge, was "heaps better" and still graded by size."""
    from pitcrew.rig import effects

    dt = 1.0 / 60.0
    pulse = effects.BumpPulse()
    held = [pulse.update(0.43, dt) for _ in range(30)]      # spring held down 0.5 s
    assert held[0] > 0.0
    assert held[-1] < 0.25 * max(held)                       # gone while still compressed
    assert pulse.update(0.0, dt) < 0.25 * max(held)          # clears
    for _ in range(30):
        pulse.update(0.0, dt)
    assert pulse.update(0.43, dt) > 0.3                      # re-armed: next bump fires

    small, big = effects.BumpPulse(), effects.BumpPulse()
    peak_small = max(small.update(0.10, dt) for _ in range(4))
    peak_big = max(big.update(1.00, dt) for _ in range(4))
    assert peak_big > peak_small                             # still graded


def test_rev_d_is_rev_c_with_his_engine_road_and_duck(monkeypatch):
    """Rev C in the seat (session 168): traction, gear changes and kerbs "great";
    engine rumble "needs to be stronger", road "still seems to lack a bit".
    Rev D changes only those, each chosen on the bench and knock-checked at full."""
    c = {s.name: s for s in synth.PORSCHE_RSR_17_REV_C}
    d = {s.name: s for s in synth.PORSCHE_RSR_17_REV_D}
    for name in ("brake_limit", "driveline", "impact", "chassis_load",
                 "rear_traction"):
        assert (d[name].felt_trim, d[name].gain) == (c[name].felt_trim, c[name].gain), name
    engine_c = c["engine"].gain * c["engine"].felt_trim
    engine_d = d["engine"].gain * d["engine"].felt_trim
    assert 20 * __import__("math").log10(engine_d / engine_c) > 3.9     # +4 dB
    assert d["engine"].felt_trim <= 4.0          # the trim guard was not moved
    assert d["road"].felt_trim > c["road"].felt_trim

    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV", "D")
    assert synth.default_profile() is synth.PORSCHE_RSR_17_REV_D
    from pitcrew.rig import effects
    assert effects.EffectDeriver()._lift_bumps is True


def test_rev_f_engine_climbs_from_66_to_86_hz(monkeypatch):
    """Rev E's pull: "I don't think engine rumble should be that deep?" The voice
    swept 28 -> 31.8 Hz across the whole rev range. Rev F puts it at 66 Hz
    rising to 86 Hz at the limiter (RPM_CURVE's 0.63), chosen on the bench over
    the deep one and a 36-50 Hz one that knocked. Nothing else changes."""
    e = {s.name: s for s in synth.PORSCHE_RSR_17_REV_E}
    f = {s.name: s for s in synth.PORSCHE_RSR_17_REV_F}
    engine = f["engine"]
    at_limiter = engine.freq_lo + (engine.freq_hi - engine.freq_lo) * 0.63
    assert engine.freq_lo == 66.0 and abs(at_limiter - 86.0) < 0.1
    assert engine.freq_lo > 60.0                  # clear of the 60 Hz resonance
    assert engine.gain < e["engine"].gain         # more sensitive region, less gain
    for name in f:
        if name != "engine":
            assert f[name] == e[name], name

    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV", "F")
    assert synth.profile_name(synth.default_profile()) == "REV F"


def test_rev_g_kerbs_are_graded_by_the_worst_wheel():
    """Rev F: "a small kerb and big kerb hit the same". The old grading put the
    p10 and p90 kerb ~1 dB apart; Rev G sizes the worst wheel's peak on a log
    scale. Measured kerb speeds of 13 Sep: p10 0.049, p50 0.133, p90 0.425."""
    import math
    from pitcrew.rig import effects

    impact = {s.name: s for s in synth.PORSCHE_RSR_17_REV_G}["impact"]

    def db(v):
        return 20 * math.log10(impact.shape(effects.kerb_grade(v)))

    assert db(0.049) < db(0.133) < db(0.425)
    assert db(0.425) - db(0.049) > 4.5                     # was ~1 dB
    assert effects.kerb_grade(10.0) == effects.KERB_GRADE_TOP
    assert abs(20 * math.log10(impact.shape(effects.KERB_GRADE_TOP)) + 3.0) < 0.1   # he set -3 dB
    assert effects.kerb_grade(0.0) == effects.KERB_GRADE_FLOOR


def test_rev_g_kerb_thump_fires_on_the_edge_and_grows(monkeypatch):
    from pitcrew.rig import effects, vehicle

    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV", "G")
    d = effects.EffectDeriver()
    assert d._grade_kerbs is True
    state, dt = vehicle.VehicleState(), 1.0 / 60.0
    state.kerb_strike = True
    d._spike_speed = 0.05
    first = d._kerb_thump(state, dt)
    assert first >= effects.KERB_GRADE_FLOOR                # no latency on the edge
    state.kerb_strike = False
    d._spike_speed = 0.45                                   # the hit develops
    grown = d._kerb_thump(state, dt)
    assert grown > first
    for _ in range(30):
        d._kerb_thump(state, dt)
    assert d._kerb_thump(state, dt) < 0.1                   # and it is gone

    monkeypatch.setenv("PITCREW_RIG_REV", "F")
    assert effects.EffectDeriver()._grade_kerbs is False


def test_rev_g_engine_pull_climbs_66_to_100_hz(monkeypatch):
    g = {s.name: s for s in synth.PORSCHE_RSR_17_REV_G}["engine"]
    pitch = lambda i: g.freq_lo + (g.freq_hi - g.freq_lo) * i
    assert abs(pitch(0.166) - 66.0) < 0.5 and abs(pitch(0.599) - 100.0) < 0.5
    f = {s.name: s for s in synth.PORSCHE_RSR_17_REV_F}
    for name, spec in {s.name: s for s in synth.PORSCHE_RSR_17_REV_G}.items():
        if name != "engine":
            assert spec == f[name], name
    monkeypatch.delenv("PITCREW_RIG_REV_A", raising=False)
    monkeypatch.setenv("PITCREW_RIG_REV", "G")
    assert synth.revision_at_least("D") and synth.revision_at_least("G")
    monkeypatch.setenv("PITCREW_RIG_REV", "ORIGINAL")
    assert synth.rig_revision() == "" and not synth.revision_at_least("A")


def _nothing_continuous_shares_the_traction_band(profile) -> bool:
    specs = {s.name: s for s in profile}
    traction = specs["rear_traction"]
    for spec in profile:
        if spec is traction or spec.priority <= synth.TRANSIENT:
            continue
        if spec.felt_trim <= 0.01:                    # switched off
            continue
        if (spec.freq_hi or spec.freq_lo) > traction.freq_lo:
            return False
    return True


import pytest  # noqa: E402


@pytest.mark.xfail(
    not _nothing_continuous_shares_the_traction_band(synth.PORSCHE_RSR_17_REV_G),
    strict=True,
    reason="OPEN CONFLICT, recorded not resolved: test_synth's rule that no "
           "continuous voice shares the traction band is checked against the "
           "ORIGINAL profile only. The locked tune's engine climbs 66->100 Hz on "
           "a pull (freq_hi 131.5) into rear_traction's 86-104 - the failure that "
           "rule was written against. Kept because the driver drove it and "
           "called traction 'great'; the replay put traction 4% buried. Strict, "
           "so it flags if the engine is ever moved back out.")
def test_the_locked_tune_keeps_the_traction_band_clear():
    assert _nothing_continuous_shares_the_traction_band(synth.default_profile())
