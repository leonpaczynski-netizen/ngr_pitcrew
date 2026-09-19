"""The bench: does the hardware actually work, asked standing still.

**Extracted from `controller.py` on 29 Aug 2026**, the third cut. Nothing in
this file runs during a session. It is what the Settings screen's buttons do:
open the port and see whether anything is on it, sound the beep, say a line,
watch for the wheel button, read the gauge off the capture, and once every
ten ticks write down what the whole rig is doing.

That is a different job from running a race, and it was 343 lines in the
middle of the class that runs one.

### The verdict is three-valued, and that is the whole point

`verdict()` exists because a test that *acted* is not a test that *worked*.
Returning from `play_now` proves the app got as far as writing samples; it
proves nothing about whether the card rendered them. A dead endpoint accepts
everything and plays nothing, and from in here that used to read as success,
in green.

So there are four states and only two of them are "fine": acted-and-heard,
acted-and-demonstrably-not-heard, acted-and-unmeasurable, and did-not-act.
**Unmeasurable is reported as unmeasurable**, never as either of the others,
because claiming a measurement that was not taken is exactly how this class of
fault hides.

### Everything is read, and nothing is held

`listener` and `settings` are both rebound by the controller - a new listener
per session, a new settings object on every save - so both go in as callables.
Anything holding the object it was constructed with would be testing the port
the app opened with rather than the one it is on. That is the same trap the
rig supervisor documents, and it is the failure mode this codebase produces
most.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from pitcrew.diagnostics import log
from pitcrew.engineer.ptt import best_listener
from pitcrew.settings import FEED_PS5
from pitcrew.telemetry.listener import GT7_STREAM_PORT
from pitcrew.telemetry.recorder import SAMPLE_HZ
from pitcrew.telemetry.selftest import LISTEN_S, check_feed

# Packets the stream may lose before the health line calls it a fault. Any
# loss at all is recorded - see `LapRecorder` - but a handful over a session
# is the network, and thirty is something worth a line.
_LOST_PACKET_BUDGET = 30


class Bench:
    """The Settings screen's hardware checks, and the periodic health line."""

    def __init__(self, *, settings, settings_screen, bridge, voice, rig,
                 listener=None, practice=None, confirm_audio=None,
                 parse_errors=None) -> None:
        self._settings = settings if callable(settings) else (lambda: settings)
        # **A reader, because a listener is per session.** Held as an object,
        # every one of these checks would report on the port the app opened
        # with rather than the one it is listening on now.
        self._listener = listener if callable(listener) else (lambda: listener)
        # How many packets failed to decode this session. It is owned by the
        # controller because the parse-failure handler increments it; this
        # only ever reads it.
        self._parse_errors = parse_errors or (lambda: 0)
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
        self.bridge = bridge
        self.voice = voice
        self.rig = rig
        # **A reader, or the screen itself** (round 4): the Practice screen is
        # built after the window's first frame, and this object is built
        # before it. A reader is a callable with no `set_status` - a screen
        # (or a test's stand-in for one) always has that.
        self._practice = (practice if callable(practice)
                          and not hasattr(practice, "set_status")
                          else (lambda: practice))
        # **A reader returning the checker, not the checker.** Tests rebind
        # `controller._confirm_audio` after construction to ask a different
        # question - a stubbed tone, or a build agent with no audio hardware -
        # and a bench holding the original would go on calling the real
        # Windows peak meter. The same trap this file's docstring names for
        # `listener` and `settings`, and it caught the first draft of this
        # extraction.
        self._confirm_audio_source = (
            confirm_audio if callable(confirm_audio) else (lambda: None))
        self._button_probe = None
        self._health_ticks = 0

    @property
    def settings(self):
        return self._settings()

    @property
    def settings_screen(self):
        """Whichever settings screen exists now, or None before one is built.

        Resolved on every read rather than captured, so a screen that arrives
        after this object does is not invisible to it.
        """
        return self._settings_screen()

    def listener(self):
        return self._listener()

    @property
    def practice(self):
        """The Practice screen as it is now - built on first use by the
        controller's reader, so a line for it is never written into nothing."""
        return self._practice()

    @practice.setter
    def practice(self, screen) -> None:
        self._practice = lambda: screen

    def parse_errors(self) -> int:
        return self._parse_errors()

    @property
    def confirm_audio(self):
        """Whether the sound card actually rendered what the app sent it."""
        return self._confirm_audio_source()

    def shutdown(self) -> None:
        """Let the button probe go. Nothing else here owns anything."""
        if self._button_probe is not None:
            self._button_probe.stop()
            self._button_probe = None

    def test_feed(self, listen_s: float = LISTEN_S) -> bool:
        """Can the port actually be opened, and is anything on it?

        Tested against the value in the boxes rather than the saved one, so
        the answer is about the change he is considering. It reports the two
        failures separately: a port that will not bind is a different problem
        from a port that binds and stays silent, and only the first is
        something this screen can fix.
        """
        if self.settings_screen is None:
            # **Said, not swallowed.** This is a pre-race check with
            # a visible result, and returning quietly leaves a driver
            # who pressed the button and got nothing. Under pythonw
            # this line is the only evidence there will ever be.
            log("bench").warning(
                "%s was asked for, but the settings screen is not "
                "built", "test the feed")
            return False
        wanted = self.settings_screen.values()
        direct = (wanted.feed_source == FEED_PS5
                  and bool(wanted.ps5_ip.strip()))

        # **Compare against the port that would actually be bound.** Direct
        # mode ignores the configured port and uses GT7's own, so comparing
        # `udp_port` to the live listener never matched: the test then tried
        # to bind 33740 out from under the app's own listener, could not,
        # and reported "another program is holding it" while the feed was
        # working perfectly. The self-test called the healthy case a fault.
        would_bind = GT7_STREAM_PORT if direct else wanted.udp_port
        if self.listener() is not None and would_bind == self.listener().port:
            seen = self.listener().total_received
            decoded = self.listener().decoded
            rate = self.listener().packet_rate
            detail = (f"{decoded} of {seen} packets decoded"
                      + (f", {rate:.0f} Hz" if rate else ""))
            self.settings_screen.note_feed(
                f"Port {would_bind} is in use by this session's own "
                f"listener, which is the answer you want. {detail}.",
                warn=bool(seen and not decoded))
            return True

        # **Not a port probe.** A free port proves nothing: a wrong port
        # pair, a console nobody has asked, and a game sitting in the
        # menus all bind cleanly and deliver nothing. This opens the
        # socket, sends real heartbeats where they are required, and says
        # what decoded - CLAUDE.md 7, the connection fails loudly.
        if wanted.feed_source == FEED_PS5 and not wanted.ps5_ip.strip():
            self.settings_screen.note_feed(
                "Direct mode needs the console's address. Without it "
                "there is nothing to send a heartbeat to, and GT7 streams "
                "only to an address that has asked it.", warn=True)
            return False

        # **Say it is working before it blocks.** `check_feed` listens for
        # four seconds on this thread, deliberately - it is driven by a button
        # pressed while sitting still, and a background version would report
        # into a screen he has already left. But the button was not disabled
        # and nothing said "listening", so the app was an unresponsive
        # white-flagged window for four seconds after every click. The PTT
        # probe beside it already does this properly.
        self.settings_screen.set_feed_testing(True)
        QApplication.processEvents()
        try:
            report = check_feed(
                port=GT7_STREAM_PORT if direct else wanted.udp_port,
                heartbeat_to=wanted.ps5_ip.strip() if direct else None,
                source_ip=wanted.udp_source_ip,
                listen_s=listen_s)
        finally:
            self.settings_screen.set_feed_testing(False)
        self.settings_screen.note_feed(report.as_text(), warn=not report.ok)
        return report.ok

    def test_gauge(self) -> bool:
        """Read the wear gauge once, now, and say exactly what happened.

        **The gauge has never been read during a live race** - only against
        recorded video and synthetic frames - so the first time it is asked to
        work must not be a race. This is that rehearsal: it grabs one frame
        through the source in the boxes, transcribes it, and reports the four
        numbers or the reason there are none.

        Tested against the values on screen rather than the saved ones, like
        the feed test beside it, so the answer is about the change he is
        considering. It builds its own source and touches the live sampler not
        at all: `ObsSource` opens and closes per grab and `ScreenSource` holds
        nothing, so neither can disturb a session already running.
        """
        if self.settings_screen is None:
            # **Said, not swallowed.** This is a pre-race check with
            # a visible result, and returning quietly leaves a driver
            # who pressed the button and got nothing. Under pythonw
            # this line is the only evidence there will ever be.
            log("bench").warning(
                "%s was asked for, but the settings screen is not "
                "built", "read the gauge")
            return False
        from pitcrew.settings import HUD_SOURCE_SCREEN
        from pitcrew.telemetry.hud import ObsSource, ScreenSource, read_gauge

        wanted = self.settings_screen.values()
        if wanted.hud_source == HUD_SOURCE_SCREEN:
            source = ScreenSource()
            where = "the screen"
        else:
            source = ObsSource(wanted.obs_host, wanted.obs_port,
                               wanted.obs_password)
            where = f"OBS at {wanted.obs_host}:{wanted.obs_port}"

        # **Say it is working before it blocks**, for the reason the feed test
        # does: a websocket grab can sit on its connect timeout for four
        # seconds, and an undisabled button over an unresponsive window is how
        # a working test gets pressed five times.
        self.settings_screen.set_gauge_testing(True)
        QApplication.processEvents()
        try:
            frame, why = source.grab()
            reading = read_gauge(frame) if frame is not None else None
        except Exception as exc:                             # noqa: BLE001
            # Nothing in a settings screen may take the app down with it.
            self.settings_screen.set_gauge_testing(False)
            self.settings_screen.note_gauge(
                f"Reading from {where} raised {type(exc).__name__}: {exc}",
                warn=True)
            return False
        finally:
            self.settings_screen.set_gauge_testing(False)

        if frame is None:
            self.settings_screen.note_gauge(f"No frame from {where}. {why}",
                                            warn=True)
            return False
        if reading is None or not reading.ok:
            # A frame arrived and could not be read. That is a different fault
            # from no frame at all, and usually a benign one - a paused game,
            # a menu, a transition - so it is said as what it is.
            self.settings_screen.note_gauge(
                f"A frame arrived from {where}, but the gauge was not "
                f"readable. {reading.reason if reading else ''} "
                f"Try again with the car on track and the game running.",
                warn=True)
            return False

        worst = max((v for v in reading.wear.values() if v is not None),
                    default=None)
        cells = ", ".join(
            f"{corner.upper()} " + ("--" if value is None
                                    else f"{value * 100:.0f}%")
            for corner, value in sorted(reading.wear.items()))
        note = f"Read from {where}: {cells}."
        if worst is not None:
            note += f" Worst corner {worst * 100:.0f}%."
        if reading.reason:
            # A located reading carries how coarse it is. That travels.
            note += f" {reading.reason}"
        self.settings_screen.note_gauge(note)
        return True

    def _chosen_output(self) -> str:
        return self.settings.audio_output_device or ""

    def _where_he_listens(self) -> str:
        return self._chosen_output() or "the system default output"

    def test_beep(self) -> bool:
        """Sound the beep now. The only way to know it carries over the engine.

        Played and then **verified against the sound card's own peak meter**.
        Returning from `play_now` only proves the app got as far as writing
        samples, and a card that has stopped rendering accepts those without
        complaining - see `endpoint_meter` for the measurement that proved it.
        """
        if self.settings_screen is None:
            # **Said, not swallowed.** This is a pre-race check with
            # a visible result, and returning quietly leaves a driver
            # who pressed the button and got nothing. Under pythonw
            # this line is the only evidence there will ever be.
            log("bench").warning(
                "%s was asked for, but the settings screen is not "
                "built", "test the beep")
            return False
        beep = self.bridge.shift_beep
        outcome: dict[str, bool] = {}

        def play() -> None:
            outcome["played"] = beep.play_now()

        heard, detail = self.confirm_audio(
            play, device=self._chosen_output() or None)
        played = outcome.get("played", False)
        note, warn = self._audio_verdict(
            acted=played,
            failed=(f"No beep - {beep.last_error}" if beep.last_error else
                    "No beep - this machine has no tone device"),
            worked=("Beeped at "
                    + (", ".join(f"g{g} {rpm:.0f} rpm"
                                 for g, rpm in sorted(beep.per_gear.items()))
                       if beep.per_gear else
                       "no measured threshold - the fitted sheet has none")),
            heard=heard, detail=detail)
        self.settings_screen.note_beep(note, warn=warn)
        return played and heard is not False

    def test_voice(self) -> None:
        if self.settings_screen is None:
            # **Said, not swallowed.** This is a pre-race check with
            # a visible result, and returning quietly leaves a driver
            # who pressed the button and got nothing. Under pythonw
            # this line is the only evidence there will ever be.
            log("bench").warning(
                "%s was asked for, but the settings screen is not "
                "built", "test the voice")
            return
        self.voice.warm()
        line = "Radio check. Box this lap or next."
        # Synchronously, and report what happened rather than that it was
        # queued: this button exists because he is in a headset and cannot see
        # whether a sound came out, which is exactly the case where a false
        # success is worst. Speaking is still not the same as being heard, so
        # the endpoint meter answers the second half of the question.
        outcome: dict[str, object] = {}

        def play() -> None:
            outcome["spoke"], outcome["why"] = self.voice.say_now(line)

        heard, detail = self.confirm_audio(
            play, device=self._chosen_output() or None)
        spoke = bool(outcome.get("spoke", False))
        note, warn = self._audio_verdict(
            acted=spoke,
            failed=f"Nothing came out - {outcome.get('why', '')}. "
                   f"Check the output device and the log",
            worked=f"Said it through {self.voice.engine_name}: “{line}”",
            heard=heard, detail=detail)
        self.settings_screen.note_beep(note, warn=warn)

    def _audio_verdict(self, *, acted: bool, failed: str, worked: str,
                       heard: bool | None, detail: str) -> tuple[str, bool]:
        """What to tell the driver, given what the app did and what the card
        actually rendered.

        Three outcomes, not two, and the third is the point of the whole
        exercise: **the app played it and the card did not**. That is what a
        dead endpoint looks like from in here, and it used to read as success
        in green. `heard is None` is a fourth state - unmeasurable - and is
        deliberately not reported as either, because claiming a measurement
        that was not taken is how this class of fault hides.
        """
        if not acted:
            return f"{failed}.", True
        if heard is False:
            return (f"{worked}, but no audio reached "
                    f"{self._where_he_listens()} - {detail}. The device is "
                    f"accepting sound and dropping it; choose another.", True)
        if heard is None:
            return f"{worked}. Could not verify it reached the sound card.", False
        return f"{worked} - {detail}.", False

    def probe_button(self, listening: bool) -> None:
        """Watch for the configured key and say when it is pressed.

        The button is on a wheel, mapped through Fanatec's software, and the
        app cannot see any of that. Pressing it here is the only proof.
        """
        if self.settings_screen is None:
            # **Said, not swallowed.** This is a pre-race check with
            # a visible result, and returning quietly leaves a driver
            # who pressed the button and got nothing. Under pythonw
            # this line is the only evidence there will ever be.
            log("bench").warning(
                "%s was asked for, but the settings screen is not "
                "built", "listen for the button")
            return
        if self._button_probe is not None:
            self._button_probe.stop()
            self._button_probe = None
        if not listening:
            self.settings_screen.set_listening(False)
            self.settings_screen.note_ptt("Stopped listening.")
            return

        key = self.settings_screen.values().ptt_key
        probe = best_listener(key)
        if probe is None:
            self.settings_screen.set_listening(False)
            self.settings_screen.note_ptt(
                "No keyboard hook on this machine, so the button cannot be "
                "read at all. Check the log.", warn=True)
            return

        # Through the bridge, not straight into the label: pynput dispatches
        # these on its own daemon thread, and `note_ptt` calls setText and
        # setStyleSheet. That is the cross-thread widget write this controller
        # already documents fixing one method along, left behind on this path.
        probe.start(
            lambda: self.bridge.button_probed.emit(f"{key} down - held."),
            lambda: self.bridge.button_probed.emit(
                f"{key} released. That is the button."))
        self._button_probe = probe
        self.settings_screen.set_listening(True)

    def _report_health(self) -> None:
        """Say which of the several silences this one is.

        A listener that never bound, a console that is not streaming, and a
        source filter eating every packet all look identical from the rack -
        no laps appear. Zeros are the one failure mode that survives all the
        way into a setup recommendation, so each gets its own sentence.
        """
        self._health_ticks = getattr(self, "_health_ticks", 0) + 1
        if self._health_ticks % 10 == 0:
            self.rig._report_rig()
        if self.listener() is None:
            return
        # The port the listener is actually on. `self.port` is the configured
        # relay port and is not what direct mode binds, so printing it sent
        # him to check a number nothing was listening on.
        port = self.listener().port
        direct = self.listener().heartbeat_to is not None
        upstream = ("the console" if direct else "SimHub")

        if self.listener().bind_error:
            self.practice.set_status(
                f"Port {port} could not be opened: "
                f"{self.listener().bind_error}. Nothing will arrive until that "
                f"is fixed - change the port on the Settings screen, or close "
                f"whatever else is holding it.", warn=True)
        elif self.listener().send_error:
            # Only reachable in direct mode, and it is a different failure
            # from silence: the console was never asked, so of course it is
            # not streaming. Without this the driver was told to check GT7.
            self.practice.set_status(
                f"Could not reach the console at {self.listener().heartbeat_to}: "
                f"{self.listener().send_error}. GT7 streams only to an address "
                f"that has asked it to, so nothing will arrive until this is "
                f"fixed - check the address on the Settings screen and that "
                f"the PS5 is awake.", warn=True)
        elif self.listener().foreign_dropped and not self.listener().total_received:
            self.practice.set_status(
                f"{self.listener().foreign_dropped} packets arrived on "
                f"{port} and every one was refused: they are not from "
                f"{self.listener().source_ip}. Clear the source address on the "
                f"Settings screen if the console moved.", warn=True)
        elif not self.listener().connected:
            if direct:
                why = (f"The console has been asked "
                       f"{self.listener().heartbeats_sent} times and has not "
                       f"answered. Is GT7 running and out of the menus?")
            else:
                why = "Is GT7 running and SimHub relaying?"
            self.practice.set_status(f"No telemetry on {port}. {why}",
                                     warn=True)
        elif self.listener().total_received and not self.listener().decoded:
            # Bytes are arriving and none of them are telemetry. Distinct
            # from silence, and it means something else is on this port.
            self.practice.set_status(
                f"{self.listener().total_received} packets arrived on {port} "
                f"and none decoded. Something other than GT7 is talking on "
                f"this port.", warn=True)
        elif self.parse_errors():
            self.practice.set_status(
                f"{self.parse_errors()} packets failed to decode. Check "
                f"{upstream}.", warn=True)
        elif self.bridge.recorder.lost_packets > _LOST_PACKET_BUDGET:
            # Lap distance is INTEGRATED, so a gap is paid for by every metre
            # after it, and corner windows are keyed on lap distance. A lap
            # that lost packets still looks clean on the rack, which is the
            # reason to say so here rather than let it through quietly.
            lost = self.bridge.recorder.lost_packets
            gaps = self.bridge.recorder.stream_gaps
            self.practice.set_status(
                f"The feed has dropped {lost} packets in {gaps} "
                f"break{'' if gaps == 1 else 's'}. Lap distance is integrated "
                f"from the packet clock, so corner positions drift by roughly "
                f"{lost / SAMPLE_HZ:.1f} s of driving.", warn=True)
        elif self.listener().packet_rate and self.listener().packet_rate < 45.0:
            # CLAUDE.md 7: the connection must fail loudly. A feed limping at
            # 20 Hz used to report as healthy - and the recorder converts
            # packet-id deltas into METRES at an assumed flat 60 Hz, so a
            # degraded rate silently skews lap distance and every corner
            # window derived from it.
            self.practice.set_status(
                f"Telemetry is arriving at {self.listener().packet_rate:.0f} Hz, "
                f"not 60. Lap distance is derived from the packet clock, so "
                f"corner positions will be off until this is fixed.",
                warn=True)
