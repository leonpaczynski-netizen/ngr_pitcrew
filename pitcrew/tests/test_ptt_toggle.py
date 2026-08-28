"""Tap to open the radio, tap to close it, static both ways.

*"I don't have time to hold the button. One press, hear a radio static sound so
I know it's recording, then it records, I talk, radio static to confirm to me
recording has stopped, and then engineer responds."* - the driver, 22 Aug.

Hold-to-talk asks for a hand that is on a wheel, and the questions come in the
places where both hands are busy. With the button no longer held there is also
nothing to tell him the microphone is open, which is what the two bursts are
for - and why the opening one plays **before** the stream opens and the closing
one **after** it shuts, so neither ends up in the transcript.
"""
from __future__ import annotations

import threading
import time

from pitcrew.engineer import gate
from pitcrew.engineer.ptt import (
    LOST_KEY_UP_S,
    MAX_CAPTURE_S,
    KeyboardListener,
    PushToTalk,
)


class Burst:
    def __init__(self, label): self.label, self.played = label, 0

    def play_blocking(self): self.played += 1


class Recogniser:
    """Records the order of everything against the bursts."""

    name = "moonshine"

    def __init__(self, heard="how are my tyres", log=None):
        self.heard, self.last_reason, self.log = heard, None, log
        self.open_count = 0

    def begin(self):
        self.open_count += 1
        self.log.append("mic-open")

    def end(self):
        self.log.append("mic-shut")
        return self.heard


def build(**over):
    log: list[str] = []
    opening, closing = Burst("in"), Burst("out")

    class Watched(Burst):
        pass

    def note(label):
        def play():
            log.append(f"static-{label}")
        return play

    opening.play_blocking = note("in")
    closing.play_blocking = note("out")
    recogniser = over.pop("recogniser", None) or Recogniser(log=log)
    if "bursts" in over:
        opening, closing = over.pop("bursts") or (None, None)
    said: list[str] = []
    talk = PushToTalk(snapshot=lambda: {}, speak=lambda text: (
                          said.append(text), log.append("spoke"))[0],
                      recogniser=recogniser,
                      bursts=(opening, closing), **over)
    return talk, log, said, recogniser


def test_the_order_is_static_mic_talk_mic_static_answer():
    """**The whole request, as one sequence.** The opening burst is before the
    stream opens and the closing one after it shuts, so the static he hears is
    never static the recogniser hears."""
    talk, log, said, _ = build()
    talk.tap()
    talk.tap()
    assert log == ["static-in", "mic-open", "mic-shut", "static-out", "spoke"]
    assert said


def test_one_tap_opens_and_leaves_it_open():
    talk, log, _, _ = build()
    talk.tap()
    assert talk.recording
    assert log == ["static-in", "mic-open"]


def test_the_second_tap_closes_it():
    talk, _, _, _ = build()
    talk.tap()
    talk.tap()
    assert not talk.recording


def test_a_third_tap_starts_a_new_question_rather_than_reopening_the_old():
    talk, log, _, recogniser = build()
    for _ in range(3):
        talk.tap()
    assert recogniser.open_count == 2
    assert talk.recording


def test_a_microphone_that_will_not_open_says_so_and_does_not_arm():
    """Otherwise he talks into a radio that is not on and finds out at the end
    of the question - which at racing speed is a whole corner wasted."""
    class Dead(Recogniser):
        def begin(self):
            self.log.append("mic-open")
            raise OSError("device claimed")

    talk, log, said, _ = build(recogniser=Dead(log=[]))
    talk._recogniser.log = log
    talk.tap()
    assert not talk.recording, "armed on a microphone that never opened"
    assert any("microphone" in text.lower() for text in said)
    assert talk.last_verdict.reason == gate.NO_DEVICE


def test_hold_to_talk_still_works_for_anyone_who_wants_it():
    talk, log, _, _ = build(toggle=False)
    talk.begin()
    talk.end()
    assert log[:2] == ["mic-open", "mic-shut"]
    assert "static-in" not in log, "hold mode announces itself by being held"


def test_a_radio_left_open_closes_itself_on_the_capture_cap():
    """**He may never press again.** In hold mode the button coming up is
    guaranteed; here it is not, and a radio left open would sit there with the
    capture already truncated and no answer ever spoken."""
    talk, log, said, _ = build()
    talk.tap()
    assert talk._deadline is not None
    assert talk._deadline.interval > MAX_CAPTURE_S
    talk._expired()
    assert not talk.recording
    assert said, "the cap closed the radio without answering"


