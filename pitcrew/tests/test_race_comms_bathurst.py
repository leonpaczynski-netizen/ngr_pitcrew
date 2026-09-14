"""Bathurst Rd7, 14 Sep 2026 (session 176), laps 1-19: George's volunteered radio.

The driver, afterwards: *"want more comms from him about what is going on in
the race."* This replays the whole race through the coordinator from the
checked-in record (`fixtures/race_comms_s176.json`, poured from the database
by `tools/extract_race_comms_fixture.py`): the approved plan and the event's
stop rule, every lap crossing with GT7's own figures, our stop, all 900 gap
readings at the moment the pit wall took them, and every rival visit - and
prints what he would have heard, with the seconds of speech in each lap.

### What is reconstructed rather than read, and why

* **The position byte between crossings.** The packet stream is not stored;
  `laps.position` gives the place at each crossing and the call ledger the
  moments it moved (each place call less its eight-second hold). Simplified
  exactly as `test_bathurst_rival_comms` simplifies laps 9-14.
* **The offs.** Times from the ledger's "You're back on it" calls less the
  settle, durations from `laps.off_track_s`.
* **Rival visits** enter when the wall's filing bar would have confirmed them
  and leave when their stop was filed - `test_bathurst_rival_comms.VISITS`.
* **No board.** `board_positions` holds, per lap, each name's LAST row index
  ever seen - sticky, windowed and split across handles (38 of 51 snapshots
  on file hold a place twice) - so it is not a frame's board and cannot be
  replayed as one. The championship call therefore has nothing to place a
  rival with, and says nothing; the stop picture has the lane alone.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pitcrew.engineer import phrase_manifest as manifest
from pitcrew.engineer import voice as voice_module
from pitcrew.race import news as news_module
from pitcrew.race.calls import GAPS, PACE, POSITION, STOPS_PICTURE, WATCHED
from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.race.pit_wall import Entered
from pitcrew.telemetry.recorder import SAMPLE_HZ
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent

from .test_bathurst_rival_comms import CONFIRM_AFTER_S, FUEL_IN, PARTIAL, VISITS

FIXTURE = Path(__file__).parent / "fixtures" / "race_comms_s176.json"


def clock(text: str) -> float:
    h, m, s = (int(x) for x in text.split(":"))
    return h * 3600 + m * 60 + s


@lru_cache(maxsize=1)
def record() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def race_s(text: str) -> float:
    """A wall-clock moment on the race clock."""
    return clock(text) - record()["green_clock_s"]


# The place byte, from the ledger: each place call's moment less its hold.
POSITIONS = [("20:20:07", 10), ("20:22:42", 11), ("20:23:35", 10),
             ("20:30:32", 9), ("20:30:49", 8), ("20:31:13", 7),
             ("20:35:25", 8), ("20:37:13", 7), ("20:38:30", 10),
             ("20:39:00", 9), ("20:41:59", 8), ("20:44:22", 6),
             ("20:46:20", 8), ("20:47:52", 11), ("20:55:20", 12)]
IN_PIT = ("20:46:30", "20:47:50")
# (start, seconds): the ledger's "back on it" less the 12 s settle, and the
# lap's own off-track seconds.
OFFS = [("20:22:01", 8.6), ("20:35:21", 2.6), ("20:41:31", 5.0),
        ("20:43:40", 4.2), ("20:50:49", 4.0), ("20:55:00", 20.5),
        ("20:58:35", 11.1), ("21:02:10", 4.0)]
# The brief's watch list that night.
WATCHED_RIVALS = ("Magical daddy", "Rocky", "CruisingChaos")


@dataclass
class _Packet:
    current_position: int
    cars_in_race: int = 13
    surface_types: tuple = ("T", "T", "T", "T")
    laps_completed: int | None = None


def _at(series, second):
    value = series[0][1]
    for start, v in series:
        if second >= start:
            value = v
    return value


@dataclass
class Heard:
    race_s: float
    lap: int                  # the lap being driven, as his screen shows it
    how: str                  # "line" (a crossing) or "mid-lap"
    kind: str | None
    text: str

    @property
    def clock(self) -> str:
        total = int(record()["green_clock_s"] + self.race_s)
        return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def replay() -> tuple[RaceCoordinator, list[Heard], list]:
    data = record()
    event = data["event"]
    stints = data["stints"]
    plan = {"stops": len(stints) - 1, "stints": stints,
            "binding_constraint": "fuel",
            "pit_laps": [s["start_lap"] + s["laps"] - 1 for s in stints[:-1]]}
    co = RaceCoordinator(
        plan, pit_loss_s=event["pit_loss_secs"],
        pit_loss_measured=event["pit_loss_source"] == "measured",
        refuel_rate_lps=event["refuel_rate_lps"],
        mandatory_stops=event["mandatory_stops"])
    assert co.arm(None, None)
    co.state.laps_total = event["race_laps"]
    co.state.field_size = 13
    co.state.watched_rivals = frozenset(n.lower() for n in WATCHED_RIVALS)
    heard: list[Heard] = []
    verdicts: list[tuple[int, str, str]] = []

    def keep(call, second, how):
        if call is not None and call.spoken():
            heard.append(Heard(second, co.state.lap + 1, how, call.kind,
                               call.spoken()))

    keep(co.handle(SessionEvent(EventKind.RACE_STARTED,
                                {"laps_in_race": event["race_laps"]})),
         0.0, "line")

    crossings = {lap["lap_num"]: lap["race_elapsed_s"] for lap in data["laps"]}
    laps = {lap["lap_num"]: lap for lap in data["laps"]}
    positions = [(race_s(when), place) for when, place in POSITIONS]
    in_pit = (race_s(IN_PIT[0]), race_s(IN_PIT[1]))
    offs = [(race_s(when), race_s(when) + seconds) for when, seconds in OFFS]
    enter_at = {int(race_s(second)) + CONFIRM_AFTER_S: (d, lap, ahead)
                for d, lap, second, _, ahead in VISITS}
    leave_at = {int(race_s(filed)): d for d, _, _, filed, _ in VISITS}
    reads = sorted(data["gap_reads"], key=lambda r: r["race_s"])
    next_read = 0
    was_in_pit = False
    end = int(crossings[max(crossings)]) + 5

    for second in range(0, end):
        for num, at in crossings.items():
            if second <= at < second + 1:
                row = laps[num]
                lap = Lap(lap_num=num, lap_time_ms=row["lap_time_ms"],
                          best_lap_ms=row["lap_time_ms"], delta_ms=0,
                          fuel_start=row["fuel_start"],
                          fuel_end=row["fuel_end"],
                          fuel_used=row["fuel_used"],
                          position=row["position"],
                          is_pit_lap=bool(row["is_pit_lap"]),
                          is_out_lap=bool(row["is_out_lap"]),
                          laps_completed=row["laps_completed"])
                if row["excluded"] and row["exclusion_reason"] == "incident":
                    co.note_incident()
                keep(co.handle(SessionEvent(EventKind.LAP_COMPLETED,
                                            {"lap": lap})), at, "line")
                verdicts.extend(_pace_at_the_line(co, num))
        pit_now = in_pit[0] <= second < in_pit[1]
        if pit_now and not was_in_pit:
            co.handle(SessionEvent(EventKind.PIT_ENTRY, {}))
        if was_in_pit and not pit_now:
            co.handle(SessionEvent(EventKind.PIT_EXIT, {"tyres_changed": True}))
        was_in_pit = pit_now
        if second in enter_at:
            driver, lap, ahead = enter_at[second]
            co.note_rival_entered(Entered(
                driver=driver, driver_id=0, lap=lap, fuel_in_l=FUEL_IN[driver],
                partial=driver in PARTIAL, ahead_at_entry=ahead))
        if second in leave_at:
            co.state.lane.left(leave_at[second], lap=co.state.lap)
        off = any(a <= second < b for a, b in offs)
        packet = _Packet(current_position=_at(positions, second),
                         surface_types=("G",) * 4 if off else ("T",) * 4)
        for frame in range(int(SAMPLE_HZ)):
            moment = second + frame / SAMPLE_HZ
            while next_read < len(reads) and reads[next_read]["race_s"] <= moment:
                read = reads[next_read]
                subject = read["subject"]
                name = None if subject is None or str(subject).isdigit() \
                    else subject
                co.note_gap_read(read["side"], read["gap_s"], subject=subject,
                                 name=name)
                next_read += 1
            keep(co.note_packet(packet), moment, "mid-lap")
    return co, heard, verdicts


def _pace_at_the_line(co, lap_num: int) -> list[tuple[int, str, str]]:
    """What the pace test said about each neighbour at this crossing - for
    the report, so a silent race shows what kept it silent."""
    from dataclasses import replace as copy

    from pitcrew.race.news import _lane_keys, pace_verdict

    news = co.news
    out = []
    for side in ("ahead", "behind"):
        trend = news._trends[side]
        if trend.subject is None:
            out.append((lap_num, side, "no car"))
            continue
        now_key = co.state.lap_now()
        dirty = frozenset(set(news._dirty)
                          | _lane_keys(co.state.lane, str(trend.subject),
                                       now_key))
        verdict, why = pace_verdict(copy(trend, seen=dict(trend.seen)), side,
                                    news._pace[side], dict(news._ours_s),
                                    now_key=now_key, dirty_keys=dirty)
        out.append((lap_num, side, f"{trend.subject}: " + (
            why if verdict is None else
            f"PASS {verdict.rate:+.2f} s/lap, +/-{verdict.half_width_s:.2f}")))
    return out


@lru_cache(maxsize=1)
def _pack_samples() -> dict:
    path = voice_module.PACK_ROOT / "en_GB-alan-medium" / voice_module.PACK_MANIFEST
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("clips") or {}


def speech_s(text: str) -> tuple[float, str]:
    """Seconds to say `text`: off the rendered pack where it holds every clip,
    else the measured live rate (`voice.LIVE_SECONDS_PER_CHAR`)."""
    spoken = voice_module.spoken_form(text)
    clips = _pack_samples()
    segments = manifest.segments_for(spoken) or ()
    if clips and segments and all(s in clips for s in segments):
        return (sum(clips[s]["samples"] for s in segments)
                / voice_module.PACK_SAMPLE_RATE, "pack")
    return len(spoken) * voice_module.LIVE_SECONDS_PER_CHAR, "live"


@lru_cache(maxsize=1)
def replayed():
    return replay()


def transcript() -> tuple[list[str], list[str]]:
    """The lines, and the per-lap speech table."""
    _, heard, _ = replayed()
    lines = []
    for h in heard:
        seconds, source = speech_s(h.text)
        lines.append(f"{h.clock}  L{h.lap:<2} {h.how:8} {seconds:4.1f}s "
                     f"{source:4}  {h.text}")
    laps = {lap["lap_num"]: lap for lap in record()["laps"]}
    table = ["lap  lap_s  news  news_s  line_s  news%"]
    for num in sorted(laps):
        mine = [h for h in heard if h.lap == num]
        news = [h for h in mine if h.how == "mid-lap"]
        news_s = sum(speech_s(h.text)[0] for h in news)
        line_s = sum(speech_s(h.text)[0] for h in mine if h.how == "line")
        lap_s = laps[num]["lap_time_ms"] / 1000.0
        table.append(f"{num:>3}  {lap_s:5.1f}  {len(news):>4}  {news_s:6.1f}  "
                     f"{line_s:6.1f}  {100 * news_s / lap_s:4.1f}%")
    return lines, table


def test_print_the_volunteered_transcript(capsys):
    lines, table = transcript()
    print("\n".join(lines))
    print("\n".join(table))
    _, _, verdicts = replayed()
    print("\n".join(f"L{lap:<2} {side:6} {why}"
                    for lap, side, why in verdicts))
    assert lines


def test_every_confirmed_stop_still_reaches_him_once():
    _, heard, _ = replayed()
    rival = [h.text for h in heard if re.search(r"\bboxed\b", h.text)]
    for driver, *_ in VISITS:
        assert len([t for t in rival if driver in t]) == 1, (driver, rival)


def test_the_gaps_are_said_and_a_handle_is_never_read_out():
    _, heard, _ = replayed()
    gaps = [h.text for h in heard if h.kind == GAPS]
    assert gaps
    assert not any("#" in text or "hash" in text for text in gaps)
    # Unnamed board clusters ("78", "82") are the car ahead and behind.
    assert any(text.startswith("The car ahead") for text in gaps)


def test_the_place_the_lane_made_is_the_stop_picture():
    """Lap 11, 20:44: Car #31 and Car #28 boxed from ahead of us, our stop
    still owed. That night: "P6 of 13. You've made 2 places." Now one call:
    the road place, the place after the stops, the assumption, and the word
    that the board could not confirm it."""
    _, heard, _ = replayed()
    p6 = [h for h in heard if h.text.startswith("P6 ")]
    assert [h.text for h in p6] == [
        "P6 on the road. Effectively P8 after the stops. If they stop once. "
        "Unconfirmed."]
    assert p6[0].kind == STOPS_PICTURE
    assert not any("Not passes" in h.text for h in heard)


def test_volunteered_lines_keep_their_spacing():
    _, heard, _ = replayed()
    mid = [h for h in heard if h.how == "mid-lap"
           and not h.text.startswith("You're back on it")]
    for a, b in zip(mid, mid[1:]):
        assert b.race_s - a.race_s >= RaceCoordinator.NEWS_SPACING_S - 1e-6, \
            (a.text, b.text)
    for kind in (GAPS, PACE, WATCHED, STOPS_PICTURE, POSITION):
        times = [h.race_s for h in mid if h.kind == kind]
        for a, b in zip(times, times[1:]):
            assert b - a >= RaceCoordinator.MID_LAP_SPACING_S - 1e-6, kind


def test_no_championship_place_is_guessed_without_a_board():
    """Rule 3: the stored board is not a frame's board (module docstring), so
    no watched rival is given a place."""
    _, heard, _ = replayed()
    assert not [h for h in heard if h.kind == WATCHED]


def test_every_unnamed_volunteered_line_plays_from_declared_clips():
    """Bathurst missed the pack on 32 of 46 lines. A new family that did the
    same would be a pause before every gap line of the next race."""
    _, heard, _ = replayed()
    clips = set(manifest.clips())
    unnamed = [h.text for h in heard
               if h.kind in (GAPS, STOPS_PICTURE)
               and (h.text.startswith("The car") or h.text.startswith("P"))]
    assert unnamed
    for text in unnamed:
        segments = manifest.segments_for(text)
        assert segments and all(s in clips for s in segments), (text, segments)


# ------------------------------------------------ one car, or several

_FIGURE = re.compile(r"(ahead|behind), (under a tenth|\d+\.\d|\d+ seconds)\.")


def spoken_gaps(heard) -> list[tuple[float, str, float, float]]:
    """`(race_s, side, figure, rounding)` for every gap figure he heard."""
    out = []
    for h in heard:
        if h.kind != GAPS:
            continue
        for side, figure in _FIGURE.findall(h.text):
            if figure == "under a tenth":
                value, rounding = 0.05, 0.05
            elif figure.endswith("seconds"):
                value, rounding = float(figure.split()[0]), 0.5
            else:
                value, rounding = float(figure), 0.05
            out.append((h.race_s, side, value, rounding))
    return out


def slot_events() -> list[float]:
    """Every moment on the race clock that could put another car in the
    ahead or behind box, or move a gap by what it cost us: the place byte's
    changes, each rival entering and leaving the lane, our offs, our stop -
    taken from this module's reconstruction, not from the coordinator."""
    times = [race_s(when) for when, _ in POSITIONS[1:]]
    times += [race_s(second) + CONFIRM_AFTER_S for _, _, second, _, _ in VISITS]
    times += [race_s(filed) for _, _, _, filed, _ in VISITS]
    times += [race_s(when) for when, _ in OFFS]
    times += [race_s(when) for when in IN_PIT]
    return sorted(times)


