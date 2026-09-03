"""Supervising the rig: bringing it up, and telling when it has gone deaf.

**Extracted from `controller.py` on 29 Aug 2026**, where it was 597 lines of a
5,464-line file. It came out first because it is the cleanest seam in that
file: fourteen methods that between them called exactly ONE controller method,
and whose state - the watchdog, the endpoint note, the recovery ladder - was
touched by nothing else.

`docs/ENGINEER-TARGET-STATE_2026-08-29.md` D18 freezes the rig to bug fixes,
which is what makes this the safe first cut rather than the interesting one.

### What this is, and what `rig/` already was

`rig/haptics.py`, `rig/wind.py` and `rig/transducer.py` are the engines: they
render, they open devices, they push samples. **This is the layer above them** -
the one that decides when to start them, whether what came out was actually
heard, and what to tell the driver when it was not. That layer had no home, so
it lived in the controller with the event screen and the pit-radio.

### Why the endpoint note exists at all

A check that passes was, for the whole life of this app, indistinguishable in
the log from a check that never ran. In session 39 the endpoint wedged BELOW
the audio engine; the engine went on metering the app's own signal back at
itself, every health check passed, and the log said nothing either way for a
whole race night. `_endpoint_note` separates *checked, engine renders* from
*not asked, too quiet* from *unreadable* - so a driver reporting dead haptics
against a logged healthy endpoint isolates the fault to below the engine in one
line rather than a night of forensics.

Nothing in software can certify the piston. This says exactly how far down it
could see, which is the honest version of the same report.

### What it is handed, and what it therefore cannot do

Four collaborators and one reader, all injected:

* `bridge` - where the engines live, and the effects and wind curve they drive
* `settings` - what the driver asked for
* `voice` - how a rig fault reaches him when he is in a headset
* `settings_screen` - where a fault is written when he is not
* `event()` - the active event, for one thing only: scaling the fans to the
  circuit's own top speed rather than the car's

**It holds no store, no session and no race.** That is the point of the cut: a
rig fault cannot reach a lap, and a lap cannot reach the rig.
"""
from __future__ import annotations

import threading
import time

from time import monotonic as _monotonic

from PyQt6.QtWidgets import QApplication

from pitcrew.diagnostics import log
from pitcrew.engineer import endpoint_meter
from pitcrew.rig import transducer
from pitcrew.rig.haptics import HapticsEngine, TransducerWatchdog
from pitcrew.rig.wind import WindSim