def test_closing_normally_cancels_the_cap_timer():
    talk, _, _, _ = build()
    talk.tap()
    talk.tap()
    assert talk._deadline is None


def test_a_card_that_cannot_render_static_still_delivers_the_answer():
    """Confirmation is not the question."""
    talk, log, said, _ = build(bursts=(None, None))
    talk.tap()
    talk.tap()
    assert said


def test_static_that_throws_still_delivers_the_answer():
    class Broken:
        def play_blocking(self): raise RuntimeError("no output device")

    talk, log, said, _ = build(bursts=(Broken(), Broken()))
    talk.tap()
    talk.tap()
    assert said


# --------------------------------------------------------------- the button
#
# Everything below is about the thread the button arrives on rather than about
# what it asks for. `pynput` calls its callbacks from inside a `WH_KEYBOARD_LL`
# hook procedure, and Windows stops giving events to a hook that does not
# return inside `LowLevelHooksTimeout` - 300 ms by default, against a measured
# 382-787 ms for the opening static burst alone on 28 Aug 2026. The event it
# stopped giving was the **key-up**, and with no key-up the auto-repeat latch
# in `KeyboardListener` swallowed the next press: eleven exchanges on record
# between 22 and 28 Aug and not one of them ever closed on a second tap.


class FakeListener:
    """A button with the wires brought out, so a test can press it."""

    def __init__(self) -> None:
        self.on_press = self.on_release = None
        self.options: dict = {}

    def start(self, on_press, on_release, **options) -> None:
        self.on_press, self.on_release, self.options = (
            on_press, on_release, options)

    def stop(self) -> None:
        self.on_press = self.on_release = None


def test_a_press_returns_to_windows_before_the_work_is_done():
    """**The load-bearing one.** The hook has to be given back inside 300 ms,
    and opening a card and a microphone does not fit in 300 ms - so the press
    may only queue the work, never do it."""
    holding = threading.Event()

    class Slow(Recogniser):
        def begin(self):
            self.open_count += 1
            self.log.append("mic-open")
            holding.wait(5)             # the card, taking its time

    hook = FakeListener()
    talk, log, _, _ = build(recogniser=Slow(log=[]), listener=hook)
    talk._recogniser.log = log
    talk.start()

    started = time.perf_counter()
    hook.on_press()
    handed_back = time.perf_counter() - started

    assert handed_back < 0.05, (
        f"the button thread waited {handed_back * 1000:.0f} ms for the "
        f"microphone - Windows drops a hook that overruns 300 ms")
    holding.set()
    assert talk._settle(), "the press never finished off the button thread"
    talk.stop()


def test_the_press_still_gets_the_radio_open():
    """Off the button thread is not the same as not at all."""
    hook = FakeListener()
    talk, log, _, _ = build(listener=hook)
    talk.start()
    hook.on_press()
    assert talk._settle()
    assert log == ["static-in", "mic-open"]
    assert talk.recording
    talk.stop()


def test_two_taps_in_quick_succession_keep_their_order():
    """A close arriving while the open is still in its burst has to happen
    second, or it ends a radio that is not open yet. One queue, one thread."""
    hook = FakeListener()
    talk, log, said, _ = build(listener=hook)
    talk.start()
    hook.on_press()
    hook.on_press()
    assert talk._settle()
    assert log == ["static-in", "mic-open", "mic-shut", "static-out", "spoke"]
    assert said
    assert not talk.recording
    talk.stop()


def test_the_button_is_armed_against_a_lost_key_up():
    hook = FakeListener()
    talk, _, _, _ = build(listener=hook)
    talk.start()
    assert hook.options == {"lost_key_up_after_s": LOST_KEY_UP_S}
    talk.stop()


def test_hold_mode_goes_off_the_button_thread_too_and_keeps_its_latch():
    """`begin` opens a microphone, which is the same 300 ms problem from the
    other end. What hold mode must not take is the lost-key-up guard: there
    the latch tracks a key that really is held, and clearing it early would
    cut his question off mid-sentence."""
    hook = FakeListener()
    talk, log, _, _ = build(toggle=False, listener=hook)
    talk.start()
    assert hook.options == {}, "a held key must not be written off"
    hook.on_press()
    hook.on_release()
    assert talk._settle()
    assert log[:2] == ["mic-open", "mic-shut"]
    talk.stop()