def implausible_jumps(heard, *, explained: bool = True) -> list[tuple]:
    """Consecutive figures heard on one side that no car's gap moves between
    in the time between them (`news.continuous`, plus what saying a figure
    rounds off), with - where `explained` - nothing in `slot_events` inside
    `news.EXPLAIN_LAG_S` before the first figure up to the second."""
    events = slot_events()
    jumps, last = [], {}
    for at, side, value, rounding in spoken_gaps(heard):
        before, last[side] = last.get(side), (at, value, rounding)
        if before is None:
            continue
        then, was, was_rounding = before
        allowed = (news_module.jump_allowed_s(at - then)
                   + was_rounding + rounding)
        if abs(value - was) <= allowed:
            continue
        if explained and any(then - news_module.EXPLAIN_LAG_S < t <= at
                             for t in events):
            continue
        jumps.append((side, round(then), was, round(at), value))
    return jumps


def test_no_gap_he_hears_jumps_with_nothing_on_the_circuit_to_explain_it():
    """Replayed before the guard: "The car ahead, 0.5." then, thirty seconds
    later, "The car ahead, 9 seconds." - the board's cluster "78" holding the
    ahead box across a pass. Each figure he hears is now continuous with the
    last on its side, or has a place change, a stop or an off between."""
    _, heard, _ = replayed()
    assert spoken_gaps(heard)
    assert implausible_jumps(heard) == []


