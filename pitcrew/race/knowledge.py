"""What Ludo knows about racing here, that George's rules cannot work out.

**This is the load-bearing piece of "smarter".** The driver's answer, 29 Aug
2026, to what was wrong with the engineer: *"more intuitive and smarter, to
give me what I need in a race and adapt to the race."* And then, in the same
interview: no model runs in the live loop, and the playbook is a rail rather
than a briefing. Those three together leave exactly one place for intelligence
to enter - **numbers, written at the desk, read by deterministic rules.**

The archive already holds measurements: `track_clock`, `tyre_models`, a refuel
rate. What it has never held is judgement. It has never known that pit loss at
Watkins is 15.7 s ex-fuel against the 20 s the plan declared, that the undercut
is weak in GT7 and the overcut is not, or that a particular rival always stops
early. George was generic at every circuit because nothing told him otherwise.

### The six fields, and why each one is here

1. **The stop, measured.** `pit_loss_s` and `refuel_l_per_s`. Both were
   measured at Watkins - 15.7 s and 1.001 L/s - against a plan that declared
   20 s, and nothing carried the measurement into the next race.
2. **What a stop is worth against the cars around him.** `undercut_s` and
   `overcut_s`, signed so positive means the manoeuvre gains. F1 instincts are
   wrong here and the app cannot derive that.
3. **The limit Ludo expects to bind**, and what would change it. Rule 12 is
   about reporting the constraint that actually bound the answer; this is the
   same discipline pointed forwards.
4. **Who he is racing.** Filled by the post-race replay pass - rivals are read
   after a race, never during one, because in VR the HUD moves with his head.
5. **What a slipstream is worth here.** CLAUDE.md 5.3 calls the tow the
   highest-value live call the app can make and says the feed cannot give it.
   It still cannot. This is where the number comes from instead.
6. **Calls Ludo does not want made here, and why.** The rail expressed as
   knowledge rather than as a veto - *"don't call short-shift here, the
   straights are too short to pay"* - which is Ludo teaching George rather than
   muzzling him.

Plus `wear_rates_json`, which the replay wear pass fills: George stops
modelling wear during a race and runs a rate that was measured.

### Absent is a state, and it is announced

A race arrives with no record and George falls back to the generic model -
**and says so once at the green.** Silent fallback is the defect pattern that
made the gauge ratchet invisible for a whole race: the number setting the bar
never appeared anywhere the driver could see it. "Unconfirmed" is a word he can
act on; silence is not.

### Nothing here is measured by the app

Every field is declared by a person. It is stored as such, it is reported as
such, and no rule may present one of these numbers as something the telemetry
saw. CLAUDE.md rule 5.
"""
from __future__ import annotations

import json

from pitcrew.diagnostics import log
from dataclasses import dataclass, field

# What George says at the green when nobody wrote anything down. Said once, and
# said in the same shape as every other confidence statement he makes.
NO_NOTES = "No notes for this circuit. I'm running on the model."

def silenceable() -> frozenset:
    """The call kinds `calls_off` may name.

    A record naming anything else is refused rather than ignored, because a
    rule the driver believes is in force and silently is not is worse than no
    rule - the same doctrine as the playbook's own `TRIGGERS`.

    **Imported inside the function, not at module scope.** `calls.py` takes
    `NO_NOTES` from here, so the two would import each other; `calls` owns the
    vocabulary and is the lower of the two, so this is the direction that
    yields.
    """
    from pitcrew.race.calls import REGISTER

    return frozenset(REGISTER)


def _multiplier(raw) -> float | None:
    """`"2x"`, `"2"`, `2`, `2.0` -> 2.0; nothing -> None."""
    if raw is None:
        return None
    text = str(raw).strip().lower().rstrip("x")
    try:
        return float(text)
    except ValueError:
        return None


class KnowledgeError(ValueError):
    """A record that cannot be trusted, refused rather than half-read."""


