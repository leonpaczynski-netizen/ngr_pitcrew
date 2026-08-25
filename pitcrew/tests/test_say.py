"""How the engineer says a number — lap times and gaps."""
from __future__ import annotations

import pytest

from pitcrew.engineer import say


# ---------------------------------------------------------------- lap times


@pytest.mark.parametrize("ms, written", [
    (89_412, "1:29.412"),
    (65_300, "1:05.300"),
    (109_464, "1:49.464"),
    (145_130, "2:25.130"),
    (59_900, "0:59.900"),
])
def test_written_lap_time_is_mm_ss_sss(ms, written):
    assert say.lap_time(ms) == written


@pytest.mark.parametrize("ms, spoken", [
    (89_412, "one twenty-nine point four"),
    (65_300, "one oh five point three"),      # the leading zero is spoken
    (109_464, "one forty-nine point five"),   # .464 rounds up to .5
    (145_130, "two twenty-five point one"),
    (90_000, "one thirty flat"),              # a whole second is said "flat"
    (59_900, "fifty-nine point nine"),        # under a minute: no minutes part
])
def test_spoken_lap_time_is_how_a_timing_screen_reads(ms, spoken):
    assert say.spoken_lap_time(ms) == spoken


def test_the_driver_complaint_verbatim():
    """He heard "eighty-nine point four" where every screen says 1:29.4."""
    assert say.spoken_lap_time(89_412) != "89.4"
    assert say.spoken_lap_time(89_412).startswith("one twenty-nine")


def test_no_time_is_not_a_zero():
    assert say.lap_time(0) == "--:--.---"
    assert say.lap_time(None) == "--:--.---"
    assert say.spoken_lap_time(None) == "no time"
    assert say.spoken_lap_time(0) == "no time"


# --------------------------------------------------------------------- gaps


@pytest.mark.parametrize("seconds, spoken", [
    (0.1, "a tenth"),
    (0.3, "three tenths"),
    (0.9, "nine tenths"),
    (1.0, "one second"),
    (1.3, "1.3 seconds"),
    (2.04, "2.0 seconds"),
    (12.7, "12.7 seconds"),
])
def test_a_gap_carries_its_unit(seconds, spoken):
    assert say.spoken_gap(seconds) == spoken


def test_a_gap_is_never_a_bare_decimal_above_a_second():
    """The old formatter said "1.3" with no dimension in mid-sentence."""
    assert say.spoken_gap(1.3) == "1.3 seconds"
    assert "second" in say.spoken_gap(4.2)


def test_ten_tenths_can_never_be_produced():
    """0.95 is the switch precisely so rounding cannot reach it."""
    for hundredths in range(0, 200):
        text = say.spoken_gap(hundredths / 100.0)
        assert "ten tenths" not in text


def test_magnitude_only_so_the_caller_owns_direction():
    assert say.spoken_gap(-0.3) == say.spoken_gap(0.3)


def test_below_a_tenth_still_names_a_tenth():
    """Callers gate on their own level band; reaching here means it counts."""
    assert say.spoken_gap(0.02) == "a tenth"
    assert say.spoken_gap(None) == ""