STRAIGHTS = Path(__file__).parent / "fixtures" / "straights_mount_panorama.json"


def test_no_volunteered_line_is_longer_than_the_longest_straight():
    """Replayed before: "Magical daddy has boxed on 32 litres. That is about
    67 seconds standing, on our burn." - 10.5 s of live synthesis, and laps 11
    and 12 carried 37.8 and 35.0 s of mid-lap speech. No mid-lap line may now
    outrun the lower quartile of Mount Panorama's longest straight, and a
    rival's stop is the fact, said in under four seconds."""
    windows = json.loads(STRAIGHTS.read_text(encoding="utf-8"))["windows"]
    longest_p25 = max(w["p25_s"] for w in windows)
    _, heard, _ = replayed()
    mid = [(h.text, speech_s(h.text)[0]) for h in heard if h.how == "mid-lap"]
    assert mid and all(seconds <= longest_p25 for _, seconds in mid), mid
    rival = [(h.text, speech_s(h.text)[0]) for h in heard
             if re.search(r"\bboxed\b", h.text)]
    assert rival and all(seconds <= 4.0 for _, seconds in rival), rival
    assert not any("standing" in text for text, _ in rival)


def test_a_pace_claim_carries_its_test():
    _, heard, _ = replayed()
    for h in heard:
        if h.kind == PACE:
            assert "Over 5 laps." in h.text


