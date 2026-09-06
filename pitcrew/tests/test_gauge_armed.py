"""The grid brief promises the gauge only when it is armed - and it reads the
right attribute to find out.

Deep Forest, 6 Sep 2026: George opened the race with "No tyre gauge this race -
read it to me when you can", then read 19 of 20 laps off it. `_say_brief` was
reading `getattr(self, "_hud", None)` - a name that never existed on the
controller - so `wear_gauge` was False every race since the brief was written.
The fix is a probe on the session that owns the sampler, and the probe must not
build one: `sampler()` opens a socket, and the brief runs before a practice
session that may never cross a line.
"""
from __future__ import annotations

from .test_gauge_preflight import _Settings, _session


class _Sampler:
    def __init__(self, stood_down: bool):
        self.stood_down = stood_down


def test_off_in_settings_is_not_armed():
    session = _session(settings=_Settings(hud_wear_enabled=False))
    assert session.armed() is False


def test_on_and_not_yet_built_is_armed_and_builds_nothing():
    session = _session(settings=_Settings(hud_wear_enabled=True))
    assert session._sampler is None
    assert session.armed() is True
    # The probe must not have built a reader - that is the whole reason it
    # exists instead of calling `sampler()`.
    assert session._sampler is None


def test_a_standing_sampler_is_armed():
    session = _session(settings=_Settings(hud_wear_enabled=True))
    session._sampler = _Sampler(stood_down=False)
    assert session.armed() is True


def test_a_stood_down_sampler_is_not_armed():
    session = _session(settings=_Settings(hud_wear_enabled=True))
    session._sampler = _Sampler(stood_down=True)
    assert session.armed() is False


def test_the_controller_no_longer_reads_a_name_that_does_not_exist():
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[1] / "controller.py"
    text = source.read_text(encoding="utf-8")
    assert 'getattr(self, "_hud", None)' not in text
    assert "wear_gauge=self.hud.armed()" in text
