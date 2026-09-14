"""Plan row 5.13 - the hygrometer reader - on real frames.

`fixtures/hygrometer_panels.npz` holds the wear-panel region (x 280-500, y
930-1070 of a flat 1920x1080 HUD) cut from two captures, with the bars
`hud.locate_gauge` found on each full frame:

* the driver's video with water on the track, 14 Sep 2026 - steady (30 s), the
  spray peak (91.2 s), the tunnel (135.5 s), a codec glitch that blanked the
  fill (19.2 s), and the HUD fading at the end (160.8 s);
* the dry Suzuka race of 13 Sep 2026, first frame with the panel lit.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pitcrew.telemetry.hygrometer import (
    MIN_READS,
    WET_LEVEL,
    HygroReading,
    HygrometerLap,
    read_hygrometer,
)

FIXTURE = Path(__file__).parent / "fixtures" / "hygrometer_panels.npz"


@pytest.fixture(scope="module")
def panels():
    data = np.load(FIXTURE)
    out = {}
    for name in ("wet_steady", "wet_spray_peak", "wet_tunnel_empty",
                 "wet_glitch_blank", "hud_dimmed_end", "dry_suzuka_race"):
        bars = data[f"{name}__bars"]
        out[name] = (data[name], None if bars.size == 0 else
                     {k: tuple(int(v) for v in bars[i])
                      for i, k in enumerate(("fl", "rl", "fr", "rr"))})
    return out


def test_wet_track_reads_wet(panels):
    for name in ("wet_steady", "wet_spray_peak"):
        reading = read_hygrometer(*panels[name])
        assert reading.wet is True, (name, reading)
    assert read_hygrometer(*panels["wet_spray_peak"]).fill_px > \
        read_hygrometer(*panels["wet_steady"]).fill_px


def test_dry_track_reads_dry(panels):
    reading = read_hygrometer(*panels["dry_suzuka_race"])
    assert reading.level == 0.0 and reading.wet is False


def test_the_tunnel_on_a_wet_track_reads_empty(panels):
    """Why the answer is per lap and never one frame."""
    assert read_hygrometer(*panels["wet_tunnel_empty"]).wet is False


def test_a_dimmed_or_unlocated_hud_is_cannot_see_not_dry(panels):
    frame, bars = panels["hud_dimmed_end"]
    assert bars is None
    assert read_hygrometer(frame, bars).level is None
    frame, bars = panels["wet_steady"]
    dark = (frame * 0.5).astype(np.uint8)
    assert read_hygrometer(dark, bars).level is None


def _lap(levels):
    lap = HygrometerLap()
    for level in levels:
        lap.add(HygroReading(level, None if level is None else int(level * 86)))
    return lap.close()


def test_one_blank_frame_in_a_wet_lap_is_dropped():
    """The glitch at 19.2 s: one read empty between two wet ones."""
    result = _lap([0.7, 0.7, 0.0, 0.7, 0.7, 0.7, 0.7])
    assert result.dropped == 1
    assert result.state == "wet" and result.wet_share == 1.0


def test_a_tunnel_is_a_run_not_an_outlier_and_the_lap_stays_wet():
    result = _lap([0.7] * 12 + [0.0, 0.0, 0.0] + [0.7] * 5)
    assert result.dropped == 0
    assert result.state == "wet"


def test_a_drying_lap_is_mixed():
    assert _lap([0.7] * 6 + [0.0] * 6).state == "mixed"


def test_too_few_readings_is_cannot_see_never_dry():
    result = _lap([0.0] * (MIN_READS - 1) + [None] * 20)
    assert result.state == "cannot see" and result.wet_share is None
    assert result.unreadable == 20


def test_a_lap_closes_empty_and_a_session_reset_clears_it():
    lap = HygrometerLap()
    lap.add(HygroReading(0.7, 60))
    lap.new_session()
    assert lap.close().reads == 0
    assert WET_LEVEL > 0
