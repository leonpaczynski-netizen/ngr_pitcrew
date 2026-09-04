"""Build `telemetry/hud_smallfont.json` from hand-labelled frames of a race.

**This tool owns that file. Never hand-edit it.** Same rule, and the same
reason, as `tools/extract_reference.py` and the reference catalogues: a bank
edited by hand has no provenance, and the only thing standing between the
driver and a fabricated gap is that every template in it came off a frame
somebody looked at.

    python tools/gap_bank.py frames  --video "<capture.mp4>" --set tune
    python tools/gap_bank.py sheets  --set tune
    #   ...read the sheets, write the labels into LABELS below...
    python tools/gap_bank.py build   --set tune
    python tools/gap_bank.py score   --set tune     # and then --set hold

### The three passes, and why there are three

* **`bootstrap`** cuts glyphs where the ordinary connected-run segmentation
  happens to agree with the label - 55 of 136 boxes - and averages those into a
  first bank. It exists only to give the next pass something to align with.
* **`supervise`** then aligns EVERY labelled box against its own label: the
  character sequence is given, only the positions are searched. This is the
  pass that matters. An earlier version instead re-fitted from the boxes the
  reader already read correctly, which is a self-selection trap - it converged
  on 77 of 136 and stopped, because the glyph phases it was failing on were
  exactly the ones that never contributed a template. Supervised alignment took
  the same corpus to 136 of 136.
* **`score`** reads every box back and compares. On the tune set that is a
  statement about fit, not about accuracy; `--set hold` is the one to believe.

### What a template is

A **cell**, not a glyph: its width is the character's own advance, so cells
tile edge to edge and the match window carries the sidebearing as well as the
ink. The advance is a LOW percentile of the observed spacings rather than the
median, because a `+` is followed by a space in `+ 0.435` and by a digit in
`+27.712` and the tight case is the one that must be placed exactly; where a
space follows, the reader walks the blank columns itself.

And there are **several cells per character**, clustered. The gap field is
right-aligned in a fixed layout, so a `0` in the units column lands on the same
fractional pixel every frame while a `0` in the milliseconds lands on three
others. One averaged template is the mean of all four and matches none of them
well: measured on one box, the single `0` template scored 0.970 on the units
digit and below the floor on the millisecond `0` two glyphs later, which came
back as a `6`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np                                               # noqa: E402
from PIL import Image, ImageDraw                                 # noqa: E402

from pitcrew.telemetry.board import gap_lines, own_row           # noqa: E402
from pitcrew.telemetry.hud_time import read_gap                  # noqa: E402
from pitcrew.telemetry.smallfont import (                        # noqa: E402
    BAND_H, INK_FRAC, _bank, _score, band_of, read_text,
)

OUT = (Path(__file__).resolve().parents[1]
       / "pitcrew/telemetry/hud_smallfont.json")

# The two frame sets, as (first second, step, count). **They share not one
# frame**, which is the only thing that makes the second one worth quoting.
SETS = {"tune": (60.0, 17.0, 120), "hold": (53.4, 21.3, 100)}

# A glyph of this font is 2-9 columns of ink wide; anything else the run-based
# segmentation hands back is two glyphs run together or a sliver of scenery.
WIDE = range(2, 10)
# Most cells kept per character. Four sub-pixel phases is what a right-aligned
# field of six glyphs produces; six leaves headroom without letting one odd
# frame become a template of its own.
VARIANTS = 6

# --- the hand labels -------------------------------------------------------
#
# Read off the contact sheets `sheets` writes, each box upscaled 7x NEAREST so
# the pixels stay square, with its index printed beside it. `"none"` where the
# box is not a gap readout at all - a blown-out white bar, a patch of scenery,
# the number on a car's door - and `"clipped"` where the value is there but the
# frame cut its leading characters off.
#
# A trailing `?` marks a glyph not worth swearing to: the capture is an OBS
# recording and its inter-frame compression half-eats the last millisecond
# digit from time to time. Those boxes are scored but kept OUT of the build.

LABELS = {
    "tune": {
        "f00077.00 ahead": "+0.435", "f00094.00 ahead": "+0.398?",
        "f00094.00 behind": "-0.289", "f00111.00 ahead": "+0.074",
        "f00111.00 behind": "-0.924", "f00128.00 ahead": "1.136",
        "f00145.00 ahead": "+1.101", "f00145.00 behind": "-2.074",
        "f00162.00 ahead": "+1.085", "f00162.00 behind": "-1.901",
        "f00179.00 ahead": "+1.541", "f00196.00 behind": "--:--.---",
        "f00213.00 ahead": "+0.240", "f00213.00 behind": "5.378",
        "f00230.00 ahead": "+0.448", "f00230.00 behind": "-5.524",
        "f00247.00 ahead": "+2.194", "f00247.00 behind": "-0.145",
        "f00264.00 ahead": "+0.018", "f00281.00 ahead": "+2.556?",
        "f00281.00 behind": "-0.774", "f00315.00 ahead": "+0.949",
        "f00315.00 behind": "-2.328", "f00332.00 ahead": "+0.995",
        "f00349.00 ahead": "+0.099?", "f00349.00 behind": "-2.676",
        "f00366.00 ahead": "+0.100", "f00366.00 behind": "-2.597",
        "f00400.00 ahead": "+0.027", "f00400.00 behind": "-2.439",
        "f00434.00 ahead": "+0.965", "f00434.00 behind": "-1.220",
        "f00451.00 ahead": "+0.869", "f00451.00 behind": "-1.133?",
        "f00468.00 behind": "-0.734", "f00485.00 ahead": "+0.606?",
        "f00485.00 behind": "-1.142", "f00502.00 ahead": "+0.186?",
        "f00502.00 behind": "-1.702", "f00536.00 behind": "clipped",
        "f00553.00 ahead": "+3.117", "f00553.00 behind": "-1.668",
        "f00570.00 ahead": "+3.203", "f00570.00 behind": "-1.980",
        "f00587.00 ahead": "+2.477?", "f00587.00 behind": "-2.916",
        "f00604.00 ahead": "+2.357", "f00604.00 behind": "-3.119",
        "f00621.00 ahead": "+1.654", "f00621.00 behind": "-3.934?",
        "f00655.00 ahead": "+4.951", "f00655.00 behind": "-0.474",
        "f00672.00 ahead": "+4.765", "f00672.00 behind": "-0.560",
        "f00689.00 ahead": "3.945", "f00689.00 behind": "1.507",
        "f00706.00 ahead": "+3.831", "f00706.00 behind": "-1.608",
        "f00723.00 ahead": "+3.398?", "f00740.00 behind": "none",
        "f00757.00 behind": "-4.420", "f00774.00 ahead": "+1.119",
        "f00774.00 behind": "-5.217", "f00791.00 ahead": "+0.404",
        "f00791.00 behind": "-5.894", "f00808.00 ahead": "+3.993",
        "f00808.00 behind": "-0.024", "f00825.00 ahead": "+3.922",
        "f00825.00 behind": "-0.893", "f00842.00 behind": "-1.488?",
        "f00859.00 ahead": "+1.443", "f00876.00 ahead": "+0.775",
        "f00876.00 behind": "-2.525", "f00893.00 ahead": "+4.919",
        "f00893.00 behind": "-0.045", "f00910.00 ahead": "+4.979",
        "f00927.00 ahead": "+4.883", "f00927.00 behind": "-0.484",
        "f00944.00 ahead": "+4.533", "f00944.00 behind": "none",
        "f00978.00 ahead": "+3.383", "f00978.00 behind": "-2.214",
        "f00995.00 ahead": "+3.399?", "f00995.00 behind": "-2.141",
        "f01029.00 ahead": "+3.201", "f01029.00 behind": "-2.954?",
        "f01046.00 ahead": "none", "f01046.00 behind": "-3.469",
        "f01063.00 ahead": "+2.569?", "f01063.00 behind": "-4.188?",
        "f01080.00 ahead": "+2.053", "f01080.00 behind": "-5.621",
        "f01097.00 ahead": "+2.477", "f01097.00 behind": "-5.620",
        "f01114.00 ahead": "+2.148?", "f01114.00 behind": "-6.428?",
        "f01131.00 ahead": "+1.963", "f01131.00 behind": "-6.398?",
        "f01165.00 ahead": "+0.285", "f01165.00 behind": "-7.645",
        "f01182.00 ahead": "+1.112", "f01182.00 behind": "-0.039",
        "f01199.00 ahead": "+0.460", "f01199.00 behind": "-8.654?",
        "f01216.00 ahead": "+2.042", "f01216.00 behind": "-4.090",
        "f01233.00 behind": "-4.314", "f01284.00 ahead": "+0.669",
        "f01284.00 behind": "-5.621", "f01301.00 ahead": "+0.694?",
        "f01301.00 behind": "-5.961?", "f01318.00 ahead": "+0.263",
        "f01318.00 behind": "-6.181", "f01369.00 ahead": "--:--.---",
        "f01369.00 behind": "-7.137", "f01386.00 ahead": "--:--.---",
        "f01454.00 ahead": "+27.712", "f01454.00 behind": "-6.166",
        "f01471.00 ahead": "+25.873", "f01471.00 behind": "-8.320",
        "f01488.00 ahead": "+24.522", "f01488.00 behind": "-9.397",
        "f01505.00 ahead": "+22.451", "f01505.00 behind": "-10.839",
        "f01522.00 ahead": "+22.387", "f01522.00 behind": "--:--.---",
        "f01539.00 ahead": "+7.886?", "f01539.00 behind": "-9.386?",
        "f01556.00 ahead": "+6.702", "f01573.00 ahead": "+5.698?",
        "f01573.00 behind": "-11.624", "f01590.00 ahead": "+5.794",
        "f01590.00 behind": "-12.517", "f01607.00 ahead": "+4.396?",
        "f01624.00 ahead": "+4.141", "f01624.00 behind": "-14.016",
        "f01641.00 behind": "-14.298", "f01658.00 ahead": "+2.360",
        "f01675.00 ahead": "+1.090", "f01675.00 behind": "-16.153",
        "f01692.00 ahead": "+1.151", "f01692.00 behind": "-17.216",
        "f01709.00 ahead": "+1.245", "f01709.00 behind": "-0.154",
        "f01743.00 ahead": "+0.213", "f01743.00 behind": "-1.073",
        "f01777.00 ahead": "+1.130", "f01777.00 behind": "-0.301",
        "f01794.00 ahead": "+1.258", "f01794.00 behind": "-0.039",
        "f01811.00 ahead": "+0.981", "f01811.00 behind": "-0.857",
        "f01845.00 ahead": "+0.906?", "f01896.00 ahead": "+0.706?",
        "f01896.00 behind": "-9.966", "f01913.00 ahead": "+0.649",
        "f01913.00 behind": "-10.353", "f01947.00 ahead": "+0.279",
        "f01947.00 behind": "-10.958?", "f01998.00 ahead": "+2.001",
        "f01998.00 behind": "-10.007", "f02015.00 ahead": "+1.844?",
        "f02015.00 behind": "-10.783?", "f02032.00 ahead": "+0.879",
        "f02032.00 behind": "-10.590", "f02066.00 ahead": "+1.442",
        "f02066.00 behind": "-11.105", "f02083.00 ahead": "+0.627",
        "f02083.00 behind": "-10.416",
    },
    # **Transcribed before the reader was ever run on them**, off
    # sheets that carry no reading beside the picture. Shown the
    # answer I would have been agreeing with it, not checking it.
    "hold": {
        "f00053.40 ahead": "+0.818", "f00053.40 behind": "none",
        "f00074.69 ahead": "+0.413", "f00074.69 behind": "-0.244",
        "f00095.98 ahead": "+0.526", "f00117.27 ahead": "+0.142",
        "f00117.27 behind": "-0.817", "f00138.56 ahead": "+0.948",
        "f00138.56 behind": "-2.043", "f00159.85 ahead": "+1.184",
        "f00159.85 behind": "-1.854", "f00181.14 ahead": "+1.520",
        "f00181.14 behind": "-1.923", "f00202.43 ahead": "+0.573",
        "f00202.43 behind": "-4.174", "f00223.72 ahead": "+0.247",
        "f00223.72 behind": "-5.514", "f00245.01 ahead": "+2.135",
        "f00245.01 behind": "-0.189", "f00266.30 ahead": "+2.336",
        "f00266.30 behind": "-0.125", "f00287.59 ahead": "+2.364",
        "f00287.59 behind": "-0.921", "f00330.17 ahead": "+0.968",
        "f00330.17 behind": "-2.404", "f00351.46 ahead": "+0.097",
        "f00351.46 behind": "-2.658", "f00372.75 ahead": "+0.395",
        "f00372.75 behind": "-2.529", "f00394.04 ahead": "+0.319",
        "f00394.04 behind": "-2.345", "f00436.62 ahead": "+1.008",
        "f00436.62 behind": "-1.169", "f00457.91 ahead": "+0.938",
        "f00457.91 behind": "-0.984", "f00479.20 ahead": "none",
        "f00500.49 ahead": "+0.230", "f00500.49 behind": "-1.706",
        "f00521.78 ahead": "none", "f00564.36 ahead": "+3.005",
        "f00564.36 behind": "-1.872", "f00585.65 ahead": "+2.501",
        "f00585.65 behind": "-2.869", "f00606.94 ahead": "+2.278",
        "f00606.94 behind": "none", "f00628.23 ahead": "+1.243",
        "f00628.23 behind": "-4.438", "f00649.52 ahead": "none",
        "f00670.81 ahead": "+4.765", "f00670.81 behind": "-0.573",
        "f00692.10 ahead": "+3.909", "f00692.10 behind": "-1.553",
        "f00713.39 ahead": "none", "f00734.68 ahead": "+2.803",
        "f00734.68 behind": "none", "f00755.97 ahead": "none",
        "f00777.26 ahead": "+1.132", "f00777.26 behind": "-5.249",
        "f00798.55 ahead": "+0.247", "f00798.55 behind": "-6.268",
        "f00819.84 ahead": "+3.929", "f00819.84 behind": "none",
        "f00841.13 ahead": "+3.311", "f00841.13 behind": "none",
        "f00862.42 ahead": "+1.173", "f00862.42 behind": "-2.030",
        "f00883.71 ahead": "+0.880", "f00883.71 behind": "-2.527",
        "f00905.00 ahead": "+4.930", "f00905.00 behind": "-0.217",
        "f00926.29 ahead": "+4.883", "f00926.29 behind": "-0.544",
        "f00947.58 ahead": "+4.405", "f00947.58 behind": "clipped",
        "f00968.87 ahead": "+3.429", "f00968.87 behind": "-2.104",
        "f00990.16 ahead": "+3.866", "f00990.16 behind": "-2.239",
        "f01011.45 behind": "none", "f01032.74 ahead": "+3.179",
        "f01032.74 behind": "-3.249", "f01054.03 ahead": "+3.854",
        "f01054.03 behind": "-3.651", "f01075.32 ahead": "+2.032",
        "f01075.32 behind": "-5.271", "f01096.61 ahead": "+2.477",
        "f01096.61 behind": "-5.637", "f01117.89 behind": "-6.450",
        "f01139.18 ahead": "+1.798", "f01139.18 behind": "-6.822",
        "f01160.47 behind": "none", "f01181.76 ahead": "+1.112",
        "f01181.76 behind": "-0.039", "f01203.05 ahead": "+0.114",
        "f01203.05 behind": "-8.625", "f01224.34 ahead": "none",
        "f01224.34 behind": "none", "f01245.63 ahead": "+1.649",
        "f01245.63 behind": "-4.448", "f01288.21 ahead": "+0.624",
        "f01288.21 behind": "-5.904", "f01309.50 ahead": "+0.546",
        "f01309.50 behind": "-5.753", "f01330.79 ahead": "+0.273",
        "f01330.79 behind": "-6.274", "f01352.08 ahead": "none",
        "f01373.37 ahead": "--:--.---", "f01373.37 behind": "-7.137",
        "f01394.66 ahead": "none", "f01394.66 behind": "none",
        "f01415.95 ahead": "--:--.---", "f01415.95 behind": "none",
        "f01437.24 ahead": "+30.026", "f01437.24 behind": "-4.305",
        "f01479.82 ahead": "+25.343", "f01479.82 behind": "-9.065",
        "f01501.11 ahead": "+22.684", "f01501.11 behind": "-10.363",
        "f01522.40 ahead": "+22.387", "f01522.40 behind": "--:--.---",
        "f01543.69 ahead": "+7.801", "f01543.69 behind": "-9.693",
        "f01564.98 behind": "-10.955", "f01586.27 ahead": "+5.673",
        "f01586.27 behind": "-12.516", "f01607.56 ahead": "+4.396",
        "f01607.56 behind": "-13.284", "f01628.85 ahead": "+3.749",
        "f01628.85 behind": "-14.016", "f01650.14 ahead": "+3.071",
        "f01650.14 behind": "-14.550", "f01671.43 ahead": "+1.186",
        "f01671.43 behind": "-15.725", "f01692.72 ahead": "none",
        "f01714.01 behind": "none", "f01735.30 ahead": "+0.442",
        "f01735.30 behind": "-0.924", "f01756.59 ahead": "+0.826",
        "f01756.59 behind": "-0.454", "f01777.88 ahead": "+1.126",
        "f01777.88 behind": "-0.296", "f01799.17 ahead": "+0.105",
        "f01799.17 behind": "-0.576", "f01820.46 ahead": "+1.034",
        "f01820.46 behind": "-0.656", "f01841.75 ahead": "+0.793",
        "f01841.75 behind": "-0.870", "f01863.04 ahead": "+0.386",
        "f01863.04 behind": "-1.605", "f01884.33 ahead": "+1.489",
        "f01884.33 behind": "-9.941", "f01905.62 ahead": "+0.633",
        "f01905.62 behind": "-10.338", "f01926.91 ahead": "+0.103",
        "f01926.91 behind": "-10.518", "f01948.20 ahead": "+0.279",
        "f01948.20 behind": "-10.958", "f01969.49 ahead": "+3.925",
        "f01969.49 behind": "-9.355", "f02012.07 ahead": "+1.831",
        "f02012.07 behind": "-10.783", "f02033.36 ahead": "+0.863",
        "f02033.36 behind": "-10.840", "f02054.65 ahead": "+0.583",
        "f02054.65 behind": "-11.020", "f02075.94 ahead": "+0.926",
        "f02075.94 behind": "-10.118", "f02118.52 ahead": "+6.998",
        "f02118.52 behind": "-1.019", "f02139.81 behind": "clipped",
        "f02161.10 ahead": "+6.684", "f02161.10 behind": "-2.165",
    },
}


def firm(label):
    """A label solid enough to cut a template out of."""
    return (bool(label) and label not in ("none", "clipped")
            and "?" not in label)


# --- frames and boxes ------------------------------------------------------

def cache_for(which) -> Path:
    return Path.cwd() / f"_gapbank/{which}"


def grab(video: Path, which: str) -> None:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                            # noqa: BLE001
        exe = "ffmpeg"
    start, step, count = SETS[which]
    out = cache_for(which)
    out.mkdir(parents=True, exist_ok=True)
    made = 0
    for index in range(count):
        at = start + index * step
        shot = out / f"f{at:08.2f}.png"
        if shot.exists():
            made += 1
            continue
        done = subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-ss", f"{at:.3f}",
             "-i", str(video), "-frames:v", "1", "-y", str(shot)],
            capture_output=True)
        made += done.returncode == 0 and shot.exists()
    print(f"{made}/{count} frames in {out}")


def boxes(which):
    """`(key, t, patch)` for every box `gap_lines` frames on this set.

    The patch is exactly what `race.gaps.read_gaps` hands the reader, so
    nothing between the frame and the label is reimplemented here - which is
    the defect `tools/board_bench.py` exists to have stopped repeating.

    **Keyed by frame and side, never by position in this list.** The labels
    were first keyed by index and it went wrong immediately: a `zip` of the
    label keys against a differently-filtered box list truncated in silence and
    three boxes carried somebody else's value. A frame name and a side are what
    a label is actually about.
    """
    out = []
    for shot in sorted(cache_for(which).glob("*.png")):
        pixels = np.asarray(Image.open(shot).convert("RGB"))
        row = own_row(pixels)
        if row is None:
            continue
        for side, box in zip(("ahead", "behind"), gap_lines(pixels, row)):
            if box is None:
                continue
            x0, y0, x1, y1 = box
            out.append((f"{shot.stem} {side}", float(shot.stem[1:]),
                        pixels[y0:y1 + 1, x0:x1 + 1]))
    return out


def sheets(which, per=20, scale=7):
    """Contact sheets to read the labels off. No readings printed on them."""
    out = Path.cwd() / f"_gapbank/{which}-sheets"
    out.mkdir(parents=True, exist_ok=True)
    rows, sheet = [], 0
    got = boxes(which)
    for item in got:
        rows.append(item)
        if len(rows) == per or item is got[-1]:
            _draw(rows, out / f"s{sheet:02d}.png", scale)
            sheet, rows = sheet + 1, []
    print(f"{len(got)} boxes, {sheet} sheets in {out}")


def _draw(rows, path, scale):
    lum = [np.clip(p.min(axis=2).astype(float) * 1.6, 0, 255).astype("uint8")
           for _, _, p in rows]
    wide = max(a.shape[1] for a in lum) * scale + 150
    tall = sum(a.shape[0] * scale + 10 for a in lum) + 8
    canvas = Image.new("L", (wide, tall), 40)
    pen = ImageDraw.Draw(canvas)
    y = 4
    for (key, _, _), bits in zip(rows, lum):
        canvas.paste(Image.fromarray(bits, "L").resize(
            (bits.shape[1] * scale, bits.shape[0] * scale), Image.NEAREST),
            (140, y))
        pen.text((4, y + bits.shape[0] * scale // 2 - 6), key, fill=255)
        y += bits.shape[0] * scale + 10
    canvas.save(path)


def bands(which):
    """`(label, band)` for every labelled box, in the reader's own units."""
    labels = LABELS[which]
    return [(labels.get(key), band_of(patch))
            for key, _, patch in boxes(which)]


