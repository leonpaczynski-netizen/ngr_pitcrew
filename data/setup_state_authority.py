"""Canonical applied-setup-state authority (pure, Qt-free, DB-free).

UAT Finding 1. Before this module there was **no single owner** of "the setup
that is actually on the car right now." The concept was split across the Live
engineer's free-text running-setup label, the GT7-confirmed
``applied_setup_checkpoints`` row, per-lap manual ``lap_records.setup_id``, and
the advisory ``SetupContext`` — telemetry, feedback and analysis each keyed off
a different, loosely-coupled identity. The result: live advice could be based on
an old base setup, a proposed-but-not-applied setup, or manually duplicated
values.

This module defines the canonical state model and the deterministic policy that
governs it:

  * ``SetupState`` — CURRENT / PROPOSED / APPLIED / VALIDATION / ACCEPTED.
  * ``SetupIdentity`` — the (car, track, layout) tuple, normalised for matching.
  * ``ActiveSetup`` — an immutable applied-setup revision: complete field
    snapshot, name, revision number, state, hash and application time.
  * ``evaluate_analysis_gate`` — the single rule that decides whether
    setup-specific analysis may run (blocks incomplete / mismatched / merely
    proposed / stale / unknown setups, honestly).
  * ``ActiveSetupAuthority`` — the owner. In-memory state machine over the
    current session, backed by an injected persistence store so the last
    confirmed active setup restores after restart.

Everything here is deterministic and has no Qt or DB dependency; the store is
duck-typed (``load()`` / ``save(record: dict)``) so it can be a JSON file in the
app and an in-memory dict in tests. A concrete JSON store lives in
``data/active_setup_store.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from data.applied_checkpoint import compute_setup_hash


class SetupState(str, Enum):
    """Lifecycle of a setup as the Live Race Engineer sees it.

    Only APPLIED / VALIDATION / ACCEPTED are *active on the car* — a setup that
    is merely CURRENT (being edited) or PROPOSED (recommended) must never drive
    setup-specific live analysis.
    """
    CURRENT = "current"        # in the editor; may be unsaved / a base setup
    PROPOSED = "proposed"      # a recommendation generated but not applied
    APPLIED = "applied"        # confirmed applied in GT7 — the active baseline
    VALIDATION = "validation"  # applied and currently under validation testing
    ACCEPTED = "accepted"      # validated and accepted as the new baseline


# States that count as "actually on the car right now".
ACTIVE_STATES = (SetupState.APPLIED, SetupState.VALIDATION, SetupState.ACCEPTED)


class AnalysisBlockReason(str, Enum):
    OK = "ok"
    NO_ACTIVE_SETUP = "no_active_setup"
    INCOMPLETE_SNAPSHOT = "incomplete_snapshot"
    IDENTITY_MISMATCH = "identity_mismatch"
    NOT_APPLIED = "not_applied"     # only proposed / current
    STALE = "stale"                 # editor differs from the applied snapshot


def _norm(s: object) -> str:
    return str(s or "").strip().lower()


@dataclass(frozen=True)
class SetupIdentity:
    """The car/track/layout a setup belongs to. Matching is case/space-insensitive."""
    car: str = ""
    track: str = ""
    layout_id: str = ""

    @property
    def is_known(self) -> bool:
        return bool(_norm(self.car) and _norm(self.track))

    def matches(self, other: "SetupIdentity") -> bool:
        return (
            _norm(self.car) == _norm(other.car)
            and _norm(self.track) == _norm(other.track)
            and _norm(self.layout_id) == _norm(other.layout_id)
        )

    def as_key(self, purpose: str = "Race") -> str:
        return "|".join((_norm(self.car), _norm(self.track),
                         _norm(self.layout_id), _norm(purpose)))


@dataclass(frozen=True)
class ActiveSetup:
    """An immutable applied-setup revision — the canonical 'active setup'."""
    identity: SetupIdentity
    setup_id: str
    name: str
    revision: int
    state: SetupState
    fields: Mapping = field(default_factory=dict)
    setup_hash: str = ""
    applied_at: str = ""
    purpose: str = "Race"
    source: str = ""

    def is_complete(self, required_fields: Sequence[str] = ()) -> bool:
        """True when the snapshot has non-empty values for every required field.

        An empty ``required_fields`` means completeness is asserted by the caller
        having provided any fields at all.
        """
        if not self.fields:
            return False
        for k in required_fields:
            v = self.fields.get(k)
            if v is None or v == "":
                return False
        return True

    @property
    def is_active_on_car(self) -> bool:
        return self.state in ACTIVE_STATES

    def label(self) -> str:
        base = self.name or self.setup_id or "Setup"
        return f"{base} · rev {self.revision}"

    def to_record(self) -> dict:
        return {
            "car": self.identity.car,
            "track": self.identity.track,
            "layout_id": self.identity.layout_id,
            "purpose": self.purpose,
            "setup_id": self.setup_id,
            "name": self.name,
            "revision": int(self.revision),
            "state": self.state.value,
            "fields": dict(self.fields or {}),
            "setup_hash": self.setup_hash,
            "applied_at": self.applied_at,
            "source": self.source,
        }

    @classmethod
    def from_record(cls, rec: Mapping) -> "ActiveSetup":
        ident = SetupIdentity(
            car=str(rec.get("car", "") or ""),
            track=str(rec.get("track", "") or ""),
            layout_id=str(rec.get("layout_id", "") or ""),
        )
        try:
            state = SetupState(str(rec.get("state", SetupState.APPLIED.value)))
        except ValueError:
            state = SetupState.APPLIED
        return cls(
            identity=ident,
            setup_id=str(rec.get("setup_id", "") or ""),
            name=str(rec.get("name", "") or ""),
            revision=int(rec.get("revision", 1) or 1),
            state=state,
            fields=dict(rec.get("fields", {}) or {}),
            setup_hash=str(rec.get("setup_hash", "") or ""),
            applied_at=str(rec.get("applied_at", "") or ""),
            purpose=str(rec.get("purpose", "Race") or "Race"),
            source=str(rec.get("source", "") or ""),
        )


@dataclass(frozen=True)
class AnalysisGate:
    """Whether setup-specific analysis may run, and an honest reason if not."""
    allowed: bool
    reason: AnalysisBlockReason
    message: str
    active: Optional[ActiveSetup] = None

    @property
    def blocked(self) -> bool:
        return not self.allowed


def evaluate_analysis_gate(
    active: Optional[ActiveSetup],
    session_identity: SetupIdentity,
    *,
    required_fields: Sequence[str] = (),
    editor_fields: Optional[Mapping] = None,
) -> AnalysisGate:
    """The single deterministic rule for setup-specific analysis eligibility.

    Blocks (with a display-ready reason) when:
      * there is no active setup (unknown);
      * the active setup is only PROPOSED / CURRENT (not applied);
      * car/track/layout identity does not match the current session;
      * the applied snapshot is incomplete;
      * the editor has drifted from the applied snapshot (stale — re-apply first).
    """
    if active is None:
        return AnalysisGate(
            False, AnalysisBlockReason.NO_ACTIVE_SETUP,
            "No applied setup yet — apply a setup in game before setup-specific "
            "analysis.",
        )

    if not active.is_active_on_car:
        return AnalysisGate(
            False, AnalysisBlockReason.NOT_APPLIED,
            "The current recommendation is proposed but not yet applied in game. "
            "Confirm it with “Applied in Game” first.",
            active=active,
        )

    if not active.identity.matches(session_identity):
        return AnalysisGate(
            False, AnalysisBlockReason.IDENTITY_MISMATCH,
            "Active setup is for a different car/track/layout than this session — "
            "setup-specific analysis is disabled.",
            active=active,
        )

    if not active.is_complete(required_fields):
        return AnalysisGate(
            False, AnalysisBlockReason.INCOMPLETE_SNAPSHOT,
            "The applied setup snapshot is incomplete — re-apply a complete setup "
            "before setup-specific analysis.",
            active=active,
        )

    if editor_fields is not None:
        if compute_setup_hash(dict(editor_fields)) != active.setup_hash:
            return AnalysisGate(
                False, AnalysisBlockReason.STALE,
                "The setup has changed since it was applied — re-apply in game so "
                "analysis matches what is on the car.",
                active=active,
            )

    return AnalysisGate(True, AnalysisBlockReason.OK,
                        f"Active setup: {active.label()}", active=active)


class ActiveSetupAuthority:
    """Owns the active applied setup per (identity, purpose).

    In-memory state machine for the running session, backed by an injected store
    (duck-typed ``load() -> list[dict]`` / ``save(records: list[dict])``) so the
    last confirmed active setup restores after restart. The authority is the sole
    thing the Live Race Engineer defaults its baseline to.
    """

    def __init__(self, store=None):
        self._store = store
        # key -> ActiveSetup
        self._active: dict[str, ActiveSetup] = {}
        self._load()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        if self._store is None:
            return
        try:
            records = self._store.load() or []
        except Exception:
            records = []
        for rec in records:
            try:
                a = ActiveSetup.from_record(rec)
            except Exception:
                continue
            self._active[a.identity.as_key(a.purpose)] = a

    def _persist(self) -> None:
        if self._store is None:
            return
        try:
            self._store.save([a.to_record() for a in self._active.values()])
        except Exception:
            pass

    # ---------------------------------------------------------------- query
    def active_setup(self, identity: SetupIdentity,
                     purpose: str = "Race") -> Optional[ActiveSetup]:
        """The setup currently on the car for this identity+purpose, or None."""
        return self._active.get(identity.as_key(purpose))

    def revision_for(self, identity: SetupIdentity, purpose: str = "Race") -> int:
        """Revision number the *next* apply for this scope would receive."""
        cur = self.active_setup(identity, purpose)
        return (cur.revision + 1) if cur else 1

    def analysis_gate(
        self, session_identity: SetupIdentity, purpose: str = "Race", *,
        required_fields: Sequence[str] = (),
        editor_fields: Optional[Mapping] = None,
    ) -> AnalysisGate:
        active = self.active_setup(session_identity, purpose)
        # An active setup for a *different* scope must still surface as a mismatch,
        # not "no active setup" — look across scopes for the same identity.
        if active is None:
            for a in self._active.values():
                if a.purpose.lower() == purpose.lower() and not a.identity.matches(session_identity):
                    # Report the newest cross-identity applied setup as a mismatch.
                    active = a
                    break
        return evaluate_analysis_gate(
            active, session_identity,
            required_fields=required_fields, editor_fields=editor_fields,
        )

    # -------------------------------------------------------------- mutate
    def mark_applied(
        self, identity: SetupIdentity, *, setup_id: str, name: str,
        fields: Mapping, purpose: str = "Race", applied_at: str = "",
        source: str = "applied_in_game",
    ) -> ActiveSetup:
        """Confirm a complete setup snapshot as APPLIED — the new active baseline.

        Increments the revision, persists the complete snapshot, and marks it
        active for the exact car/track/layout+purpose. This is what
        "Applied in Game" calls.
        """
        rev = self.revision_for(identity, purpose)
        snap = dict(fields or {})
        active = ActiveSetup(
            identity=identity,
            setup_id=str(setup_id or ""),
            name=str(name or setup_id or "Setup"),
            revision=rev,
            state=SetupState.APPLIED,
            fields=snap,
            setup_hash=compute_setup_hash(snap),
            applied_at=str(applied_at or ""),
            purpose=str(purpose or "Race"),
            source=source,
        )
        self._active[identity.as_key(purpose)] = active
        self._persist()
        return active

    def _transition(self, identity: SetupIdentity, purpose: str,
                    new_state: SetupState) -> Optional[ActiveSetup]:
        cur = self.active_setup(identity, purpose)
        if cur is None:
            return None
        updated = replace(cur, state=new_state)
        self._active[identity.as_key(purpose)] = updated
        self._persist()
        return updated

    def start_validation(self, identity: SetupIdentity,
                        purpose: str = "Race") -> Optional[ActiveSetup]:
        """Move the applied setup into VALIDATION (still active on the car)."""
        return self._transition(identity, purpose, SetupState.VALIDATION)

    def accept(self, identity: SetupIdentity,
               purpose: str = "Race") -> Optional[ActiveSetup]:
        """Accept the validated setup as the confirmed baseline."""
        return self._transition(identity, purpose, SetupState.ACCEPTED)

    def attach_target(self, identity: SetupIdentity,
                     purpose: str = "Race") -> Tuple[str, int]:
        """The (setup_id, revision) that telemetry/feedback captured now should be
        stamped with. Empty setup_id + 0 when nothing is applied."""
        cur = self.active_setup(identity, purpose)
        if cur is None:
            return "", 0
        return cur.setup_id, cur.revision
