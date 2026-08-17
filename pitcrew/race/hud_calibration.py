"""Pairing what the driver can SEE with what the app can MEASURE.

GT7's HUD draws a frame around each tyre and, in Polyphony's own words from
the online manual, *"as the tires get hotter, the outside frame for the four
tires will get redder."* That is the only temperature feedback the game gives
the driver, and it is monotonic: no green, no in-window state, no thresholds,
no scale. Nobody has ever mapped a frame colour to a telemetry value - not the
community, not any dashboard project, not Polyphony.

**So this is the one calibration bridge that exists**, and it is cheap: when
he sees a frame go red he says so, and the app writes down the per-wheel
temperature its own feed was reporting at that instant. Over a season that
becomes a per-car anchor between the thing he can see in VR and the thing this
app measures - which is the only route to a car-specific upper bound that does
not depend on a stranger's 2025 forum post.

Two disciplines, both deliberate:

* **The driver reports an EVENT; the app supplies the NUMBER.** He is not
  being asked to read a temperature off anything. His report is a timestamp,
  and CLAUDE.md §4.1 makes it primary evidence. The °C beside it is ours.
* **Nothing reads this yet, and nothing should.** One observation is one
  observation. The community's own record on this channel is a warning: the
  frame is also reported to flash red transiently during a slide and go dark
  again the moment traction returns, which looks more like an instantaneous
  friction event than a bulk temperature - PD's manual says temperature,
  observed behaviour looks like slip, and the two are recorded as the conflict
  they are rather than averaged. Deciding which is right needs a body of
  paired observations, and this file is how that body gets collected.
"""
from __future__ import annotations

import datetime
import json

from pitcrew.diagnostics import log
from pitcrew.paths import DATA_DIR

# One JSON object per line, appended. A flat log rather than a table because
# the schema of a thing nobody has measured before will change, and a JSONL
# file survives that where a migration does not.
CALIBRATION_FILE = DATA_DIR / "tyre_hud_calibration.jsonl"


def note_frame_red(*, car_id, compound: str | None, temps,
                   lap: int | None = None, speed_kmh: float | None = None,
                   event_id: int | None = None,
                   path=None) -> dict | None:
    """Record one "the frame went red" report against the live temperatures.

    `temps` is the four-corner tuple straight off the packet, FL/FR/RL/RR.
    Returns the row written, or None where there was nothing to pair the
    report with - a report with no telemetry beside it is not an observation,
    and writing it would put a bare timestamp into a file whose whole purpose
    is the pairing.

    `speed_kmh` travels because of the slip hypothesis: a red frame at racing
    speed and one during a spin are different events, and the analysis that
    eventually reads this file will want to separate them.
    """
    if temps is None or len(temps) != 4:
        return None
    front = (temps[0] + temps[1]) / 2.0
    rear = (temps[2] + temps[3]) / 2.0
    row = {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "carId": car_id,
        "eventId": event_id,
        "compound": compound,
        "lap": lap,
        "speedKmh": round(speed_kmh, 1) if speed_kmh is not None else None,
        "tempC": {"fl": round(temps[0], 1), "fr": round(temps[1], 1),
                  "rl": round(temps[2], 1), "rr": round(temps[3], 1)},
        "frontMeanC": round(front, 1),
        "rearMeanC": round(rear, 1),
        "hottestCornerC": round(max(temps), 1),
        # What the driver actually reported, kept in his own terms so a later
        # reader is never in doubt about which half of the row is observation
        # and which half is telemetry.
        "driverReport": "tyre frame went red",
        "source": "driver-reported HUD frame colour, paired with the app feed",
    }
    target = path or CALIBRATION_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError as exc:
        # Never let a note-taking failure reach a driver mid-race. The report
        # is still logged, which is where it can be recovered from.
        log("race").warning("could not write the HUD calibration row: %s", exc)
    log("race").info(
        "HUD frame reported red: fronts %.1f, rears %.1f, hottest %.1f degC "
        "on car %s, compound %s", front, rear, max(temps), car_id, compound)
    return row
