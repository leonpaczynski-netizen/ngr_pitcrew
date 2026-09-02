"""Reading GT7's wear gauge off the capture, and owning the recording.

**Extracted from `controller.py` on 29 Aug 2026**, the second cut after the
rig. `telemetry/hud.py` is the instrument - it finds the gauge on a canvas
nobody calibrated, decides whether four bars are a reading, and holds the rule
for whether one reading can follow another on a real set of tyres. **This is
the session around it**: when to build the sampler, when to reset it, what to
do with a reading on a worker thread, and the OBS recording whose start time
is the only thing that makes a replay alignable afterwards.

### The pit wall rides the same frame

`race/pit_wall.py` reads the leaderboard, and it does it on the frame this
sampler has already grabbed rather than grabbing its own. The grab is
vsync-bound at about 16.6 ms whatever its size and it does not compose, so a
second sampler would halve the gauge's rate to watch a board that changes once
a lap. `on_frame` is that seam, and every failure inside it is swallowed:
nothing riding along may cost the gauge a reading.

It matters that it is live rather than a post-race pass. **The pit columns mark
the car standing in the box at that instant** - measured over a whole race, a
driver who stopped five minutes ago is indistinguishable on screen from one who
never stopped - so entry fuel exists only while the watcher is running.

### Four things it hands out, and they are the whole interface

The controller consumes exactly four values, from three different places - the
lap handler, the race-event handler and the PTT snapshot - and they were four
loose attributes on a five-thousand-line class:

* `latest_wear()` - what the gauge last transcribed, and which lap it was
* `take_blind_note()` - the gauge having gone blind, said once
* `note_lap(lap_id, lap_num)` - so a reading can be attributed to a lap
* `request(lap_id)` - ask for a reading at this crossing

### Two threads, and no lock

The sampler calls back on its own worker. `_write_wear` and `_status` run
there and do nothing but write plain attributes; the Qt side only ever reads
them. **A lock here would be a lock a lap handler could wait on**, and a
reader that catches the pair mid-update sees a reading against the previous
lap - which `RaceState.note_wear` already declines as a repeat.

### Why `new_session` exists, and what it cost that it did not

`LiveWearSampler.new_session` was written, documented, and called from a test
file and nowhere else. The sampler is cached and torn down only at app exit,
so every piece of its state crossed session boundaries - including the
comparison baseline every later reading is judged against, and the lap-id map.
At Fuji the first race crossing filed session 87's practice reading, on a
different set of tyres fitted twenty minutes earlier, against a race lap that
had not happened; the engineer then said "FR 29" out loud on lap 2, in the
register reserved for measured numbers.

CLAUDE.md standing rule 11 is on file for that: state that outlives a session
is read as if it belongs to this one.

### Nothing here may reach the race path

Built on first use, so a driver who never turns it on never opens a socket.
Every failure inside it is logged and swallowed. The lap is recorded whatever
the gauge does.
"""
from __future__ import annotations

import datetime

from pitcrew.diagnostics import log
from pitcrew.store.db import WEAR_HUD_VIDEO

# How many lap ids to remember when attributing a reading. The sampler answers
# a crossing or two later, never more, so this only has to outlive the lag.
LAP_MEMORY = 8


