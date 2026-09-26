"""Fill verdict and rival stop rows for the race monitor (Story 2, 25 Sep 2026).

`fill_verdict` answers "can this rival reach the flag on what he took?" for our
OWN fuel planning (standalone, no laps_total needed).  The MONITOR rows use
`_rival_verdict`, which calls `fuel_shortfall` from `rival_calls.py` — the same
function the tablet's `predict()` and George's voice use — so the monitor and
the voice cannot disagree about one car's fuel (rule 13).  `_rival_verdict`
uses `laps_total - stop.lap` (laps from when HE stopped to the flag), which is
the correct horizon for a rival's fuel, not our own laps_remaining.

**The bound semantics, from schema.py line 75 and pit_wall.py line 1252.**

* `partial=True` → `fuel_in_l` is an UPPER BOUND on what he arrived with
  (the watcher joined the fill already running).  The litres taken are
  therefore a LOWER BOUND: less fuel appears to have been used, so real
  burn ≥ computed burn.  A lower-bound burn is optimistic about his fuel:
  "must save" with an optimistic burn still holds (bound=True); anything
  better is "can't tell".

* `exit_is_a_bound=True` → `fuel_out_l` is a LOWER BOUND on what he left
  with (car moved before the last column read was taken).  A "spare" verdict
  still holds (mark bound=True); anything worse is "can't tell" because the
  real exit fuel could be higher and change the verdict.

* Both bounds active → they point opposite ways → "can't tell".

**Rule 9 applies everywhere.**  A negative margin is returned as-is, never
clamped to zero.  A margin of -8 L means he needs 8 L he does not have, and
clamping it would read as "exactly meets demand" downstream.

**Orchestrator amendment (binding, 25 Sep 2026):**
  exit_is_a_bound=True: "spare" holds (bound=True); "must save"/"exact" → "can't tell".
  partial=True (burn lower bound): "must save" holds (bound=True); otherwise "can't tell".
  Both bounds → "can't tell".
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.calls import as_his_hud_numbers_it


@dataclass(frozen=True)
class FillVerdictResult:
    """What his fuel says for the laps remaining.

    `verdict` is one of: ``"spare"``, ``"exact"``, ``"must save"``,
    ``"can't tell"``.

    `margin_l` is the signed fuel balance - positive is spare, negative is
    short.  **Never None when a verdict other than "can't tell" is returned.**
    Never clamped (rule 9).

    `bound` flags that at least one figure was a bound rather than a reading
    and the verdict could be different with exact numbers.

    `saving_per_lap_l` is the save rate that would just reach the flag, or
    None when the verdict is not "must save" or when laps are zero.

    **Vocabulary** (``fill_verdict`` and ``_rival_verdict``):
      ``"spare"`` — reaches, margin > reading error (tablet: "X L to push");
      ``"on the limit"`` — reaches, margin ≤ reading error (tablet: "on the
        limit") — used only by ``_rival_verdict``, which aligns with the
        tablet (rule 13);
      ``"exact"`` — used only by standalone ``fill_verdict`` for OUR own fuel;
      ``"must save"`` — short but saveable;
      ``"stops again"`` — short and not saveable;
      ``"can't tell"`` — inputs missing or bounds prevent a verdict.
    """
    verdict: str
    margin_l: float | None = None
    bound: bool = False
    saving_per_lap_l: float | None = None


# Exact-fuel tolerance: a margin within this is "exact" rather than "spare".
# One litre is inside the reading noise (rival_calls.READ_ERROR_L = 2.0), so
# it is generous but not deceptive.
_EXACT_TOLERANCE_L = 1.0

_CANT_TELL = FillVerdictResult(verdict="can't tell")


# ---------------------------------------------------------------------------
# Minimal proxies for _rival_verdict — satisfy the fuel_shortfall interface
# without importing the full Rival dataclass (which carries live-race state
# fields not present in a stop-row dict).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _StopSnap:
    """The two fields fuel_shortfall reads from rival.stop."""
    lap: int | None
    fuel_out_l: float | None


@dataclass(frozen=True)
class _RivalProxy:
    """Satisfies the Rival interface that fuel_shortfall needs."""
    stop: _StopSnap
    exit_is_a_bound: bool
    burn_per_lap_l: float | None = None


def _rival_verdict(
    fuel_out_l: float | None,
    burn: float | None,
    stop_lap: int | None,
    laps_total: int | None,
    *,
    partial: bool,
    exit_is_a_bound: bool,
) -> FillVerdictResult:
    """Monitor fill verdict via `fuel_shortfall` — one expression (rule 13).

    Uses `laps_total - stop_lap` (his horizon from the stop to the flag)
    rather than our own `laps_remaining`.  Delegates to the same
    `fuel_shortfall` + `must_stop_again` path the tablet uses so the monitor
    and the voice cannot disagree about the same car (rule 13).

    Verdict vocabulary: ``"spare"``, ``"on the limit"``, ``"must save"``,
    ``"stops again"``, ``"can't tell"`` — matches the tablet (rule 13).

    **Bound rules** (same semantics as `fill_verdict`):
      * `partial and exit_is_a_bound` → can't tell.
      * `exit_is_a_bound` only → fuel_shortfall refuses (guard); compute
        margin manually.  "spare" still holds (bound=True); anything else
        can't tell.
      * `partial` only → burn is a lower bound; "must save" still holds
        (bound=True); anything better can't tell.
    """
    # Import here to avoid a circular-import at module load; rival_calls imports
    # from calls, gaps, rivals, strategy — none of which import fill_verdict.
    from pitcrew.race.rival_calls import (       # noqa: PLC0415
        fuel_shortfall as _fs,
        must_stop_again as _msa,
    )

    if partial and exit_is_a_bound:
        return _CANT_TELL
    if fuel_out_l is None or burn is None or stop_lap is None or laps_total is None:
        return _CANT_TELL

    laps_to_flag = laps_total - stop_lap
    if laps_to_flag <= 0:
        return _CANT_TELL

    if exit_is_a_bound:
        # fuel_shortfall refuses an exit-is-a-bound figure (it would invent a
        # shortfall from a lower bound — rule 9).  Compute the margin manually
        # for the "spare still holds" case only.
        needs = burn * laps_to_flag
        margin = fuel_out_l - needs          # positive = spare; never clamped (rule 9)
        if margin > _EXACT_TOLERANCE_L:
            return FillVerdictResult(verdict="spare", margin_l=margin, bound=True)
        return _CANT_TELL

    # Build a proxy so fuel_shortfall can be called once (rule 13).
    proxy = _RivalProxy(
        stop=_StopSnap(lap=stop_lap, fuel_out_l=fuel_out_l),
        exit_is_a_bound=False,   # handled above
        burn_per_lap_l=None,     # burn is passed as the fallback parameter
    )
    short = _fs(proxy, burn, laps_total=laps_total)
    if short is None:
        return _CANT_TELL

    if partial:
        # burn is a lower bound → true margin ≤ computed.  "must save" still
        # holds (if optimistic burn says short, real burn is worse); anything
        # better can't tell.
        if short.litres > 0:
            saving = short.litres / laps_to_flag
            return FillVerdictResult(
                verdict="must save", margin_l=-short.litres,
                bound=True, saving_per_lap_l=saving,
            )
        return _CANT_TELL

    # No bounds: delegate to must_stop_again for the canonical three-way split
    # (reaches / saves / stops again) — same path the tablet and voice use.
    verdict = _msa(proxy, burn, laps_total=laps_total)
    if verdict is True:
        return FillVerdictResult(verdict="stops again", margin_l=-short.litres)
    if verdict is None:
        saving = short.litres / laps_to_flag
        return FillVerdictResult(
            verdict="must save", margin_l=-short.litres,
            saving_per_lap_l=saving,
        )
    # verdict is False: spare or "on the limit" — match the tablet's vocabulary
    # (rule 13).  The tablet uses `spare_readable = spare > short.error_l`:
    # a margin inside the reading error is "on the limit" (the point estimate
    # says he reaches, but the instrument cannot resolve the gap); a margin
    # larger than the error is "spare".
    spare = -short.litres
    if spare > short.error_l:
        return FillVerdictResult(verdict="spare", margin_l=spare)
    return FillVerdictResult(verdict="on the limit", margin_l=spare)


def fill_verdict(
    fuel_out_l: float | None,
    burn_per_lap_l: float | None,
    laps_remaining: int | float | None,
    *,
    partial: bool,
    exit_is_a_bound: bool,
) -> FillVerdictResult:
    """Can he reach the flag on what he took?

    Parameters
    ----------
    fuel_out_l:
        Litres in the tank when he left the pits.  None → "can't tell".
    burn_per_lap_l:
        Estimated litres per lap for him.  None → "can't tell".
    laps_remaining:
        OUR remaining laps (`RaceState.laps_remaining()`), used as a proxy
        for his too.  None → "can't tell".
    partial:
        True if the pit wall joined his stop mid-fill: `fuel_in_l` is an upper
        bound, so `burn_per_lap_l` derived from it is a lower bound.
    exit_is_a_bound:
        True if `fuel_out_l` is a lower bound (car left before the last column
        read was taken, per pit_wall.py line 394).
    """
    # Any missing input → cannot price it (rule 3).
    if fuel_out_l is None or burn_per_lap_l is None or laps_remaining is None:
        return _CANT_TELL

    # Both bounds active → they point opposite ways; the verdict cannot be
    # stated in any direction (orchestrator amendment, 25 Sep 2026).
    if partial and exit_is_a_bound:
        return _CANT_TELL

    needs = burn_per_lap_l * laps_remaining
    margin = fuel_out_l - needs   # positive = spare, negative = short; rule 9

    if exit_is_a_bound:
        # `fuel_out_l` is a lower bound → true exit fuel ≥ what was read →
        # margin could only be HIGHER than computed.  A "spare" reading
        # therefore still holds (he has AT LEAST this much spare) but a "must
        # save" reading is suspect - the real figure might be positive.
        if margin > _EXACT_TOLERANCE_L:
            return FillVerdictResult(
                verdict="spare", margin_l=margin, bound=True
            )
        return _CANT_TELL

    if partial:
        # `burn_per_lap_l` is a lower bound → true burn per lap ≥ computed →
        # true margin ≤ computed.  A "must save" reading therefore still holds
        # (if even the optimistic burn says he is short, the real burn makes
        # it worse) but a "spare" or "exact" reading is suspect.
        if margin < 0:
            saving = abs(margin) / laps_remaining if laps_remaining > 0 else None
            return FillVerdictResult(
                verdict="must save", margin_l=margin, bound=True,
                saving_per_lap_l=saving,
            )
        return _CANT_TELL

    # No bounds: straight arithmetic.
    if margin < 0:
        saving = abs(margin) / laps_remaining if laps_remaining > 0 else None
        return FillVerdictResult(
            verdict="must save", margin_l=margin, bound=False,
            saving_per_lap_l=saving,
        )
    if margin <= _EXACT_TOLERANCE_L:
        return FillVerdictResult(verdict="exact", margin_l=margin)
    return FillVerdictResult(verdict="spare", margin_l=margin)


def _burn_per_lap(prev_fuel_out_l: float | None,
                  fuel_in_l: float | None) -> float | None:
    """Litres per lap derived from consecutive stop figures, or None.

    `prev_fuel_out_l` is the fuel he LEFT the previous stop with; `fuel_in_l`
    is what he ARRIVED with at this one.  The difference is what he burned in
    that stint.  Divided by the stint laps... but we do not have per-rival stint
    laps here, so this helper is used in `rival_stop_rows` where the caller
    supplies the lap count separately.

    **A negative result is returned as None** (rule 9): negative fuel burned
    means one of the two figures is wrong (partial-flag mismatches, watcher
    gaps, or a car that pitted before its start was registered).  A negative
    is the instrument saying "I cannot tell", and clamping it would be a
    confident wrong answer.

    This helper is kept narrow: one arithmetic step, one guard.  Callers
    that can derive a per-lap figure from stop metadata should prefer that.
    """
    if prev_fuel_out_l is None or fuel_in_l is None:
        return None
    burned = prev_fuel_out_l - fuel_in_l
    if burned < 0:
        # The reading is internally inconsistent (rule 9): return None and
        # let the caller surface it as "can't tell".
        return None
    return burned


@dataclass(frozen=True)
class RivalStopRow:
    """One row of the rival-stops monitor table, pre-worded.

    `driver` is the name string as the roster knows it.
    `dimmed` is True when the driver is not in the entered list for this
    round — his data is history, not a current field entry.

    Stop figures use `None` for any value that was not read — rule 3 applies:
    a zero fuel-in would look like a measurement nobody made.

    `verdict` is the `FillVerdictResult` for the latest stop, using
    `own_laps_remaining` as the proxy for his remaining laps.  None where the
    verdict could not be computed.

    `burn_per_lap_l` is `[DERIVED]`: it comes from consecutive stop fuel
    figures and is the estimate used to compute the fill verdict.  `burn_is_bound`
    is True when `partial=True` on the entry stop (the burn is a lower bound).

    `earlier_stops` holds raw stop dicts for the same driver, oldest first,
    for the expandable-row display.  The latest stop's fuel and compound data
    are on this row directly.
    """
    driver: str
    dimmed: bool = False
    last_stop_lap: int | None = None
    fuel_in_l: float | None = None
    fuel_in_is_bound: bool = False        # partial=True on that stop
    fuel_out_l: float | None = None
    fuel_out_is_bound: bool = False       # exit_is_a_bound on that stop
    compound_in: str | None = None        # the set he arrived on
    compound_out: str | None = None       # the set he left on (None = unconfirmed)
    stop_count: int = 0
    burn_per_lap_l: float | None = None   # DERIVED
    burn_is_bound: bool = False           # burn is a lower bound (partial entry)
    # `burn_assumed` is True when the start-fuel figure was NOT a direct
    # measurement (rule 5).  Starting on a full tank is an assumption about the
    # start, not a reading — flagged regardless of whether the source is
    # `assumed_start_l`, `capacity_l`, or the 100 L default.
    burn_assumed: bool = False
    # `start_basis` names the source used for the start-fuel figure:
    # "assumed_start_l" — the wall recorded a per-stop assumed start;
    # "capacity"        — `capacity_l` was used (we know the tank size);
    # "100 L assumed"   — neither was available, 100 L is the fallback.
    # None when burn came from consecutive stop figures (measured).
    start_basis: str | None = None
    verdict: "FillVerdictResult | None" = None
    earlier_stops: tuple = ()             # raw stop dicts, oldest first
    # Live board position.  None when no fresh read.
    # `position_fresh` is True only when `board_age_s <= BOARD_FRESH_S`
    # (from `news.py`), the SAME rule field.py uses for the places it draws —
    # so the monitor's P column goes to "--" under exactly the same condition
    # as the tablet's old field view would have refused the place (rule 13).
    position: int | None = None
    position_fresh: bool = False


def rival_stop_rows(
    stops: list[dict],
    entered: list,
    own_driver: str | None,
    laps_remaining: int | float | None,
    own_burn_l: float | None,
    *,
    rivals: dict | None = None,
    capacity_l: float | None = None,
    laps_total: int | None = None,
    positions: "dict[str, int] | None" = None,
    board_age_s: float | None = None,
) -> tuple[RivalStopRow, ...]:
    """Grouped per driver, latest stop first, with fill verdict.

    `stops` is the flat list from `db.rival_stops(session_id=...)`, newest
    last.  `entered` is `LeagueRace.entered` — who declared for this round.
    `own_driver` is excluded.  `laps_remaining` is kept for API compat but
    the verdict now uses `laps_total - stop.lap` (his horizon from the stop),
    not our remaining laps.  `laps_total` is `RaceState.laps_total`.  When
    `laps_total` is absent the verdict falls back to `laps_remaining` for
    backwards compat.  `own_burn_l` is used when a rival's burn cannot be
    derived from his stop figures.

    `rivals` is the live `state.rivals` dict; when present, the latest stop's
    `burn_per_lap_l` is read from the matching `Rival` object so the monitor
    and the voice never disagree about the same figure (rule 13).

    `capacity_l` is the car's fuel capacity; used as the assumed start fuel
    for a driver's first stop when `assumed_start_l` is absent from the stop
    row.  Guarded: a capacity of 0 (electric car) yields None (rule 9 — a
    zero capacity cannot yield a burn).

    **C2 — every entered driver gets a row.** The result includes one row for
    every name in `entered` (except own_driver), even drivers with no stops
    yet (stop_count=0, all fuel/compound fields None).  This ensures the table
    is keyed by who declared for the round, not by who has been seen in the
    lane.

    **Dimmed:** a driver is dimmed when their name appears in `stops` but NOT
    in `entered` — they are historical, not current field members.

    **Grouping:** stops are collected by driver name (case-insensitive), and
    the LATEST stop (highest id, last in the list) is the one the verdict is
    built from.  Earlier stops are attached for the expandable-row display.

    **Burn per lap:** for the latest stop, `rivals[name].burn_per_lap_l` is
    used when available (same source the voice uses, rule 13).  Where that is
    absent, the burn is derived:
      - two or more stops: `(prev_fuel_out_l - fuel_in_l) / stint_laps` from
        the gap between the two most recent stops;
      - first stop: `(assumed_start_l or capacity_l or 100.0 - fuel_in_l) /
        stop_lap` where assumed_start_l comes from the stop row itself;
        100 L is assumed when capacity is unknown (`burn_assumed=True`).
    A burn that goes negative is refused (rule 9) and the live rival figure
    is tried before falling back to `own_burn_l`.
    """
    entered_lower = {str(e).lower() for e in (entered or [])}
    own_lower = str(own_driver).lower() if own_driver else None

    # Group stops by driver, preserving order (oldest first within group).
    groups: dict[str, list[dict]] = {}
    for stop in stops:
        name = str(stop.get("driver") or "")
        groups.setdefault(name, []).append(stop)

    # C2: seed from entered list — every entered driver (except own) gets a row,
    # even if they have no stops yet.  Keyed by lowercase for normalisation;
    # the display name is taken from the entered list.
    # `display_name_for` maps lower → canonical entered name.
    display_name_for: dict[str, str] = {}
    for e in (entered or []):
        key = str(e).lower()
        if own_lower and key == own_lower:
            continue
        display_name_for[key] = str(e)

    # Drivers who appear in stops but not in entered → dimmed.
    # Only drivers NOT already in display_name_for.
    for name_key in list(groups):
        if own_lower and name_key.lower() == own_lower:
            continue
        if name_key.lower() not in display_name_for:
            # Use the name as it appears in stops.
            display_name_for[name_key.lower()] = name_key

    # Build a lowercase → position lookup from the positions dict so the
    # per-row lookup is case-insensitive (same pattern as the rivals lookup).
    _positions_lower: dict[str, int] = {}
    if positions:
        for name, place in positions.items():
            _positions_lower[str(name).lower()] = int(place)

    rows: list[RivalStopRow] = []
    for driver_lower, driver_name in display_name_for.items():
        driver_stops = groups.get(driver_lower) or groups.get(driver_name) or []

        # Normalise: group keys may differ in case from the entered canonical.
        if not driver_stops:
            for k, v in groups.items():
                if k.lower() == driver_lower:
                    driver_stops = v
                    break

        # Own driver exclusion is already handled by display_name_for, but
        # guard here too so a case change in own_driver cannot slip through.
        if own_lower and driver_lower == own_lower:
            continue

        dimmed = driver_lower not in entered_lower

        _pos = _positions_lower.get(driver_lower)
        # **Same freshness rule as field.py** (rule 13).  The board may hold a
        # position up to a lap old between crossings; the P column must go "--"
        # exactly when the tablet's field view would have refused the place.
        # Import BOARD_FRESH_S — never copy the constant.
        from pitcrew.race.news import BOARD_FRESH_S
        _pos_fresh = (_pos is not None
                      and board_age_s is not None
                      and board_age_s <= BOARD_FRESH_S)

        if not driver_stops:
            # Entered but no stops yet: row with dashes.
            rows.append(RivalStopRow(
                driver=driver_name,
                dimmed=dimmed,
                stop_count=0,
                position=_pos,
                position_fresh=_pos_fresh,
            ))
            continue

        latest = driver_stops[-1]
        earlier = driver_stops[:-1]

        burn_is_bound = bool(latest.get("partial"))
        burn_assumed = False
        start_basis_val: str | None = None

        # **Rule 13: use the live rival burn where the voice does.** The
        # coordinator files `burn_per_lap_l` on `state.rivals[name]` via
        # `rival_book.profile_of(); the voice reads the same object.  The
        # monitor must show the same figure, not a second derivation.
        live_rival = None
        if rivals is not None:
            live_rival = rivals.get(driver_name) or rivals.get(driver_lower)
            if live_rival is None:
                for k, v in rivals.items():
                    if str(k).lower() == driver_lower:
                        live_rival = v
                        break

        burn: float | None = None
        if live_rival is not None:
            burn = getattr(live_rival, "burn_per_lap_l", None)

        if burn is None and len(driver_stops) >= 2:
            # Two or more stops: derive from consecutive exit→entry figures.
            prev = driver_stops[-2]
            prev_out = prev.get("fuel_out_l")
            cur_in = latest.get("fuel_in_l")
            prev_lap = prev.get("lap")
            cur_lap = latest.get("lap")
            # I1: explicit None check — rule 3, a zero lap number is a real
            # value; `or 0` would misread it as "no lap known" (rule 9).
            if prev_lap is None or cur_lap is None:
                stint_laps = None
            else:
                stint_laps = cur_lap - prev_lap
            if (stint_laps is not None and stint_laps > 0
                    and cur_in is not None and prev_out is not None):
                total_burned = _burn_per_lap(prev_out, cur_in)
                if total_burned is not None:
                    burn = total_burned / stint_laps
            # Multi-stop consecutive path failed: fall back to own burn, NOT
            # the first-stop 100 L assumption (that is only valid for the
            # first stop when no prior exit figure exists at all).
            if burn is None:
                burn = own_burn_l
                burn_assumed = False

        elif burn is None and len(driver_stops) == 1:
            # First stop only: derive from assumed start fuel (C3).
            # The 100 L / capacity assumption is a model, not a reading —
            # flagged `burn_assumed` (rule 5).
            cur_in = latest.get("fuel_in_l")
            cur_lap = latest.get("lap")
            assumed_start = latest.get("assumed_start_l")

            # capacity_l=0 is an electric car: no meaningful L/lap (rule 9).
            if capacity_l == 0:
                # Electric car guard: no burn computable.
                pass  # burn stays None
            else:
                if assumed_start is not None:
                    start_fuel = float(assumed_start)
                    burn_assumed = True    # the assumed_start is itself an assumption
                    start_basis_val = "assumed_start_l"
                elif capacity_l is not None and capacity_l > 0:
                    start_fuel = float(capacity_l)
                    burn_assumed = True    # starting on a full tank is assumed
                    start_basis_val = "capacity"
                else:
                    start_fuel = 100.0
                    burn_assumed = True    # neither capacity nor per-stop datum
                    start_basis_val = "100 L assumed"

                if (cur_in is not None and cur_lap is not None
                        and cur_lap > 0):
                    burned = start_fuel - cur_in
                    if burned > 0:
                        burn = burned / cur_lap

        # Fall back to own burn if all derivation paths are exhausted.
        if burn is None:
            burn = own_burn_l
            burn_assumed = False

        # Compound: `compound_in` is the set he ARRIVED on (confirmed via disc
        # vote).  `compound` is the set he LEFT on (last disc read at exit,
        # schema.py lines 1003-1009).  `compound_in` may be None on old rows.
        stop_lap_raw = latest.get("lap")
        # Fix 1 (25 Sep 2026): use _rival_verdict (fuel_shortfall-based, rule 13)
        # with laps_total - stop.lap rather than our own laps_remaining.
        if laps_total is not None:
            verdict = _rival_verdict(
                latest.get("fuel_out_l"),
                burn,
                stop_lap_raw,
                laps_total,
                partial=bool(latest.get("partial")),
                exit_is_a_bound=bool(latest.get("exit_is_a_bound", False)),
            )
        else:
            # No laps_total: own-laps proxy gives the wrong horizon (a rival
            # who stopped on lap 15 of 30 has 15 laps to the flag, not
            # whatever we have left — using our number produced a false
            # "SPARE +54 L" at Sardegna Rd9 lap 25).  Say so rather than
            # asserting a wrong answer (rule 9).
            verdict = _CANT_TELL

        # Fix 2 (25 Sep 2026): stop laps are in the completed-lap domain; convert
        # to HUD domain so the monitor and the voice name the same lap (rule 13).
        # as_his_hud_numbers_it adds 1 (the lap in progress when he stopped).
        stop_lap_hud = as_his_hud_numbers_it(stop_lap_raw)
        earlier_hud = tuple(
            dict(s, lap=as_his_hud_numbers_it(s.get("lap")))
            for s in earlier
        )

        rows.append(RivalStopRow(
            driver=driver_name,
            dimmed=dimmed,
            last_stop_lap=stop_lap_hud,
            fuel_in_l=latest.get("fuel_in_l"),
            fuel_in_is_bound=bool(latest.get("partial")),
            fuel_out_l=latest.get("fuel_out_l"),
            fuel_out_is_bound=bool(latest.get("exit_is_a_bound", False)),
            compound_in=latest.get("compound_in"),
            compound_out=latest.get("compound"),
            stop_count=len(driver_stops),
            burn_per_lap_l=burn,
            burn_is_bound=burn_is_bound,
            burn_assumed=burn_assumed,
            start_basis=start_basis_val,
            verdict=verdict,
            earlier_stops=earlier_hud,
            position=_pos,
            position_fresh=_pos_fresh,
        ))

    return tuple(rows)