# --- the three passes ------------------------------------------------------

def _runs_at(band, cut):
    used = np.where((band > cut).any(axis=0))[0]
    out, start, last = [], None, None
    for column in used:
        if start is None:
            start = column
        elif column != last + 1:
            out.append((start, last))
            start = column
        last = column
    if start is not None:
        out.append((start, last))
    return out


def bootstrap(labelled):
    placed = []
    for label, band in labelled:
        if not firm(label) or band is None:
            continue
        for cut in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
            pieces = _runs_at(band, cut)
            if len(pieces) != len(label):
                continue
            if not all((b - a + 1) in WIDE for a, b in pieces):
                continue
            placed.append((band, [(c, a) for c, (a, _) in
                                  zip(label, pieces)]))
            break
    return placed


def align(band, text, slack=2):
    """Where each character of a KNOWN string sits in this band, or None."""
    bank = _bank()
    if any(c not in bank for c in text):
        return None
    wide = band.shape[1]
    inked = (band > INK_FRAC).any(axis=0)
    memo = {}

    def skip(x):
        while x < wide and not inked[x]:
            x += 1
        return x

    def solve(x, i):
        x = skip(x)
        if i == len(text):
            return (0.0, []) if x >= wide else None
        if x >= wide or (x, i) in memo:
            return memo.get((x, i))
        memo[(x, i)] = None
        variants, advance = bank[text[i]]
        fit = max(_score(band[:, x:x + one.shape[1]], one)[2]
                  for one in variants)
        found = None
        for drift in range(-slack, slack + 1):
            nxt = x + advance + drift
            if nxt <= x:
                continue
            rest = solve(nxt, i + 1)
            if rest is None:
                continue
            if found is None or fit + rest[0] > found[0]:
                found = (fit + rest[0], [(text[i], x)] + rest[1])
        memo[(x, i)] = found
        return found

    got = solve(0, 0)
    return got[1] if got else None


