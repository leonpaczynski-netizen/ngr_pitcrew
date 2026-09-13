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