# ------------------------------------------------ through the voice's queue
#
# **15 Sep 2026, the driver: "George can speak at anytime."** With NEWS held
# for a straight (model-backed, else 4 s held), 24 of the 52 lines volunteered
# mid-lap on this race played and 28 went stale waiting: Mountain to Conrod
# is about a minute. With no gate a line waits only behind other speech, and
# this replays exactly that - every line, crossing and mid-lap, offered to the
# voice's own queue (`voice._LineQueue`: its classes, its replacement of a
# queued same-kind line, its per-kind staleness) at the moment it was
# composed, and played one at a time for as long as the pack takes to say it.

@dataclass
class Through:
    heard: Heard
    outcome: str              # "played", "stale", or why it was dropped
    seconds: float            # how long it takes to say
    wait_s: float | None      # queued to started, where it played


def through_the_voice(heard) -> list[Through]:
    """What the voice does with `heard`, on the race clock."""
    queue = voice_module._LineQueue()
    of: dict[int, Heard] = {}
    out: dict[int, Through] = {}
    free_at = 0.0

    def settle(line, outcome, wait_s=None):
        h = of[id(line)]
        out[id(h)] = Through(h, outcome, speech_s(h.text)[0], wait_s)

    def play_until(moment: float) -> None:
        nonlocal free_at
        while queue.qsize() and free_at <= moment:
            line, stale = queue.take(free_at)
            for old, _age in stale:
                settle(old, "stale")
            if line is None:
                return
            settle(line, "played", free_at - line.queued_at)
            free_at += speech_s(line.text)[0]

    for h in sorted(heard, key=lambda h: h.race_s):
        play_until(h.race_s)
        line = queue.line(h.text, h.kind, queued_at=h.race_s)
        of[id(line)] = h
        for dropped, why in queue.offer(line):
            settle(dropped, why)
        free_at = max(free_at, h.race_s)
    play_until(float("inf"))
    return [out[id(h)] for h in heard]


