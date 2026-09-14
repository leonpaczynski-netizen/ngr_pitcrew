"""The compound read off the HUD wear panel's label, on real flat-screen frames.

`fixtures/compound_label_panels.npz`: the wear-panel region (x 280-500, y 930-1070
of 1920x1080) from session 160 (Huracan, Bathurst, RS) and session 158 (RSR,
Sardegna, RM), three frames each, with the bars `locate_gauge` found; plus one RS
panel with its front label blanked out.
"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pitcrew.telemetry.hud_compound import CompoundRead, known_codes, read_compound

FIXTURE = Path(__file__).parent / "fixtures" / "compound_label_panels.npz"


@pytest.fixture(scope="module")
def panels():
    data = np.load(FIXTURE)
    out = {}
    for name in ("RS_0", "RS_1", "RS_2", "RM_0", "RM_1", "RM_2", "blanked"):
        b = data[name + "__bars"]
        out[name] = (data[name],
                     {k: tuple(int(x) for x in b[i])
                      for i, k in enumerate(("fl", "rl", "fr", "rr"))})
    return out


def test_only_the_codes_ever_seen_can_be_read():
    assert known_codes() == ("RM", "RS")


@pytest.mark.parametrize("name,code", [("RS_0", "RS"), ("RS_1", "RS"), ("RS_2", "RS"),
                                       ("RM_0", "RM"), ("RM_1", "RM"), ("RM_2", "RM")])
def test_real_labels_read_as_the_tyre_that_was_fitted(panels, name, code):
    frame, bars = panels[name]
    got = read_compound(frame, bars)
    assert got.code == code and got.front == code and got.rear == code


def test_one_unreadable_label_is_no_answer(panels):
    frame, bars = panels["blanked"]
    got = read_compound(frame, bars)
    assert got.code is None and got.rear == "RS" and "front" in got.why


def test_a_label_it_has_no_template_for_is_refused_not_rounded(panels):
    """RH, IM, HW have never been seen flat. A fake second letter (the R copied
    over the S) stands in: it must not come back as the nearer of RS and RM."""
    frame, bars = panels["RS_0"]
    img = frame.astype(np.int16).copy()
    x0 = bars["fl"][0] + 34
    for y in (bars["fl"][2] - 12, bars["rl"][3]):
        img[y:y + 13, x0 + 15:x0 + 30] = img[y:y + 13, x0:x0 + 15]
    got = read_compound(img, bars)
    assert got.code is None and got.front is None and got.rear is None


def test_an_uncalibrated_size_or_no_panel_is_refused(panels):
    frame, bars = panels["RS_0"]
    small = dict(bars, fl=(bars["fl"][0], bars["fl"][1], bars["fl"][2], bars["fl"][2] + 25))
    assert "measured at" in read_compound(frame, small).why
    assert read_compound(frame, None).code is None


def test_the_compound_is_settled_only_when_reads_agree_and_none_dispute():
    from pitcrew.telemetry.hud_session import HudSession

    hud = HudSession(settings=SimpleNamespace(hud_wear_enabled=False), store=None)
    now = 1000.0
    for at, code in ((990.0, "RS"), (992.0, None), (994.0, "RS")):
        hud._compound.append((at, code))
    assert hud.compound_now(now) is None           # two agreeing, three needed
    hud._compound.append((996.0, "RS"))
    assert hud.compound_now(now) == "RS"
    hud._compound.append((998.0, "RM"))
    assert hud.compound_now(now) is None           # disputed
    assert hud.compound_now(now + 120) is None     # stale
    hud.new_session()
    assert not hud._compound


def test_the_sampler_hands_on_a_compound_read_every_grab(panels):
    from pitcrew.telemetry.hud import CropFrame, LiveWearSampler, Reading

    got = []
    sampler = LiveWearSampler(source=None, write=lambda *a: None,
                              on_compound=got.append)
    sampler._pass_hygro(b"", Reading(None, "no gauge"))
    assert isinstance(got[-1], CompoundRead) and got[-1].code is None
    panel, bars = panels["RM_0"]
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[930:1070, 280:500] = panel
    full = {k: (v[0] + 280, v[1] + 280, v[2] + 930, v[3] + 930) for k, v in bars.items()}
    sampler._pass_hygro(CropFrame(pixels=frame, origin=(0, 0), canvas=(1920, 1080)),
                        Reading({"fl": 0.1}, bars=full))
    assert got[-1].code == "RM"