class HudSession:
    """The live gauge reader and the OBS recording, for one session."""

    def __init__(self, *, settings, store) -> None:
        # A getter, for the same reason `RigSupervisor` takes one:
        # `save_settings` REBINDS the settings object rather than mutating it,
        # so anything holding the one it was built with reads the settings as
        # they were when the app opened.
        self._settings = settings if callable(settings) else (lambda: settings)
        self.store = store
        self._sampler = None
        self._lap_nums: dict[int, int] = {}
        self._wear_now: dict | None = None
        self._wear_now_lap: int | None = None
        self._blind_note: str | None = None
        self._video_started = False
        # The pit wall, if one has asked to ride along. Read on the sampler's
        # worker thread and written on the Qt one - a plain attribute, like
        # everything else crossing that boundary here, because a lock here is
        # a lock a lap handler could wait on.
        self._wall = None
        self._wall_lap = None

    @property
    def settings(self):
        return self._settings()

    # ------------------------------------------------------- what it hands out

    def latest_wear(self) -> tuple[dict | None, int | None]:
        """What the gauge last transcribed, and the lap it describes.

        `(None, None)` after the gauge goes blind - **cleared, not left
        standing.** It was only ever written on a good reading and never
        expired, so a blind gauge left the radio quoting a transcription many
        laps old as though it were current.
        """
        return self._wear_now, self._wear_now_lap

    def take_blind_note(self) -> str | None:
        """The gauge having gone blind, once. Cleared as it is taken.

        Said rather than logged: he raced Road Atlanta believing the
        instrument was watching while it answered six of twenty-two crossings.
        """
        note, self._blind_note = self._blind_note, None
        return note

    def note_lap(self, lap_id: int, lap_num: int) -> None:
        """Remember which lap a pending reading will belong to."""
        self._lap_nums[lap_id] = lap_num
        while len(self._lap_nums) > LAP_MEMORY:
            self._lap_nums.pop(next(iter(self._lap_nums)))

    def request(self, lap_id: int) -> bool:
        """Ask for a reading at this crossing. False when the reader is off."""
        sampler = self.sampler()
        if sampler is None:
            return False
        sampler.request(lap_id)
        return True

    def sampler(self):
        """The live gauge reader, built on first use, or None if it is off.

        **Nothing about it may reach the race path.** It is constructed here
        rather than at start-up so that a driver who never turns it on never
        opens a socket, and every failure inside it is logged and swallowed -
        the lap is recorded whatever the gauge does.
        """
        if not self.settings.hud_wear_enabled:
            return None
        existing = self._sampler
        if existing is not None:
            return existing
        from pitcrew.settings import HUD_SOURCE_SCREEN
        from pitcrew.telemetry.hud import (LiveWearSampler, ObsSource,
                                           ScreenSource)

        if self.settings.hud_source == HUD_SOURCE_SCREEN:
            # Reads an OBS projector window off the desktop. No socket is
            # opened at all, which is also why nothing here can hang on one.
            source = ScreenSource()
        else:
            source = ObsSource(self.settings.obs_host, self.settings.obs_port,
                               self.settings.obs_password)
        interval = float(self.settings.hud_sample_interval_s or 0.0)
        sampler = LiveWearSampler(source, self._write_wear,
                                  on_status=self._status,
                                  interval_s=interval,
                                  on_frame=self._pass_frame)
        sampler.start()
        log("pitcrew").info(
            "hud-wear: %s source, %s", self.settings.hud_source,
            f"sampling every {interval:g}s" if interval
            else "sampling at each crossing only")
        self._sampler = sampler
        return sampler

    # ------------------------------------------------------------- pit wall

    def watch_board(self, wall, *, lap_of=None) -> None:
        """Have the pit wall read every frame the gauge grabs.

        `lap_of` is called with no arguments and returns our current lap, or
        None. It is a callable rather than a number because this runs on the
        sampler's worker thread, at whatever moment the grab returns.
        """
        self._wall = wall
        self._wall_lap = lap_of
        # **Ask for the whole screen.** With the projector at exactly the
        # calibrated canvas the sampler grabs only the gauge rectangle, and
        # there is no leaderboard in an 82x76 crop - so a wall attached to that
        # configuration would see nothing, on every frame, in silence.
        sampler = self._sampler
        source = getattr(sampler, "_source", None) if sampler else None
        if source is not None and hasattr(source, "whole"):
            source.whole = True

    def stop_watching_board(self) -> None:
        self._wall = None
        self._wall_lap = None
        sampler = self._sampler
        source = getattr(sampler, "_source", None) if sampler else None
        if source is not None and hasattr(source, "whole"):
            source.whole = False

    def _pass_frame(self, frame) -> None:
        """Worker thread. Hand the grabbed frame to the pit wall.

        Swallows everything: the gauge is the reason the grab happened and a
        passenger must never cost it a reading. `PitWall.see` also catches its
        own failures, so this is a second belt on purpose.
        """
        wall = self._wall
        if wall is None:
            return
        lap = None
        if self._wall_lap is not None:
            try:
                lap = self._wall_lap()
            except Exception:
                lap = None
        try:
            wall.see(frame, lap=lap)
        except Exception:
            log("pitcrew").exception("pit-wall: frame not seen")

    def _status(self, reading) -> None:
        """Worker thread. What the sampler wants the driver to know.

        **Only refusals arrive here as news.** A good reading already reaches
        the race through `_write_wear`; this is the other half - the gauge
        having gone blind, which used to be a log line and nothing else. He
        raced Road Atlanta believing the instrument was watching while it
        answered six of twenty-two crossings.

        **No Qt from this thread.** Same rule as `_write_wear`: a plain
        attribute write, picked up by the Qt side at the next crossing. A
        `set_status` call from here is the cross-thread defect the PTT answer
        path already had to have fixed once.

        **And it expires the stale reading.** `_wear_now` is only ever written
        on a good reading and was never cleared, so a blind gauge left the
        radio quoting a transcription many laps old as though it were current.
        A wear number nobody can refresh is exactly the zero-that-means-missing
        CLAUDE.md refuses.
        """
        if reading is None or reading.ok:
            return
        self._wear_now = None
        self._wear_now_lap = None
        self._blind_note = reading.reason

    def _write_wear(self, lap_id: int, wear: dict) -> None:
        """Worker thread. Writes the reading and nothing else.

        `set_lap_wear` already refuses to let a video reading overwrite one the
        driver gave: CLAUDE.md makes his report primary evidence and this
        corroboration, so where the two disagree the disagreement stays visible
        instead of being settled by whichever arrived last.
        """
        # Kept for the radio as well as the store: "how are my tyres" is asked
        # mid-lap and cannot wait for the lap to be written and read back.
        present = {c: wear.get(c) for c in ("fl", "fr", "rl", "rr")
                   if wear.get(c) is not None}
        self._wear_now = present or None
        # **And which lap it describes**, for the measured wear call. Two plain
        # attribute writes rather than a lock: this thread only ever writes and
        # the Qt thread only ever reads, and a reader that catches the pair
        # mid-update sees a reading against the previous lap - which
        # `RaceState.note_wear` already declines as a repeat. A lock here would
        # be a lock a lap handler could wait on.
        self._wear_now_lap = self._lap_nums.get(lap_id)
        try:
            self.store.set_lap_wear(
                lap_id, wear.get("fl"), wear.get("fr"),
                wear.get("rl"), wear.get("rr"), source=WEAR_HUD_VIDEO)
        except Exception as exc:                             # noqa: BLE001
            log("hud").warning("could not store lap %s wear: %s", lap_id, exc)

    def new_session(self) -> None:
        """Tell the gauge reader a new session has started.

        **`LiveWearSampler.new_session` existed, documented why it was needed,
        and had no caller in the app at all** - only two lines in
        `tests/test_hud_blind_gauge.py`. The sampler is cached on this
        controller and torn down only in `shutdown`, so without this every
        piece of state it holds crosses session boundaries: the one-shot
        "I cannot see the gauge" announcement, and - worse - the comparison
        baseline every later reading is judged against. A race then opens
        measuring its fresh set against whatever practice left behind.

        Resets an existing sampler only. Building one here would open a socket
        at session start for a driver who has the reader switched on but never
        crosses a line, which is the cost `sampler` is lazy to avoid.
        """
        sampler = self._sampler
        if sampler is not None:
            sampler.new_session()
        # **The lap-id map outlives the session too, and it leaked a practice
        # wear figure into a race.** `_write_wear` looks a lap_id up here
        # to decide which lap a reading belongs to; the ids carried over, so
        # at the Fuji race's first crossing the controller filed session 87's
        # gauge reading - FL 19 / FR 29 / RL 29 / RR 23, a different set of
        # tyres fitted twenty minutes earlier - against race lap 6, a lap that
        # had not happened. The engineer then said "FR 29." out loud on lap 2,
        # in the register `colour.py` reserves for measured numbers.
        self._lap_nums.clear()
        self._wear_now_lap = None
        self._blind_note = None

    def stop(self) -> None:
        sampler, self._sampler = self._sampler, None
        if sampler is not None:
            sampler.stop()

    def start_video(self, session_id: int | None) -> None:
        """Ask OBS to record, and write down the wall clock at second zero.

        **The zero is the whole point.** With it, a lap's position in the
        capture is `recorded_at - video_started_at`; without it the offline
        tool has to be handed an offset by hand and admits its estimate is a
        few seconds early.

        Silent on every failure. A recording is a convenience and a session is
        not, so nothing here may stop one opening.
        """
        if not self.settings.obs_record_sessions or session_id is None:
            return
        from pitcrew.telemetry.hud import ObsSource

        source = ObsSource(self.settings.obs_host, self.settings.obs_port,
                           self.settings.obs_password)
        started, why = source.start_recording()
        if started is None:
            log("session").info("could not start the OBS recording: %s", why)
            return
        if not started:
            # **Already running, so the app does not own it and cannot know
            # its zero.** Recording nothing is better than recording a zero
            # that is wrong by however long it had been going.
            log("session").info(
                "OBS was already recording - this session gets no video zero, "
                "because the app did not start the capture and cannot know "
                "where in it second zero fell")
            return
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        self.store.set_session_video(session_id, path=None,
                                     started_at=stamp)
        self._video_started = True
        log("session").info("OBS recording started, video zero at %s", stamp)

    def stop_video(self, session_id: int | None) -> None:
        """Stop the recording this app started, and file where OBS put it.

        **Never stops one it did not start** - `ObsSource.stop_recording`
        already refuses, and `_video_started` is the app's own half of the
        same rule.
        """
        if not getattr(self, "_video_started", False):
            return
        self._video_started = False
        from pitcrew.telemetry.hud import ObsSource

        source = ObsSource(self.settings.obs_host, self.settings.obs_port,
                           self.settings.obs_password)
        path, why = source.stop_recording()
        if path is None:
            log("session").info("OBS recording not stopped cleanly: %s", why)
            return
        if session_id is not None:
            # **The zero was written at the start and must survive.** Only the
            # path is new here, so it is read back and passed through rather
            # than left to default to None - which would throw away the one
            # thing this whole path exists to record.
            row = self.store.get_session(session_id) or {}
            self.store.set_session_video(
                session_id, path=path,
                started_at=row.get("video_started_at"))
        log("session").info("OBS recording written to %s", path)
