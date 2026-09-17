"""Plan row 5.20 - contact read off the HUD car icon, on real flat-screen frames.

`fixtures/damage_icon_panels.npz`: 111 x 117 crops at (fl.x0 - 8, fl.y0 - 14) with
the bars `locate_gauge` found, from the 14 Sep survey. Session 166 (Suzuka race):
rear arc lit on lap 2 (288-381 s), front arc lit on lap 10 (~1266-1401 s) at 22,
28, 34 and 41 px, the frame after the rear cleared, the pale onset. Clean:
sessions 158, 160, 165, 166, a red kerb behind the panel, and the pit lane.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pitcrew.telemetry import hud_damage
from pitcrew.telemetry.hud_damage import MIN_ARC_PX, DamageRead, read_damage

FIXTURE = Path(__file__).parent / "fixtures" / "damage_icon_panels.npz"


@pytest.fixture(scope="module")
def panels():
    data = np.load(FIXTURE)
    out = {}
    for name in {key.split("__")[0] for key in data.files}:
        b = data[name + "__bars"]
        bars = {k: tuple(int(x) for x in b[i])
                for i, k in enumerate(("fl", "rl", "fr", "rr"))}
        frame = np.zeros((1080, 1920, 3), np.uint8)
        x0, y0 = bars["fl"][0] - 8, bars["fl"][2] - 14
        frame[y0:y0 + 117, x0:x0 + 111] = data[name]
        out[name] = (frame, bars)
    return out


def _paint(frame, bars, part, count, colour=(230, 20, 20)):
    """Paint `count` of one mask part's own cells red."""
    ys, xs = hud_damage._bank()[part]
    img = frame.copy()
    fx0, fy0 = bars["fl"][0], bars["fl"][2]
    for y, x in list(zip(ys, xs))[:count]:
        img[fy0 + y, fx0 + x] = colour
    return img


CLEAN = ("clean_158_t275", "clean_160_t1865", "clean_165_t485", "clean_166_t275",
         "kerb_166_t485", "pitlane_160_t1370", "rear_cleared_166_t381")


@pytest.mark.parametrize("name", CLEAN)
def test_a_clean_icon_reads_no_contact(panels, name):
    got = read_damage(*panels[name])
    assert got.front is False and got.rear is False
    assert got.front_px == 0 and got.rear_px == 0


@pytest.mark.parametrize("name", ("rear_166_t320", "rear_dim_166_t340"))
def test_rear_contact_lights_the_rear_arc_only(panels, name):
    got = read_damage(*panels[name])
    assert got.rear is True and got.front is False
    assert got.rear_px >= MIN_ARC_PX


@pytest.mark.parametrize("name,px", (("front_166_t1342", 34), ("front_jitter_166_t1370", 41),
                                     ("front_28px_166_t1325", 28),
                                     ("front_22px_166_t1295", 22)))
def test_front_contact_lights_the_front_arc_only(panels, name, px):
    """The 22 and 28 px reads pin the threshold low: raised to 30 it would blank
    most of the front hit (critic pass 1)."""
    got = read_damage(*panels[name])
    assert got.front is True and got.rear is False and got.front_px == px


def test_the_pale_onset_is_below_the_bar(panels):
    got = read_damage(*panels["front_onset_166_t1267"])
    assert got.front is False and 0 < got.front_px < MIN_ARC_PX


def test_the_threshold_is_inclusive_at_eight_pixels(panels):
    frame, bars = panels["clean_166_t275"]
    assert MIN_ARC_PX == 8
    at = read_damage(_paint(frame, bars, "front_arc", MIN_ARC_PX), bars)
    below = read_damage(_paint(frame, bars, "front_arc", MIN_ARC_PX - 1), bars)
    assert at.front is True and at.front_px == MIN_ARC_PX
    assert below.front is False and below.front_px == MIN_ARC_PX - 1


def test_one_red_pixel_off_the_arcs_refuses_the_frame(panels):
    frame, bars = panels["rear_166_t320"]
    got = read_damage(_paint(frame, bars, "guard", 1), bars)
    assert got.front is None and got.rear is None and "outside" in got.why


def test_an_uncalibrated_panel_is_refused(panels):
    frame, bars = panels["rear_166_t320"]
    tall = dict(bars, fl=(bars["fl"][0], bars["fl"][1], bars["fl"][2] - 3, bars["fl"][3]))
    assert "measured at" in read_damage(frame, tall).why

    def rear_down(dy):
        rl = bars["rl"]
        return dict(bars, rl=(rl[0], rl[1], rl[2], rl[3] + dy))

    assert read_damage(frame, rear_down(1)).rear is True
    assert "apart" in read_damage(frame, rear_down(2)).why
    assert read_damage(frame, None).rear is None


