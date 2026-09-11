"""Settings — the feed, the button and the beep.

Three things the driver genuinely has to be able to change, and until now could
not: where the telemetry arrives, which button push-to-talk listens on, and
whether the shift beep sounds and at what rpm.

Both are hardware questions, and hardware is the one thing this app cannot
inspect. So both carry a **test** button. He is in a headset while driving and
cannot see this screen at all; the only way to know the wheel button is bound
to the right key, or that the beep is audible over engine noise, is to press it
here and listen. A settings page for a device you cannot hear is not a setting,
it is a guess.

Everything on this screen is declared, so everything on it is crayon. The one
piece of stencil is what the app found on the machine — which speech engine and
which hook actually loaded — because that is measured, not chosen.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QScrollArea,
    QFrame,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dataclasses import replace

from pitcrew.engineer import audio_devices

from pitcrew.settings import (
    COLOUR_CHATTY,
    COLOUR_NORMAL,
    COLOUR_QUIET,
    FEED_PS5,
    FEED_SIMHUB,
    COMMON_KEYS,
    DEFAULT_UDP_PORT,
    HUD_SOURCE_OBS,
    HUD_SOURCE_SCREEN,
    Settings,
)
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    Field,
    MarkButton,
    Measured,
    Plate,
    StencilLabel,
    block_wheel,
    mark_unset,
)

# Spin boxes have no null. The minimum of the range renders as a dash, so a
# gear nobody has measured never reads as "beep at 1000 rpm".
NO_SHIFT_POINT = 0.0
# GT7 has no seven-speed in the driver's league and the table is per gear, so
# six rows covers every car he runs. A car with fewer simply leaves the tail
# blank.
SHIFT_GEARS = (1, 2, 3, 4, 5, 6)




class SettingsScreen(QWidget):
    """Set the button and the beep, and prove both of them work."""

    # The per-gear tables as loaded, and which car the rows on screen belong
    # to. Class attributes because the plates are built during `__init__` and
    # the picker fires its own signal on the way, before `load` has run.

    saved = pyqtSignal(object)          # Settings
    test_beep_requested = pyqtSignal()
    test_voice_requested = pyqtSignal()
    test_haptics_requested = pyqtSignal()
    test_feed_requested = pyqtSignal()
    test_gauge_requested = pyqtSignal()
    capture_toggled = pyqtSignal(bool)      # raw session capture
    listen_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._listening = False
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 0)
        page.setSpacing(theme.GAP_WIDE)

        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(StencilLabel("Settings", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        header.addWidget(BodyLabel(
            "The feed, the button and the beep. Test them here — in the "
            "headset you cannot see whether any of them worked.",
            colour=theme.STENCIL_DIM))
        page.addLayout(header)

        # **This screen scrolls, and was the only one that did not.** It is
        # also the tallest: the two plates in the left column alone need
        # 1,117 px, and with the header and the fixed footer the whole thing
        # asks for 1,291. The app's own preferred window is 1,000 tall, and
        # the display it was sized for gives 501 logical pixels.
        #
        # Without a bar, "Save settings" sat 291 px below the visible area
        # with no way to reach it - on the one screen that carries the
        # recovery controls for a broken feed, where the driver goes
        # *because* something is already wrong.
        body = QWidget()
        columns = QHBoxLayout(body)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(theme.GAP_WIDE)

        left = QVBoxLayout()
        left.setSpacing(theme.GAP_WIDE)
        left.addWidget(self._feed_plate())
        # No stretch factor: the trailing stretch takes the slack, as it does
        # on the right. The factor was harmless while push-to-talk was last in
        # the column, but it is the gauge plate that is last now.
        left.addWidget(self._ptt_plate())
        left.addWidget(self._gauge_plate())
        left.addStretch(1)
        columns.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(theme.GAP_WIDE)
        right.addWidget(self._beep_plate())
        right.addWidget(self._audio_plate())
        right.addWidget(self._rig_plate())
        right.addWidget(self._voice_plate())
        right.addStretch(1)
        columns.addLayout(right, 1)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroller.setWidget(body)
        page.addWidget(scroller, 1)

        # Outside the scroller, so the thing you came here to press cannot be
        # scrolled away from.
        page.addWidget(self._footer())

    def _feed_plate(self) -> Plate:
        """Where the telemetry comes from.

        Two sources, and the difference is who does the asking. Direct sends
        GT7's heartbeat to the console itself, because the console streams
        only to an address that has asked it to. The relay leaves that to
        SimHub and this app just binds a port and listens.

        Decryption is this app's either way - SimHub forwards the encrypted
        bytes, it does not decode them - so direct mode loses nothing.

        The source address at the bottom is a filter on what arrives, not a
        destination, which is why setting it never made a console start
        streaming.
        """
        plate = Plate("Telemetry feed")
        plate.body.addWidget(BodyLabel(
            "Direct asks the console itself and needs nothing else running. "
            "The relay takes SimHub's forwarded copy instead. Either way the "
            "decryption happens here.",
            size=13, colour=theme.STENCIL_DIM))

        # Which of the two sources. Direct removes SimHub from the chain
        # entirely; the decryption has always been in this app, because
        # SimHub relays the encrypted bytes rather than decoding them.
        self.feed_source = QComboBox()
        self.feed_source.addItem("SimHub relay", FEED_SIMHUB)
        self.feed_source.addItem("PS5 direct", FEED_PS5)
        self.feed_source.currentIndexChanged.connect(self._sync_feed_source)
        block_wheel(self.feed_source)
        plate.body.addWidget(Field(
            "Source", self.feed_source,
            hint="Direct asks the console itself and needs no SimHub. It "
                 "uses GT7's own ports, so the port below is ignored."))

        self.ps5_ip = QLineEdit()
        self.ps5_ip.setPlaceholderText("192.168.1.20")
        self.ps5_field = Field(
            "PS5 address", self.ps5_ip,
            hint="The console's address on this network. GT7 streams only "
                 "to an address that has asked it to, on a timer.")
        plate.body.addWidget(self.ps5_field)

        self.udp_port = QSpinBox()
        self.udp_port.setRange(1024, 65535)
        self.udp_port.setGroupSeparatorShown(False)
        block_wheel(self.udp_port)
        plate.body.addWidget(Field(
            "Port", self.udp_port,
            hint=f"SimHub's relay is {DEFAULT_UDP_PORT}. Ignored in direct "
                 f"mode, which uses GT7's own pair — 33739 out, 33740 back."))

        self.udp_source_ip = QLineEdit()
        self.udp_source_ip.setPlaceholderText("any address")
        plate.body.addWidget(Field(
            "Only accept from", self.udp_source_ip,
            hint="Leave empty unless something else is talking on this port. "
                 "Set wrong, nothing arrives at all."))

        # Filed against every measurement the app makes. It sits with the
        # feed rather than on the event because one console runs one version,
        # and the export refuses a payload that has no version on it - which
        # an event created without one produced, with nothing on screen to
        # connect the empty box to the refusal.
        self.game_version = QLineEdit()
        self.game_version.setPlaceholderText("e.g. 1.71 - required, and no default is assumed")
        plate.body.addWidget(Field(
            "GT7 version", self.game_version,
            hint="Filed with every measurement. The physics have been "
                 "rewritten twice in two updates, so a figure without the "
                 "version it was taken under cannot be compared with the "
                 "next one."))

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.banner_enabled = QCheckBox("Show a full-screen notice")
        self.banner_enabled.setToolTip(
            "One line, as large as the screen will carry it, when a session "
            "starts and stops. Sized to be read through a headset's "
            "passthrough from a metre away, which the lap rack is not. It "
            "never takes focus, so it cannot steal a keypress from the game.")
        plate.body.addWidget(self.banner_enabled)

        # **A way to turn the board off.** It opens itself when a race arms,
        # frameless and always on top, and the setting that governs it had no
        # control anywhere in the app - so the only way to be rid of it was to
        # stop the race. Escape closes one that is already open; this stops it
        # opening at all.
        self.driver_board_enabled = QCheckBox(
            "Open the driver board when a race arms")
        self.driver_board_enabled.setToolTip(
            "The glance-up board for the screen above the game: tyre "
            "temperatures and laps to the stop while running, and the fuel, "
            "tyres, rejoin and release countdown while you are stopped.\n\n"
            "Drag it onto the monitor you want it on and it reopens there. "
            "Escape closes it without stopping the race.")
        plate.body.addWidget(self.driver_board_enabled)

        self.test_feed_button = MarkButton("Test the feed", compact=True)
        self.test_feed_button.setToolTip(
            "Opens the socket for real, asks the console if asking is "
            "required, and reports what actually decoded. A port that "
            "binds proves nothing on its own - a wrong port pair, an "
            "unasked console and a game sitting in the menus all look "
            "identical from here.")
        self.test_feed_button.clicked.connect(self.test_feed_requested.emit)
        row.addWidget(self.test_feed_button)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.feed_note = BodyLabel("", size=13, colour=theme.CHALK)
        self.feed_note.setWordWrap(True)
        plate.body.addWidget(self.feed_note)

        # Raw capture. Off by default and started before going out, because a
        # 30-minute session is ~40 MB and because there is nothing here anyone
        # should be operating in a headset at speed.
        plate.body.addWidget(BodyLabel(
            "Record every packet to disk for a measurement run. Start it "
            "before you go out, stop it when you come in. Nothing here is "
            "operable at speed.",
            size=13, colour=theme.STENCIL_DIM))
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.capture_button = MarkButton("Record raw session", compact=True)
        self.capture_button.setCheckable(True)
        self.capture_button.toggled.connect(self.capture_toggled.emit)
        row.addWidget(self.capture_button)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.capture_note = BodyLabel("", size=13, colour=theme.CHALK)
        self.capture_note.setWordWrap(True)
        plate.body.addWidget(self.capture_note)
        return plate

    def _ptt_plate(self) -> Plate:
        plate = Plate("Push to talk")
        plate.body.addWidget(BodyLabel(
            "Hold the button, ask, let go. Map a wheel button to a key in the "
            "Fanatec software, then name that key here.",
            size=13, colour=theme.STENCIL_DIM))

        self.ptt_enabled = QCheckBox("Push to talk is on")
        plate.body.addWidget(self.ptt_enabled)

        self.ptt_key = QComboBox()
        self.ptt_key.setEditable(True)
        self.ptt_key.addItems(COMMON_KEYS)
        block_wheel(self.ptt_key)
        plate.body.addWidget(Field(
            "Button", self.ptt_key,
            hint="A key name, as pynput reports it."))

        self.ptt_in_practice = QCheckBox("Also arm it during practice")
        self.ptt_in_practice.setToolTip(
            "The engineer only answers during a race. Arming it in practice "
            "lets you check the button works without racing to find out.")
        plate.body.addWidget(self.ptt_in_practice)

        # **Tap is the default, and hold is the fallback.** *"I do not have
        # time to hold the button. One press, hear a radio static sound so I
        # know it is recording, then it records, I talk, radio static to
        # confirm to me recording has stopped."* - the driver, 22 Aug. Holding
        # occupies a hand that is on a wheel; the two static bursts are what
        # tells him the microphone is open, since he cannot look.
        #
        # It stays a setting because tap has one failure hold does not: a press
        # nobody closes leaves the radio open. The bursts are the guard, and if
        # they are ever inaudible at the rig this is the way back.
        self.ptt_toggle = QCheckBox("Tap to talk, rather than hold")
        self.ptt_toggle.setToolTip(
            "Tap once to open the radio and again to close it, with a static "
            "burst at each end. Unticked, the button must be held down for as "
            "long as you are speaking.")
        plate.body.addWidget(self.ptt_toggle)

        plate.body.addWidget(self._rule_label("What this machine has"))
        self.engine_note = Measured("—", size=14)
        plate.body.addWidget(self.engine_note)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.listen_button = MarkButton("Listen for the button", compact=True)
        self.listen_button.clicked.connect(self._on_listen)
        row.addWidget(self.listen_button)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.ptt_note = BodyLabel("", size=13, colour=theme.CHALK)
        plate.body.addWidget(self.ptt_note)
        plate.body.addStretch(1)
        return plate

    def _gauge_plate(self) -> Plate:
        """Tyre wear, read off the picture, because the feed does not carry it.

        **GT7 broadcasts no tyre wear channel in any packet format** - CLAUDE.md
        3.3 calls that the single most consequential fact in the document. The
        app models wear and asks the driver to corroborate it from the in-game
        gauge, and across five sessions running he read it zero times. The gauge
        is on screen for the whole race and OBS is already pointed at it, so
        this transcribes the instrument he was being asked to read.

        It is off by default and stays off until switched on here: the OBS
        source reaches out to another process on a port, and that is not
        something that should start happening because the app was updated.
        """
        plate = Plate("Tyre wear off the video")
        plate.body.addWidget(BodyLabel(
            "The feed carries no wear channel, so the gauge in the corner of "
            "the screen is the only measurement there is. This reads it — the "
            "game's own number, transcribed, not a model.",
            size=13, colour=theme.STENCIL_DIM))

        self.hud_wear_enabled = QCheckBox("Read the wear gauge")
        plate.body.addWidget(self.hud_wear_enabled)

        self.hud_source = QComboBox()
        self.hud_source.addItem("OBS, over the websocket", HUD_SOURCE_OBS)
        self.hud_source.addItem("The screen, off an OBS projector window",
                                HUD_SOURCE_SCREEN)
        block_wheel(self.hud_source)
        self.hud_source.currentIndexChanged.connect(self._sync_hud_source)
        plate.body.addWidget(Field(
            "Read from", self.hud_source,
            hint="Both need OBS running. The websocket does not care whether "
                 "it is visible; the screen reads what the monitor shows."))

        # **The measured cost, because it is the whole reason there are two.**
        # Stencilled rather than crayon: these are measurements, not choices.
        plate.body.addWidget(self._rule_label("What each one costs"))
        self.hud_cost = Measured("—", size=14)
        self.hud_cost.setWordWrap(True)
        plate.body.addWidget(self.hud_cost)

        # --- the OBS connection, shown only where it is used
        self.obs_host = QLineEdit()
        self.obs_host_field = Field(
            "OBS host", self.obs_host,
            hint="Where OBS is. The same machine, normally.")
        plate.body.addWidget(self.obs_host_field)

        self.obs_port = QSpinBox()
        self.obs_port.setRange(1, 65535)
        block_wheel(self.obs_port)
        self.obs_port_field = Field(
            "OBS port", self.obs_port,
            hint="Tools, WebSocket Server Settings. 4455 unless it was moved.")
        plate.body.addWidget(self.obs_port_field)

        self.obs_password = QLineEdit()
        self.obs_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.obs_password_field = Field(
            "OBS password", self.obs_password,
            hint="Blank if authentication is off.")
        plate.body.addWidget(self.obs_password_field)

        # --- what the screen source needs instead
        self.hud_projector_note = BodyLabel(
            "In OBS, right click the preview and choose Windowed Projector "
            "(Program). Size it with the button below — it has to be exactly "
            "1720x916 and a mouse cannot do exact. It is found by title, so "
            "it can sit on any screen and you can move it whenever you like; "
            "only the size is fixed. But it must be VISIBLE, and nothing may "
            "sit on top of the gauge in its bottom-left corner — this reads "
            "what the monitor shows, so a window over that corner is read as "
            "tyre wear.",
            size=13, colour=theme.STENCIL_DIM)
        self.hud_projector_note.setWordWrap(True)
        plate.body.addWidget(self.hud_projector_note)

        # **A button rather than a note telling him the number.** A projector
        # does not survive a restart, so this is a before-every-session job,
        # and `ScreenSource` refuses anything that is not the canvas to the
        # pixel. Dragging a window edge against a figure you cannot see, every
        # session, is the kind of chore that ends with the source switched off.
        snap_row = QHBoxLayout()
        snap_row.setSpacing(theme.GAP)
        self.snap_projector_button = MarkButton("Size the projector",
                                                compact=True)
        self.snap_projector_button.clicked.connect(self._on_snap_projector)
        snap_row.addWidget(self.snap_projector_button)
        snap_row.addStretch(1)
        plate.body.addLayout(snap_row)

        self.snap_note = BodyLabel("", size=13, colour=theme.CHALK)
        self.snap_note.setWordWrap(True)
        plate.body.addWidget(self.snap_note)

        self.hud_interval = QDoubleSpinBox()
        self.hud_interval.setRange(0.0, 30.0)
        self.hud_interval.setSingleStep(0.5)
        self.hud_interval.setDecimals(1)
        block_wheel(self.hud_interval)
        plate.body.addWidget(Field(
            "Sample every", self.hud_interval, suffix="s",
            hint="0 reads the gauge only as you cross the line. Above 0 it "
                 "also samples in between, and the crossing then files the "
                 "last reading taken before it — so a paused frame on the "
                 "line no longer costs the lap, and a stint gets a series to "
                 "fit a slope across. Leave it at 0 on the OBS source."))

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.test_gauge_button = MarkButton("Read the gauge now", compact=True)
        self.test_gauge_button.clicked.connect(self.test_gauge_requested.emit)
        row.addWidget(self.test_gauge_button)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.gauge_note = BodyLabel("", size=13, colour=theme.CHALK)
        self.gauge_note.setWordWrap(True)
        plate.body.addWidget(self.gauge_note)
        return plate

    def _sync_hud_source(self) -> None:
        """Show only the fields the chosen source actually reads.

        The same rule the feed plate follows: leaving an unread box enabled is
        how somebody comes to believe a password is doing something.
        """
        screen = self.hud_source.currentData() == HUD_SOURCE_SCREEN
        for field in (self.obs_host_field, self.obs_port_field,
                      self.obs_password_field):
            field.setVisible(not screen)
        for widget in (self.hud_projector_note, self.snap_projector_button,
                       self.snap_note):
            widget.setVisible(screen)
        # Measured 22 Aug 2026 on this PC. The gap is what makes sampling
        # between crossings affordable on one source and not the other.
        self.hud_cost.setText(
            "0.21 ms of CPU a reading — a projector window is copied, not "
            "encoded. Sampling every 2 s costs 0.01% of one core."
            if screen else
            "about 537 ms of OBS CPU a reading — the whole canvas is "
            "rendered, PNG-encoded and sent over the socket. Affordable once "
            "a lap; not affordable faster.")

    def _on_snap_projector(self) -> None:
        """Size the projector to the canvas, and say what happened.

        **Inline rather than through the controller.** `SetWindowPos` on a
        window that is already up is local and instant - there is no socket,
        no device and nothing to wait on - so routing it through a signal
        would buy indirection and no safety. The gauge test next to it goes
        the other way precisely because an OBS grab can take seconds.
        """
        from pitcrew.telemetry.hud import snap_projector
        ok, said = snap_projector()
        self.snap_note.setText(said)
        self.snap_note.setStyleSheet(
            f"color: {theme.CHALK if ok else theme.WARNING};"
            "background: transparent;")

    def set_gauge_testing(self, testing: bool) -> None:
        """The seconds a websocket grab can take, said out loud."""
        self.test_gauge_button.setEnabled(not testing)
        self.test_gauge_button.setText(
            "Reading…" if testing else "Read the gauge now")
        if testing:
            self.note_gauge("Asking for a frame. This can take a few seconds "
                            "on the OBS source.")

    def note_gauge(self, text: str, *, warn: bool = False) -> None:
        self.gauge_note.setText(text)
        self.gauge_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def _beep_plate(self) -> Plate:
        plate = Plate("Shift beep")
        plate.body.addWidget(BodyLabel(
            "One beep as the rpm crosses the threshold, re-armed once it "
            "falls back. It never sounds off track, and a downshift mutes it "
            "briefly so the throttle blip cannot trigger it.",
            size=13, colour=theme.STENCIL_DIM))

        self.beep_enabled = QCheckBox("Shift beep is on")
        plate.body.addWidget(self.beep_enabled)

        plate.body.addWidget(BodyLabel(
            "The thresholds are issued by the tune builder, one per gear, "
            "because a shift point belongs to the gearbox - change a ratio "
            "and it moves. No table issued for the car and circuit means "
            "nobody has designed one, and the beep stays silent rather than "
            "guessing at a number.",
            size=13, colour=theme.STENCIL_DIM))

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        beep = MarkButton("Test beep", compact=True)
        beep.clicked.connect(self.test_beep_requested.emit)
        voice = MarkButton("Test engineer voice", compact=True)
        voice.clicked.connect(self.test_voice_requested.emit)
        row.addWidget(beep)
        row.addWidget(voice)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.beep_note = BodyLabel("", size=13, colour=theme.CHALK)
        plate.body.addWidget(self.beep_note)
        plate.body.addStretch(1)
        return plate

    def _rig_plate(self) -> Plate:
        """The transducer and the fans - what the app drives rather than reads.

        Both are off until switched on: the transducer puts 150 W into a piston
        under the seat, and neither is something that should start making
        itself felt because the app was updated.

        The gain moves everything together; the balance BETWEEN effects is the
        driver's own SimHub tuning and belongs in the effect list.

        **It is capped at 1.5, and that is a safety limit rather than a taste
        one.** The limiter holds the peak at any setting, but not the duty
        cycle - and duty cycle is what an amplifier's protection responds to.
        Measured over a real lap: a master of 2.5 puts 31.5% of blocks into
        the limiter and holds the mix at -9.1 dBFS sustained, against 0.05%
        and -16.4 dBFS at 1.0. A master of 2 tripped this amp and cost a PC
        restart. The hint here used to invite exactly that setting.
        """
        plate = Plate("Rig")
        plate.body.addWidget(BodyLabel(
            "Wind and haptics, driven straight from the telemetry. Both need "
            "their hardware connected — a transducer that is not there stays "
            "silent rather than borrowing another card.",
            size=13, colour=theme.STENCIL_DIM))

        self.haptics_enabled = QCheckBox("Transducer is on")
        plate.body.addWidget(self.haptics_enabled)

        self.haptics_gain = QDoubleSpinBox()
        self.haptics_gain.setRange(0.0, 1.5)
        self.haptics_gain.setSingleStep(0.1)
        self.haptics_gain.setDecimals(1)
        block_wheel(self.haptics_gain)
        plate.body.addWidget(Field(
            "Strength", self.haptics_gain, suffix="x",
            hint="1.0 is the level the transducer was calibrated against. "
                 "If it wants to be stronger, turn the amplifier up first — "
                 "it is at 35 of 50. This drives the limiter and the duty "
                 "cycle; the amp's own knob does not."))

        self.wind_enabled = QCheckBox("Wind simulator is on")
        plate.body.addWidget(self.wind_enabled)

        self.rig_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        self.rig_note.setWordWrap(True)
        plate.body.addWidget(self.rig_note)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        test = MarkButton("Test transducer", compact=True)
        test.clicked.connect(self.test_haptics_requested.emit)
        row.addWidget(test)
        row.addStretch(1)
        plate.body.addLayout(row)
        return plate

    def note_rig(self, text: str, *, warn: bool = False) -> None:
        self.rig_note.setText(text)
        self.rig_note.setStyleSheet(
            f"color: {theme.DANGER_INK};" if warn else "")

    def _audio_plate(self) -> Plate:
        """Which sound card the engineer speaks into, and which one hears him.

        This exists because of what silence looked like without it. PortAudio
        resolves "the default device" once, when it is first imported; the
        driver puts the PSVR2 on after the app is already running, so the call
        went to whatever was default at launch. A disconnected endpoint does
        not raise - measured, a full second of audio written to one completed
        and returned cleanly - so the engineer spoke, the counter went up, the
        call appeared on the race screen, and the man in the headset heard
        nothing with every indicator green.

        Named devices rather than indices: PortAudio renumbers whenever
        something is plugged in, and a stale index is how this failed before.
        """
        plate = Plate("Sound devices")
        plate.body.addWidget(BodyLabel(
            "Set these to the headset you race in. Left on the system "
            "default, a device connected after the app started will not be "
            "found, and nothing will say so.",
            size=13, colour=theme.STENCIL_DIM))

        self.audio_output = QComboBox()
        self.audio_input = QComboBox()
        # **Not filled here.** `audio_devices.devices()` tears PortAudio down
        # and rebuilds it to enumerate, twice, and this ran at every launch
        # purely to populate two combo boxes on a screen the driver opens
        # perhaps once a month.
        #
        # It is also more correct filled late than early. The label above this
        # promises that a device connected after the app started will be
        # found; a list built at launch cannot keep that promise, and the
        # headset gets plugged in on the way to the desk.
        self._audio_filled = False
        # Set by `load`, which runs before the fill below and therefore
        # cannot find a device the list does not hold yet. The fill re-reads
        # it, so a configured headset is not quietly replaced by the default.
        self._loaded = getattr(self, "_loaded", None)
        self._session_open = False
        self._audio_syncs = []
        for combo in (self.audio_output, self.audio_input):
            combo.addItem("System default", "")
            self._audio_syncs.append(mark_unset(combo, unset=""))

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)
        grid.addWidget(Field("He hears the engineer on", self.audio_output), 0, 0)
        grid.addWidget(Field("The engineer hears him on", self.audio_input), 1, 0)
        plate.body.addLayout(grid)
        return plate

    def _voice_plate(self) -> Plate:
        """How the engineer sounds.

        Here rather than in a file because this app reads no config file, and
        at the rig rather than in code because it is settled by ear.
        """
        plate = Plate("Engineer's voice")
        plate.body.addWidget(BodyLabel(
            "A race engineer is calm. Jitter is what makes a synthetic voice "
            "sound nervous — it is the one to reach for first.",
            size=13, colour=theme.STENCIL_DIM))

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)

        self.length_scale = self._tuning_box(0.5, 2.0, 0.02, 1.12)
        self.noise_scale = self._tuning_box(0.0, 1.5, 0.05, 0.60)
        self.noise_w_scale = self._tuning_box(0.0, 1.5, 0.05, 0.55)

        grid.addWidget(Field("Pace", self.length_scale,
                             hint="Higher is slower."), 0, 0)
        grid.addWidget(Field("Timbre variation", self.noise_scale), 0, 1)
        grid.addWidget(Field("Jitter", self.noise_w_scale,
                             hint="Lower is calmer."), 1, 0)
        plate.body.addLayout(grid)

        # **How much he fills the quiet laps.** The setting has existed since
        # the colour calls were written and nothing ever exposed it, so the
        # engineer has only ever run at `normal` - there was no way to ask him
        # for more. Strategy is unaffected at every level: this governs the
        # radio that is not an instruction. See `race/colour.py`.
        plate.body.addWidget(self._rule_label("How much he says"))
        self.colour_calls = QComboBox()
        self.colour_calls.addItem("Quiet — instructions only", COLOUR_QUIET)
        self.colour_calls.addItem("Normal", COLOUR_NORMAL)
        self.colour_calls.addItem("Chatty", COLOUR_CHATTY)
        block_wheel(self.colour_calls)
        plate.body.addWidget(Field(
            "On the laps that carry no instruction", self.colour_calls,
            hint="Strategy calls are unaffected. Quiet means off, not less "
                 "often."))
        return plate

    def _tuning_box(self, low: float, high: float, step: float,
                    value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(low, high)
        box.setSingleStep(step)
        box.setDecimals(2)
        box.setValue(value)
        block_wheel(box)
        return box

    def _rule_label(self, text: str) -> StencilLabel:
        label = StencilLabel(text, size=11, tracking=12.0)
        label.setContentsMargins(0, 8, 0, 0)
        return label

    def _footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(72)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, theme.GAP, 0, theme.GAP)
        row.setSpacing(theme.GAP)
        self.footer_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        row.addWidget(self.footer_note, 1)
        save = MarkButton("Save settings", primary=True)
        save.clicked.connect(self._on_save)
        row.addWidget(save)
        return bar

    # ---------------------------------------------------------------- state

    def set_session_open(self, open_now: bool) -> None:
        """Whether a session is running, so the device list knows to wait."""
        self._session_open = bool(open_now)

    def showEvent(self, event) -> None:                  # noqa: N802 - Qt
        super().showEvent(event)
        # Scheduled, not run inline: the screen paints first, and PortAudio
        # is touched after the driver can already see where he is.
        QTimer.singleShot(0, self._fill_audio_devices)

    def _fill_audio_devices(self) -> None:
        """Enumerate the sound devices, once, when the screen is looked at.

        **Not while a session is open.** Enumerating tears PortAudio down and
        rebuilds it; `audio_devices` defers that for up to six seconds per
        call while something is playing, and there are two calls. A visit to
        this screen mid-race would freeze the window for twelve seconds and
        drop the transducer for the duration. A list that is one headset out
        of date, and says so, is the better failure.
        """
        if self._audio_filled or getattr(self, "_session_open", False):
            if not self._audio_filled:
                self.note_rig("Device list not refreshed - a session is "
                              "open. Close it to re-read the sound devices.",
                              warn=True)
            return
        self._audio_filled = True
        for combo, kind, sync in ((self.audio_output, "output",
                                   self._audio_syncs[0]),
                                  (self.audio_input, "input",
                                   self._audio_syncs[1])):
            chosen = combo.currentData()
            for _index, name in audio_devices.devices(kind):
                if combo.findData(name) < 0:
                    combo.addItem(name, name)
            # **Re-selected, or the setting is silently lost.** `load` runs
            # before this and cannot find a device that was not listed yet,
            # so it falls back to index 0 - and `values()` would then report
            # "System default" for a device the driver had actually chosen.
            if self._loaded is not None:
                chosen = (self._loaded.audio_output_device if kind == "output"
                          else self._loaded.audio_input_device)
            index = combo.findData(chosen)
            combo.setCurrentIndex(index if index >= 0 else 0)
            if callable(sync):
                sync()

    def load(self, settings: Settings) -> None:
        # Kept so `values()` can carry through the fields with no control on
        # this screen. Building a fresh Settings from the widgets meant every
        # Save silently rewrote `speech_backend` and `speech_sensitivity` back
        # to their defaults - settings that could be stored and never set.
        self._loaded = settings
        self.udp_port.setValue(settings.udp_port)
        self.udp_source_ip.setText(settings.udp_source_ip)
        index = self.feed_source.findData(settings.feed_source)
        self.feed_source.setCurrentIndex(max(0, index))
        self.ps5_ip.setText(settings.ps5_ip)
        self.banner_enabled.setChecked(settings.banner_enabled)
        self.driver_board_enabled.setChecked(settings.driver_board_enabled)
        self._sync_feed_source()
        self.game_version.setText(settings.game_version)
        for combo, chosen in ((self.audio_output, settings.audio_output_device),
                              (self.audio_input, settings.audio_input_device)):
            index = combo.findData(chosen)
            combo.setCurrentIndex(index if index >= 0 else 0)
        self.haptics_enabled.setChecked(settings.haptics_enabled)
        self.haptics_gain.setValue(settings.haptics_gain)
        self.wind_enabled.setChecked(settings.wind_enabled)
        self.ptt_enabled.setChecked(settings.ptt_enabled)
        self.ptt_key.setCurrentText(settings.ptt_key)
        self.ptt_in_practice.setChecked(settings.ptt_in_practice)
        self.ptt_toggle.setChecked(settings.ptt_toggle)
        self.hud_wear_enabled.setChecked(settings.hud_wear_enabled)
        index = self.hud_source.findData(settings.hud_source)
        self.hud_source.setCurrentIndex(max(0, index))
        self.obs_host.setText(settings.obs_host)
        self.obs_port.setValue(settings.obs_port)
        self.obs_password.setText(settings.obs_password)
        self.hud_interval.setValue(settings.hud_sample_interval_s)
        self._sync_hud_source()
        self.beep_enabled.setChecked(settings.beep_enabled)
        index = self.colour_calls.findData(settings.colour_calls)
        self.colour_calls.setCurrentIndex(max(0, index))
        self.length_scale.setValue(settings.voice_length_scale)
        self.noise_scale.setValue(settings.voice_noise_scale)
        self.noise_w_scale.setValue(settings.voice_noise_w_scale)

    def _sync_feed_source(self) -> None:
        """Show the address box only where it is read.

        In relay mode it is not a destination and never was, and leaving
        it enabled is how somebody comes to believe the app already talks
        to the console.
        """
        self.ps5_field.setVisible(self.feed_source.currentData() == FEED_PS5)

    def values(self) -> Settings:
        # `replace`, not a fresh Settings: anything this screen has no control
        return replace(
            getattr(self, "_loaded", Settings()),
            udp_port=self.udp_port.value(),
            udp_source_ip=self.udp_source_ip.text().strip(),
            feed_source=self.feed_source.currentData(),
            ps5_ip=self.ps5_ip.text().strip(),
            banner_enabled=self.banner_enabled.isChecked(),
            driver_board_enabled=self.driver_board_enabled.isChecked(),
            # `driver_board_geometry` deliberately has no line here: it has no
            # control on this screen, and the `replace` above is exactly what
            # carries such a field through untouched.
            # **No fallback.** Coercing an empty box to "1.70" was the same
            # hard-coded default wearing a different hat, and it outlived the
            # patch that made it wrong.
            game_version=self.game_version.text().strip(),
            ptt_enabled=self.ptt_enabled.isChecked(),
            ptt_key=self.ptt_key.currentText().strip().lower(),
            ptt_in_practice=self.ptt_in_practice.isChecked(),
            ptt_toggle=self.ptt_toggle.isChecked(),
            hud_wear_enabled=self.hud_wear_enabled.isChecked(),
            hud_source=self.hud_source.currentData() or HUD_SOURCE_OBS,
            obs_host=self.obs_host.text().strip(),
            obs_port=self.obs_port.value(),
            # Not stripped: a password may legitimately end in a space,
            # and silently trimming one is a failure nobody can see.
            obs_password=self.obs_password.text(),
            hud_sample_interval_s=self.hud_interval.value(),
            beep_enabled=self.beep_enabled.isChecked(),
            colour_calls=self.colour_calls.currentData() or COLOUR_NORMAL,
            voice_length_scale=self.length_scale.value(),
            voice_noise_scale=self.noise_scale.value(),
            voice_noise_w_scale=self.noise_w_scale.value(),
            audio_output_device=self.audio_output.currentData() or "",
            audio_input_device=self.audio_input.currentData() or "",
            haptics_enabled=self.haptics_enabled.isChecked(),
            haptics_gain=self.haptics_gain.value(),
            wind_enabled=self.wind_enabled.isChecked(),
        )

    def show_capabilities(self, *, speech: str, hook: bool) -> None:
        """What actually loaded on this machine, as opposed to what was asked
        for. Measured, so it is stencilled."""
        button = "keyboard hook loaded" if hook else "NO keyboard hook"
        self.engine_note.setText(f"speech: {speech} · {button}")
        self.engine_note.setStyleSheet(
            f"color: {theme.STENCIL if hook else theme.WARNING};"
            "background: transparent;")

    def set_listening(self, listening: bool) -> None:
        self._listening = listening
        self.listen_button.setText(
            "STOP LISTENING" if listening else "LISTEN FOR THE BUTTON")
        if listening:
            self.note_ptt("Listening. Press the button on the wheel.")

    def note_ptt(self, text: str, *, warn: bool = False) -> None:
        self.ptt_note.setText(text)
        self.ptt_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def note_capture(self, text: str, *, warn: bool = False) -> None:
        self.capture_note.setText(text)
        self.capture_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def set_capturing(self, on: bool) -> None:
        """Reflect what is actually happening, not what was clicked."""
        was = self.capture_button.blockSignals(True)
        self.capture_button.setChecked(on)
        self.capture_button.setText(
            "Stop recording" if on else "Record raw session")
        self.capture_button.blockSignals(was)

    def set_feed_testing(self, testing: bool) -> None:
        """The four seconds the socket is open, said out loud."""
        self.test_feed_button.setEnabled(not testing)
        self.test_feed_button.setText(
            "Listening…" if testing else "Test the feed")
        if testing:
            self.note_feed("Listening for four seconds. If the console is "
                           "streaming, this will say what decoded.")

    def note_feed(self, text: str, *, warn: bool = False) -> None:
        self.feed_note.setText(text)
        self.feed_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def note_beep(self, text: str, *, warn: bool = False) -> None:
        self.beep_note.setText(text)
        self.beep_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};")

    # --------------------------------------------------------------- actions

    def _on_listen(self) -> None:
        self.listen_toggled.emit(not self._listening)

    def _on_save(self) -> None:
        try:
            self.values().validate()
        except ValueError as exc:
            self.note(f"Refused: {exc}", warn=True)
            return
        self.note("")
        self.saved.emit(self.values())
