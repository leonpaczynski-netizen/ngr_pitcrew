"""`tools/haptics_bench.py` must play SHARED unless exclusive is asked for.

This pins a defect that was silent by construction. `band` defaulted to
exclusive mode, and exclusive on this transducer opens, reports a sensible
latency, and renders nothing at all - `transducer.EXCLUSIVE = False` exists to
record exactly that. So every tone of a response sweep would have been played
into a dead stream and rated 0 by the driver, with the rig working perfectly
and nothing in the output saying otherwise.

It was caught by hand before the first tone of the post-remount sweep on
12 Sep 2026. Nothing would have caught it the second time, which is what this
file is for.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tools.haptics_bench as bench  # noqa: E402
from pitcrew.rig import transducer  # noqa: E402


class _Args:
    """Just the fields `cmd_band` reads."""

    def __init__(self, **kw):
        self.freq = 40.0
        self.seconds = 0.1
        self.amplitude = 0.125
        self.exclusive = False
        self.shared = False
        self.__dict__.update(kw)


def _record_mode(monkeypatch) -> list[bool]:
    seen: list[bool] = []

    def fake(_block, *, exclusive=False):
        seen.append(exclusive)
        return "the card rendered it - fake"

    monkeypatch.setattr(bench, "_play_metered", fake)
    return seen


def test_band_plays_shared_by_default(monkeypatch):
    seen = _record_mode(monkeypatch)
    assert bench.cmd_band(_Args()) == 0
    assert seen == [False], "band must not open the transducer exclusively"


def test_band_opts_in_to_exclusive(monkeypatch):
    seen = _record_mode(monkeypatch)
    assert bench.cmd_band(_Args(exclusive=True)) == 0
    assert seen == [True]


def test_legacy_shared_flag_still_plays_shared(monkeypatch):
    """`--shared` is accepted and ignored - it must not flip the mode back."""
    seen = _record_mode(monkeypatch)
    assert bench.cmd_band(_Args(shared=True)) == 0
    assert seen == [False]


def test_play_metered_defaults_to_shared():
    """The default on the helper itself, not only at the one call site.

    `cmd_calibrate` calls it with no mode at all, so the helper's own default
    is what decides whether the reference tone reaches the piston.
    """
    import inspect

    default = inspect.signature(bench._play_metered).parameters["exclusive"].default
    assert default is False


def test_default_matches_the_measured_fact():
    """The bench and the transducer module must not disagree about this.

    If `transducer.EXCLUSIVE` ever becomes True because a device is found that
    works that way, this fails and the bench default gets revisited with it,
    rather than the two drifting apart.
    """
    import inspect

    default = inspect.signature(bench._play_metered).parameters["exclusive"].default
    assert default == transducer.EXCLUSIVE