def test_bars_out_of_their_columns_are_refused(panels):
    frame, bars = panels["rear_166_t320"]
    fl, rl, fr = bars["fl"], bars["rl"], bars["fr"]
    assert read_damage(frame, dict(bars, rl=(rl[0] + 3,) + rl[1:])).rear is True
    assert "columns" in read_damage(frame, dict(bars, rl=(rl[0] + 4,) + rl[1:])).why
    assert read_damage(frame, dict(bars, fr=(fl[0] + 88,) + fr[1:])).rear is True
    assert "columns" in read_damage(frame, dict(bars, fr=(fl[0] + 89,) + fr[1:])).why


@pytest.mark.parametrize("fl", ((2, 13, 5, 40), (1900, 1911, 500, 535), (500, 511, 1060, 1095)))
def test_an_icon_off_any_edge_is_refused(panels, fl):
    frame, _ = panels["rear_166_t320"]
    bars = {"fl": fl, "rl": (fl[0], fl[1], fl[2] + 54, fl[2] + 89)}
    assert "off the frame" in read_damage(frame, bars).why


# ------------------------------------------------------------ the session's answer

def _hud():
    from pitcrew.telemetry.hud_session import HudSession

    return HudSession(settings=SimpleNamespace(hud_wear_enabled=False), store=None)


def _feed(hud, reads):
    """(time, front px, rear px) into the history as `read_damage` would have
    judged them; None unreadable."""
    for at, front, rear in reads:
        hud._damage.append((at, front, rear,
                            None if front is None else front >= MIN_ARC_PX,
                            None if rear is None else rear >= MIN_ARC_PX))


def test_contact_needs_two_lit_reads_and_no_contact_needs_no_red_at_all():
    from pitcrew.telemetry.hud_session import DAMAGE_MIN_LIT, DAMAGE_MIN_READS, DAMAGE_WINDOW_S

    assert DAMAGE_MIN_LIT == 2 and DAMAGE_MIN_READS == 3
    hud = _hud()
    now = 1000.0
    assert hud.contact_recent(now) == {"front": None, "rear": None}
    _feed(hud, [(990.0, 0, 0), (992.0, 0, 0), (994.0, 0, 0)])
    assert hud.contact_recent(now) == {"front": False, "rear": False}
    # One lit read is evidence, not noise: never False (critic pass 1, blocker).
    _feed(hud, [(996.0, 30, 0)])
    assert hud.contact_recent(now) == {"front": None, "rear": False}
    # A sub-threshold red pixel is not "no contact" either.
    _feed(hud, [(997.0, 0, 3)])
    assert hud.contact_recent(now)["rear"] is None
    _feed(hud, [(998.0, 25, 0)])
    assert hud.contact_recent(now)["front"] is True
    assert hud.contact_recent(now + DAMAGE_WINDOW_S + 10) == {"front": None, "rear": None}


def test_both_arcs_are_judged_alike():
    hud = _hud()
    _feed(hud, [(1.0, 0, 30), (2.0, 0, 30), (3.0, 0, 0)])
    assert hud.contact_recent(4.0) == {"front": False, "rear": True}


def test_unreadable_grabs_count_for_neither_answer():
    hud = _hud()
    _feed(hud, [(1.0, 0, 0), (2.0, None, None), (3.0, None, None), (4.0, 0, 0)])
    assert hud.contact_recent(5.0) == {"front": None, "rear": None}


def test_once_red_is_in_the_window_it_is_never_called_clear():
    """A made-up onset - 0 px reads with single lit frames between. The real one
    on file is worse and is the next test."""
    hud = _hud()
    onset = [0, 0, 0, 30, 0, 6, 0, 0, 26, 30]
    for i, px in enumerate(onset):
        _feed(hud, [(float(i * 2), px, 0)])
        got = hud.contact_recent(float(i * 2))["front"]
        if any(onset[: i + 1]):
            assert got is not False, i


def test_a_real_read_is_filed_front_as_front_and_rear_as_rear():
    hud = _hud()
    for _ in range(2):
        hud._note_damage(DamageRead(False, True, 0, 40))
    hud._note_damage(DamageRead(False, False, 0, 0))
    assert [entry[1:] for entry in hud._damage] == [(0, 40, False, True)] * 2 + [(0, 0, False, False)]
    assert hud.contact_recent() == {"front": False, "rear": True}
    hud._note_damage(DamageRead(None, None, why="no panel"))
    assert list(hud._damage)[-1][1:] == (None, None, None, None)
    hud.new_session()
    assert not hud._damage


def test_a_lit_arc_is_logged_when_it_appears_and_when_it_goes(monkeypatch):
    import pitcrew.telemetry.hud_session as module

    said = []
    monkeypatch.setattr(module, "log", lambda name: SimpleNamespace(
        info=lambda *a: said.append(a[1:3])))
    hud = _hud()
    for read in (DamageRead(False, False, 0, 0), DamageRead(False, True, 0, 40),
                 DamageRead(False, True, 0, 44), DamageRead(False, False, 0, 0),
                 DamageRead(None, None)):
        hud._note_damage(read)
    assert said == [("rear", "lit"), ("rear", "dim")]


