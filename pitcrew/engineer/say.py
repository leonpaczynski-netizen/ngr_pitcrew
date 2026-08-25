"""How the engineer says a number out loud.

Two complaints from the driver, 23 Aug 2026, and both are about the same thing:
**the app was handing the voice a figure formatted for a machine.**

* A lap time was spoken as total seconds — *"eighty-nine point four"* — where
  every driver and every timing screen in the world says **1:29.4**.
* A gap was spoken as a bare decimal — *"one point three off your best"* — with
  no unit, so the number floats free of what it measures.

Under a helmet, at racing speed, a figure he has to convert is a figure he does
not use. So this module owns the conversion and nothing else does.

**The split that matters: spoken text and written text are not the same string.**

* `lap_time` gives **1:29.412** — for the log, the screen and the debrief, where
  the milliseconds are the point and can be read back at leisure.
* `spoken_lap_time` gives **"one twenty-nine point four"** — for Piper and SAPI,
  which are unreliable readers of punctuation. Handing a TTS engine `1:29.412`
  invites *"one colon twenty nine point four one two"*, and the tenth is all he
  can act on anyway.

**Tenths below a second, plain seconds above it**, because that is how the gap
is described in a real pit lane: *"three tenths"*, not *"zero point three"*. The
switch is at 0.95 s so that nothing is ever spoken as *"ten tenths"*.
"""
from __future__ import annotations

_UNITS = ("zero", "one", "two", "three", "four", "five", "six", "seven",
          "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
          "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty"}

_TENTHS = {1: "a tenth", 2: "two tenths", 3: "three tenths", 4: "four tenths",
           5: "five tenths", 6: "six tenths", 7: "seven tenths",
           8: "eight tenths", 9: "nine tenths"}

# Above this a gap is said in plain seconds. Set just under a whole second so
# "ten tenths" can never be produced by rounding.
TENTHS_LIMIT_S = 0.95


def _words_under_60(value: int) -> str:
    if value < 20:
        return _UNITS[value]
    tens, units = divmod(value, 10)
    if units == 0:
        return _TENS[tens]
    return f"{_TENS[tens]}-{_UNITS[units]}"


def lap_time(ms: int | None) -> str:
    """`1:29.412` — for the screen, the log and the debrief.

    The written form keeps all three digits: a lap time is compared against
    other lap times, and the thousandth is what separates two of his laps.
    """
    if not ms or ms <= 0:
        return "--:--.---"
    minutes, remainder = divmod(int(ms), 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def spoken_lap_time(ms: int | None) -> str:
    """`"one twenty-nine point four"` — for the voice.

    Rounded to the tenth deliberately. The thousandth is real and belongs in
    the written form, but it is not something he can hear, hold and act on
    between two corners.

    A time landing on a whole second is said **"flat"**, which is what an
    engineer says and is shorter than the alternative.
    """
    if not ms or ms <= 0:
        return "no time"
    total_tenths = int(round(int(ms) / 100.0))
    minutes, remainder = divmod(total_tenths, 600)
    seconds, tenths = divmod(remainder, 10)

    if minutes:
        # "one oh five", not "one five" - the leading zero is spoken.
        if seconds < 10:
            head = f"{_UNITS[minutes]} oh {_UNITS[seconds]}"
        else:
            head = f"{_UNITS[minutes]} {_words_under_60(seconds)}"
    else:
        head = _words_under_60(seconds)
    # "Flat" rather than a bare "one forty-nine": it says out loud that the
    # tenth is zero, where silence would leave him wondering whether it was
    # dropped.
    return f"{head} flat" if tenths == 0 else f"{head} point {_UNITS[tenths]}"


def spoken_gap(seconds: float | None) -> str:
    """A gap, said the way the pit lane says it.

    Under a second, tenths in words — *"three tenths"*. At a second and above,
    plain seconds with the unit attached — *"1.3 seconds"* — because a bare
    decimal in the middle of a sentence is a number without a dimension.

    **Magnitude only.** Direction is the caller's to state, because "under your
    best" and "down" carry opposite signs in the same sentence and only the
    caller knows which it means.

    Anything smaller than a tenth still says "a tenth" rather than rounding to
    nothing — callers gate on their own level band before they get here, and a
    gap that reached this function is one the caller has already decided is
    worth naming.
    """
    if seconds is None:
        return ""
    value = abs(float(seconds))
    if value < TENTHS_LIMIT_S:
        return _TENTHS[max(1, min(9, int(round(value * 10.0))))]
    if abs(value - 1.0) < 0.05:
        return "one second"
    return f"{value:.1f} seconds"
