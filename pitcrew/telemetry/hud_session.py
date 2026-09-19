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
import threading
import time
from collections import deque
from dataclasses import dataclass

from pitcrew.diagnostics import log
from pitcrew.settings import HUD_SOURCE_SCREEN
from pitcrew.store.db import WEAR_HUD_VIDEO

# The WET light's window: reads inside this many seconds, at least this many
# readable, the last `HYGRO_KEEP` kept. With the driver's 2 s grab interval that
# is the last ten seconds and three readings to say anything at all.
HYGRO_WINDOW_S = 10.0
HYGRO_MIN_READS = 3
HYGRO_KEEP = 8
# The compound label: this many agreeing reads inside the window, and not one
# read of a different code among them, before the tyre counts as known.
COMPOUND_WINDOW_S = 30.0
COMPOUND_MIN_AGREE = 3
# The car icon's bumper arcs (`telemetry/hud_damage.py`): contact is
# `DAMAGE_MIN_LIT` lit reads of one arc inside `DAMAGE_WINDOW_S`; "no contact"
# needs `DAMAGE_MIN_READS` readable grabs with not one red pixel on that arc
# (621 clean frames carried none); anything between is None. Sized for the
# driver's 2 s grab; `DAMAGE_KEEP` holds a full window down to a 0.5 s grab.
# **Off at crossing-only sampling** (`hud_sample_interval_s = 0`, the default):
# one read a lap never reaches `DAMAGE_MIN_READS`, so every answer is None.
DAMAGE_WINDOW_S = 20.0
DAMAGE_MIN_READS = 3
DAMAGE_MIN_LIT = 2
DAMAGE_KEEP = 40

# How long a pre-flight grab may take before it is called a failure.
#
# **The default source is the OBS websocket, not the projector**, and a grab
# there is a connect, an identify and a whole-canvas screenshot - measured at
# about two seconds, and `ObsSource._request` re-arms its receive timeout on
# every message, so a socket that chatters without answering never returns at
# all. This runs on the Qt thread inside a button handler, so it is bounded.
#
# **5.0 was too short and it blocked the driver minutes before a race.** It was
# chosen for the websocket path and never costed against the SCREEN path, where
# the first grab in a fresh worker thread pays cold-start: importing win32gui
# and mss, creating a per-thread mss instance, and enumerating every top-level
# window. On 6 Sep 2026 that exceeded 5 s three times running and told him
# nothing was being captured while his projector was open in front of him.
# 12 s is past that cold start and still finite for a genuinely sick OBS.
PREFLIGHT_TIMEOUT_S = 12.0
# How long closing a session waits for a `start_video` still in flight. OBS
# answers in well under this; past it the worker stops what it started.
VIDEO_START_WAIT_S = 5.0