class RigSupervisor:
    """The rig's lifecycle and its health, for one run of the app."""

    def __init__(self, *, bridge, settings, voice, settings_screen=None,
                 event=None) -> None:
        self.bridge = bridge
        # **A getter, not the object.** `save_settings` REBINDS
        # `controller.settings` rather than mutating it, so a supervisor
        # holding the object it was constructed with would go on reading the
        # settings as they were when the app opened - the driver would turn
        # the haptics off and the rig would carry on. Reading through a
        # callable means there is no second place to keep in step, which is
        # the failure mode this codebase produces most.
        #
        # A plain object is still accepted, for a test that wires one by hand.
        self._settings = settings if callable(settings) else (lambda: settings)
        self.voice = voice
        # **A reader too, and for the same reason one line up.** The settings
        # screen is built lazily now - it does not exist when this is
        # constructed, and it arrives when the driver first navigates to it.
        # Held as the object it was wired with, that is permanently None and
        # every hardware test button below returns at its own `is None` guard:
        # silently, with no log and no exception. Those buttons are the
        # pre-race checks - "test the feed", "read the gauge now" - so the
        # failure is a driver who verified nothing and was told it was fine.
        #
        # A plain object is still accepted, for a test that wires one by hand.
        self._settings_screen = (settings_screen if callable(settings_screen)
                                 else (lambda: settings_screen))
        # **A callable, not an event.** The active event changes under the
        # supervisor and `start_wind` needs whichever one is current; holding
        # a dict here would scale the fans to whatever was loaded when the app
        # started. `lambda: None` is a legitimate wiring - the curve then falls
        # back to the car's broadcast maximum and says which it used.
        self._event = event or (lambda: None)

    @property
    def settings_screen(self):
        """Whichever settings screen exists now, or None before one is built.

        Resolved on every read rather than captured, so a screen that arrives
        after this object does is not invisible to it.
        """
        return self._settings_screen()

    @property

    def settings(self) -> object:
        """The settings as they are NOW. See `__init__` for why it is a read."""
        return self._settings()

    def start_haptics(self) -> bool:
        """Open the transducer for this session, if the driver wants it.

        Returns whether anything is now running. A False is not a failure the
        session cares about: an output must never be able to stop the app
        recording, so this reports and the run goes on either way.
        """
        if not self.settings.haptics_enabled or self.bridge.haptics is not None:
            return self.bridge.haptics is not None
        engine = HapticsEngine(
            device=self.settings.haptics_device or transducer.DEVICE_NAME,
            master=self.settings.haptics_gain)
        if not engine.start():
            log("haptics").warning(
                "no haptics this session: %s", engine.error)
            return False
        self.bridge.effects.reset()
        self.bridge.haptics = engine
        # A fresh watchdog per engine: its cadence baseline and its recovery
        # ladder belong to this stream, not to whatever the last session did.
        self._rig_watchdog = TransducerWatchdog()
        return True

    def test_haptics(self) -> None:
        """Make the transducer do something, here, without going out.

        The whole point of a settings page for hardware: he is in a headset
        while driving and cannot see this screen, so the only way to know the
        strength is right is to feel it standing still. Runs the road-rumble
        effect at half, which is the one he will spend a lap inside.
        """
        if self.settings_screen is None:
            # Said, not swallowed - see the same guard in `bench`. A
            # transducer test that returns quietly is a driver who pressed
            # the button, felt nothing, and learned nothing from it.
            log("rig").warning(
                "test the transducer was asked for, but the settings screen "
                "is not built")
            return
        wanted = self.settings_screen.values()
        engine = self.bridge.haptics
        borrowed = engine is None
        if borrowed:
            engine = HapticsEngine(
                device=wanted.haptics_device or transducer.DEVICE_NAME,
                master=wanted.haptics_gain)
            if not engine.start():
                self.settings_screen.note_rig(engine.error or
                                              "The transducer would not open.",
                                              warn=True)
                return
        else:
            # Live session: honour the number in the box rather than the one
            # the session started with, so turning it up can be judged now.
            engine.set_master(wanted.haptics_gain)

        names = list(self.bridge.effects.NAMES)
        levels = [0.0] * (len(names) + len(self.bridge.effects.MODIFIERS))
        levels[names.index("road")] = 0.5
        try:
            deadline = _monotonic() + 2.0
            while _monotonic() < deadline:
                engine.set_intensities(levels)
                QApplication.processEvents()
                time.sleep(0.02)
            engine.silence()
        finally:
            if borrowed:
                engine.stop()
        self.settings_screen.note_rig(
            f"Road rumble at half, {wanted.haptics_gain:.1f}x. Felt about "
            f"right? If it wants to be stronger, turn the amplifier up "
            f"first - this control drives the limiter and the duty cycle, "
            f"and its own knob does not.")

    def stop_haptics(self) -> None:
        engine, self.bridge.haptics = self.bridge.haptics, None
        self._rig_watchdog = None
        if engine is not None:
            engine.stop()

    def start_wind(self) -> bool:
        """Bring the fans up for this session, if the driver wants them.

        The worker thread finds the device itself and keeps trying, so a wind
        sim that is switched on halfway through a session joins in rather than
        staying dark until the next one.

        **The link outlives the session, and it used to be rebuilt for each
        one.** `stop_practice` tore the `WindSim` down and `start_race` built
        a new one, so every practice -> qualifying -> race night paid three
        full reconnects: close the port, reopen it, wait out the bootloader
        settle, probe the CRC. Several seconds of dead fans each time, and
        from the seat that is indistinguishable from the hardware dropping -
        which is very likely most of what "the wind keeps cutting out" has
        been. The log recorded them as orderly shutdowns, so they never
        looked like faults; there are 78 of those lines and exactly one real
        drop in ten days.

        The device is not per-session. The thread now lives for as long as
        the controller does, and a session boundary only zeroes the fans and
        re-seeds the curve. `shutdown_wind` is the one place it is really
        torn down.
        """
        if not self.settings.wind_enabled:
            # Turned off in settings while a link was up: that is the one
            # case where a running thread must actually be stopped, and it
            # is not a session boundary.
            self.shutdown_wind()
            return False
        sim = self.bridge.wind
        if sim is None:
            sim = WindSim()
            sim.start()
            self.bridge.wind = sim
        self.bridge.wind_curve.reset()
        # **Scale the fans to the circuit, not to the car.** An event is one
        # car at one circuit, so its recorded top speed is the pair's and it
        # is the speed the fans should reach full at. NULL on an event nobody
        # has driven yet, and the curve then falls back to the car's broadcast
        # maximum and says which it used - see `WindCurve.scale_kph`.
        event = self._event()
        self.bridge.wind_curve.observed_top_kph = (
            event["observed_top_kph"]
            if event is not None and "observed_top_kph" in event.keys()
            else None)
        return True

    def stop_wind(self) -> None:
        """Park the fans at the end of a session. The link stays up.

        Zeroed rather than closed. The firmware's deadman would catch it a
        second later anyway, but a second of wind after the session ended is
        a second of wondering whether it is stuck - and holding the port
        means the next session starts blowing immediately instead of after a
        reconnect the driver feels as a dropout.
        """
        sim = self.bridge.wind
        if sim is not None:
            sim.stop_fans()

    def shutdown_wind(self) -> None:
        """Really let the device go. Closing the app, or wind switched off."""
        sim, self.bridge.wind = self.bridge.wind, None
        if sim is not None:
            sim.stop_fans()
            sim.shutdown()
    # A rendered peak below this is a quiet moment, not a signal, and asking
    # the card whether it played it would prove nothing either way.
    _AUDIBLE_PEAK = 0.02
    # The last health check's outcome, written by the meter thread and read by
    # the next report. **The success path used to record nothing**, and that
    # cost a diagnosis: in session 39 the endpoint wedged below the audio
    # engine, the engine kept metering the app's own signal back, and every
    # check passed silently - a check that passes was indistinguishable in the
    # log from one that never ran. This line cannot see below the engine
    # either (nothing in software certifies the piston), but it separates
    # "checked, engine renders" / "not asked, too quiet" / "unreadable", and a
    # driver reporting dead haptics against a logged healthy endpoint now
    # isolates the fault to below the engine in one line instead of a night
    # of forensics.
    _endpoint_note = "endpoint not yet asked"
    # Judges the endpoint's numbers and holds the recovery ladder. Created
    # with the engine in `start_haptics`; lazily here only so a bridge wired
    # by hand in a test still gets one.
    _rig_watchdog: TransducerWatchdog | None = None

    def _check_transducer_is_heard(self, haptics) -> None:
        """Did the card play what we rendered, or only accept it?

        **This session is why.** The log read `blocks 10767 · fades 0 ·
        running True` for a whole lap while the transducer produced nothing at
        all - the app synthesised, the card took every sample, and the driver
        felt none of it. Windows reported the device present, allowed,
        unmuted, at volume 50, and its own test tone was silent on it too, so
        the fault was the hardware. But nothing in here said so: every
        indicator was green for a device rendering silence.

        That is precisely the failure `endpoint_meter` exists to catch, and it
        was only ever wired to the settings-screen test button - the one place
        the driver is not looking while racing.

        Two halves make the claim: `take_recent_peak` says whether WE produced
        a signal, and the endpoint's own meter says whether the card rendered
        one. Loud in and nothing out is a dead transducer, and nothing else
        looks like that.

        Runs on its own thread. The meter needs a few hundred milliseconds to
        say anything, and spending that on the Qt thread would be a visible
        stutter every ten seconds of a race.
        """
        # The degraded latch stays visible on every path, including the ones
        # that never reach the meter - it is the one state the driver acts on.
        watchdog = self._rig_watchdog
        # **`stood_down`, not `degraded`.** `degraded` now lifts every
        # STAND_DOWN_RETRY_S so the ladder can try again, which means it is
        # false for most of a fault rather than true. The line the driver
        # reads must not blink out while the thing it describes is still
        # true; `stood_down` latches once the ladder has been spent and
        # stays latched.
        exhausted = (" · recovery exhausted"
                     if watchdog is not None
                     and getattr(watchdog, "stood_down", False) else "")
        produced = haptics.take_recent_peak()
        refused = getattr(haptics, "refused", None)
        if refused is not None:
            # **The meter cannot testify about audio nobody sent.** Asking it
            # here would write down "it is accepting the audio and playing
            # none of it" - true, and entirely about a silence of our own
            # making - and the ladder would then be climbing after a fault
            # the app had caused. The frame clock is the instrument for this
            # one, so the ladder runs off that instead.
            self._endpoint_note = f"output REFUSED - {refused}{exhausted}"
            if watchdog is not None:
                self._climb_ladder_off_thread(haptics, watchdog)
            return
        if produced < self._AUDIBLE_PEAK:
            self._endpoint_note = (
                f"endpoint not asked (rendered {produced:.3f}, quiet)"
                f"{exhausted}")
            return
        device = self.settings.haptics_device or transducer.DEVICE_NAME

        def ask() -> None:
            from pitcrew.engineer import endpoint_meter

            try:
                reading = endpoint_meter.poll_briefly(device, seconds=0.4)
            except Exception as exc:                        # noqa: BLE001
                self._endpoint_note = f"endpoint unreadable{exhausted}"
                log("haptics").debug("could not read the endpoint: %s", exc)
                return
            self._act_on_endpoint_reading(haptics, device, produced, reading,
                                          _monotonic())

        threading.Thread(target=ask, name="PitCrewHapticsMeter",
                         daemon=True).start()

    def _act_on_endpoint_reading(self, haptics, device: str, produced: float,
                                 reading, now: float) -> None:
        """Judge one endpoint reading and run the recovery ladder it earns.

        Separated from the worker thread that takes the reading so the whole
        ladder can be driven in a test without a sound card or a thread. Two
        readings are wedge evidence of equal rank: the meter reading nothing
        while we render loud, and - the race of 16 Aug 2026 - the meter
        reading the SAME number every check while what we render varies. The
        old detector only knew the first, so a meter that froze at 0.054 was
        read as healthy for twenty minutes of dead haptics.

        `reading` is an `endpoint_meter.Reading`; a bare float is accepted as
        the plain "this is the peak, no doubt about it" case. The distinction
        that matters is `measured`: a meter that could not be opened used to
        arrive here as `0.0` and be convicted as silence, which is how the
        app came to tell the driver his haptics were dead on the strength of
        an instrument that was never there.
        """
        if self.bridge.haptics is not haptics:
            # A poll still in flight from a session that has since been
            # stopped. It must not deposit its reading into - or lazily
            # create - the next session's watchdog.
            return
        reading = endpoint_meter.Reading.of(reading)
        watchdog = self._rig_watchdog
        if watchdog is None:
            watchdog = self._rig_watchdog = TransducerWatchdog()
        exhausted = (" · recovery exhausted"
                     if getattr(watchdog, "stood_down", False) else "")
        if not reading.measured:
            # **"Cannot measure" is not "failed", and no rung of the ladder
            # is earned by it.** Written down so a driver reporting dead
            # haptics against a silent log still lands on the right line.
            watchdog.unmeasurable(reading.detail)
            self._endpoint_note = (
                f"rendered {produced:.2f} · endpoint UNREADABLE "
                f"({reading.detail}){exhausted}")
            log("haptics").warning(
                "the transducer rendered a peak of %.3f and the endpoint "
                "meter for %s could not be read (%s). That is a fact about "
                "the meter and none at all about the device - nothing is "
                "being recovered off it.", produced, device, reading.detail)
            return
        watchdog.note_endpoint(reading.endpoint, reading.matches)
        watchdog.note_stream_changed(getattr(haptics, "last_open_changed", ()))
        heard = reading.peak
        if heard > endpoint_meter.SILENT_PEAK:
            verdict = watchdog.judge(produced, heard, now)
            if verdict == "live":
                # The engine renders what we produce. This says nothing about
                # the piston - session 39's wedge sat below the engine and
                # passed this check throughout - which is exactly why the
                # value is written down rather than silently returned past.
                watchdog.settled(now)
                self._endpoint_note = (
                    f"rendered {produced:.2f} · endpoint {heard:.3f}"
                    f"{exhausted}")
                self._deliver_rig_notice(watchdog)
                return
            if verdict == "unsettled":
                # A number, but not yet a verdict either way - typically the
                # first readings after a value change. Written down as
                # unconfirmed; no recovery is planned off it and no recovery
                # is declared to have worked off it.
                self._endpoint_note = (
                    f"rendered {produced:.2f} · endpoint {heard:.3f} "
                    f"(unconfirmed){exhausted}")
                return
            run = watchdog.stale_details()
            self._endpoint_note = (
                f"rendered {produced:.2f} · endpoint STALE "
                f"(frozen at {heard:.3f}){exhausted}")
            # One ERROR when the run first convicts; the polls after it say
            # nothing new, and the race night would have written this line
            # 119 times. The status line above carries STALE every cycle.
            # `first` is latched by the watchdog on the candidate itself -
            # keying on count == needed here missed the conviction when the
            # cadence corroboration lowered `needed` between polls.
            writer = (log("haptics").error
                      if run["first"]
                      else log("haptics").debug)
            writer(
                "the transducer rendered varying peaks (%.2f-%.2f) and %s "
                "has metered exactly %.3f for %d checks. A meter on a live "
                "signal jitters - this one is dead, and the endpoint behind "
                "it has stopped rendering, which is the same wedge as "
                "metering nothing.%s", run["rendered_low"],
                run["rendered_high"], device, heard, run["count"],
                (" The block cadence dropped at the same time, which "
                 "corroborates a device-side drop."
                 if watchdog.corroborated(now) else ""))
        else:
            watchdog.silent(now)
            self._endpoint_note = (
                f"rendered {produced:.2f} · endpoint SILENT{exhausted}")
            # Deliberately an error rather than a warning. The driver cannot
            # see this screen, and a transducer that is accepting audio and
            # playing none of it is indistinguishable from a working one by
            # every other measure the app has.
            #
            # **Hedged when it has to be.** A silent meter is only a claim
            # about the transducer when there was one endpoint it could have
            # meant and the stream is still on the terms it opened with.
            log("haptics").error(
                "the transducer rendered a peak of %.3f here and %s metered "
                "nothing - it is accepting the audio and playing none of "
                "it.%s", produced, device,
                (" This cannot be relied on: " + "; ".join(watchdog.doubts())
                 + ". If the seat is still working, the meter is not "
                   "watching what the stream is feeding."
                 if watchdog.uncertain else ""))
        # **And then do something about it.** This exact wedge has needed a
        # laptop restart from the seat more than once, and a log line is not
        # a recovery. Reopen in place first; if the evidence comes straight
        # back - the "came and went" flapping - tear down and rebuild from a
        # fresh device list, a capped number of times, and then say so once
        # and stand down rather than hammer a device that is gone.
        self._climb_ladder(haptics, watchdog, now)

    def _climb_ladder(self, haptics, watchdog, now: float) -> None:
        """One rung, whichever instrument earned it.

        Inline and synchronous, so the whole ladder can still be driven in a
        test without a sound card or a thread. Callers that are on the Qt
        thread go through `_climb_ladder_off_thread` instead, because
        `rebuild` stands back for a second before it reopens.
        """
        action = watchdog.plan_recovery(now)
        if action == "reopen":
            haptics.recover()
            watchdog.reopened(now)
        elif action == "rebuild":
            outcome = haptics.rebuild()
            if outcome is not None:
                # None is the driver's own stop cutting the rebuild short -
                # not an attempt, so not spent against the cap.
                watchdog.rebuilt(outcome, now)
        self._deliver_rig_notice(watchdog)
    # A rebuild outlives the ten-second cycle that started it, and two of
    # them racing would each tear down the other's stream.
    _ladder_busy = False
    # Said once per session, not every ten seconds. The condition persists
    # until the scheduling changes, and 119 identical error lines inside a
    # headset is how the last one of these was missed.
    _starvation_reported = False

    def _climb_ladder_off_thread(self, haptics, watchdog) -> None:
        """The same rung, for callers that must not block."""
        if self._ladder_busy:
            return
        self._ladder_busy = True

        def climb() -> None:
            try:
                self._climb_ladder(haptics, watchdog, _monotonic())
            finally:
                self._ladder_busy = False

        threading.Thread(target=climb, name="PitCrewHapticsLadder",
                         daemon=True).start()

    def _apply_clock_verdict(self, haptics, watchdog) -> None:
        """Refuse the output when the card is not pulling it at 48 kHz.

        `HapticsEngine._open` already refuses a stream that NEGOTIATES a rate
        the mix is not generated for, because the amplifier passes one band
        and the driver's verdict on the alternative is that wrong output is
        worse than not being on. This is that same rule applied to the rate
        the card turns out to be pulling at - not the same number, and on
        17 Aug 2026 not the same answer: the stream opened at 48000, was
        pulled at 30611, and drove the piston with everything transposed
        0.64x for nineteen minutes while the app logged what was wrong.

        Spoken both ways, because a seat that has gone quiet on purpose is
        indistinguishable from one that has died, and he is in a headset with
        no way to check.
        """
        clock = watchdog.clock_hz
        if watchdog.clock_suspect and clock is not None:
            nominal = float(transducer.SAMPLE_RATE)
            ratio = clock / nominal
            # **Ask the card before blaming it.** `clock_hz` is frames this
            # process handed over per wall-clock second - a statement about
            # our own scheduling, which for ten days was logged as "the card
            # is pulling N frames a second" and acted on as a property of the
            # hardware. `dac_clock_hz` is PortAudio's own stream clock and is
            # the card's. When the two disagree, the app is the fault.
            #
            # Measured 22 Aug 2026: with the GIL contended by the app's own
            # threads, a healthy 48 kHz ButtKicker was being handed 30699
            # frames a second at 64 blocks a second - the field signature to
            # four figures - while the endpoint itself never moved. Nothing
            # was transposed. Muting was the wrong answer, and it was the
            # answer given for nineteen minutes of a race.
            tolerance = getattr(watchdog, "CLOCK_TOLERANCE", 0.04)
            dac = getattr(haptics, "dac_clock_hz", None)
            if dac is not None and abs(dac - nominal) / nominal <= tolerance:
                # Starving a healthy endpoint. Do NOT mute: the cues are
                # gapped, not transposed, so they are still in the right
                # places and silence is the worse of the two. Do not run the
                # ladder either - reopening a stream cannot give this
                # process the GIL, and three rebuilds proved that on 17 Aug.
                if not getattr(self, "_starvation_reported", False):
                    self._starvation_reported = True
                    log("haptics").error(
                        "the transducer is being UNDERFED, not mis-clocked: "
                        "the endpoint's own clock is %.0f Hz, which is the "
                        "rate the mix is generated at, but this process is "
                        "only handing it %.0f frames a second (%.2fx). The "
                        "cues are gapped rather than transposed, so they are "
                        "still in the right places and muting would be the "
                        "worse answer. This is the app's scheduling, not the "
                        "card - see SWITCH_INTERVAL_S and BLOCKSIZE in "
                        "rig/haptics.py. Sustained underfeed is also what "
                        "degrades the endpoint itself, so this must not be "
                        "left to run.", dac, clock, ratio)
                return
            reason = (f"the card is pulling about {clock:.0f} frames a "
                      f"second against the {transducer.SAMPLE_RATE} the mix "
                      f"is generated at, so every effect would arrive "
                      f"transposed by {ratio:.2f}x")
            if haptics.refuse(reason):
                log("haptics").error(
                    "nothing further is being sent to the transducer: %s. "
                    "The road bed at %.0f Hz would arrive at %.0f Hz and the "
                    "amplifier passes %.0f-%.0f Hz, so the cues would be in "
                    "the wrong places rather than merely weak, which the "
                    "driver has said is worse than none. The stream is left "
                    "open so the frame clock can still be watched.",
                    reason, 38.0, 38.0 * ratio,
                    transducer.BAND_LOW_HZ, transducer.BAND_HIGH_HZ)
                self.voice.say(
                    "Haptics muted. The sound card is running them at the "
                    "wrong speed, so every cue would land in the wrong "
                    "place. I have stopped sending rather than give you a "
                    "wrong one.")
            return
        if haptics.allow():
            # **The one place the ladder can be told it is over, because it
            # is the only evidence that arrives while the output is
            # refused.** `settled` was reachable only from the endpoint
            # meter, and `_check_transducer_is_heard` deliberately does not
            # poll the meter while refused - it would be asking about a
            # silence of our own making. So refusal and the ladder's reset
            # were mutually exclusive: the attempt counters could never be
            # cleared in the one state that needed them cleared, and the
            # engine stayed spent for the rest of the process.
            #
            # A clock back at nominal is exactly the health `settled` exists
            # to record. It costs nothing to say so here.
            watchdog.settled(_monotonic())
            log("haptics").warning(
                "the transducer's frame clock is back at the rate the mix is "
                "generated for, so it is being sent to again.")
            self.voice.say("Haptics are back.")

    def _deliver_rig_notice(self, watchdog) -> None:
        """The one operational instruction, where the driver will get it.

        The log line carries the evidence; the spoken line is the seam that
        reaches a man in a headset. `take_notice` is one-shot, so neither can
        repeat.
        """
        notice = watchdog.take_notice()
        if notice is None:
            return
        written, spoken = notice
        log("haptics").error(written)
        self.voice.say(spoken)
    # Below this an effect was not doing anything worth writing down.
    _EXPLAIN_FLOOR = 0.01

    def _log_haptic_state(self, haptics) -> None:
        """One line naming every effect that was actually contributing.

        Deliberately only the ones above the floor: a report listing seven
        effects of which five are at zero is a report nobody reads, and the
        interesting case is almost always one or two of them.
        """
        try:
            rows = [r for r in haptics.explain() if r["final"] > self._EXPLAIN_FLOOR]
        except Exception as exc:                            # noqa: BLE001
            log("haptics").debug("could not read the mix: %s", exc)
            return
        # **Silence is logged, not skipped, and skipping it cost a diagnosis.**
        #
        # Reported from the seat: "haptics died on second lap". The log for
        # that minute held block counts and nothing else - no mix line, no
        # state line - because this returned early whenever every effect was
        # below the floor. The one event worth diagnosing produced the one
        # gap in the evidence.
        #
        # It was then diagnosed WRONGLY from a neighbouring subsystem. The
        # wind level read 0.00 over the same ten seconds, so the car looked
        # parked. The driver said otherwise and the stored frames agreed with
        # him: 1,320 of a possible 1,320 for that stretch, mean 173 km/h,
        # minimum 59, no gaps. Two outputs silent, one recorder perfectly
        # happy, and nothing written down that could separate them.
        parts = [f"{r['effect']} {r['final']:.3f}@{r['hz']:.0f}Hz"
                 + (f" -{r['ducked_by']*100:.0f}%" if r["ducked_by"] > 0.05 else "")
                 for r in rows]
        log("haptics").info("mix: %s", " · ".join(parts) if parts
                            else "SILENT - every effect under the floor")
        car = self.bridge.effects.explain()
        # **The inputs, not only the verdicts.** Silence has several causes and
        # they are indistinguishable without these: a car in the garage should
        # be silent and a car at 173 km/h should not. A stream that has gone to
        # zeros without dropping a packet then shows up here as a
        # contradiction rather than as an absence.
        inputs = car["inputs"]
        # `lock@` is the learned lock threshold. Session 39 was diagnosed
        # blind on exactly this number: the cue collapsed because the
        # threshold had climbed, and the climb was inferred from code because
        # nothing had written the value down.
        log("haptics").info(
            "car: %.0f km/h · thr %.2f brk %.2f · traction %s %.2f (%s, %s) · "
            "brake %s %.2f (%s, lock@%.2f) · rotation %s %.2f (%s) · "
            "unload %.2f",
            inputs["speed_ms"] * 3.6, inputs["throttle"], inputs["brake"],
            car["traction"]["state"], car["traction"]["level"],
            car["traction"]["witness"], car["traction"]["confidence"],
            car["brake"]["state"], car["brake"]["level"], car["brake"]["axle"],
            car["brake"]["lock_threshold"],
            car["rotation"]["state"], car["rotation"]["level"],
            car["rotation"]["confidence"], car["load"]["unload"])

    def _report_rig(self) -> None:
        """Write down what the outputs are actually doing, once every so often.

        Because two sessions were spent guessing. "The haptics dropped in the
        first corner" and "the wind stopped again" are both symptoms with
        several possible causes, and every number that would separate them -
        how many blocks the transducer rendered, how many it faded out, how
        many the limiter caught, how many frames the fans sent, how many the
        device rejected - was being counted and thrown away.

        A symptom the driver reports an hour later is worth much less than a
        line in the log, and this is cheap.
        """
        haptics = self.bridge.haptics
        if haptics is not None:
            if self._rig_watchdog is None:
                self._rig_watchdog = TransducerWatchdog()
            # The callback count once per cycle is the cadence watchdog's
            # whole diet: the rate falling and staying fallen is the
            # endpoint's audio pump being rebuilt under the stream. The frame
            # count beside it is what says whether the buffer got longer or
            # the clock got slower, which the block count alone cannot.
            self._rig_watchdog.note_cadence(
                haptics.callbacks, _monotonic(),
                frames=getattr(haptics, "frames", None))
            self._apply_clock_verdict(haptics, self._rig_watchdog)
            # The endpoint note is the PREVIOUS cycle's check - the check runs
            # after this line, on its own thread. Ten seconds stale is fine;
            # invisible was the problem.
            clock = self._rig_watchdog.clock_hz
            # **The underrun count sits next to the frame clock because it
            # is the control on it.** A frame clock below nominal says only
            # that fewer frames went out than the mix generated; it does not
            # say whose fault that was. PortAudio's own `output_underflow`
            # does: underruns rising alongside a low clock means the card
            # still wants 48 kHz and we are failing to fill it - the cues are
            # gapped, not transposed - while a low clock with NO underruns is
            # a card genuinely consuming slower, which is the transposition
            # the refusal was written for. On 17 Aug 2026 the app spent a
            # whole race asserting the second without being able to rule out
            # the first.
            underruns = haptics.take_underflows()
            log("haptics").info(
                "blocks %d · %s · fades %d · limited %d · running %s · %s · "
                "underruns %d this cycle (%d total, %d flagged blocks) · "
                "recoveries %d · rebuilds %d",
                haptics.callbacks,
                f"clock {clock:.0f}Hz" if clock is not None else "clock -",
                haptics.faded_out,
                haptics._mix.limited_blocks, haptics.running,
                self._endpoint_note, underruns, haptics.underflows,
                haptics.status_blocks,
                haptics.recoveries, haptics.rebuilds)
            # **What the mix was doing, not just that it was running.**
            #
            # "I felt something odd in turn four" is unanswerable an hour
            # later unless the numbers were written down at the time. One line
            # per report is cheap and it is the difference between diagnosing
            # a cue and re-driving the session to reproduce it.
            self._log_haptic_state(haptics)
            self._check_transducer_is_heard(haptics)
        wind = self.bridge.wind
        if wind is not None and getattr(wind, "state", None) is not None:
            state = wind.state
            # **`drops` is here because `connected` could not see them.**
            # This line runs every ten seconds and a drop heals in seven to
            # twelve, so an outage the driver felt could fall entirely
            # between two reports and leave nothing behind. Ten days of logs
            # hold one drop; the driver reports them repeatedly. A monotonic
            # count cannot be missed by a sampling interval.
            since = ("" if state.last_drop_at is None else
                     f" ({_monotonic() - state.last_drop_at:.0f}s ago)")
            # `faults` are the driver failures ridden out on the same handle
            # since 3 Sep 2026; before that every one was a failure and a
            # drop. If this climbs while drops stay flat, the change worked.
            log("wind").info(
                "frames %d · resyncs %d · stale %d · timeouts %d · "
                "faults %d · failures %d · drops %d%s · level %.2f · "
                "connected %s",
                state.frames_sent, state.resyncs, state.stale_bytes,
                state.write_timeouts, getattr(state, "driver_faults", 0),
                state.write_failures, state.disconnects, since,
                self.bridge.wind_curve.level, state.connected)
