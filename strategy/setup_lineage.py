"""Closed-loop setup development — lineage, outcome attribution, failed-direction
lockout and rollback (pure, Qt-free).

Engineering-brain plan, Phase 1 ("stop harmful behaviour"). Today the app can make
the car WORSE and then repeat the same change, because it never closes the loop: it
does not know what a tested setup changed from its parent, whether those changes
helped or hurt, and it does not block a direction that already failed.

This module is that loop, as pure reasoning over data structures (persistence and UI
capture are wired separately):

  * ``SetupExperiment`` — a tested setup derived from a PARENT by a set of
    ``FieldChange``s, each carrying the handling symptoms it was EXPECTED to improve.
  * ``ExperimentOutcome`` — the driver's better/worse/unchanged verdict, per-symptom
    outcomes and any NEW problems the change introduced.
  * ``attribute_change_outcomes`` — per-change verdict: EFFECTIVE / INEFFECTIVE /
    HARMFUL / UNKNOWN, from the intersection of what the change targeted, what
    actually happened, and the change's known side effects.
  * ``failed_directions`` — the harmful ``DirectionKey``s (scoped to driver + car +
    track + objective + symptom + field-direction), so a failed direction is not
    repeated globally, only in the context it failed.
  * ``apply_direction_lockout`` — filters proposed changes that repeat a failed
    direction (with an explanation), unless stronger new evidence overturns it.
  * ``rollback_target`` — the parent to roll back to when an experiment made it worse.

It authors no setup values and calls no AI. It only decides what NOT to repeat and
what to revert — the deterministic memory an engineer keeps between runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional


# Overall + per-symptom outcome vocabulary.
OUTCOME_BETTER = "better"
OUTCOME_WORSE = "worse"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_UNKNOWN = "unknown"

# Per-change verdicts.
VERDICT_EFFECTIVE = "effective"       # did what it was meant to
VERDICT_INEFFECTIVE = "ineffective"   # no measured improvement on its target
VERDICT_HARMFUL = "harmful"           # made its target or a coupled axis worse
VERDICT_UNKNOWN = "unknown"           # not enough evidence to judge

# What each (field, direction) can WORSEN — the coupled side effects an engineer
# watches for. direction: +1 = value increased, -1 = decreased. Sign conventions
# match the rest of the setup engine (arb higher = stiffer/less grip; aero higher =
# more grip; toe_rear higher = toe-in/stability; brake_bias higher = rearward;
# lsd_accel higher = more accel lock).
# DIRECT causes only — a change is blamed for a new problem only when it is a primary
# driver of it, so an ineffective change (e.g. a front-ARB tweak that didn't help) is
# not falsely blamed for a rear problem that a coupled LSD change actually caused.
_FIELD_SIDE_EFFECTS: dict = {
    ("lsd_accel", +1): ("rear_loose_on_exit", "snap_oversteer_exit", "power_oversteer"),
    ("arb_rear", +1): ("rear_loose_on_exit", "snap_oversteer_exit"),    # stiffer rear = less rear grip
    ("aero_rear", -1): ("rear_loose_on_exit", "snap_oversteer_exit", "high_speed_instability"),
    ("aero_front", -1): ("mid_corner_understeer", "entry_understeer", "floaty_front"),
    ("toe_rear", -1): ("rear_loose_on_exit", "snap_oversteer_exit"),
    ("brake_bias", +1): ("braking_instability", "rear_loose_under_braking"),  # rearward
    ("ride_height_front", -1): ("bottoming",),
    ("ride_height_rear", -1): ("bottoming",),
}


def _direction(from_value, to_value) -> int:
    try:
        d = float(to_value) - float(from_value)
    except (TypeError, ValueError):
        return 0
    return 1 if d > 0 else -1 if d < 0 else 0


@dataclass(frozen=True)
class FieldChange:
    field: str
    from_value: object
    to_value: object
    expected_effects: tuple = ()      # symptom keys this change was meant to improve

    @property
    def direction(self) -> int:
        return _direction(self.from_value, self.to_value)

    def side_effects(self) -> tuple:
        return _FIELD_SIDE_EFFECTS.get((self.field, self.direction), ())


@dataclass(frozen=True)
class ExperimentScope:
    """The context a direction's success/failure is specific to. A failed Fuji test
    must not ban the change for every Porsche at every circuit (plan §5.5)."""
    car: str = ""
    track: str = ""
    layout: str = ""
    objective: str = ""
    driver_version: str = ""

    def key(self) -> tuple:
        return (str(self.car).strip().lower(), str(self.track).strip().lower(),
                str(self.layout).strip().lower(), str(self.objective).strip().lower())


@dataclass(frozen=True)
class SetupExperiment:
    experiment_id: str
    parent_id: Optional[str]
    changes: tuple                    # tuple[FieldChange]
    scope: ExperimentScope
    symptom_context: tuple = ()       # the symptoms present when this was authored
    label: str = ""


@dataclass(frozen=True)
class ExperimentOutcome:
    experiment_id: str
    overall: str = OUTCOME_UNKNOWN
    symptom_outcomes: dict = _dc_field(default_factory=dict)   # {symptom: outcome}
    new_problems: tuple = ()          # symptoms that did NOT exist before this change
    notes: str = ""


@dataclass(frozen=True)
class ChangeVerdict:
    field: str
    direction: int
    verdict: str
    reason: str
    expected_effects: tuple
    scope_key: tuple

    def direction_key(self) -> "DirectionKey":
        return DirectionKey(self.scope_key, self.field, self.direction)


@dataclass(frozen=True)
class DirectionKey:
    scope_key: tuple
    field: str
    direction: int


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------
def attribute_change_outcomes(experiment: SetupExperiment,
                              outcome: ExperimentOutcome) -> list:
    """Return a ChangeVerdict per change in the experiment.

    A change is HARMFUL when a symptom it targeted got worse, OR a NEW problem it is
    known to cause appeared, OR (a change that failed to help) the car got worse
    overall. It is EFFECTIVE when its targets improved, INEFFECTIVE when they were
    unchanged, and UNKNOWN when there is no evidence either way.
    """
    sym = outcome.symptom_outcomes or {}
    new_probs = set(outcome.new_problems or ())
    scope_key = experiment.scope.key()
    out: list[ChangeVerdict] = []
    for ch in experiment.changes:
        exp = tuple(ch.expected_effects or ())
        exp_outcomes = [str(sym.get(s, OUTCOME_UNKNOWN)) for s in exp]
        side = set(ch.side_effects())
        # A coupled side effect showed up as a new problem, or a targeted symptom
        # (or a side-effect symptom) got worse → the change hurt.
        side_hit = sorted(side & (new_probs | {s for s, o in sym.items() if o == OUTCOME_WORSE}))
        if any(o == OUTCOME_WORSE for o in exp_outcomes):
            verdict, reason = VERDICT_HARMFUL, (
                f"its target ({', '.join(exp)}) got worse")
        elif side_hit:
            verdict, reason = VERDICT_HARMFUL, (
                f"introduced/worsened {', '.join(side_hit)} (a known side effect of "
                f"this move)")
        elif exp and all(o == OUTCOME_BETTER for o in exp_outcomes):
            verdict, reason = VERDICT_EFFECTIVE, (
                f"improved its target ({', '.join(exp)})")
        elif exp and all(o in (OUTCOME_UNCHANGED, OUTCOME_UNKNOWN) for o in exp_outcomes):
            # No improvement on its own target and no side effect it is known to cause →
            # INEFFECTIVE (deprioritise), NOT harmful. Harm is only attributed to the
            # change that actually caused it (via a targeted-worse or a known side effect),
            # so an ineffective change is not falsely blamed for another change's damage.
            verdict, reason = VERDICT_INEFFECTIVE, (
                f"no measured improvement on its target ({', '.join(exp)})")
        elif outcome.overall == OUTCOME_BETTER:
            verdict, reason = VERDICT_EFFECTIVE, "the car improved overall after this change"
        else:
            verdict, reason = VERDICT_UNKNOWN, (
                "no evidence to attribute this change either way")
        out.append(ChangeVerdict(ch.field, ch.direction, verdict, reason, exp, scope_key))
    return out


# ---------------------------------------------------------------------------
# Failed-direction lockout
# ---------------------------------------------------------------------------
def failed_directions(attributed: list) -> set:
    """Collect the HARMFUL DirectionKeys from a flat list of ChangeVerdicts (across
    experiments). These are the (scope, field, direction) moves not to repeat."""
    return {v.direction_key() for v in attributed if v.verdict == VERDICT_HARMFUL}


def ineffective_directions(attributed: list) -> set:
    """DirectionKeys that were INEFFECTIVE — worth deprioritising (not hard-blocking)."""
    return {v.direction_key() for v in attributed if v.verdict == VERDICT_INEFFECTIVE}


def apply_direction_lockout(
    proposed_changes: list,
    blocked: set,
    scope: ExperimentScope,
    *,
    override_reasons: "dict | None" = None,
) -> tuple:
    """Split proposed changes into (allowed, blocked_out).

    ``proposed_changes`` is a list of dicts with at least ``field`` and a signed
    ``delta`` (or ``from``/``to``). A change is blocked when its (scope, field,
    direction) is in ``blocked`` — UNLESS ``override_reasons`` supplies a stronger
    new-evidence justification for that field (the loop can be overturned, not
    ossified). Each blocked item is returned with a human explanation.
    """
    scope_key = scope.key()
    overrides = override_reasons or {}
    allowed: list = []
    blocked_out: list = []
    for ch in proposed_changes or []:
        field = ch.get("field")
        direction = _change_direction(ch)
        key = DirectionKey(scope_key, field, direction)
        if direction != 0 and key in blocked and field not in overrides:
            _dirword = "increase" if direction > 0 else "decrease"
            blocked_out.append({
                **ch,
                "_lockout": True,
                "_lockout_reason": (
                    f"a previous {_dirword} of {str(field).replace('_', ' ')} at this "
                    "car/track/objective made the car worse — not repeating it without "
                    "stronger new evidence (run a different experiment or roll back)"),
            })
        else:
            allowed.append(ch)
    return allowed, blocked_out


def _change_direction(ch: dict) -> int:
    d = ch.get("delta")
    if d is not None:
        try:
            f = float(d)
            return 1 if f > 0 else -1 if f < 0 else 0
        except (TypeError, ValueError):
            pass
    return _direction(ch.get("from"), ch.get("to_clamped", ch.get("to")))


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Rule-level lockout from the persisted learning_outcomes (the store that already
# exists and is already scoped to car+track+layout). A rule whose recorded outcomes
# at this scope are decisively negative (worsened, never improved) is LOCKED OUT — not
# merely confidence-downgraded — so the app stops re-recommending a change that made
# the car worse. Overturned only by a later improved outcome.
# ---------------------------------------------------------------------------
LOCKOUT_MIN_WORSENED = 2   # need at least this many worsened records to hard-block


def blocked_rules_from_outcomes(outcomes: list, *, min_worsened: int = LOCKOUT_MIN_WORSENED) -> dict:
    """Return {rule_id: reason} for rules to LOCK OUT given persisted learning-outcome
    rows (each a dict with ``rule_id`` and ``verdict`` ∈ improved/worsened/neutral/…).

    A rule is blocked when it worsened the car at least ``min_worsened`` times at this
    scope AND was never recorded as improved. A single later ``improved`` verdict lifts
    the block (the loop can be overturned by new evidence, never ossified)."""
    counts: dict = {}   # rule_id -> {"worsened": n, "improved": n}
    for row in outcomes or []:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("rule_id") or "").strip()
        verdict = str(row.get("verdict") or "").strip().lower()
        if not rid or verdict not in ("worsened", "improved"):
            continue
        c = counts.setdefault(rid, {"worsened": 0, "improved": 0})
        c[verdict] += 1
    blocked: dict = {}
    for rid, c in counts.items():
        if c["improved"] == 0 and c["worsened"] >= min_worsened:
            blocked[rid] = (
                f"locked out — this change worsened the car {c['worsened']} time(s) at "
                "this car/track and never improved it; not repeating without new evidence")
    return blocked


# Map a rule to the (field, direction) it authors, so a blocked rule can also lock out
# the SAME field-direction produced by another author (the balance solver, driver-fit).
_RULE_DIR_CACHE: "dict | None" = None


def _delta_fn_direction(delta_fn: str) -> int:
    s = str(delta_fn or "").strip().lower()
    if not s or s == "noop":
        return 0
    if s.startswith(("increase", "raise")) or s.endswith(("_up", "_rear")):
        return +1
    if s.startswith("decrease") or s.endswith(("_down", "_front")):
        return -1
    return 0


def _rule_field_directions() -> dict:
    """{rule_id: (field, direction)} built once from the knowledge base delta_fn names."""
    global _RULE_DIR_CACHE
    if _RULE_DIR_CACHE is None:
        m: dict = {}
        try:
            from strategy.setup_knowledge_base import get_all_rules
            for r in get_all_rules():
                d = _delta_fn_direction(getattr(r, "delta_fn", ""))
                if d != 0 and getattr(r, "field", None):
                    m[r.rule_id] = (r.field, d)
        except Exception:
            m = {}
        _RULE_DIR_CACHE = m
    return _RULE_DIR_CACHE


def failed_directions_from_learning_outcomes(
    outcomes: list, scope: ExperimentScope,
    *, min_worsened: int = LOCKOUT_MIN_WORSENED,
) -> set:
    """DirectionKeys for field-directions that decisively worsened the car, derived from
    the persisted learning-outcome rows (rule_id + verdict) via the rule→direction map.
    Lets the field-level lockout cover EVERY author (rules, balance solver, driver-fit),
    not just the rule engine."""
    blocked = blocked_rules_from_outcomes(outcomes, min_worsened=min_worsened)
    res = _rule_field_directions()
    out: set = set()
    for rid in blocked:
        fd = res.get(rid)
        if fd:
            out.add(DirectionKey(scope.key(), fd[0], fd[1]))
    return out


def rollback_target(experiment: SetupExperiment, outcome: ExperimentOutcome) -> Optional[str]:
    """The parent setup id to roll back to when the experiment made the car worse
    overall (or every change in it was harmful). None when there is nothing to undo."""
    if experiment.parent_id is None:
        return None
    if outcome.overall == OUTCOME_WORSE:
        return experiment.parent_id
    return None


def rollback_from_lineage(lineage_rows: list) -> dict:
    """Given persisted setup_lineage rows (newest first, each a dict with id/parent_id/
    changes_json/outcome_verdict/label), decide whether to recommend a ROLLBACK.

    If the newest SCORED node worsened the car, recommend reverting its changes back to
    its parent. Returns ``{recommend_rollback, target_id, revert_changes, reason}``.
    """
    import json as _json
    rows = [r for r in (lineage_rows or []) if isinstance(r, dict)]
    for r in rows:   # newest first
        verdict = str(r.get("outcome_verdict") or "").strip().lower()
        if verdict == "":
            continue          # unscored — keep looking for the newest scored node
        if verdict == "worsened" and r.get("parent_id") is not None:
            try:
                changes = _json.loads(r.get("changes_json") or "[]")
            except Exception:
                changes = []
            revert = [{"field": c.get("field"), "from": c.get("to", c.get("to_clamped")),
                       "to": c.get("from")} for c in changes if isinstance(c, dict)
                      and c.get("field")]
            return {
                "recommend_rollback": True,
                "target_id": r.get("parent_id"),
                "revert_changes": revert,
                "reason": (f"Your last applied setup ({r.get('label') or r.get('id')}) "
                           "tested WORSE — roll back to the previous setup and try a "
                           "different direction."),
            }
        break             # newest scored node was fine → nothing to roll back
    return {"recommend_rollback": False, "target_id": None, "revert_changes": [], "reason": ""}


def rollback_advice(experiment: SetupExperiment, outcome: ExperimentOutcome,
                    attributed: "list | None" = None) -> dict:
    """A rollback recommendation surface: whether to revert, to what, and why."""
    target = rollback_target(experiment, outcome)
    harmful = [v for v in (attributed or []) if v.verdict == VERDICT_HARMFUL]
    if target is None and not harmful:
        return {"recommend_rollback": False, "target": None, "reason": "", "harmful": []}
    reason = (f"This setup ({experiment.label or experiment.experiment_id}) tested WORSE "
              f"than its parent — roll back to {target} and try a different direction."
              if target else
              "Some changes were harmful — consider reverting those fields to the parent.")
    return {
        "recommend_rollback": bool(target),
        "target": target,
        "reason": reason,
        "harmful": [{"field": v.field, "direction": v.direction, "reason": v.reason}
                    for v in harmful],
    }
