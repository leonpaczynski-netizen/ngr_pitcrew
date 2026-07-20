"""Setup Working-Window Learning — Layer 4 of the Race-Engineer Activation (Program 2, Phase 37).

Derives an evidence-backed working window for EVERY supported setup field (not just LSD) from the
EXACT-CONTEXT lineage: the current value, proven-good values/ranges and the context they worked in,
values associated with a regression, confidence, evidence count and independence, evidence-observed
field interactions, transfer limitations, and whether the field should currently be PROTECTED,
EXPLORED or AVOIDED.

Doctrine:
  * Do NOT average incompatible setups into a fake optimum. A window is the union of what was proven,
    with regression-associated values marked to avoid - never a mean.
  * The window is derived only from EXACT-CONTEXT evidence for one discipline. Qualifying and Race
    windows are therefore already separate (the scope discipline is part of exact-context identity);
    they merge only if evidence explicitly proves transferability, which this layer never assumes.
  * A single noisy record cannot overturn a mature converged window without a defined invalidation
    reason (a recorded regression at that value).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Authors NO setup value; recommends applying NOTHING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

SETUP_WORKING_WINDOW_VERSION = "setup_working_window_v1"
SETUP_WORKING_WINDOW_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{SETUP_WORKING_WINDOW_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class FieldStatus(str, Enum):
    PROTECT = "protect"          # converged proven window; keep within it
    EXPLORE = "explore"          # some evidence; a bounded experiment could still improve it
    AVOID = "avoid"              # a value/direction here is associated with a regression
    INSUFFICIENT = "insufficient"  # not enough exact-context evidence to form a window


_IMPROVED = ("confirmed_improvement", "partial_improvement", "improvement", "improved")
_CONF_RANK = {"": 0, "low": 1, "medium": 2, "high": 3, "very_high": 4}


@dataclass(frozen=True)
class WorkingWindow:
    field: str
    current_value: str
    proven_good_values: Tuple[str, ...]
    proven_context: str
    regression_values: Tuple[str, ...]
    window_min: str
    window_max: str
    confidence: str
    evidence_count: int
    independent_count: int
    interactions: Tuple[str, ...]
    transfer_limitation: str
    status: str
    reason: str

    def to_dict(self) -> dict:
        return {"field": self.field, "current_value": self.current_value,
                "proven_good_values": list(self.proven_good_values),
                "proven_context": self.proven_context,
                "regression_values": list(self.regression_values), "window_min": self.window_min,
                "window_max": self.window_max, "confidence": self.confidence,
                "evidence_count": self.evidence_count, "independent_count": self.independent_count,
                "interactions": list(self.interactions),
                "transfer_limitation": self.transfer_limitation, "status": self.status,
                "reason": self.reason}


@dataclass(frozen=True)
class SetupWorkingWindows:
    scope_fingerprint: str
    discipline: str
    windows: Tuple[dict, ...]
    empty_state: str
    doctrine: str
    content_fingerprint: str
    schema_version: int = SETUP_WORKING_WINDOW_SCHEMA
    eval_version: str = SETUP_WORKING_WINDOW_VERSION

    def to_dict(self) -> dict:
        return {"scope_fingerprint": self.scope_fingerprint, "discipline": self.discipline,
                "windows": [dict(w) for w in self.windows], "empty_state": self.empty_state,
                "doctrine": self.doctrine, "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_DOCTRINE = ("Windows are derived only from exact-context evidence for this one discipline; proven-good "
             "values are a union, never an average; regression-associated values are marked to avoid; a "
             "mature converged window is not overturned by one noisy record without a recorded "
             "regression at that value.")


def _order_key(rec: Mapping):
    return (_norm(rec.get("recorded_at")), _norm(rec.get("record_key")))


def build_setup_working_windows(scope_fingerprint: str, discipline: str,
                                exact_records: Optional[Sequence[Mapping]],
                                blocked_directions: Optional[Sequence[Mapping]] = None
                                ) -> SetupWorkingWindows:
    """Build per-field working windows from the EXACT-CONTEXT records. ``blocked_directions`` (from the
    Phase-37 outcome learning) marks fields whose recorded direction is a blocked regression. Pure;
    order-independent; never raises."""
    try:
        return _build(_norm(scope_fingerprint), _lc(discipline),
                      sorted([r for r in (exact_records or []) if isinstance(r, Mapping)],
                             key=_order_key),
                      [b for b in (blocked_directions or []) if isinstance(b, Mapping)])
    except Exception:  # pragma: no cover - defensive
        return SetupWorkingWindows(scope_fingerprint=_norm(scope_fingerprint),
                                   discipline=_lc(discipline), windows=(),
                                   empty_state="Working windows unavailable.", doctrine=_DOCTRINE,
                                   content_fingerprint=_fp({"error": True}))


def _minmax(values: Sequence[str]) -> Tuple[str, str]:
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return "", ""
    return (_norm(min(nums)), _norm(max(nums)))


def _build(scope_fp: str, discipline: str, ordered: List[Mapping],
           blocked: List[Mapping]) -> SetupWorkingWindows:
    blocked_fields = {(_norm(b.get("field")), _lc(b.get("direction"))) for b in blocked}
    blocked_field_names = {_norm(b.get("field")) for b in blocked}

    # accumulate per field
    fields: "Dict[str, dict]" = {}
    co_change: "Dict[str, set]" = {}
    for rec in ordered:
        status = _lc(rec.get("outcome_status"))
        improved = status in _IMPROVED and not (rec.get("new_regressions") or [])
        worsened = status == "regression" or bool(rec.get("new_regressions") or [])
        ctx = rec.get("context") or {}
        ctx_label = f"{_norm(ctx.get('track'))}/{_norm(ctx.get('layout_id'))}/{_norm(ctx.get('compound'))}"
        session = _norm(rec.get("test_session_id")) or _norm(rec.get("session_date")) \
            or _norm(rec.get("record_key"))
        changed = [(_norm(c.get("field")), _norm(c.get("to_value")), _lc(c.get("direction")))
                   for c in (rec.get("changes") or []) if _norm(c.get("field"))]
        for fld, to_val, _dirn in changed:
            f = fields.setdefault(fld, {"proven": [], "regression": [], "current": "", "sessions": set(),
                                        "count": 0, "conf": "", "ctx": ""})
            f["count"] += 1
            f["current"] = to_val or f["current"]
            f["sessions"].add(session)
            if _CONF_RANK.get(_lc(rec.get("confidence_level")), 0) > _CONF_RANK.get(f["conf"], 0):
                f["conf"] = _lc(rec.get("confidence_level"))
            if improved and to_val:
                f["proven"].append(to_val)
                f["ctx"] = ctx_label
            if worsened and to_val:
                f["regression"].append(to_val)
            co_change.setdefault(fld, set()).update(
                other for other, _t, _d in changed if other and other != fld)
        # window snapshots carry converged windows directly.
        for w in (rec.get("working_window_snapshot") or []):
            fld = _norm(w.get("field"))
            if not fld:
                continue
            f = fields.setdefault(fld, {"proven": [], "regression": [], "current": "", "sessions": set(),
                                        "count": 0, "conf": "", "ctx": ""})
            f["snap_min"] = _norm(w.get("min"))
            f["snap_max"] = _norm(w.get("max"))
            if _CONF_RANK.get(_lc(w.get("confidence")), 0) > _CONF_RANK.get(f["conf"], 0):
                f["conf"] = _lc(w.get("confidence"))
            f["independent"] = int(w.get("valid_experiment_count") or 0)

    windows: List[WorkingWindow] = []
    for fld in sorted(fields):
        f = fields[fld]
        proven = tuple(dict.fromkeys(f["proven"]))          # de-dup, preserve order
        regression = tuple(dict.fromkeys(f["regression"]))
        wmin, wmax = f.get("snap_min", ""), f.get("snap_max", "")
        if not (wmin or wmax) and proven:
            wmin, wmax = _minmax(proven)
        independent = int(f.get("independent") or len(f["sessions"]))
        count = int(f["count"])
        conf = f["conf"]
        has_regression = bool(regression) or fld in blocked_field_names
        converged = bool(proven) and (wmin != "" and wmax != "") and \
            _CONF_RANK.get(conf, 0) >= _CONF_RANK["medium"] and independent >= 2
        if has_regression:
            status = FieldStatus.AVOID
            reason = ("a value/direction for this field is associated with a recorded regression - "
                      "avoid it; stay within the proven-good range.")
        elif converged:
            status = FieldStatus.PROTECT
            reason = ("converged proven window from independent exact-context evidence - protect it; "
                      "keep changes inside the window.")
        elif proven:
            status = FieldStatus.EXPLORE
            reason = "some proven-good evidence but not yet converged - a bounded experiment could help."
        else:
            status = FieldStatus.INSUFFICIENT
            reason = "insufficient exact-context evidence to form a working window for this field."
        windows.append(WorkingWindow(
            field=fld, current_value=f["current"], proven_good_values=proven, proven_context=f["ctx"],
            regression_values=regression, window_min=wmin, window_max=wmax, confidence=conf,
            evidence_count=count, independent_count=independent,
            interactions=tuple(sorted(co_change.get(fld, set()))),
            transfer_limitation=("window is specific to this track, layout, compound and discipline; "
                                 "it does not transfer to another context without an explicit "
                                 "transfer decision."),
            status=status.value, reason=reason))

    empty = "" if windows else ("No exact-context working windows yet - no applied field changes have "
                                "been reviewed in this exact context.")
    fp = _fp({"scope": scope_fp, "discipline": discipline,
              "windows": [(w.field, w.status, w.window_min, w.window_max, w.confidence,
                           list(w.proven_good_values), list(w.regression_values)) for w in windows]})
    return SetupWorkingWindows(scope_fingerprint=scope_fp, discipline=discipline,
                               windows=tuple(w.to_dict() for w in windows), empty_state=empty,
                               doctrine=_DOCTRINE, content_fingerprint=fp)


def working_window_versions() -> dict:
    return {"setup_working_window": SETUP_WORKING_WINDOW_VERSION,
            "schema": SETUP_WORKING_WINDOW_SCHEMA}
