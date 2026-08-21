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

from pitcrew.engineer import gate
from pitcrew.engineer.ptt import MAX_CAPTURE_S, PushToTalk


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