def test_stopping_and_starting_again_leaves_a_working_button():
    """Rebinding the key does both, mid-session."""
    hook = FakeListener()
    talk, log, _, _ = build(listener=hook)
    talk.start()
    talk.stop()
    talk.start()
    hook.on_press()
    assert talk._settle()
    assert log == ["static-in", "mic-open"]
    talk.stop()


def test_a_radio_left_open_does_not_survive_into_the_next_session():
    """CLAUDE.md rule 11. Left armed, the first tap of the next session is a
    close - so he opens the radio, says his piece, and the app answers a
    question it never recorded."""
    hook = FakeListener()
    talk, log, _, _ = build(listener=hook)
    talk.start()
    hook.on_press()
    assert talk._settle()
    assert talk.recording
    talk.stop()
    assert not talk.recording

    log.clear()
    talk.start()
    hook.on_press()
    assert talk._settle()
    assert log == ["static-in", "mic-open"], "the new session opened a close"
    talk.stop()


# ------------------------------------------------------- the auto-repeat latch


class FakeKeyboard:
    """Stands in for `pynput.keyboard`, with the key events under test control.

    A real one installs a global Windows hook, which is not a thing to do
    eleven times in a test run - and the behaviour under test is what happens
    when the hook does *not* deliver an event, which a real one will not do to
    order.
    """

    class _Key:
        name = "f8"

    daemon = True

    def __init__(self) -> None:
        self._on_press = self._on_release = None

    def Listener(self, on_press, on_release):   # noqa: N802 - pynput's name
        self._on_press, self._on_release = on_press, on_release
        return self

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def press(self) -> None:
        self._on_press(self._Key())

    def release(self) -> None:
        self._on_release(self._Key())


def a_button(**options):
    keys = FakeKeyboard()
    listener = KeyboardListener("f8")
    listener._keyboard = keys
    taps: list[str] = []
    listener.start(lambda: taps.append("tap"), lambda: None, **options)
    return keys, listener, taps


def test_auto_repeat_is_still_swallowed():
    """The latch is not the defect and does not go. A button held past the
    repeat delay produces more key-downs with no key-up between them, and each
    one would otherwise toggle the radio."""
    keys, listener, taps = a_button(lost_key_up_after_s=LOST_KEY_UP_S)
    keys.press()
    keys.press()
    keys.press()
    assert taps == ["tap"]
    listener.stop()


def test_a_lost_key_up_does_not_eat_the_next_press():
    """**The bug, in one test.** Windows dropped the key-up of the press that
    opened the radio, `_down` stayed set, and the press he made to close it
    was discarded - which is why every exchange on record ran to the cap."""
    keys, listener, taps = a_button(lost_key_up_after_s=0.05)
    keys.press()                        # its key-up never arrives
    time.sleep(0.15)
    keys.press()
    assert taps == ["tap", "tap"], "the second press was swallowed"
    listener.stop()


def test_a_key_up_that_does_arrive_clears_the_latch_without_waiting():
    keys, listener, taps = a_button(lost_key_up_after_s=5.0)
    keys.press()
    keys.release()
    keys.press()
    assert taps == ["tap", "tap"]
    listener.stop()


def test_hold_mode_never_writes_a_held_key_off():
    """With no cap the latch is only ever cleared by a real key-up, which is
    what a held button needs: a long question is a held key, not a lost one."""
    keys, listener, taps = a_button()
    keys.press()
    time.sleep(0.15)
    keys.press()
    assert taps == ["tap"]
    listener.stop()


def test_a_close_that_worked_leaves_a_line_too(caplog):
    """CLAUDE.md rule 10. Only the cap wrote a line, so eleven exchanges of
    *"closed on the cap - no second press"* read as a driver who stopped
    pressing rather than as a button eating every second press. Both outcomes
    say which one they were, or the log cannot tell them apart."""
    talk, _, _, _ = build()
    with caplog.at_level("INFO", logger="pitcrew.ptt"):
        talk.tap()
        talk.tap()
    closes = [r.getMessage() for r in caplog.records
              if "radio closed" in r.getMessage()]
    assert closes == ["radio closed on the second press"]


def test_the_cap_still_says_it_was_the_cap(caplog):
    talk, _, _, _ = build()
    with caplog.at_level("INFO", logger="pitcrew.ptt"):
        talk.tap()
        talk._expired()
    closes = [r.getMessage() for r in caplog.records
              if "radio closed" in r.getMessage()]
    assert closes == [f"radio closed on the {MAX_CAPTURE_S:.0f}s cap - "
                      f"no second press"]