@dataclass(frozen=True)
class GaugeCheck:
    """What one pre-flight grab found, and what may honestly be said about it.

    `ok` is "something was captured", **not** "the gauge will read" - see
    `HudSession.preflight` for why those are different and `caveat` for the
    sentence that keeps the dialog honest about it.
    """

    ok: bool
    reason: str | None = None
    # "projector" or "OBS" - the message has to name the thing he must go and
    # fix, and naming the wrong one has already cost a race night here.
    source: str = "OBS"
    enabled: bool = True
    # False where the check could not be run at all, as distinct from run and
    # failed. Unknown is not the same as absent - CLAUDE.md rule 3.
    checked: bool = True
    # Whether OBS is recording, so the gauge could be transcribed afterwards
    # with `tools/read_hud_wear.py`. None where it could not be told.
    recording: bool | None = None

    @property
    def headline(self) -> str:
        if self.source == "projector":
            return "No OBS projector window is being captured."
        return "The app cannot get a frame from OBS."

    @property
    def recovery(self) -> str:
        """What is still true about recovering the wear afterwards."""
        if self.recording is True:
            return ("OBS IS recording, so the gauge can be transcribed from "
                    "the recording afterwards with tools/read_hud_wear.py. "
                    "You would not lose the wear record - only the live "
                    "readings during the session.")
        if self.recording is False:
            return ("OBS is not recording either, so there would be nothing "
                    "to transcribe afterwards. GT7 broadcasts no wear "
                    "channel, so this session would simply have no wear "
                    "evidence.")
        return ("I could not tell whether OBS is recording, so I cannot say "
                "whether the wear could be transcribed afterwards.")

    @property
    def caveat(self) -> str:
        return ("This only checks that something is being captured. It cannot "
                "check the gauge itself - you are in a menu, so the gauge is "
                "not on screen yet.")

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
        # The settings the cached sampler was built from. A change to any of
        # them has to rebuild it - see `sampler`.
        self._sampler_key: tuple | None = None
        self._lap_nums: dict[int, int] = {}
        self._wear_now: dict | None = None
        self._wear_now_lap: int | None = None
        self._blind_note: str | None = None
        self._video_started = False
        # The session a `start_video` worker is starting OBS for, and the
        # worker. Written under the lock on both threads - see `stop_video`.
        self._video_lock = threading.Lock()
        self._video_session: int | None = None
        self._video_thread: threading.Thread | None = None
        # The pit wall, if one has asked to ride along. Read on the sampler's
        # worker thread and written on the Qt one - a plain attribute, like
        # everything else crossing that boundary here, because a lock here is
        # a lock a lap handler could wait on.
        self._wall = None
        self._wall_lap = None
        # The last few hygrometer reads, `(monotonic time, level or None)`,
        # appended on the worker thread and read on the Qt one. A bounded
        # deque: append and a snapshot copy are safe across the two without a
        # lock, which a lap handler must never wait on.
        self._hygro: deque = deque(maxlen=HYGRO_KEEP)
        self._compound: deque = deque(maxlen=HYGRO_KEEP)
        # `(monotonic time, front px, rear px, front lit, rear lit)` - the
        # read's own verdicts kept beside its counts, so "lit" is decided in
        # one place (`read_damage`). None for an unreadable grab.
        self._damage: deque = deque(maxlen=DAMAGE_KEEP)
        # The last answer per arc that was logged, so a change is logged once.
        self._contact_said: dict[str, bool | None] = {"front": None, "rear": None}

    @property
    def settings(self):
        return self._settings()

    # ------------------------------------------------------- what it hands out

    def wet_now(self, now: float | None = None) -> str | None:
        """The WET light: "wet", "mixed", "dry", or None when it cannot say.

        **The hygrometer is water under the car right now, not how wet the
        track is** (`telemetry/hygrometer.py`): a tunnel on a wet track reads
        empty for a second. So the light is the last few reads inside
        `HYGRO_WINDOW_S`, and needs `HYGRO_MIN_READS` of them - with the 2 s
        grab that is the last 10 s. Fewer, or all unreadable, is None: the
        board says "cannot see", never DRY.
        """
        from pitcrew.telemetry.hygrometer import WET_LEVEL

        now = time.monotonic() if now is None else now
        recent = [level for at, level in list(self._hygro)
                  if now - at <= HYGRO_WINDOW_S and level is not None]
        if len(recent) < HYGRO_MIN_READS:
            return None
        share = sum(1 for level in recent if level >= WET_LEVEL) / len(recent)
        if share >= 2 / 3:
            return "wet"
        if share <= 1 / 3:
            return "dry"
        return "mixed"

    def compound_now(self, now: float | None = None) -> str | None:
        """The compound the HUD label shows, once it is settled, or None.

        **Settled means agreed and undisputed**: `COMPOUND_MIN_AGREE` reads of
        one code in the last `COMPOUND_WINDOW_S`, and no read of another code
        among them. Unreadable grabs (menus, a crew in front of the car, a
        label this reader has no template for) neither count for nor against.
        A tyre attributed wrongly corrupts the wear model; a missing one is a
        gap, so this refuses on any doubt.
        """
        now = time.monotonic() if now is None else now
        codes = [code for at, code in list(self._compound)
                 if now - at <= COMPOUND_WINDOW_S and code is not None]
        if len(codes) < COMPOUND_MIN_AGREE or len(set(codes)) != 1:
            return None
        return codes[0]

    def contact_recent(self, now: float | None = None) -> dict[str, bool | None]:
        """Is the HUD showing recent contact on the front / rear bumper arc?

        **The icon, not the car's condition** (critic pass 1, rule 13): GT7
        clears the red on its own 90-135 s after contact with no stop, so False
        two minutes after a crash means "icon grey", never "undamaged".

        * True: `DAMAGE_MIN_LIT` lit reads of the arc in `DAMAGE_WINDOW_S`.
        * False: `DAMAGE_MIN_READS` readable grabs and **not one red pixel** on
          that arc - a clean icon carried none on 621 frames, so any red is
          evidence, not noise.
        * None otherwise - too few readable grabs, or some red below the bar.

        **Onset latency**: after the one front hit on file (lit from 1267 s)
        the arc read 0 px on most samples at first. Replayed at a 2 s grab it
        read **False until 1284 s - 17 s after the onset - then None, and first
        True at 1290 s, 23 s after it** (critic pass 2). A consumer that needs
        the moment of contact must not wait on this.
        """
        now = time.monotonic() if now is None else now
        recent = [entry[1:] for entry in list(self._damage)
                  if now - entry[0] <= DAMAGE_WINDOW_S and entry[1] is not None
                  and entry[2] is not None]

        def side(px: list[int], lit: list[bool]) -> bool | None:
            if sum(1 for value in lit if value) >= DAMAGE_MIN_LIT:
                return True
            if len(px) < DAMAGE_MIN_READS or any(value > 0 for value in px):
                return None
            return False

        return {"front": side([r[0] for r in recent], [r[2] for r in recent]),
                "rear": side([r[1] for r in recent], [r[3] for r in recent])}

    def damage_history(self) -> list[tuple]:
        """The car-icon reads kept, oldest first: `(monotonic time, front px,
        rear px, front lit, rear lit)`, px None for an unreadable grab. A
        snapshot copy - safe to walk on the Qt thread (`race/hud_alerts.py`)."""
        return list(self._damage)

    def hygro_history(self) -> list[tuple]:
        """The hygrometer reads kept, oldest first: `(monotonic time, level or
        None)`. A snapshot copy, like `damage_history`."""
        return list(self._hygro)

    def _note_damage(self, read) -> None:
        """Worker thread: one car-icon read from the grab just taken.

        **A frame's arc is logged when it turns lit and when it turns dim**
        (rule 10: log the accepts), so a debrief can audit what the history
        held. "dim" is one frame below the bar - inside an episode that is the
        pulse - never `contact_recent`'s False.
        """
        self._damage.append((time.monotonic(), read.front_px, read.rear_px,
                             read.front, read.rear))
        for name, lit in (("front", read.front), ("rear", read.rear)):
            if lit is None or lit == self._contact_said.get(name):
                continue
            if lit or self._contact_said.get(name):
                log("pitcrew").info("hud-damage: %s arc %s (%s px)", name,
                                    "lit" if lit else "dim",
                                    read.front_px if name == "front" else read.rear_px)
            self._contact_said[name] = lit

    def _note_compound(self, read) -> None:
        """Worker thread: one compound label read from the grab just taken."""
        self._compound.append((time.monotonic(), read.code))

    def _note_hygro(self, reading) -> None:
        """Worker thread: one hygrometer read from the grab just taken."""
        self._hygro.append((time.monotonic(), reading.level))

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

    def _source_key(self) -> tuple:
        """Everything about the settings that changes what gets read."""
        settings = self.settings
        return (settings.hud_source, settings.obs_host, settings.obs_port,
                settings.obs_password,
                float(settings.hud_sample_interval_s or 0.0))

    def build_source(self):
        """The screen source the gauge reads, per the settings.

        **One definition, because `preflight` has to test the SAME source the
        sampler will use.** A pre-flight that opened a different source would
        be checking something the session then does not do, which is worse
        than not checking at all - it would say "the gauge can see" about a
        path nothing reads from.
        """
        from pitcrew.settings import HUD_SOURCE_SCREEN
        from pitcrew.telemetry.hud import ObsSource, ScreenSource

        if self.settings.hud_source == HUD_SOURCE_SCREEN:
            # Reads an OBS projector window off the desktop. No socket is
            # opened at all, which is also why nothing here can hang on one.
            return ScreenSource()
        return ObsSource(self.settings.obs_host, self.settings.obs_port,
                         self.settings.obs_password)

    def preflight(self, *, timeout_s: float = PREFLIGHT_TIMEOUT_S):
        """Can anything be captured for the gauge right now? A `GaugeCheck`.

        **This exists because the failure is silent and total.** The sampler
        stands down about thirty seconds in and never recovers: session 126
        lost its whole wear record that way, and on 6 Sep 2026 session 133 lost
        its gauge because the driver forgot to open OBS, went out, and only
        found out afterwards. GT7 broadcasts no wear channel, so the gauge is
        the only instrument that measures it.

        ⚠️ **What this can and cannot prove, because the dialog it feeds must
        not overclaim.** It takes one grab. A grab that succeeds means
        *something was captured* - it does NOT mean the gauge will read:

        * `ScreenSource` captures the MONITOR the projector is on, not the
          window, so a projector sitting behind another window returns a full,
          healthy-looking frame. That is a measured failure - a stint sampled
          every two seconds for six minutes came back dark for exactly that
          reason (`hud.py`).
        * `find_projector` matches the word "projector" in any visible window
          title, so an editor or a browser tab can satisfy it.
        * At the moment he presses Start he is in a GT7 menu, so the gauge is
          not on screen at all and `locate_gauge` would return None. **The
          gauge itself cannot be tested at the only moment this check runs.**

        So this catches "nothing is being captured", which is the case that
        actually happened twice. It does not catch "the wrong thing is being
        captured", and `GaugeCheck.caveat` says so in the driver's own words.

        Never raises, and never blocks for long: on the default `obs` source a
        grab is a websocket round trip that has been measured at about two
        seconds and whose response wait re-arms on every message, so it is run
        with a hard timeout - this is called from a button handler on the Qt
        thread and the gauge must never be able to freeze the app.
        """
        settings = self.settings
        kind = ("projector" if settings.hud_source == HUD_SOURCE_SCREEN
                else "OBS")
        if not settings.hud_wear_enabled:
            # Not a nag: turning it off is a choice. But it IS the other way
            # to end a session with no wear record, so it goes in the log
            # rather than passing invisibly.
            log("pitcrew").info(
                "hud-wear: pre-flight skipped - the gauge is switched off")
            return GaugeCheck(ok=True, source=kind, enabled=False)

        TIMED_OUT = object()
        frame, why = self._bounded(
            lambda: self.build_source().grab(), timeout_s,
            lambda t: (TIMED_OUT, f"it did not answer within {t:g}s"))
        if frame is TIMED_OUT:
            # **A timeout is "I could not tell", NOT "there is nothing there".**
            # CLAUDE.md rule 3. Reported as a refusal it blocked the driver
            # minutes before a race with his projector open in front of him,
            # three times, and the sentence he was shown was false. He is not
            # asked - the gauge may never stop him driving - and the log
            # carries it so an empty wear record afterwards is still
            # explicable.
            log("pitcrew").warning(
                "hud-wear: pre-flight could not CHECK the %s source in %gs - "
                "going out without an answer either way. The gauge itself is "
                "unaffected; its own sampler thread is long-lived and does not "
                "pay this cold start.", kind, timeout_s)
            return GaugeCheck(ok=True, source=kind, checked=False,
                              reason=why)
        if frame is not None:
            # **The accept is logged, not only the refusal.** CLAUDE.md rule
            # 10: the ratchet was invisible for a whole race precisely because
            # only refusals reached the log. Without this line an empty wear
            # record cannot be told apart from a gate that never ran.
            log("pitcrew").info(
                "hud-wear: pre-flight OK - %s source is capturing", kind)
            return GaugeCheck(ok=True, source=kind)

        recording = self._obs_recording()
        log("pitcrew").warning(
            "hud-wear: pre-flight found nothing to capture on the %s source: "
            "%s (obs recording: %s)", kind, why, recording)
        return GaugeCheck(ok=False, reason=why or "nothing to capture",
                          source=kind, recording=recording)

    def _bounded(self, work, timeout_s: float, on_timeout):
        """Run `work` off the Qt thread with a hard timeout.

        **Everything that touches OBS from a button handler goes through
        here.** The first version bounded the grab and then called
        `_obs_recording` - down the identical `ObsSource._request` path, whose
        receive timeout re-arms on every message so a chattering socket never
        returns - straight on the Qt thread, immediately after. A critic found
        it. Bounding one of two doors is not bounding the room.

        An exception is the answer, not an error: nothing here may escape into
        the start path.
        """
        import threading

        out: list = []

        def run():
            try:
                out.append(work())
            except Exception as exc:                        # noqa: BLE001
                out.append(("__raised__", f"{type(exc).__name__}: {exc}"))

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(timeout=timeout_s)
        if not out:
            return on_timeout(timeout_s)
        got = out[0]
        if isinstance(got, tuple) and len(got) == 2 and got[0] == "__raised__":
            return None, got[1]
        return got

    def _obs_recording(self) -> bool | None:
        """Is OBS recording, so the gauge could be transcribed afterwards?

        **The dialog is wrong without this.** `tools/read_hud_wear.py` reads
        this gauge off a recorded file, and `LiveWearSampler` already tells the
        driver to use it - so "the wear cannot be recovered" is only true when
        nothing is recording. Telling him otherwise either aborts a session he
        did not need to abort, or stops him running the recovery pass on one
        he did.

        `None` where it cannot be told, which is not the same as `False`.
        """
        from pitcrew.telemetry.hud import ObsSource

        # **`obs_record_sessions` is "the APP drives the recording", not "OBS
        # is recording".** Reading it as the second told him "OBS is not
        # recording either, so there would be nothing to transcribe" whenever
        # the app was not driving it - while he may well have started the
        # recording himself. That is a confident claim about the world derived
        # from a flag about the app, and it is the sentence most likely to make
        # him abort a race he did not need to abort. CLAUDE.md rule 3: unknown
        # is not False. A critic found it.
        obs = ObsSource(self.settings.obs_host, self.settings.obs_port,
                        self.settings.obs_password)
        state, _why = self._bounded(obs.recording, PREFLIGHT_TIMEOUT_S,
                                    lambda _t: (None, "timed out"))
        return state

    def armed(self) -> bool:
        """Whether the gauge can be promised for the session about to start.

        **A probe, not a build.** `sampler()` is lazy on purpose - constructing
        it opens a socket - and the grid brief runs before `new_session`, so a
        brief that built the reader would open one for a practice that may
        never cross a line. Read the cached one instead: switched on in
        settings, and either not built yet (nothing has stood it down) or built
        and still standing. The brief used to read `getattr(self, "_hud",
        None)` on the controller - a name that never existed - so it said "No
        tyre gauge this race" at Deep Forest while the gauge read 19 of 20 laps.
        """
        if not self.settings.hud_wear_enabled:
            return False
        sampler = self._sampler
        return sampler is None or not bool(getattr(sampler, "stood_down", False))

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
        if existing is not None and self._source_key() == self._sampler_key:
            return existing
        if existing is not None:
            # **A settings change has to reach the cached sampler.** It is
            # built once and only `shutdown` stops it, and `save_settings`
            # rebinds settings without touching it - so switching source, host
            # or port left the old sampler reading the path he had just
            # abandoned, while `preflight` checked the new one and passed.
            # That is exactly what `build_source`'s docstring says must not
            # happen: a check on a source nothing reads from.
            log("pitcrew").info(
                "hud-wear: settings changed, rebuilding the sampler")
            try:
                existing.stop()
            except Exception:                               # noqa: BLE001
                log("pitcrew").warning("hud-wear: the old sampler would not "
                                       "stop; dropping it anyway")
            self._sampler = None
        from pitcrew.telemetry.hud import LiveWearSampler

        source = self.build_source()
        self._sampler_key = self._source_key()
        interval = float(self.settings.hud_sample_interval_s or 0.0)
        sampler = LiveWearSampler(source, self._write_wear,
                                  on_status=self._status,
                                  interval_s=interval,
                                  on_frame=self._pass_frame,
                                  on_hygro=self._note_hygro,
                                  on_compound=self._note_compound,
                                  on_damage=self._note_damage)
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
        # Rule 11: the last session's wet and tyre are not this session's.
        self._hygro.clear()
        self._compound.clear()
        self._damage.clear()
        self._contact_said = {"front": None, "rear": None}
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

        **Asked on a worker, never on the Qt thread.** This is a websocket
        connect, an identify and two requests, and OBS answers `StartRecord`
        only once the output is running: measured in the log at 0.3 to 3.9 s
        between the pre-flight and "OBS recording started", on the button
        handler, with the window frozen - and 2.0 s of refused connect on
        every start with OBS closed. The zero is still stamped at the moment
        OBS says it is recording, so what it means is unchanged; it simply
        does not hold the session hostage while it waits. No indexed crossing
        is lost: synchronously, the listener only started after OBS
        confirmed, so no crossing inside the wait was recorded at all. Now one
        is recorded as a lap, and `video_index.build` places it at second zero
        if it fell within `CLOCK_SLACK_S` (2 s) of the zero, or leaves it out
        of the video if earlier - a moment the capture does not contain.

        Silent on every failure. A recording is a convenience and a session is
        not, so nothing here may stop one opening.
        """
        if not self.settings.obs_record_sessions or session_id is None:
            return
        from pitcrew.telemetry.hud import ObsSource

        source = ObsSource(self.settings.obs_host, self.settings.obs_port,
                           self.settings.obs_password)
        with self._video_lock:
            self._video_session = session_id
        worker = threading.Thread(
            target=self._start_video_worker, args=(session_id, source),
            name="obs-record", daemon=True)
        self._video_thread = worker
        worker.start()

    def _start_video_worker(self, session_id: int, source) -> None:
        """The OBS round trip, off the Qt thread. Never raises."""
        try:
            started, why = source.start_recording()
        except Exception as exc:                             # noqa: BLE001
            started, why = None, f"{type(exc).__name__}: {exc}"
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
        with self._video_lock:
            # The zero is filed BEFORE the flag goes up, both under the lock,
            # so a `stop_video` can never see a recording it may stop whose
            # zero is not yet on the row it then writes the path to.
            current = self._video_session == session_id
            if current:
                try:
                    self.store.set_session_video(session_id, path=None,
                                                 started_at=stamp)
                except Exception as exc:                     # noqa: BLE001
                    log("session").warning("could not file the video zero "
                                           "for session %s: %s",
                                           session_id, exc)
                self._video_started = True
        if not current:
            # **The session closed while OBS was still starting.** `stop_video`
            # waited as long as it will and gave up, so nobody else is going
            # to stop this recording: the app started it, the app stops it.
            path, why = source.stop_recording()
            log("session").info(
                "OBS started recording after session %s had closed - stopped "
                "it again (%s)", session_id,
                path if path is not None else f"not cleanly: {why}")
            return
        log("session").info("OBS recording started, video zero at %s", stamp)

    def video_settled(self, timeout_s: float | None = None) -> bool:
        """Wait for an in-flight `start_video`. True when none is running."""
        worker = self._video_thread
        if worker is None:
            return True
        worker.join(timeout=VIDEO_START_WAIT_S if timeout_s is None
                    else timeout_s)
        return not worker.is_alive()

    def stop_video(self, session_id: int | None) -> None:
        """Stop the recording this app started, and file where OBS put it.

        **Never stops one it did not start** - `ObsSource.stop_recording`
        already refuses, and `_video_started` is the app's own half of the
        same rule.

        **A start still in flight is waited for, boundedly.** Otherwise a
        session closed inside the start's round trip would find nothing
        started, return, and leave OBS recording all night. If it does not
        settle in `VIDEO_START_WAIT_S` the worker is told the session is gone
        and stops the recording itself when it lands.
        """
        if not self.video_settled(VIDEO_START_WAIT_S):
            log("session").warning(
                "the OBS recording was still starting after %gs - the session "
                "closes now and the recording is stopped when OBS answers",
                VIDEO_START_WAIT_S)
        with self._video_lock:
            self._video_session = None
            started, self._video_started = self._video_started, False
        if not started:
            return
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
