"""Single source of truth for GT7 tyre compound definitions.

All tabs, AI prompts, and telemetry import from here so compound lists
stay consistent without editing multiple files.

**The four-tier temperature band that used to live here has been deleted, not
repaired.** It carried `cold_max` / `warming_max` / `optimal_max` / `hot_max`
per compound, flagged `window_measured = False`, and kept "for the UI's colour
bands". The flag did not stop it being read, and the shape itself was the
defect: a four-zone window with a cold side, for which **no evidence of any
kind exists in GT7.**

What the research actually found, Aug 2026:

* **Nobody has ever published an optimal tyre-temperature window for GT7** -
  not Polyphony, not the GTPlanet testing community, not any telemetry
  project. The question was asked directly on GTPlanet in April 2025 and
  answered "I didn't test the lower range". It has not been answered since.
* The deleted numbers were **real-world racing-slick figures** (90-110 degC),
  traceable to two ancient GTPlanet threads quoting motorsport engineering.
  GT7's own channel never goes there: 51 laps of Monza sat 68-78 degC and 18
  laps of Yas Marina sat 72-88 degC, and GT7 fits a fresh set at exactly
  70.0 degC - which was precisely the Racing Soft "cold ceiling", so a Racing
  Soft could never once reach its own window. That is CLAUDE.md §4 rule 8's
  failure mode exactly.
* **One credible figure survives**, and it is an UPPER WEAR threshold rather
  than a window: see `WEAR_ONSET_C` below.

So the compound record now carries one sourced number and its whole
provenance, and nothing else about temperature. There is no `cold_max`,
because nothing in the evidence base describes a cold side.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

# --- the one sourced temperature figure, and everything that qualifies it ---
#
# Racing Soft 88, Racing Medium 90, Racing Hard 93 degC: the temperature above
# which tyre wear starts climbing disproportionately.
#
# **Why this one is usable at all:** it was read off SimHub, whose GT7 plugin
# consumes the same single `float tyreTemp[4]` out of the same UDP stream this
# app reads. It is already in our units and our channel - no conversion, no
# reinterpretation. That is rare, and it is the only reason the figure is here.
#
# **It is a wear threshold, not a window.** The author states he did not test
# the low end at all, so there is no cold side and this app must never invent
# one.
WEAR_ONSET_C: dict[str, float] = {"RS": 88.0, "RM": 90.0, "RH": 93.0}
WEAR_ONSET_SOURCE = "gtplanet:DigitalRelay:2025-02-15"
WEAR_ONSET_GAME_VERSION = "GT7 1.55"
WEAR_ONSET_KIND = "wear-onset threshold - NOT a grip window"
WEAR_ONSET_METHOD = (
    "held-temperature wear test: 5-6 races per compound each driven to hold a "
    "target temperature, wear read off the in-game icon at lap 10. One car "
    "(Gr.3 911), one track (Northern Isle), 4x wear, n=1")
WEAR_ONSET_CAVEATS: tuple[str, ...] = (
    "the slip/temperature confound is unresolved - holding temperature down "
    "requires driving with less slip, which is independently less wear "
    "(bduddy, same thread, 2025-02-16)",
    "the aggregate is unknown: hottest wheel, axle mean or four-wheel mean is "
    "never stated, and this driver's axles live 8-11 degC apart, which is "
    "wider than the gap between the RS and RH thresholds",
    "the thermal model changed after 1.55 with no patch note at all - the "
    "author of gt7telemetry reported Racing Softs heating less and warming up "
    "slower after 1.57 (Bornhall, 2025-03-30), unanswered and uncontradicted",
    "no cold-side figure exists; the author explicitly did not test it",
    "this driver's fronts run 72-77 degC, entirely below the test's lowest "
    "point, so the threshold speaks only to his rear axle",
)

# **No Sports, Comfort or Wet figures.** None have ever been published for GT7
# in any form. Missing is null (CLAUDE.md §4 rule 3), never a guess tiered off
# the Racing numbers - which is how the deleted table came to exist.


@dataclass(frozen=True)
class TyreCompound:
    """One GT7 compound, and the one sourced temperature figure it has.

    `wear_onset_c` is None for every compound nobody has tested, which is most
    of them. None means unmeasured, and no call may be made against it.
    """
    name: str          # "Racing Soft"
    code: str          # "RS" - used in saves, strategy stints, DB
    category: str      # "Racing" | "Sports" | "Comfort" | "Wet"
    wet: bool          # True for Intermediate and Heavy Wet

    @property
    def wear_onset_c(self) -> float | None:
        """Above this, wear climbs disproportionately. None where untested."""
        return WEAR_ONSET_C.get(self.code)

    @property
    def wear_onset_source(self) -> str | None:
        """One line of provenance, or None where there is no figure."""
        if self.wear_onset_c is None:
            return None
        return (f"{WEAR_ONSET_KIND}; {WEAR_ONSET_SOURCE}, tested on "
                f"{WEAR_ONSET_GAME_VERSION}; {WEAR_ONSET_METHOD}")


ALL_COMPOUNDS: tuple[TyreCompound, ...] = (
    TyreCompound("Comfort Hard",   "CH", "Comfort", False),
    TyreCompound("Comfort Medium", "CM", "Comfort", False),
    TyreCompound("Comfort Soft",   "CS", "Comfort", False),
    TyreCompound("Sports Hard",    "SH", "Sports",  False),
    TyreCompound("Sports Medium",  "SM", "Sports",  False),
    TyreCompound("Sports Soft",    "SS", "Sports",  False),
    TyreCompound("Racing Hard",    "RH", "Racing",  False),
    TyreCompound("Racing Medium",  "RM", "Racing",  False),
    TyreCompound("Racing Soft",    "RS", "Racing",  False),
    TyreCompound("Intermediate",   "IM", "Wet",     True),
    TyreCompound("Heavy Wet",      "HW", "Wet",     True),
)

_BY_CODE: dict[str, TyreCompound] = {c.code: c for c in ALL_COMPOUNDS}

_ALIASES: dict[str, str] = {c.name.lower(): c.code for c in ALL_COMPOUNDS}
_ALIASES.update({
    # Old "Racing: Soft" style used in Setup Builder before Phase 7
    "racing: soft":         "RS",
    "racing: medium":       "RM",
    "racing: hard":         "RH",
    # Old parenthetical style used in TYRE_TEMP_PRESETS before Phase 7
    "racing soft (rs)":     "RS",
    "racing medium (rm)":   "RM",
    "racing hard (rh)":     "RH",
    "intermediate (im)":    "IM",
    "wet (w)":              "HW",
    # Short codes
    "rs": "RS", "rm": "RM", "rh": "RH",
    "sh": "SH", "sm": "SM", "ss": "SS",
    "ch": "CH", "cm": "CM", "cs": "CS",
    "im": "IM",
    "w":  "HW", "hw": "HW",
    # Common English words
    "soft":   "RS",
    "medium": "RM",
    "hard":   "RH",
    "inter":  "IM",
    "rain":   "HW",
    "wet":    "HW",
})


def compound_names() -> list[str]:
    """Ordered display names for UI dropdowns (Comfort → Sports → Racing → Wet)."""
    return [c.name for c in ALL_COMPOUNDS]


def compound_codes() -> list[str]:
    """Ordered short codes for DB, session tags, and strategy stints."""
    return [c.code for c in ALL_COMPOUNDS]


def get_by_code(code: str) -> TyreCompound | None:
    """Look up a compound by its short code (case-insensitive)."""
    return _BY_CODE.get(code.upper())


def normalise_code(s: str) -> str | None:
    """Map any user-entered string to a canonical short code. Returns None if unrecognised."""
    return _ALIASES.get(s.strip().lower())


def normalise_name(s: str) -> str | None:
    """Map any user-entered string to a canonical display name. Returns None if unrecognised."""
    code = normalise_code(s)
    tc = _BY_CODE.get(code) if code else None
    return tc.name if tc else None


def wear_onset_for(code_or_name: str | None) -> float | None:
    """The wear-onset temperature for a compound, or None where untested.

    Accepts short codes, canonical names, or any alias `normalise_code`
    understands. **None is the common answer** - only the three Racing
    compounds have ever been tested, by one person, once.

    **Nothing in the live path calls this, and nothing should.** The figure is
    a labelled external cross-check that the export names beside the measured
    temperature; it is untestable on this driver's own data, where 0 of 318
    Monza corner observations reach 88 degC at all. It is exposed here so the
    offline pipeline that eventually fits a real model has something to
    compare itself against - see `WEAR_ONSET_PRIOR` and its empty
    `speakable_scopes`.
    """
    if not code_or_name:
        return None
    compound = _BY_CODE.get(code_or_name.upper())
    if compound is None:
        resolved = normalise_code(code_or_name)
        compound = _BY_CODE.get(resolved) if resolved else None
    return compound.wear_onset_c if compound else None


# **`temp_preset` has been deleted along with the bands it returned.** It
# handed out `{cold_max, warming_max, optimal_max, hot_max}` for anything that
# wanted to colour a gauge, which is how a fabricated four-zone window stayed
# one import away from a live call for as long as it did.


# --------------------------------------------------------------- the priors
#
# **These are rows with a falsification status, not constants in a module.**
# The difference matters: "refuted at Monza" has to be a fact the app carries,
# not a fact somebody remembers. A prior with no speakable scope is a prior
# nothing may say out loud, and that is enforced by the absence of a scope
# rather than by discipline.
#
# This is deliberately a seam and not a model. A separate build adds the app's
# own longitudinal tyre model - per-corner grip observations and an offline
# re-aggregation - and these rows are what it will replace.


@dataclass(frozen=True)
class Prior:
    """A claim about tyre temperature, and how far it has survived testing."""
    id: str
    claim: str
    source: str
    status: str
    n: int
    kind: str = ""
    game_version: str = ""
    evidence: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    # **The car-and-circuit scopes where this may be spoken.** Empty means
    # nothing may be said on it anywhere. A scope is `circuit/car`, slugged by
    # `scope_key`.
    speakable_scopes: tuple[str, ...] = ()
    # For the gap prior only: the fitted slope and the thresholds derived from
    # it, per scope. None where the prior is not that shape.
    slope_s_per_c: float | None = None
    conserve_gap_c: float | None = None
    quiet_gap_c: float | None = None
    front_floor_c: float | None = None

    def speakable_at(self, scope: str | None) -> bool:
        return bool(scope) and scope in self.speakable_scopes


STATUS_REFUTED_OUT_OF_SCOPE = "REFUTED-OUT-OF-SCOPE"
STATUS_UNTESTED_OUT_OF_RANGE = "UNTESTED-OUT-OF-RANGE"

GAP_PRIOR = Prior(
    id="gap-laptime-0.89",
    claim="lap time rises about +0.89 s per degC of rear-minus-front axle gap",
    source="pitcrew:replan_parameters:2026-08-17",
    status=STATUS_REFUTED_OUT_OF_SCOPE,
    n=17,
    evidence=(
        "Yas Marina / Shelby: +0.872 +/- 0.248, t = 3.52, n = 18 - CONSISTENT",
        "Watkins Glen / Huracan: +0.778 +/- 0.398, t = 1.95 - MARGINAL",
        "Monza / Porsche: +0.011 +/- 0.077, t = 0.15, z = -11.4 against the "
        "prior - REFUTED, and on a WIDER gap range (10.3 degC against 5.9), "
        "so it is not a range-restriction artefact",
    ),
    caveats=(
        "causality is not established - a sliding lap heats tyres, and "
        "incident seconds correlate with peak rear temperature at r = 0.84",
        "it inverts against a proper grip observable: at Monza the gap "
        "predicts grip and not lap time, at Yas Marina the reverse. That "
        "disagreement is the finding and is not averaged away",
        "the gap conflates a cold front with a hot rear, hence the front "
        "floor",
    ),
    # **One scope, and it is the circuit of the race this engineer was rebuilt
    # for.** Everywhere else the call stays silent.
    #
    # The string is composed by `scope_key` from the event row as the app
    # actually stores it - `track='Yas Marina Circuit'`, `layout='Full
    # Course'` - and not from a tidied-up name. It was written as
    # "yas-marina/..." once, which matches nothing: the association was
    # unreachable for the whole race and every test that covered it was
    # passing against a fixture that invented `track="Yas Marina",
    # layout=None`. There is a test now that resolves the scope from a real
    # `events` row through `context_from_event`, which is the only way this
    # can be checked honestly.
    speakable_scopes=("yas-marina-circuit-full-course/ford-shelby-gt350r-16",),
    slope_s_per_c=0.89,
    conserve_gap_c=8.0,     # +2.5 s/lap above; the split plateau is 6.5-9.0
    quiet_gap_c=6.7,        # the fastest 6 of 17 laps sit at or under this
    front_floor_c=72.0,     # below this the gap is warm-up, not degradation
)

WEAR_ONSET_PRIOR = Prior(
    id="digitalrelay-wear-onset",
    claim="wear accelerates above RS 88 / RM 90 / RH 93 degC",
    source=WEAR_ONSET_SOURCE,
    status=STATUS_UNTESTED_OUT_OF_RANGE,
    n=1,
    kind=WEAR_ONSET_KIND,
    game_version=WEAR_ONSET_GAME_VERSION,
    caveats=WEAR_ONSET_CAVEATS + (
        "untestable on this driver's data: 0 of 318 Monza corner observations "
        "reach 88 degC at all, and there are 15 gauge readings across 175 "
        "laps with none in either race",
    ),
    # **Nothing speaks on it.** It is stored as a labelled external
    # cross-check - the export names it beside the measured temperature - and
    # no live call rests on it.
    speakable_scopes=(),
)

PRIORS: tuple[Prior, ...] = (GAP_PRIOR, WEAR_ONSET_PRIOR)

_NOT_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """**The canonical way this app turns a name into an identity.**

    Anyone composing a car key, a circuit key or a scope calls this. Not
    because the rule is clever - it is not - but because there must be exactly
    ONE of it, written down, and this is where it lives.

    The rule, stated deliberately:

    1. Unicode-normalise (NFKD) and drop the combining marks, so an accented
       letter folds to its ASCII base: "Huracán" becomes "huracan".
    2. Lower-case.
    3. Everything outside `a-z0-9` is a separator; runs collapse to one "-";
       leading and trailing separators are trimmed.
    4. A name that leaves nothing behind - a purely non-latin one - falls back
       to a short digest of the original, so two different names can never
       collide into the empty string.

    **Why folding rather than keeping the accent.** 17 Aug 2026: the same
    car was slugged two ways in two places. `str.isalnum()` returns True for
    "á", so a rule written as "keep alphanumerics" KEPT it and wrote
    `lamborghini-huracán-gt3-15` to disk, while a rule written as a regex over
    `[a-z0-9]` treated it as a separator and produced
    `lamborghini-hurac-n-gt3-15` - so a lookup for the Huracán could never
    reach its own 300 grip observations or its 8 fitted models. Folding to
    ASCII is the choice because it is stable across filesystems, encodings and
    anything that has to round-trip through a filename or a URL. The important
    property is not which rule; it is that there is one.

    This is the third bug of the same family in this codebase: an identity
    composed twice, by two rules, that had to match and did not. The first was
    a corner id, the second a tyre-association scope that named a circuit the
    events table does not contain. All three were invisible because both sides
    were internally consistent.
    """
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch))
    slug = _NOT_SLUG.sub("-", stripped.lower()).strip("-")
    if slug:
        return slug
    # Nothing survived - a name with no latin characters at all. A digest
    # rather than "", because every such name collapsing to the same empty
    # key is the identity bug this function exists to prevent.
    return "x" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def scope_key(car: str | None, track: str | None,
              layout: str | None = None) -> str | None:
    """`circuit/car`, slugged by `slugify`, or None where either half is unknown.

    **The canonical entry point for composing a scope.** Import it rather than
    writing the composition again: the circuit half is `track` and `layout`
    joined with a space BEFORE slugging, so "Yas Marina Circuit" plus "Full
    Course" is one key and not two, and that ordering is part of the identity.

    Unknown is not a scope, and a prior with no scope says nothing - which is
    the right behaviour for a car or a circuit nobody has measured.
    """
    if not car or not track:
        return None
    circuit = f"{track} {layout}" if layout else track
    return f"{slugify(circuit)}/{slugify(car)}"


def gap_association_for(car: str | None, track: str | None,
                        layout: str | None = None) -> Prior | None:
    """The front-to-rear gap association, but only where it was measured.

    **None is the common answer and it means silence.** The association was
    fitted on 17 of this driver's own laps at one car and one circuit; tested
    across 95 clean laps at three cars and three circuits it does not hold -
    Monza refutes it at z = -11.4 on a wider gap range. So it is not a law,
    it is a local measurement, and it may only be spoken where it was made.
    """
    scope = scope_key(car, track, layout)
    return GAP_PRIOR if GAP_PRIOR.speakable_at(scope) else None