def supervise(labelled):
    placed = []
    for label, band in labelled:
        if not firm(label) or band is None:
            continue
        got = align(band, label)
        if got is not None:
            placed.append((band, got))
    return placed


def _kmeans(stack, k, rounds=25):
    flat = np.stack([c.ravel() for c in stack])
    if k <= 1 or len(flat) <= k:
        return [np.mean(stack, axis=0)]
    seeds = [int(np.argmax(np.linalg.norm(flat - flat.mean(0), axis=1)))]
    while len(seeds) < k:
        far = np.min([np.linalg.norm(flat - flat[s], axis=1) for s in seeds],
                     axis=0)
        seeds.append(int(np.argmax(far)))
    centres = flat[seeds].copy()
    which = np.zeros(len(flat), dtype=int)
    for _ in range(rounds):
        which = np.argmin(np.stack(
            [np.linalg.norm(flat - c, axis=1) for c in centres]), axis=0)
        moved = False
        for i in range(k):
            members = flat[which == i]
            if not len(members):
                continue
            fresh = members.mean(axis=0)
            moved |= not np.allclose(fresh, centres[i])
            centres[i] = fresh
        if not moved:
            break
    out = [flat[which == i].mean(axis=0).reshape(stack[0].shape)
           for i in range(k) if (which == i).sum() >= 3]
    return out or [np.mean(stack, axis=0)]


