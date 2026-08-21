"""Read the race sheet out of a knowledge-base setup document.

`pitcrew/setup/parse.py` reads what the tune builder *replies* — a JSON block,
`rh_f: 62` lines, or a markdown table. **These documents are a different thing:**
a fixed-width presentation table with a RACE column and a QUALIFYING column side
by side, decorated with markers like `◄──`, `●` and `▲`. Handed one, the reply
parser found three values and all three were wrong, because the range-check
section further down the page also contains numbers.

So this reads them on their own terms, and it is deliberately timid:

* **Only the RACE column.** The qualifying sheet sits to its right and taking
  the wrong column would be silent and total.
* **Only inside the fenced sheet block**, so §5.1's range table and §6's test
  queue cannot contribute a number.
* **Coverage is reported and low coverage is refused.** A partial read compared
  against a stored sheet would report differences that are really absences,
  which is the failure this exists to prevent.

Used by `check_setup_sheets.py` to say whether an unfiled revision actually
changes anything, rather than merely being newer.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Label as printed in these documents -> the app's key. The app's own
# vocabulary calls `rh_*` "ride height"; GT7's screen and these sheets call it
# "body height", which is the same slider.
ROWS: dict[str, tuple[str, str] | str] = {
    "body height": ("rh_f", "rh_r"),
    "ride height": ("rh_f", "rh_r"),
    "anti-roll bar": ("arb_f", "arb_r"),
    "damping compr.": ("dc_f", "dc_r"),
    "damping compression": ("dc_f", "dc_r"),
    "damper compression": ("dc_f", "dc_r"),
    "damping expan.": ("de_f", "de_r"),
    "damping expansion": ("de_f", "de_r"),
    "damper expansion": ("de_f", "de_r"),
    "natural freq.": ("nf_f", "nf_r"),
    "natural frequency": ("nf_f", "nf_r"),
    "camber angle": ("cam_f", "cam_r"),
    "camber": ("cam_f", "cam_r"),
    "toe angle": ("toe_f", "toe_r"),
    "toe": ("toe_f", "toe_r"),
    "downforce": ("df_f", "df_r"),
    "initial torque": "lsd_i",
    "acceleration sens.": "lsd_a",
    "acceleration sensitivity": "lsd_a",
    "braking sens.": "lsd_b",
    "braking sensitivity": "lsd_b",
    "brake balance": "bb",
    "final gear": "fg",
    "max speed setting": "top",
    "top speed": "top",
}
GEARS = {"1st": 0, "2nd": 1, "3rd": 2, "4th": 3, "5th": 4, "6th": 5,
         "7th": 6, "8th": 7}

# A value token: an optional sign, digits, optional decimals. The first one in
# the race column is the absolute value; anything after it is the delta and the
# percent-of-range, which are derived and not what is stored.
NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
DECORATION = re.compile("[◄►●▲▼"
                        "─←→⚠️]+")


# **Minus-sign lookalikes, and this is not cosmetic.** These documents are
# typeset, so a negative toe is written with U+2212 MINUS SIGN rather than a
# hyphen. Left alone, the number regex skips it and reads the Shelby's front
# toe of -0.05 deg as +0.05 - a sign error on a parameter whose sign is the
# whole setting, arriving silently. En dash and figure dash are here for the
# same reason.
MINUSES = str.maketrans({"−": "-", "–": "-", "‒": "-",
                         "‐": "-", "‑": "-"})


def _clean(line: str) -> str:
    return DECORATION.sub(" ", line.translate(MINUSES).replace("·", " "))


def _race_column(rest: str) -> str | None:
    """The first of the two side-by-side columns.

    Columns are separated by a run of spaces. Two is enough in these documents
    and three would miss the tighter ones.
    """
    parts = [p for p in re.split(r"\s{2,}", rest.strip()) if p]
    return parts[0] if parts else None


def read_race_sheet(text: str) -> tuple[dict[str, float], list[float], list[str]]:
    """(values, gear ratios, lines that looked like settings and were not read)"""
    blocks = re.findall(r"```(.*?)```", text, re.S)
    values: dict[str, float] = {}
    gears: dict[int, float] = {}
    skipped: list[str] = []

    for block in blocks:
        if "Body height" not in block and "Anti-roll" not in block:
            continue                      # not the sheet - a code or data block
        row_key: tuple[str, str] | str | None = None
        for raw in block.splitlines():
            line = _clean(raw)
            low = line.lower()
            if not line.strip() or set(line.strip()) <= {"-", "=", "_"}:
                continue

            gear = next((g for g in GEARS if low.strip().startswith(g)), None)
            if gear is not None:
                column = _race_column(line.strip()[len(gear):])
                found = NUMBER.search(column or "")
                if found:
                    gears[GEARS[gear]] = float(found.group())
                continue

            label = next((name for name in sorted(ROWS, key=len, reverse=True)
                          if low.lstrip().startswith(name)), None)
            if label is not None:
                row_key = ROWS[label]
                rest = line.lstrip()[len(label):]
            elif row_key is not None and re.match(r"\s*(front|rear)\b", low):
                rest = line
            else:
                continue

            axis = None
            axis_match = re.match(r"\s*(front|rear)\b", rest.lower())
            if axis_match:
                axis = axis_match.group(1)
                rest = rest[axis_match.end():]

            column = _race_column(rest)
            found = NUMBER.search(column or "")
            if not found:
                if label is not None and not isinstance(row_key, tuple):
                    skipped.append(raw.strip()[:70])
                continue
            value = float(found.group())

            if isinstance(row_key, tuple):
                if axis == "front":
                    values.setdefault(row_key[0], value)
                elif axis == "rear":
                    values.setdefault(row_key[1], value)
            else:
                values.setdefault(row_key, value)
                row_key = None

    ordered = [gears[i] for i in sorted(gears)] if gears else []
    return values, ordered, skipped


def main() -> int:
    path = Path(sys.argv[1])
    values, gears, skipped = read_race_sheet(path.read_text(encoding="utf-8"))
    print(f"{path.name}: {len(values)} values, {len(gears)} gear ratios")
    for key in sorted(values):
        print(f"   {key:<8} {values[key]}")
    if gears:
        print(f"   gears    {gears}")
    for line in skipped:
        print(f"   ? unread: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
