"""Live Activation 3 — bounded race PTT answers from the canonical race state (Program 3).

A pure, deterministic mapping from ONE bounded push-to-talk intent to an honest spoken answer,
sourced ENTIRELY from the current canonical live race state — never stale UI text, never a
fabricated value. Every field the answer needs is read from the state; when it is unknown the
answer says so plainly rather than inventing a number. Unsupported intents get an honest "I can't
answer that" rather than a wrong guess.

This is the deterministic answer layer; the existing ``voice.query_listener`` owns the physical
microphone / recogniser / TTS. Keeping the answer logic here makes it testable offline and
guarantees the race PTT speaks from canonical state.

Qt-free, offline, never raises. Advisory only — a PTT answer issues no command and changes nothing.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple


class RaceQueryIntent(str, Enum):
    FUEL = "fuel"                       # how much fuel is left
    FUEL_PREDICTED = "fuel_predicted"   # predicted fuel at the finish
    LAPS_REMAINING = "laps_remaining"
    TIME_REMAINING = "time_remaining"
    POSITION = "position"
    DELTA = "delta"                     # pace vs plan / reference
    BEST_LAP = "best_lap"
    TYRE = "tyre"
    PIT_WINDOW = "pit_window"
    STRATEGY = "strategy"
    PUSH = "push"
    FUEL_SAVE = "fuel_save"
    REPEAT = "repeat"
    MUTE = "mute"


#: The bounded PTT vocabulary the race context supports (§6.2). Anything outside this set gets an
#: honest "unsupported" answer — the race PTT never opens free-form dialogue.
SUPPORTED_RACE_INTENTS = frozenset(i.value for i in RaceQueryIntent)


def _get(state, name):
    return getattr(state, name, None)


def _num(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) else None


def _fmt_l(v) -> str:
    n = _num(v)
    return f"{n:.1f} litres" if n is not None else ""


def _fmt_s(v) -> str:
    n = _num(v)
    return f"{n:.3f}" if n is not None else ""


def _fmt_mmss(secs) -> str:
    n = _num(secs)
    if n is None or n < 0:
        return ""
    m, s = divmod(int(n), 60)
    return f"{m} min {s:02d} sec" if m else f"{s} sec"


def answer_race_query(intent, state, *, last_answer: str = "") -> Tuple[str, bool]:
    """Return ``(spoken_answer, supported)`` for a bounded race PTT ``intent`` given the canonical
    ``state`` (a CanonicalLiveRaceState or any object exposing the same attributes).

    ``supported`` is False for an intent outside the bounded vocabulary; the answer is then an honest
    refusal. A supported intent whose evidence is unavailable returns an honest "I don't have that
    yet" — never a fabricated number. ``last_answer`` backs REPEAT. Never raises."""
    try:
        key = intent.value if isinstance(intent, RaceQueryIntent) else str(intent or "").strip().lower()
    except Exception:
        key = ""
    if key not in SUPPORTED_RACE_INTENTS:
        return ("I can only answer fuel, laps, time, position, pace, tyres, pit window and strategy "
                "questions.", False)

    if state is None:
        return ("I don't have live race data yet.", True)

    # Telemetry freshness gates every data answer (control intents excepted).
    fresh = bool(getattr(state, "telemetry_fresh", True))
    control = key in (RaceQueryIntent.REPEAT.value, RaceQueryIntent.MUTE.value,
                      RaceQueryIntent.PUSH.value, RaceQueryIntent.FUEL_SAVE.value)
    if not fresh and not control:
        return ("Telemetry's dropped — I can't read the car right now.", True)

    clock = _get(state, "clock")
    pit = _get(state, "pit")
    stint = _get(state, "stint")

    if key == RaceQueryIntent.FUEL.value:
        s = _fmt_l(_get(state, "fuel_remaining_l"))
        return (f"Fuel is {s}." if s else "I don't have a fuel reading yet.", True)

    if key == RaceQueryIntent.FUEL_PREDICTED.value:
        fuel = _num(_get(state, "fuel_remaining_l"))
        per_lap = _num(_get(state, "fuel_per_lap_live")) or _num(_get(state, "fuel_per_lap_plan"))
        laps_rem = _num(getattr(clock, "laps_remaining", None)) if clock is not None else None
        if fuel is None or per_lap is None or laps_rem is None:
            return ("I can't predict the finish fuel yet — I need fuel, burn rate and laps "
                    "remaining.", True)
        predicted = fuel - per_lap * laps_rem
        if predicted >= 0:
            return (f"On this burn you finish with about {predicted:.1f} litres to spare.", True)
        return (f"On this burn you're about {abs(predicted):.1f} litres short — you need to save.", True)

    if key == RaceQueryIntent.LAPS_REMAINING.value:
        lr = getattr(clock, "laps_remaining", None) if clock is not None else None
        if lr is None:
            return ("I don't have the laps remaining — the race distance isn't confirmed yet.", True)
        return (f"{int(lr)} laps to go.", True)

    if key == RaceQueryIntent.TIME_REMAINING.value:
        t = _fmt_mmss(getattr(clock, "remaining_s", None) if clock is not None else None)
        return (f"{t} remaining." if t else "This isn't a timed race, or the clock isn't set yet.", True)

    if key == RaceQueryIntent.POSITION.value:
        p = _get(state, "position")
        return (f"You're P{int(p)}." if isinstance(p, int) and p > 0
                else "I don't have your position — GT7 isn't giving me one.", True)

    if key == RaceQueryIntent.DELTA.value:
        live = _num(_get(state, "lap_time_live_s"))
        plan = _num(_get(state, "lap_time_plan_s"))
        if live is None:
            return ("I don't have a clean lap time yet.", True)
        if plan is None:
            return (f"Your last lap was {live:.3f}. I've no reference pace to compare it to.", True)
        d = live - plan
        if abs(d) < 0.05:
            return (f"Right on the plan — {live:.3f}.", True)
        word = "up" if d < 0 else "down"
        return (f"You're {abs(d):.3f} {word} on the plan — last lap {live:.3f}.", True)

    if key == RaceQueryIntent.BEST_LAP.value:
        b = _fmt_s(_get(state, "best_lap_s") or _get(state, "lap_time_live_s"))
        return (f"Best lap {b}." if b else "No best lap recorded yet.", True)

    if key == RaceQueryIntent.TYRE.value:
        comp = getattr(stint, "compound", None) if stint is not None else None
        age = getattr(stint, "stint_age_laps", None) if stint is not None else None
        if not comp and age is None:
            return ("I don't have tyre data yet — GT7 doesn't always give me compound and age.", True)
        bits = []
        if comp:
            bits.append(str(comp))
        if isinstance(age, int):
            bits.append(f"{age} laps on them")
        return ("Tyres: " + ", ".join(bits) + ".", True)

    if key == RaceQueryIntent.PIT_WINDOW.value:
        req = _get(state, "required_stops")
        done = getattr(pit, "pit_stops_completed", None) if pit is not None else None
        if req is None:
            return ("I don't have a confirmed pit window yet — the plan needs fuel and distance "
                    "evidence first.", True)
        remaining = int(req) - int(done or 0)
        if remaining <= 0:
            return ("You've made your required stops — no more scheduled.", True)
        return (f"{remaining} more stop{'s' if remaining != 1 else ''} required by the plan.", True)

    if key == RaceQueryIntent.STRATEGY.value:
        rt = getattr(getattr(clock, "race_type", None), "value", None) if clock is not None else None
        req = _get(state, "required_stops")
        if req is None:
            return ("The strategy isn't settled yet — I need more fuel and pace evidence.", True)
        kind = ("a timed race" if rt == "timed" else "a lap race" if rt == "lap" else "the race")
        return (f"Plan for {kind}: {int(req)} stop{'s' if int(req) != 1 else ''}. "
                "I'll call any change at the end of a lap.", True)

    if key == RaceQueryIntent.PUSH.value:
        return ("Copy — push now. Watch your fuel and tyres.", True)
    if key == RaceQueryIntent.FUEL_SAVE.value:
        return ("Copy — save fuel: short-shift and lift earlier into the slow corners.", True)
    if key == RaceQueryIntent.REPEAT.value:
        return ((str(last_answer) if last_answer else "Nothing to repeat."), True)
    if key == RaceQueryIntent.MUTE.value:
        return ("Going quiet — call me when you need me.", True)

    return ("I can't answer that one.", True)