# ------------------------------------------------------------ the grab

class _Source:
    def __init__(self, frame):
        self.frame = frame

    def grab(self):
        return self.frame, None


def test_the_sampler_reads_the_icon_with_no_other_passenger(panels, monkeypatch):
    """Both gates in `_read` must admit a damage-only sampler (critic pass 1)."""
    from pitcrew.telemetry import hud
    from pitcrew.telemetry.hud import CropFrame, LiveWearSampler, Reading

    frame, bars = panels["rear_166_t320"]
    grabbed = CropFrame(pixels=frame, origin=(0, 0), canvas=(1920, 1080))
    monkeypatch.setattr(hud, "read_gauge", lambda f, **_: Reading({"fl": 0.1}, bars=bars))
    got = []
    sampler = LiveWearSampler(source=_Source(grabbed), write=lambda *a: None,
                              on_damage=got.append)
    sampler._read()
    assert got and got[-1].rear is True


def test_the_sampler_hands_on_a_refusal_when_the_panel_is_not_found():
    from pitcrew.telemetry.hud import LiveWearSampler, Reading

    got = []
    sampler = LiveWearSampler(source=None, write=lambda *a: None,
                              on_damage=got.append)
    sampler._pass_hygro(b"", Reading(None, "no gauge"))
    assert isinstance(got[-1], DamageRead) and got[-1].rear is None


def test_the_session_builds_its_sampler_with_the_damage_passenger(monkeypatch):
    from pitcrew.telemetry import hud
    from pitcrew.telemetry.hud_session import HudSession

    built = {}

    class Sampler:
        def __init__(self, *args, **kwargs):
            built.update(kwargs)

        def start(self):
            pass

    monkeypatch.setattr(hud, "LiveWearSampler", Sampler)
    settings = SimpleNamespace(hud_wear_enabled=True, hud_sample_interval_s=2.0,
                               hud_source="screen")
    session = HudSession(settings=settings, store=None)
    monkeypatch.setattr(session, "build_source", lambda: None)
    monkeypatch.setattr(session, "_source_key", lambda: "k")
    session.sampler()
    assert built["on_damage"] == session._note_damage


def test_the_real_onset_reads_false_first_and_the_docstring_says_so():
    """Session 166's front hit at a 2 s grab: eight 0 px reads before any red,
    so the first answers are False - the latency `contact_recent` documents."""
    import inspect

    from pitcrew.telemetry.hud_session import HudSession

    hud = _hud()
    for i in range(8):
        _feed(hud, [(float(i * 2), 0, 0)])
    assert hud.contact_recent(14.0)["front"] is False
    _feed(hud, [(16.0, 26, 0)])
    assert hud.contact_recent(16.0)["front"] is None
    doc = inspect.getdoc(HudSession.contact_recent)
    assert "17 s after the onset" in doc and "23 s after it" in doc


def test_lit_is_the_readers_verdict_not_a_second_count():
    """Critic pass 2: the history keeps the read's own True/False."""
    hud = _hud()
    for _ in range(2):
        hud._note_damage(DamageRead(True, False, MIN_ARC_PX, 0))
    assert hud.contact_recent()["front"] is True
    hud = _hud()
    for _ in range(3):
        hud._note_damage(DamageRead(False, False, MIN_ARC_PX, 0))   # a judged dim
    assert hud.contact_recent()["front"] is None


def test_a_new_session_forgets_what_was_logged(monkeypatch):
    import pitcrew.telemetry.hud_session as module

    said = []
    monkeypatch.setattr(module, "log", lambda name: SimpleNamespace(
        info=lambda *a: said.append(a[1:3])))
    hud = _hud()
    hud._note_damage(DamageRead(False, True, 0, 40))
    hud.new_session()
    hud._note_damage(DamageRead(False, True, 0, 40))
    assert said == [("rear", "lit"), ("rear", "lit")]


def test_the_history_holds_a_whole_window_at_a_half_second_grab():
    from pitcrew.telemetry.hud_session import DAMAGE_KEEP, DAMAGE_WINDOW_S

    hud = _hud()
    assert hud._damage.maxlen == DAMAGE_KEEP >= DAMAGE_WINDOW_S / 0.5


def test_bars_left_of_their_columns_are_refused_too(panels):
    frame, bars = panels["rear_166_t320"]
    fl, rl, fr = bars["fl"], bars["rl"], bars["fr"]
    assert read_damage(frame, dict(bars, rl=(rl[0] - 3,) + rl[1:])).rear is True
    assert "columns" in read_damage(frame, dict(bars, rl=(rl[0] - 4,) + rl[1:])).why
    assert read_damage(frame, dict(bars, fr=(fl[0] + 80,) + fr[1:])).rear is True
    assert "columns" in read_damage(frame, dict(bars, fr=(fl[0] + 79,) + fr[1:])).why