def cells_from(placed):
    spacing, starts = defaultdict(list), defaultdict(list)
    for band, glyphs in placed:
        for i, (char, at) in enumerate(glyphs):
            starts[char].append((band, at))
            if i + 1 < len(glyphs):
                spacing[char].append(glyphs[i + 1][1] - at)
    bank = {}
    for char, seen in sorted(starts.items()):
        seq = spacing.get(char) or []
        advance = max(3, min(11, int(round(float(np.percentile(seq, 15))))
                             if seq else 6))
        stack = []
        for band, at in seen:
            cell = band[:, at:at + advance]
            if cell.shape[1] < advance:
                cell = np.pad(cell, ((0, 0), (0, advance - cell.shape[1])))
            stack.append(cell)
        mean = np.mean(stack, axis=0)
        # Trim to the character's own ink plus a column of sidebearing, but
        # never below the tightest spacing observed. The trim is what stops a
        # `+` taking the advance of its SPACED form (16 px, so the reader steps
        # over the first digit of `+27.712`); the floor is what stops a `1` -
        # a bare vertical stroke - taking an advance of 6 against a measured
        # 7-9, which left the reader unable to reach the glyph after it at all.
        floor = int(np.floor(np.percentile(seq, 5))) if seq else 3
        lit = np.where(mean.max(axis=0) > 0.20)[0]
        if len(lit):
            advance = max(min(advance, int(lit[-1]) + 2),
                          min(floor, advance))
        stack = [c[:, :advance] for c in stack]
        variants = _kmeans(stack, min(VARIANTS, max(1, len(stack) // 4)))
        bank[char] = {"advance": advance, "n": len(stack),
                      "variants": [v.round(3).tolist() for v in variants]}
    return bank


def build(which):
    labelled = bands(which)
    firmly = sum(1 for label, _ in labelled if firm(label))
    print(f"{len(labelled)} boxes, {firmly} firmly labelled")
    placed = bootstrap(labelled)
    print(f"  bootstrap : {len(placed)} boxes segmented cleanly")
    _write(cells_from(placed), f"bootstrap off the {which} set")
    _bank.cache_clear()
    placed = supervise(labelled)
    print(f"  supervise : {len(placed)} boxes aligned against their own label")
    _write(cells_from(placed), f"supervised alignment of the {which} labels")
    _bank.cache_clear()


def _write(bank, note):
    OUT.write_text(json.dumps({"height": BAND_H, "note": note,
                               "templates": bank}), encoding="utf-8")
    print("    " + ", ".join(f"{c}:n={v['n']}/{len(v['variants'])}v,"
                             f"a={v['advance']}" for c, v in bank.items()))


def score(which):
    labels = LABELS[which]
    right = wrong = refused = invented = 0
    for key, at, patch in boxes(which):
        truth = labels.get(key)
        side = key.split()[1]
        got = read_gap(patch)
        text = None if got is None else f"{got[0]}{got[1]:.3f}"
        if not truth or truth in ("none", "clipped", "--:--.---"):
            if text is not None:
                invented += 1
                print(f"  {key:20} {side:6} no value ({truth}) "
                      f"but READ {text}")
            continue
        if text is None:
            refused += 1
            print(f"  {key:20} {side:6} truth {truth:10} refused"
                  f"  (box {patch.shape[1]}x{patch.shape[0]})")
        elif abs(float(text) - float(truth.rstrip("?"))) < 5e-4:
            right += 1
        else:
            wrong += 1
            print(f"  {key:20} {side:6} truth {truth:10} "
                  f"READ {text}  <-- DIFFERS")
    total = right + wrong + refused
    print(f"\n{which}: {total} boxes carrying a value"
          f"\n  right     {right:4d}  ({100 * right / max(1, total):.1f}%)"
          f"\n  differs   {wrong:4d}"
          f"\n  refused   {refused:4d}"
          f"\n  read a value out of a box that has none: {invented}")


# The gap boxes committed as test fixtures, and the value each one carries.
# Cut from the tune frames rather than the hold-out ones, so the hold-out stays
# a set nothing was fitted to.
FIXTURES = [
    ("f00077.00 ahead", "gap-plus-0.435.png"),
    ("f00281.00 behind", "gap-minus-0.774.png"),
    ("f01454.00 ahead", "gap-plus-27.712.png"),
    ("f01505.00 behind", "gap-minus-10.839.png"),
    ("f01522.00 behind", "gap-dashes.png"),
    ("f00689.00 ahead", "gap-no-sign-clipped.png"),
]


def fixtures():
    """Write the committed crops. Each is the patch the reader is handed."""
    out = Path(__file__).resolve().parents[1] / "pitcrew/tests/fixtures"
    found = {key: patch for key, _at, patch in boxes("tune")}
    for key, name in FIXTURES:
        if key not in found:
            print(f"  missing {key}")
            continue
        Image.fromarray(found[key].astype("uint8"), "RGB").save(out / name)
        print(f"  {name}  {found[key].shape}  from {key}"
              f"  ({LABELS['tune'].get(key)})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=["frames", "sheets", "build", "score",
                                     "fixtures"])
    ap.add_argument("--set", dest="which", default="tune", choices=list(SETS))
    ap.add_argument("--video")
    args = ap.parse_args()
    if args.what == "frames":
        if not args.video:
            raise SystemExit("--video is required to decode frames")
        grab(Path(args.video), args.which)
    elif args.what == "sheets":
        sheets(args.which)
    elif args.what == "build":
        if args.which != "tune":
            raise SystemExit("the bank is built on the tune set only - the "
                             "hold-out is worth nothing once it is fitted to")
        build(args.which)
    elif args.what == "fixtures":
        fixtures()
    else:
        score(args.which)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
