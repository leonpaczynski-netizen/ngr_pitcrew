"""Live Activation 3 — post-session race integrity audit (Program 3).

A deterministic, offline, DB-free check that a completed race session is safe to promote to trusted
event evidence (track intelligence, setup learning, driver learning). It NEVER deletes or rewrites
user data — it only reports issues and withholds promotion. The caller quarantines / blocks
promotion / flags for review based on the report.

The audit answers one question honestly: *is this recorded race session a coherent, non-contradictory
race run bound to the intended canonical identity?* A blocker (invalid/placeholder identity, a race
record attached to a Practice/Qualifying session, a broken session↔run link, a cross-event lap,
duplicate lap numbers, or a contradictory car/track) withholds promotion; softer findings
(zero-length laps, no laps recorded, unknown layout) are limitations that do not by themselves block.

Qt-free, deterministic, no wall-clock, never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _present(v) -> bool:
    return _norm(v).lower() not in ("", "0", "0.0", "none", "null")


class IntegritySeverity(str, Enum):
    INFO = "info"
    LIMITATION = "limitation"
    BLOCKER = "blocker"


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    severity: IntegritySeverity
    message: str

    def as_payload(self) -> dict:
        return {"code": self.code, "severity": self.severity.value, "message": self.message}


@dataclass(frozen=True)
class RaceSessionIntegrityReport:
    run_id: str
    laps_checked: int
    issues: Tuple[IntegrityIssue, ...] = field(default_factory=tuple)

    @property
    def blockers(self) -> Tuple[IntegrityIssue, ...]:
        return tuple(i for i in self.issues if i.severity == IntegritySeverity.BLOCKER)

    @property
    def limitations(self) -> Tuple[IntegrityIssue, ...]:
        return tuple(i for i in self.issues if i.severity == IntegritySeverity.LIMITATION)

    @property
    def ok(self) -> bool:
        """No blocker — the session is internally coherent."""
        return not self.blockers

    @property
    def promotion_allowed(self) -> bool:
        """A race session may promote trusted learning ONLY when it is coherent AND actually
        recorded at least one lap. An empty or blocked session promotes nothing."""
        return self.ok and self.laps_checked > 0

    @property
    def summary(self) -> str:
        if self.blockers:
            return "Blocked from learning promotion: " + "; ".join(i.message for i in self.blockers)
        if not self.laps_checked:
            return "No laps recorded — nothing to promote."
        if self.limitations:
            return "Promotable with limitations: " + "; ".join(i.message for i in self.limitations)
        return "Race session is coherent and promotable."

    def as_payload(self) -> dict:
        return {"run_id": self.run_id, "laps_checked": self.laps_checked,
                "ok": self.ok, "promotion_allowed": self.promotion_allowed,
                "summary": self.summary, "issues": [i.as_payload() for i in self.issues]}


def audit_race_session(
    *,
    run: Optional[Mapping],
    laps: Optional[Sequence[Mapping]],
    expected: Optional[Mapping] = None,
    session: Optional[Mapping] = None,
) -> RaceSessionIntegrityReport:
    """Audit a completed race ``run`` (a ``session_runs`` row) and its ``laps`` against the
    ``expected`` canonical identity (``event_id``/``car_id``/``track_id``/``layout_id``, session
    type ``race``). ``session`` is the optional owning session row (for a car/track contradiction
    check). Deterministic; never raises.

    Every issue is one of INFO/LIMITATION/BLOCKER. Only blockers withhold promotion."""
    run = run if isinstance(run, Mapping) else {}
    exp = expected if isinstance(expected, Mapping) else {}
    sess = session if isinstance(session, Mapping) else {}
    rows = [r for r in (laps or []) if isinstance(r, Mapping)]
    issues: list = []

    def add(code, severity, message):
        issues.append(IntegrityIssue(code, severity, message))

    run_id = _norm(run.get("run_id"))

    # --- identity validity (invalid / placeholder identities) ----------------
    if not _present(run_id):
        add("invalid_run_id", IntegritySeverity.BLOCKER,
            "the run has no valid run id (zero/placeholder) — it cannot be trusted evidence")
    if not _present(run.get("session_id")):
        add("broken_session_link", IntegritySeverity.BLOCKER,
            "the run is not linked to a telemetry session (session/run linkage mismatch)")
    if not _present(run.get("event_id")):
        add("invalid_event_id", IntegritySeverity.BLOCKER,
            "the run carries no valid event id — a race with no event is not promotable")
    if not _present(exp.get("car_id")):
        add("invalid_car_id", IntegritySeverity.BLOCKER,
            "the expected car identity is missing or zero (placeholder car) — never promote")

    # --- race records must not be attached to Practice/Qualifying -------------
    st = _norm(run.get("session_type")).lower()
    if st and st != "race":
        add("wrong_session_type", IntegritySeverity.BLOCKER,
            f"this run is stored as a {st.title()} session, not a Race — a race record must not be "
            "attached to a Practice/Qualifying session")

    # --- event coherence (learning evidence from the wrong event) ------------
    if _present(exp.get("event_id")) and _present(run.get("event_id")) \
            and _norm(run.get("event_id")) != _norm(exp.get("event_id")):
        add("event_mismatch", IntegritySeverity.BLOCKER,
            f"the run's event {_norm(run.get('event_id'))} contradicts the expected event "
            f"{_norm(exp.get('event_id'))}")

    # --- contradictory car/track identity (session vs expected) --------------
    if _present(sess.get("car_id")) and _present(exp.get("car_id")) \
            and _norm(sess.get("car_id")) != _norm(exp.get("car_id")):
        add("contradictory_car", IntegritySeverity.BLOCKER,
            "the recorded car contradicts the event's car — do not promote a mismatched car")
    exp_track = _norm(exp.get("track_id")) or _norm(exp.get("track"))
    sess_track = _norm(sess.get("track_id")) or _norm(sess.get("track"))
    if exp_track and sess_track and exp_track.lower() != sess_track.lower():
        add("contradictory_track", IntegritySeverity.BLOCKER,
            "the recorded track contradicts the event's track — do not promote a mismatched track")

    # --- lap integrity: duplicates, orphans, zero-length ---------------------
    seen: dict = {}
    zero_len = 0
    for r in rows:
        try:
            ln = int(r.get("lap_num"))
        except (TypeError, ValueError):
            add("invalid_lap_number", IntegritySeverity.BLOCKER,
                "a lap has a non-integer lap number — corrupt lap record")
            continue
        seen[ln] = seen.get(ln, 0) + 1
        try:
            t = int(r.get("lap_time_ms") or 0)
        except (TypeError, ValueError):
            t = 0
        if t <= 0:
            zero_len += 1
    dupes = sorted(n for n, c in seen.items() if c > 1)
    if dupes:
        add("duplicate_lap_number", IntegritySeverity.BLOCKER,
            f"duplicate lap number(s) {dupes} in one run — a reconnect or replay double-wrote laps")
    if zero_len:
        add("zero_length_laps", IntegritySeverity.LIMITATION,
            f"{zero_len} lap(s) have zero/negative time and will not count toward learning")

    # --- coverage limitations (never blockers on their own) ------------------
    if not rows:
        add("orphan_run", IntegritySeverity.LIMITATION,
            "the run finalised with no laps recorded — nothing to promote")
    if not _present(exp.get("layout_id")):
        add("unknown_layout", IntegritySeverity.LIMITATION,
            "the track layout is unresolved — track-model promotion is limited")

    return RaceSessionIntegrityReport(run_id=run_id, laps_checked=len(rows), issues=tuple(issues))