@lru_cache(maxsize=1)
def voiced() -> list[Through]:
    return through_the_voice(replayed()[1])


def test_print_what_the_voice_plays():
    lines = voiced()
    mid = [t for t in lines if t.heard.how == "mid-lap"]
    played = [t for t in mid if t.outcome == "played"]
    stale = [t for t in mid if t.outcome == "stale"]
    other = [t for t in mid if t.outcome not in ("played", "stale")]
    waits = [t for t in lines if t.wait_s is not None]
    longest = max(waits, key=lambda t: t.wait_s)
    print(f"mid-lap lines: {len(mid)}  played {len(played)}  "
          f"stale {len(stale)}  otherwise dropped {len(other)}")
    for t in stale + other:
        print(f"  {t.heard.clock} {t.outcome}: {t.heard.text}")
    print(f"longest queue wait: {longest.wait_s:.1f} s - "
          f"{longest.heard.clock} {longest.heard.text!r}")
    print("lap  lap_s  spoken_s  mid_s  line_s  spoken%  max_wait_s")
    laps = {lap["lap_num"]: lap for lap in record()["laps"]}
    for num in sorted(laps):
        mine = [t for t in lines if t.heard.lap == num
                and t.outcome == "played"]
        spoken = sum(t.seconds for t in mine)
        mid_s = sum(t.seconds for t in mine if t.heard.how == "mid-lap")
        lap_s = laps[num]["lap_time_ms"] / 1000.0
        wait = max((t.wait_s for t in mine), default=0.0)
        print(f"{num:>3}  {lap_s:5.1f}  {spoken:8.1f}  {mid_s:5.1f}  "
              f"{spoken - mid_s:6.1f}  {100 * spoken / lap_s:6.1f}%  "
              f"{wait:10.1f}")
    assert mid


def test_with_no_straight_gate_nothing_volunteered_goes_stale():
    """Before the driver's decision: 24 of 52 played, 28 stale. Now every
    line volunteered mid-lap is said, and none waits long enough behind other
    speech to be dropped."""
    mid = [t for t in voiced() if t.heard.how == "mid-lap"]
    assert len(mid) == 52
    assert [t.heard.text for t in mid if t.outcome != "played"] == []
    for t in voiced():
        if t.wait_s is not None:
            assert t.wait_s <= voice_module.stale_after_s(t.heard.kind)
