"""The compound fitted, read off the HUD wear panel's own label.

GT7 prints the compound code twice on the wear panel: immediately above the
front pair of wear bars and immediately below the rear pair, centred on the
car icon between the columns. Asked for by the driver so practice laps carry
their tyre from the first lap (14 Sep 2026: "the front and rear compound type
is displayed next to tyre wear bars").

### What it is, measured on 14 Sep 2026

Seven flat-screen 1080p recordings, 327 frames, both labels on each:

* **White text, never coloured on track** (text pixels ~(225, 225, 224), no
  saturated pixel in any label window) - the driver confirms it colours only in
  the pit lane. So the letters are the signal.
* **10 px letters, flush against the bars**: front rows fl.y0-11..fl.y0-1, rear
  rows rl.y1+1..rl.y1+11, the pair centred on the car icon; the left edge
  jitters a pixel between frames, so the match searches +-1 px.
* **RS against RM separates by a wide margin**: the worst frame against its own
  code's template correlated 0.873 (over a bright background), the best frame
  against the OTHER code's template 0.039.

### What it may not claim

**Only RS and RM have ever been seen on a flat capture**, so only they have
templates. Any other label - RH, IM, HW, the sports and comfort tyres - matches
nothing above the floor and is refused, never read as the nearer of RS and RM:
*"a guessed compound would be worse than a missing one, because a wear rate
attributed to the wrong tyre is not a gap in the model, it is a corruption of
it"* (`controller._tag_race_compound`). Front and rear must agree, and the bar
height must be the calibrated one, or the answer is None with the reason.

**It reads only at the 1080p flat HUD's 36 px bars.** On the calibrated
1720x916 canvas the bars are 30 px and every label is refused "measured at
36" - honest, and a gap: nothing reads the compound there until templates are
cut at that size.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

BANK_PATH = Path(__file__).with_name("hud_compound_labels.json")

# Own-code worst 0.873, other-code best 0.039 (see module docstring). The floor
# sits well above anything a wrong code reached and below the worst true read.
MATCH_FLOOR = 0.75
# And a read must beat the second-best template by this much, so two templates
# that both fit a smudge cannot both be "read".
MATCH_MARGIN = 0.35
# The templates were cut at 36 px bars. Other sizes were never measured.
SIZE_TOLERANCE = 0.08
# A label crop with almost no contrast is not a label.
MIN_INK_SD = 12.0


@dataclass(frozen=True)
class CompoundRead:
    code: str | None
    front: str | None = None
    rear: str | None = None
    why: str = ""


@lru_cache(maxsize=1)
def _bank() -> dict:
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    templates = {name: np.asarray(rows, dtype=float)
                 for name, rows in data["templates"].items()}
    return {"anchor": data["anchor"], "templates": templates}


def known_codes() -> tuple[str, ...]:
    """The codes a template exists for - the only codes this can ever return."""
    return tuple(sorted({name.split("_")[0] for name in _bank()["templates"]}))


def _ncc(a: np.ndarray, b: np.ndarray) -> float | None:
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return None if denom == 0.0 else float((a * b).sum() / denom)


def _read_side(gray: np.ndarray, x0: int, y0: int, side: str) -> tuple[str | None, str]:
    """Best template for one label, searching +-1 px, or (None, why)."""
    bank = _bank()
    h, w = 11, 30
    best: dict[str, float] = {}
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ys, xs = y0 + dy, x0 + dx
            if ys < 0 or xs < 0 or ys + h > gray.shape[0] or xs + w > gray.shape[1]:
                continue
            patch = gray[ys:ys + h, xs:xs + w]
            if patch.std() < MIN_INK_SD:
                continue
            for name, template in bank["templates"].items():
                code, template_side = name.split("_")
                if template_side != side:
                    continue
                score = _ncc(patch, template)
                if score is not None and score > best.get(code, -1.0):
                    best[code] = score
    if not best:
        return None, "no label ink"
    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    code, score = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else -1.0
    if score < MATCH_FLOOR:
        return None, f"no known label (best {code} at {score:.2f})"
    if score - runner < MATCH_MARGIN:
        return None, f"{code} and {ranked[1][0]} both fit"
    return code, ""


def read_compound(frame, bars: dict | None) -> CompoundRead:
    """The compound on the wear panel of one frame, or None with the reason."""
    if not bars or "fl" not in bars or "rl" not in bars:
        return CompoundRead(None, why="wear panel not located")
    anchor = _bank()["anchor"]
    fx0, _, fy0, fy1 = bars["fl"]
    _, _, _, ry1 = bars["rl"]
    bar_px = fy1 - fy0 + 1
    if abs(bar_px / anchor["ref_bar_px"] - 1.0) > SIZE_TOLERANCE:
        return CompoundRead(None, why=f"bars are {bar_px} px; the labels were "
                                      f"measured at {anchor['ref_bar_px']}")
    # Crop before converting: a whole 1080p frame to float costs ~55 ms a grab
    # (critic pass 1) and only two 13x32 windows are ever looked at.
    pixels = np.asarray(frame)
    x0 = fx0 + anchor["x0_from_fl_x0"]
    front_y = fy0 + anchor["front_rows_from_fl_y0"][0]
    rear_y = ry1 + anchor["rear_rows_from_rl_y1"][0]

    def window(y: int):
        top, left = max(0, y - 1), max(0, x0 - 1)
        crop = pixels[top:y + 12, left:x0 + 31].astype(float).min(axis=2)
        return crop, x0 - left, y - top

    crop, cx, cy = window(front_y)
    front, front_why = _read_side(crop, cx, cy, "F")
    crop, cx, cy = window(rear_y)
    rear, rear_why = _read_side(crop, cx, cy, "R")
    if front and rear and front == rear:
        return CompoundRead(front, front, rear)
    if front and rear:
        return CompoundRead(None, front, rear, why="front and rear labels disagree")
    return CompoundRead(None, front, rear,
                        why=f"front: {front_why or front}; rear: {rear_why or rear}")
