"""SetupService — the setup engine, headless (single-system stage 2).

Everything the Garage does to a setup — author an initial one, analyse it, apply a
recommendation, revert, confirm it was entered in GT7 — currently lives on
``SetupBuilderMixin``, reading Qt spinboxes and reporting into a ``QTextEdit`` that the
new shell has to scrape to find out whether an analysis finished. That is the last thing
keeping the classic window load-bearing.

This is the same engine with the widgets removed. It reuses, unchanged:

  * ``strategy.setup_baseline`` / the driving advisor  — the deterministic generators
  * ``data.analysis_inputs``                          — the frozen event/track snapshot
  * ``data.setup_state_authority``                    — what is actually on the car
  * ``services.setup_store``                          — the working sheets

Every operation returns a RESULT OBJECT saying what happened and why. No status is ever
inferred by reading a text box, so "finished with no changes" and "failed" stop looking
identical to "still running" — which is exactly what UAT saw.

Synchronous by design: the caller decides what runs on a worker thread. That keeps the
engine testable without Qt, a timer, or a queue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from strategy.setup_sheet import PURPOSE, SetupSheet, normalise_discipline, sheet_from_dict
from services.setup_store import SetupSheetStore, scope_key


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


# --------------------------------------------------------------------------- results
@dataclass(frozen=True)
class SetupOutcome:
    """What an operation did. ``ok`` False always carries a reason."""
    ok: bool = False
    reason: str = ""
    discipline: str = "race"
    changed_fields: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def changed(self) -> bool:
        return bool(self.changed_fields)


@dataclass(frozen=True)
class AnalysisResult:
    """The outcome of analysing a setup — never an inferred status.

    ``ok`` means the engine ran and returned something readable. ``has_recommendation``
    means it actually proposed changes; a run that legitimately proposes nothing is a
    SUCCESS with an explanation, not a failure and not a silent hang.
    """
    ok: bool = False
    reason: str = ""
    discipline: str = "race"
    analysis: str = ""
    changes: Tuple[dict, ...] = field(default_factory=tuple)
    setup_fields: Dict[str, Any] = field(default_factory=dict)
    rejected: Tuple[dict, ...] = field(default_factory=tuple)
    validation_errors: Tuple[str, ...] = field(default_factory=tuple)
    status: str = ""
    raw: str = ""

    @property
    def has_recommendation(self) -> bool:
        return bool(self.changes and self.setup_fields)

    @property
    def headline(self) -> str:
        """One line the driver can act on, whatever happened."""
        if not self.ok:
            return self.reason or "The analysis could not run."
        if self.has_recommendation:
            n = len(self.changes)
            return f"{n} change{'s' if n != 1 else ''} recommended."
        if self.validation_errors:
            return "No change recommended — " + "; ".join(self.validation_errors[:2])
        return self.reason or "No change recommended — the setup is inside its window."


@dataclass(frozen=True)
class BaselineResult:
    """The outcome of authoring an initial setup for BOTH sheets."""
    ok: bool = False
    reason: str = ""
    built: Tuple[str, ...] = field(default_factory=tuple)     # disciplines actually written
    failed: Dict[str, str] = field(default_factory=dict)      # discipline -> why

    @property
    def headline(self) -> str:
        if self.built and not self.failed:
            return "Initial setup built — " + "  ·  ".join(
                f"{d.capitalize()} sheet ✓" for d in self.built)
        if self.built and self.failed:
            done = ", ".join(d.capitalize() for d in self.built)
            missed = "; ".join(f"{d.capitalize()}: {why}" for d, why in self.failed.items())
            return f"{done} sheet built. {missed}"
        return self.reason or "The initial setup could not be built."


# --------------------------------------------------------------------------- inputs
@dataclass(frozen=True)
class SetupInputs:
    """Everything the generators need, gathered without touching a widget."""
    car: str = ""
    track: str = ""
    layout: str = ""
    car_specs: Dict[str, Any] = field(default_factory=dict)
    car_class: str = ""
    drivetrain: str = ""
    num_gears: int = 0
    ranges: Any = None
    allowed_tuning: Optional[Sequence[str]] = None
    tuning_locked: bool = False
    tyre_wear_multiplier: Optional[float] = None
    fuel_multiplier: float = 1.0
    refuel_rate_lps: float = 0.0
    duration_mins: float = 0.0
    track_profile: Any = None
    historical_setups: Tuple[dict, ...] = field(default_factory=tuple)
    mandatory_compounds: str = ""

    @property
    def is_known(self) -> bool:
        return bool(self.car and self.track)

    @property
    def scope(self) -> str:
        return scope_key(self.car, self.track, self.layout)


def _parse_setup_response(payload: str) -> Tuple[bool, dict, str]:
    """(ok, data, reason) from a generator's JSON reply. Never raises.

    A truncated or non-JSON reply is reported as such rather than shown to the driver.
    """
    text = _norm(payload)
    if not text:
        return False, {}, "The setup engine returned nothing."
    try:
        data = json.loads(text)
    except Exception:
        return False, {}, ("The setup engine's reply could not be read — it looks "
                           "incomplete. Try again.")
    if not isinstance(data, Mapping):
        return False, {}, "The setup engine returned an unexpected reply."
    return True, dict(data), ""


class SetupService:
    """Authors, analyses and applies setups. Owns no widgets."""

    def __init__(self, *, store: SetupSheetStore, advisor=None, authority=None,
                 inputs_provider=None, db=None, history=None):
        self._store = store
        self._advisor = advisor
        self._authority = authority
        self._inputs_provider = inputs_provider    # callable() -> SetupInputs
        self._db = db
        #: Persisted applied-revision history (SetupHistoryStore), for the lineage and
        #: loading a past setup. Optional — the engine works without it.
        self._history = history
        #: (scope, discipline) -> the sheet before the last apply, for a one-step undo.
        #: Per-instance: a shared dict would let one event's revert restore another's.
        self._undo: Dict[Tuple[str, str], SetupSheet] = {}

    # ---- context ----------------------------------------------------------
    def inputs(self) -> SetupInputs:
        try:
            got = self._inputs_provider() if callable(self._inputs_provider) else None
        except Exception:
            got = None
        return got if isinstance(got, SetupInputs) else SetupInputs()

    def sheet(self, discipline: str = "race", inputs: Optional[SetupInputs] = None) -> SetupSheet:
        inp = inputs or self.inputs()
        return self._store.get(inp.scope, discipline)

    def has_setup(self, discipline: str = "race") -> bool:
        inp = self.inputs()
        return self._store.has_setup(inp.scope, discipline)

    # ---- shift beep -------------------------------------------------------
    def shift_rpm(self, discipline: str = "race") -> int:
        """The upshift point stored on this discipline's sheet (0 = not set)."""
        try:
            return int(self.sheet(discipline).get("shift_rpm", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def set_shift_rpm(self, discipline: str, rpm) -> SetupOutcome:
        """Store the upshift point for one discipline's sheet.

        The shift point travels WITH the setup — a race tune may short-shift where
        qualifying runs to the indicator — so it is written onto the sheet rather than a
        global setting. Writing it does NOT go through ``apply``/undo: it is a beep
        preference on the sheet, not a tuning change the setup brain reasons about.
        """
        d = normalise_discipline(discipline)
        try:
            value = max(0, int(round(float(rpm))))
        except (TypeError, ValueError):
            return SetupOutcome(discipline=d, reason="That is not a valid RPM.")
        if value > 20000:
            return SetupOutcome(discipline=d, reason="That RPM is out of range.")
        inp = self.inputs()
        if not inp.is_known:
            return SetupOutcome(discipline=d, reason="Pick the car and track first.")
        self._store.merge(inp.scope, d, {"shift_rpm": value})
        if value <= 0:
            return SetupOutcome(ok=True, discipline=d, changed_fields=("shift_rpm",),
                                reason="Shift beep turned off for this setup.")
        return SetupOutcome(ok=True, discipline=d, changed_fields=("shift_rpm",),
                            reason=f"Shift beep set to {value} RPM for this setup.")

    # ---- author -----------------------------------------------------------
    def build_initial_setup(self) -> BaselineResult:
        """Author a complete setup for BOTH sheets from car ranges + driving profile.

        Each sheet is reported individually: a Qualifying sheet that did not build is
        never implied to have built, which was the exact doubt UAT raised.
        """
        inp = self.inputs()
        if not inp.is_known:
            return BaselineResult(reason="Pick the car and track first — a setup is "
                                         "built for a specific car at a specific track.")
        if inp.tuning_locked:
            return BaselineResult(reason="This event locks every tuning category, so "
                                         "there is no setup to build.")
        if self._advisor is None:
            return BaselineResult(reason="The setup engine is not available.")

        built, failed, sheets = [], {}, {}
        for discipline in ("race", "qualifying"):
            ok, values, why = self._generate_baseline(inp, discipline)
            if ok:
                sheets[discipline] = self.sheet(discipline, inp).merge(values)
                built.append(discipline)
            else:
                failed[discipline] = why
        if sheets:
            self._store.set_many(inp.scope, sheets)
        return BaselineResult(ok=bool(built), built=tuple(built), failed=failed,
                              reason="" if built else "No sheet could be built.")

    def _generate_baseline(self, inp: SetupInputs, discipline: str) -> Tuple[bool, dict, str]:
        try:
            payload = self._advisor.build_baseline_setup_response(
                car_name=inp.car,
                ranges=inp.ranges,
                drivetrain=inp.drivetrain,
                num_gears=int(inp.num_gears or 0),
                allowed_tuning=inp.allowed_tuning,
                tuning_locked=inp.tuning_locked,
                session_type=f"{PURPOSE.get(discipline, 'Race')} Setup",
                tyre_wear_multiplier=inp.tyre_wear_multiplier,
                car_class=inp.car_class,
                duration_mins=float(inp.duration_mins or 0.0),
                track_profile=inp.track_profile,
                track_name=inp.track,
                historical_setups=list(inp.historical_setups),
            )
        except Exception as exc:
            return False, {}, f"the engine failed ({exc})"
        ok, data, reason = _parse_setup_response(payload)
        if not ok:
            return False, {}, reason
        values = data.get("setup_fields") or {}
        if not isinstance(values, Mapping) or not values:
            return False, {}, "the engine authored no values"
        return True, dict(values), ""

    # ---- analyse ----------------------------------------------------------
    def analyse(self, discipline: str = "race", *, feeling: str = "",
                n_laps: int = 5, live_corner_aggregates: Sequence = (),
                extra_candidates: Sequence = ()) -> AnalysisResult:
        """Run the setup brain over the current sheet and report what it concluded."""
        d = normalise_discipline(discipline)
        inp = self.inputs()
        if not inp.is_known:
            return AnalysisResult(discipline=d, reason="Pick the car and track first.")
        if self._advisor is None:
            return AnalysisResult(discipline=d, reason="The setup engine is not available.")
        sheet = self.sheet(d, inp)
        if not sheet.is_authored:
            return AnalysisResult(
                discipline=d,
                reason="There is no setup on this sheet yet — build the initial setup first.")
        try:
            payload = self._advisor.build_combined_setup_response(
                sheet.as_dict(), n_laps=int(n_laps or 0), car_name=inp.car,
                car_specs=dict(inp.car_specs or {}), feeling=_norm(feeling) or None,
                allowed_tuning=inp.allowed_tuning, tuning_locked=inp.tuning_locked,
                compound=inp.mandatory_compounds, purpose=PURPOSE.get(d, "Race"),
                car_class=inp.car_class, drivetrain=inp.drivetrain,
                historical_setups=list(inp.historical_setups), track_name=inp.track,
                fuel_multiplier=float(inp.fuel_multiplier or 1.0),
                refuel_rate_lps=float(inp.refuel_rate_lps or 0.0),
                track_profile=inp.track_profile,
                extra_candidates=list(extra_candidates or ()),
                live_corner_aggregates=list(live_corner_aggregates or ()))
        except Exception as exc:
            return AnalysisResult(discipline=d, reason=f"The analysis failed: {exc}")

        ok, data, reason = _parse_setup_response(payload)
        if not ok:
            return AnalysisResult(discipline=d, reason=reason, raw=_norm(payload))
        changes = tuple(c for c in (data.get("changes") or ()) if isinstance(c, Mapping))
        fields = data.get("setup_fields") or {}
        return AnalysisResult(
            ok=True, discipline=d, analysis=_norm(data.get("analysis")),
            changes=changes,
            setup_fields=dict(fields) if isinstance(fields, Mapping) else {},
            rejected=tuple(r for r in (data.get("rejected_changes") or ())
                           if isinstance(r, Mapping)),
            validation_errors=tuple(_norm(e) for e in
                                    (data.get("validation_errors") or ()) if _norm(e)),
            status=_norm(data.get("recommendation_status")), raw=_norm(payload))

    # ---- apply / revert ---------------------------------------------------
    def apply(self, discipline: str, fields: Optional[Mapping]) -> SetupOutcome:
        """Write recommended values onto a sheet. The previous sheet is kept for revert."""
        d = normalise_discipline(discipline)
        if not fields:
            return SetupOutcome(discipline=d, reason="There was nothing to apply.")
        inp = self.inputs()
        if not inp.is_known:
            return SetupOutcome(discipline=d, reason="Pick the car and track first.")
        before = self.sheet(d, inp)
        after = before.merge(fields)
        changed = tuple(sorted(before.diff(after)))
        if not changed:
            return SetupOutcome(ok=True, discipline=d,
                                reason="Those values were already on the sheet.")
        self._undo[(inp.scope, d)] = before
        self._store.set(inp.scope, d, after)
        return SetupOutcome(ok=True, discipline=d, changed_fields=changed,
                            reason=f"{len(changed)} field"
                                   f"{'s' if len(changed) != 1 else ''} updated.")

    def revert(self, discipline: str = "race") -> SetupOutcome:
        """Undo the last apply on this sheet. One step — the lineage owns the rest."""
        d = normalise_discipline(discipline)
        inp = self.inputs()
        previous = self._undo.pop((inp.scope, d), None)
        if previous is None:
            return SetupOutcome(discipline=d, reason="There is nothing to undo on this sheet.")
        current = self.sheet(d, inp)
        self._store.set(inp.scope, d, previous)
        return SetupOutcome(ok=True, discipline=d,
                            changed_fields=tuple(sorted(current.diff(previous))),
                            reason="Reverted to the previous values.")

    #: Fields on the sheet that are NOT part of the setup's applied identity. The shift
    #: beep RPM is a beep preference that travels with the sheet, not a tuning value —
    #: including it in the applied snapshot made this path's hash disagree with the
    #: classic path's (which never carries it), so every confirmation flipped the hash
    #: and bumped the revision. It also meant editing the beep RPM looked like a new
    #: setup. Excluded here so the applied identity is the tune alone.
    _BEEP_ONLY_FIELDS = ("shift_rpm",)

    def _applied_fields(self, sheet: SetupSheet) -> Dict[str, Any]:
        d = sheet.as_dict()
        for k in self._BEEP_ONLY_FIELDS:
            d.pop(k, None)
        return d

    # ---- confirm ----------------------------------------------------------
    def confirm_applied_in_game(self, discipline: str = "race",
                                *, applied_at: str = "") -> SetupOutcome:
        """Record that the driver entered this sheet into GT7.

        Applying only writes the sheet; GT7 can only be changed by the driver, so this
        confirmation is the ONLY thing that can make a setup active — nothing can infer it.
        """
        d = normalise_discipline(discipline)
        inp = self.inputs()
        if not inp.is_known:
            return SetupOutcome(discipline=d, reason="Pick the car and track first.")
        if self._authority is None:
            return SetupOutcome(discipline=d, reason="The setup authority is not available.")
        sheet = self.sheet(d, inp)
        if not sheet.is_authored:
            return SetupOutcome(discipline=d,
                                reason="This sheet has no setup on it yet.")
        try:
            from data.setup_state_authority import SetupIdentity
            identity = SetupIdentity(car=inp.car, track=inp.track, layout_id=inp.layout)
            label = _norm(sheet.get("setup_label")) or "Setup"
            purpose = PURPOSE.get(d, "Race")
            before = self._authority.active_setup(identity, purpose)
            active = self._authority.mark_applied(
                identity, setup_id=label, name=label, fields=self._applied_fields(sheet),
                purpose=purpose, applied_at=_norm(applied_at))
        except Exception as exc:
            return SetupOutcome(discipline=d, reason=f"Could not confirm the setup: {exc}")
        # Record this revision so the lineage can show it and it can be loaded later.
        # Idempotent by revision number, so re-confirming an unchanged setup never grows
        # the history — it stores the TUNE the authority made active, not the beep pref.
        self._record_revision(inp.scope, d, active)
        # Re-confirming an unchanged sheet is not a new setup, and saying so stops the
        # driver believing they have created one every time they switch discipline back.
        if before is not None and before.revision == active.revision:
            return SetupOutcome(ok=True, discipline=d,
                                reason=f"Already on the car — {active.label()} is unchanged.")
        return SetupOutcome(ok=True, discipline=d,
                            reason=f"Registered as the active setup: {active.label()}")

    def _record_revision(self, scope: str, discipline: str, active) -> None:
        if self._history is None or active is None:
            return
        try:
            self._history.record(
                scope, discipline, revision=int(getattr(active, "revision", 0) or 0),
                label=str(active.label()), fields=dict(getattr(active, "fields", {}) or {}),
                applied_at=str(getattr(active, "applied_at", "") or ""))
        except Exception:
            pass

    # ---- lineage / load a past revision ----------------------------------
    def revisions(self, discipline: str = "race") -> list:
        """The recorded applied revisions for this discipline, oldest first.

        Each is ``{revision, label, fields, applied_at}``; the newest that matches the
        current active revision is the one on the car.
        """
        if self._history is None:
            return []
        try:
            return list(self._history.revisions(self.inputs().scope, discipline))
        except Exception:
            return []

    def load_revision(self, discipline: str, revision) -> SetupOutcome:
        """Put a past revision's tune back on the working sheet.

        This is "load the setup I ran before" — it writes the stored values onto the
        sheet so the Garage shows them; the driver then enters them in GT7 and confirms.
        It does NOT itself mark the setup applied (only the driver's GT7 confirmation
        can), so a loaded setup is not silently claimed to be on the car.
        """
        d = normalise_discipline(discipline)
        if self._history is None:
            return SetupOutcome(discipline=d, reason="No setup history is available.")
        inp = self.inputs()
        if not inp.is_known:
            return SetupOutcome(discipline=d, reason="Pick the car and track first.")
        try:
            rev = int(revision or 0)
        except (TypeError, ValueError):
            rev = 0
        snap = self._history.snapshot(inp.scope, d, rev) if rev > 0 else None
        if not snap:
            return SetupOutcome(discipline=d, reason="That setup revision was not found.")
        # Keep the current beep preference (it is not part of a stored tune).
        current = self.sheet(d, inp)
        merged = current.merge(snap)
        self._store.set(inp.scope, d, merged)
        return SetupOutcome(
            ok=True, discipline=d, changed_fields=tuple(sorted(current.diff(merged))),
            reason=f"Loaded rev {rev} onto the {d} sheet — enter it in GT7, then confirm.")

    def active_setup(self, discipline: str = "race") -> Tuple[str, bool]:
        """(label, on the car) for this discipline. ("", False) when unknown."""
        d = normalise_discipline(discipline)
        inp = self.inputs()
        if self._authority is None or not inp.is_known:
            return "", False
        try:
            from data.setup_state_authority import SetupIdentity
            active = self._authority.active_setup(
                SetupIdentity(car=inp.car, track=inp.track, layout_id=inp.layout),
                PURPOSE.get(d, "Race"))
        except Exception:
            return "", False
        if active is None:
            return "", False
        try:
            return str(active.label()), bool(active.is_active_on_car)
        except Exception:
            return "", False
