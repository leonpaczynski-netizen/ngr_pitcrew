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
    assert synth.rig_revision() == ""
    assert synth.default_profile() is synth.PORSCHE_RSR_17

    monkeypatch.setenv("PITCREW_RIG_REV", "b")
    assert synth.rig_revision() == "B"
    assert synth.default_profile() is synth.PORSCHE_RSR_17_REV_B

    monkeypatch.setenv("PITCREW_RIG_REV", "")
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
    monkeypatch.delenv("PITCREW_RIG_REV")
    assert effects.EffectDeriver()._lift_bumps is False


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
