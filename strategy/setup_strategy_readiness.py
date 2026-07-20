"""Setup-lock & strategy-finalisation readiness (Program 2, Phase 54).

Derives the Command Centre's setup-lock and strategy-finalisation READINESS from canonical authorities:
setup convergence + the persisted lock record, and strategy maturity + the persisted finalisation record.
It distinguishes readiness from the committed decision — LOCK_READY is not LOCKED and FINALISATION_READY
is not FINALISED. It commits nothing; it only reports what an explicit user action would be permitted to
do.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

from strategy.setup_convergence import SetupConvergenceState
from strategy.setup_lock import lock_permitted
from strategy.strategy_maturity import StrategyMaturity

SETUP_STRATEGY_READINESS_VERSION = "setup_strategy_readiness_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{SETUP_STRATEGY_READINESS_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


def _to_convergence(state) -> Optional[SetupConvergenceState]:
    try:
        return SetupConvergenceState(str(state))
    except Exception:
        return None


@dataclass(frozen=True)
class SetupLockReadinessState:
    discipline: str
    convergence_state: str
    lock_eligible: bool
    is_locked: bool
    reopen_eligible: bool
    blockers: Tuple[str, ...]
    confidence: str
    rollback_fingerprint: str

    def as_payload(self) -> dict:
        return {"discipline": _norm(self.discipline), "convergence_state": _norm(self.convergence_state),
                "lock_eligible": bool(self.lock_eligible), "is_locked": bool(self.is_locked),
                "reopen_eligible": bool(self.reopen_eligible),
                "blockers": sorted(_norm(b) for b in self.blockers if _norm(b)),
                "confidence": _norm(self.confidence), "rollback_fingerprint": _norm(self.rollback_fingerprint)}


def derive_setup_lock_readiness(discipline: str, convergence_state: str, *, is_locked: bool = False,
                                reopen_eligible: bool = False, confidence: str = "",
                                rollback_fingerprint: str = "") -> SetupLockReadinessState:
    """Lock is ELIGIBLE (not locked) when the convergence state permits it AND it is not already locked.
    A LOCK_READY convergence never implies LOCKED — locking requires an explicit confirmation elsewhere."""
    conv = _to_convergence(convergence_state)
    permitted = bool(conv is not None and lock_permitted(conv))
    eligible = permitted and not is_locked
    blockers = []
    if not permitted and not is_locked:
        blockers.append(f"convergence '{_norm(convergence_state)}' does not yet permit a lock")
    if is_locked:
        blockers.append("already locked")
    return SetupLockReadinessState(
        discipline=_norm(discipline), convergence_state=_norm(convergence_state), lock_eligible=eligible,
        is_locked=bool(is_locked), reopen_eligible=bool(reopen_eligible), blockers=tuple(blockers),
        confidence=_norm(confidence), rollback_fingerprint=_norm(rollback_fingerprint))


@dataclass(frozen=True)
class StrategyFinalisationReadinessState:
    maturity: str
    finalisation_eligible: bool
    is_finalised: bool
    missing_evidence: Tuple[str, ...]

    def as_payload(self) -> dict:
        return {"maturity": _norm(self.maturity), "finalisation_eligible": bool(self.finalisation_eligible),
                "is_finalised": bool(self.is_finalised),
                "missing_evidence": sorted(_norm(m) for m in self.missing_evidence if _norm(m))}


def derive_strategy_finalisation_readiness(maturity: str, *, is_finalised: bool = False,
                                           missing_evidence: Sequence[str] = ()) -> StrategyFinalisationReadinessState:
    """Finalisation is ELIGIBLE (not finalised) when maturity is FINALISATION_READY AND it is not already
    finalised. FINALISATION_READY never implies FINALISED — finalising requires explicit confirmation."""
    ready = _norm(maturity) == StrategyMaturity.FINALISATION_READY.value
    eligible = ready and not is_finalised
    return StrategyFinalisationReadinessState(
        maturity=_norm(maturity), finalisation_eligible=eligible, is_finalised=bool(is_finalised),
        missing_evidence=tuple(missing_evidence))


@dataclass(frozen=True)
class SetupStrategyReadiness:
    lock_states: Tuple[SetupLockReadinessState, ...]
    strategy: StrategyFinalisationReadinessState
    lock_ready_disciplines: Tuple[str, ...]
    strategy_final_ready: bool
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"lock_states": [s.as_payload() for s in self.lock_states],
                "strategy": self.strategy.as_payload(),
                "lock_ready_disciplines": sorted(self.lock_ready_disciplines),
                "strategy_final_ready": bool(self.strategy_final_ready)}


def build_setup_strategy_readiness(
    setup_convergence: dict,
    strategy_maturity: str,
    *,
    locked_disciplines: Sequence[str] = (),
    strategy_finalised: bool = False,
    missing_evidence: Sequence[str] = (),
    reopen_eligible_disciplines: Sequence[str] = (),
) -> SetupStrategyReadiness:
    """Assemble per-discipline lock readiness + strategy finalisation readiness. ``setup_convergence`` is
    the {base/qualifying/race: convergence_state} mapping from the preparation report; the locked and
    finalised flags come from the persisted lock/strategy records."""
    locked = {_norm(d).lower() for d in locked_disciplines}
    reopen = {_norm(d).lower() for d in reopen_eligible_disciplines}
    lock_states = []
    for disc in ("base", "qualifying", "race"):
        conv = _norm((setup_convergence or {}).get(disc))
        if not conv:
            continue
        lock_states.append(derive_setup_lock_readiness(
            disc, conv, is_locked=(disc in locked), reopen_eligible=(disc in reopen)))
    strat = derive_strategy_finalisation_readiness(strategy_maturity, is_finalised=strategy_finalised,
                                                   missing_evidence=missing_evidence)
    ready_disc = tuple(s.discipline for s in lock_states if s.lock_eligible)
    r = SetupStrategyReadiness(tuple(lock_states), strat, ready_disc, strat.finalisation_eligible, "")
    return SetupStrategyReadiness(r.lock_states, r.strategy, r.lock_ready_disciplines,
                                  r.strategy_final_ready, _fp(r.as_payload()))