@dataclass(frozen=True)
class Knowledge:
    """One circuit's briefing. Every field optional; none of them measured here."""
    circuit_key: str = ""
    event_id: int | None = None
    pit_loss_s: float | None = None
    refuel_l_per_s: float | None = None
    undercut_s: float | None = None
    overcut_s: float | None = None
    expected_constraint: str | None = None
    constraint_watch: str | None = None
    rivals: tuple = ()
    tow_s_per_lap: float | None = None
    calls_off: tuple = ()
    wear_rates: dict = field(default_factory=dict)
    author: str | None = None
    game_version: str | None = None
    notes: str | None = None
    written_at: str | None = None

    def validate(self) -> None:
        """Refuse a record that would silence a call nobody named.

        **Named rather than ignored.** `calls_off` is the one field that
        changes what George does rather than what he knows, so a typo in it is
        a call that quietly never happens. `REGISTER` is the list of kinds that
        exist, and a kind outside it cannot be silenced because it cannot be
        said.
        """
        known = silenceable()
        for entry in self.calls_off:
            kind = (entry or {}).get("kind")
            if kind not in known:
                raise KnowledgeError(
                    f"{kind!r} is not a call George can make, so it cannot be "
                    f"turned off. Known kinds: {', '.join(sorted(known))}")
            if not (entry or {}).get("why"):
                raise KnowledgeError(
                    f"the {kind!r} entry has no reason. A call silenced with "
                    f"no reason on file is one nobody can put back")
        for number in (self.pit_loss_s, self.refuel_l_per_s,
                       self.tow_s_per_lap):
            if number is not None and number <= 0:
                raise KnowledgeError(
                    f"{number!r} is not a time or a rate - a zero here would "
                    f"price a stop at nothing")

    def silences(self, kind: str) -> str | None:
        """Why Ludo does not want this call made here, or None."""
        for entry in self.calls_off:
            if (entry or {}).get("kind") == kind:
                return entry.get("why")
        return None

    def wear_per_lap(self, compound: str | None,
                     multiplier: str | float | None = None
                     ) -> tuple[float | None, int]:
        """The measured wear rate for this compound, with its sample count.

        Every aggregate carries its sample count (CLAUDE.md 4.4): a rate from
        one stint and one from six are not the same claim, and the second
        number is what lets a caller decide whether to trust the first.

        **And only at the multiplier it was measured at** (CLAUDE.md 5.2:
        multiplier linearity is assumed, never proven; never silently
        convert). An entry that names its multiplier is refused for a race at
        a different one - Sardegna at x8 must not inherit a rate fitted at
        x2. An entry that names none is accepted and logged as assumed,
        because the older rows on file predate the field and refusing them
        all would silence every briefed rate at once.
        """
        entry = (self.wear_rates or {}).get((compound or "").upper() or None)
        if not entry:
            return None, 0
        theirs = _multiplier(entry.get("multiplier"))
        ours = _multiplier(multiplier)
        if theirs is not None and ours is not None and theirs != ours:
            log("race").warning(
                "wear rate for %s at %s was measured at x%g and this race "
                "runs x%g - refused, never converted (CLAUDE.md 5.2)",
                compound, self.circuit_key, theirs, ours)
            return None, 0
        if theirs is None and ours is not None:
            log("race").info(
                "wear rate for %s at %s names no multiplier; used for a x%g "
                "race as [ASSUMED]", compound, self.circuit_key, ours)
        return entry.get("perLap"), int(entry.get("samples") or 0)

    def as_export(self) -> dict:
        """For the payload's audit trail. Declared, never measured."""
        return {
            "source": "race-engineer, declared",
            "circuitKey": self.circuit_key,
            "eventId": self.event_id,
            "pitLossS": self.pit_loss_s,
            "refuelLPerS": self.refuel_l_per_s,
            "undercutS": self.undercut_s,
            "overcutS": self.overcut_s,
            "expectedConstraint": self.expected_constraint,
            "constraintWatch": self.constraint_watch,
            "rivals": list(self.rivals) or None,
            "towSPerLap": self.tow_s_per_lap,
            "callsOff": list(self.calls_off) or None,
            "wearRates": self.wear_rates or None,
            "author": self.author,
            "gameVersion": self.game_version,
            "writtenAt": self.written_at,
            "notes": self.notes,
        }


def from_row(row) -> Knowledge:
    """One stored row as a `Knowledge`. JSON columns decoded, never guessed."""
    return Knowledge(
        circuit_key=row["circuit_key"],
        event_id=row["event_id"],
        pit_loss_s=row["pit_loss_s"],
        refuel_l_per_s=row["refuel_l_per_s"],
        undercut_s=row["undercut_s"],
        overcut_s=row["overcut_s"],
        expected_constraint=row["expected_constraint"],
        constraint_watch=row["constraint_watch"],
        rivals=tuple(_loads(row["rivals_json"], [])),
        tow_s_per_lap=row["tow_s_per_lap"],
        calls_off=tuple(_loads(row["calls_off_json"], [])),
        wear_rates=_loads(row["wear_rates_json"], {}),
        author=row["author"],
        game_version=row["game_version"],
        notes=row["notes"],
        written_at=row["written_at"],
    )


def for_event(store, event: dict | None) -> Knowledge | None:
    """This race's briefing, or None where nobody wrote one.

    **The event's own record wins over the circuit's.** Pit loss and the tow
    are track constants and are written once with a null `event_id`; rival
    tendencies and the expected constraint belong to one race. Preferring the
    specific means the constants do not have to be re-typed every round.
    """
    if not event:
        return None
    from pitcrew.analysis.resolve import circuit_key

    track = event.get("track")
    if not track:
        return None
    return store.get_race_knowledge(circuit_key(track, event.get("layout")),
                                    event.get("id"))


def _loads(raw, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, ValueError):                          # pragma: no cover
        return fallback
