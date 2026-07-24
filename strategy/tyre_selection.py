"""Which tyre compounds this event allows, and what each discipline wants (UAT-4).

The Garage had no tyre control at all — a driver preparing a two-hour endurance race
could not move the car off Racing Medium onto Racing Hard. The pieces already existed
(``EventContext.available_tyres`` from the event's regulations, the compound table in
``data.tyres``, and a race-plan feasibility pass that already compares every available
compound); nothing joined them to a control.

Pure, deterministic, offline. Two rules the driver stated, encoded honestly:

  * **Qualifying takes the softest compound the event allows.** One lap, peak grip;
    tyre life is irrelevant. That is a rule, so it is a recommendation.
  * **The race has to try them all.** Which compound is fastest over a stint depends on
    wear, fuel and stop count, which only a measured run can settle — so this module
    refuses to guess and points at the Race Plan comparison instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

from data.tyres import ALL_COMPOUNDS, get_by_code, normalise_code

#: Racing compounds, softest first. Softness order is a property of the compound
#: table's ordering (Hard -> Medium -> Soft within a category), stated explicitly
#: here so nothing depends on that ordering by accident.
_SOFTNESS: Tuple[str, ...] = (
    "RS", "RM", "RH",       # racing
    "SS", "SM", "SH",       # sports
    "CS", "CM", "CH",       # comfort
    "IM", "HW",             # wet — never "soft"; ordered last deliberately
)
_SOFTNESS_INDEX = {code: i for i, code in enumerate(_SOFTNESS)}

#: With no regulation on file, every dry racing compound is assumed available — the
#: honest default for a GT7 event that simply does not restrict tyres.
DEFAULT_AVAILABLE: Tuple[str, ...] = ("RS", "RM", "RH")   # softest first, as presented


def _codes(values: Sequence[str]) -> Tuple[str, ...]:
    """Normalise any mix of names/codes/aliases to canonical codes, order preserved."""
    out = []
    for v in values or ():
        code = normalise_code(str(v or "").strip())
        if code and code not in out:
            out.append(code)
    return tuple(out)


def softness_rank(code: str) -> int:
    """Sort key: 0 is the softest known compound; unknown sorts last."""
    return _SOFTNESS_INDEX.get(normalise_code(str(code or "")) or "", len(_SOFTNESS))


@dataclass(frozen=True)
class TyreOption:
    code: str
    name: str
    is_softest: bool = False
    is_hardest: bool = False
    required: bool = False

    @property
    def label(self) -> str:
        bits = []
        if self.required:
            bits.append("required")
        if self.is_softest:
            bits.append("softest allowed")
        if self.is_hardest:
            bits.append("hardest allowed")
        return f"{self.name}  ({', '.join(bits)})" if bits else self.name


@dataclass(frozen=True)
class TyreChoice:
    """The compounds this event allows plus the guidance for one discipline."""
    options: Tuple[TyreOption, ...] = field(default_factory=tuple)
    recommended_code: str = ""
    recommendation_reason: str = ""
    guidance: str = ""
    restricted: bool = False        # the event actually names a compound list

    @property
    def codes(self) -> Tuple[str, ...]:
        return tuple(o.code for o in self.options)

    def name_for(self, code: str) -> str:
        c = normalise_code(str(code or "")) or ""
        for o in self.options:
            if o.code == c:
                return o.name
        comp = get_by_code(c) if c else None
        return comp.name if comp else ""


def build_tyre_choice(
    *,
    discipline: str = "race",
    available: Sequence[str] = (),
    required: Sequence[str] = (),
    race_duration_minutes: float = 0.0,
) -> TyreChoice:
    """The tyre options and guidance for one discipline. Never raises."""
    try:
        return _build(discipline=discipline, available=available, required=required,
                      race_duration_minutes=race_duration_minutes)
    except Exception:  # pragma: no cover - defensive
        return TyreChoice()


def _build(*, discipline, available, required, race_duration_minutes) -> TyreChoice:
    avail = _codes(available)
    restricted = bool(avail)
    if not avail:
        avail = DEFAULT_AVAILABLE
    req = _codes(required)
    # A required compound must be selectable even if it was left off the available list.
    for code in req:
        if code not in avail:
            avail = avail + (code,)

    ordered = sorted(avail, key=softness_rank)
    softest, hardest = ordered[0], ordered[-1]
    options = []
    for code in ordered:
        comp = get_by_code(code)
        if comp is None:
            continue
        options.append(TyreOption(
            code=code, name=comp.name,
            is_softest=(code == softest and len(ordered) > 1),
            is_hardest=(code == hardest and len(ordered) > 1),
            required=(code in req)))

    d = str(discipline or "race").strip().lower()
    if d == "qualifying":
        return TyreChoice(
            options=tuple(options), recommended_code=softest,
            recommendation_reason=(
                f"{get_by_code(softest).name} is the softest compound this event allows — "
                f"a qualifying lap wants peak grip and tyre life does not matter."),
            guidance="Qualifying always runs the softest allowed compound.",
            restricted=restricted)

    # Race. Which compound is fastest over a stint depends on wear, fuel and stop count —
    # that is measured, not assumed, so no compound is recommended here.
    long_race = float(race_duration_minutes or 0) >= 60.0
    guidance = ("Every allowed compound has to be tried: the fastest one over a stint "
                "depends on wear, fuel and stop count, which only recorded runs settle. "
                "The Race Plan compares them once there is evidence.")
    if long_race and len(ordered) > 1:
        guidance += (f" Over {int(race_duration_minutes)} minutes a harder compound usually "
                     f"trades a little one-lap pace for fewer stops — run "
                     f"{get_by_code(hardest).name} and {get_by_code(softest).name} on "
                     f"long runs and compare.")
    return TyreChoice(options=tuple(options), recommended_code="",
                      guidance=guidance, restricted=restricted)


def setup_fields_for(code: str) -> dict:
    """The setup-sheet fields that put ``code`` on the car (front and rear)."""
    comp = get_by_code(normalise_code(str(code or "")) or "")
    if comp is None:
        return {}
    return {"tyre_front": comp.name, "tyre_rear": comp.name}


def current_code(setup: Optional[dict]) -> str:
    """The compound currently on the sheet ("" when unset or mismatched front/rear)."""
    d = setup or {}
    front = normalise_code(str(d.get("tyre_front") or "").strip()) or ""
    rear = normalise_code(str(d.get("tyre_rear") or "").strip()) or ""
    return front if front and front == rear else ""
