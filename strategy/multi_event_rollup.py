"""Multi-Event Roll-Up — aggregate compatible event contexts (Program 2, Phase 22).

A deterministic, READ-ONLY grouping of per-event knowledge so that knowledge learned across
several events (same car / discipline / GT7 version / driver, different tracks) can be viewed as
one programme. It NEVER merges unlike contexts: incompatible events are kept separate and the
reason is made explicit. It merges only the campaign records; it computes no new knowledge.

Compatibility key = (car, discipline, gt7_version, driver). Track and layout MAY differ (that is
the point of multi-event); a difference in car / discipline / version / driver keeps events
apart. Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock;
deterministic; never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

MULTI_EVENT_ROLLUP_VERSION = "multi_event_rollup_v1"

# The context fields that MUST match for two events to roll together.
COMPATIBILITY_FIELDS = ("car", "discipline", "gt7_version", "driver")


def _lc(v) -> str:
    return str(v if v is not None else "").strip().lower()


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


@dataclass(frozen=True)
class EventRollupGroup:
    compatibility_key: dict
    contexts: Tuple[dict, ...]           # the event contexts merged into this group
    tracks: Tuple[str, ...]
    campaigns: Tuple[dict, ...]          # merged, deduped campaign records
    merge_reason: str
    is_primary: bool

    def to_dict(self) -> dict:
        return {"compatibility_key": dict(self.compatibility_key),
                "contexts": [dict(c) for c in self.contexts], "tracks": list(self.tracks),
                "campaigns": [dict(c) for c in self.campaigns], "merge_reason": self.merge_reason,
                "is_primary": self.is_primary}


@dataclass(frozen=True)
class EventRollup:
    primary_group: Optional[dict]
    other_groups: Tuple[dict, ...]
    excluded_reasons: Tuple[dict, ...]   # why each non-primary group is NOT merged with primary
    eval_version: str = MULTI_EVENT_ROLLUP_VERSION

    def to_dict(self) -> dict:
        return {"primary_group": (dict(self.primary_group) if self.primary_group else None),
                "other_groups": [dict(g) for g in self.other_groups],
                "excluded_reasons": [dict(e) for e in self.excluded_reasons],
                "eval_version": self.eval_version}


def _compat_key(ctx: Mapping) -> tuple:
    return tuple(_lc(ctx.get(f)) for f in COMPATIBILITY_FIELDS)


def _key_dict(ctx: Mapping) -> dict:
    return {f: _norm(ctx.get(f)) for f in COMPATIBILITY_FIELDS}


def build_rollup(events: Sequence[Mapping],
                 primary_context: Optional[Mapping] = None) -> EventRollup:
    """Group per-event knowledge into compatibility groups. ``events`` is a list of
    ``{"context": {...}, "campaigns": [...]}`` dicts. The group matching ``primary_context``
    (or the first group) is the primary; others are reported with the reason they differ.
    Deterministic; merges campaign records only; never raises."""
    try:
        return _build([e for e in (events or []) if isinstance(e, Mapping)],
                      primary_context if isinstance(primary_context, Mapping) else None)
    except Exception:   # never raise into the caller
        return EventRollup(primary_group=None, other_groups=(), excluded_reasons=())


def _build(events: List[Mapping], primary_context: Optional[Mapping]) -> EventRollup:
    # group events by compatibility key, preserving first-seen order.
    order: List[tuple] = []
    groups: dict = {}
    for ev in events:
        ctx = ev.get("context") if isinstance(ev.get("context"), Mapping) else {}
        key = _compat_key(ctx)
        if key not in groups:
            groups[key] = {"key_dict": _key_dict(ctx), "contexts": [], "campaigns": [], "seen": set()}
            order.append(key)
        g = groups[key]
        g["contexts"].append(_ctx_summary(ctx))
        for c in (ev.get("campaigns") or []):
            if not isinstance(c, Mapping):
                continue
            cid = _norm(c.get("campaign_id"))
            if cid and cid in g["seen"]:
                continue
            g["seen"].add(cid)
            g["campaigns"].append(dict(c))

    primary_key = _compat_key(primary_context) if primary_context is not None else (
        order[0] if order else None)

    built = {}
    for key in order:
        g = groups[key]
        tracks = _sorted_unique(ctx.get("track") for ctx in g["contexts"])
        is_primary = key == primary_key
        merge_reason = _merge_reason(g["key_dict"], len(g["contexts"]), tracks)
        built[key] = EventRollupGroup(
            compatibility_key=g["key_dict"], contexts=tuple(g["contexts"]),
            tracks=tuple(tracks), campaigns=tuple(g["campaigns"]),
            merge_reason=merge_reason, is_primary=is_primary).to_dict()

    primary = built.get(primary_key)
    others = [built[k] for k in order if k != primary_key]
    excluded = [_exclusion(built[k]["compatibility_key"], primary["compatibility_key"] if primary
                           else {}) for k in order if k != primary_key]
    return EventRollup(primary_group=primary, other_groups=tuple(others),
                       excluded_reasons=tuple(excluded))


def _ctx_summary(ctx: Mapping) -> dict:
    return {f: _norm(ctx.get(f)) for f in
            ("car", "track", "layout", "discipline", "gt7_version", "driver")}


def _merge_reason(key_dict: dict, n_contexts: int, tracks: List[str]) -> str:
    shared = ", ".join(f"{k}={v}" for k, v in key_dict.items() if v)
    if n_contexts <= 1:
        return f"single event ({shared or 'unscoped'})"
    return (f"{n_contexts} events merged - they share {shared or 'the compatibility key'} "
            f"(tracks: {', '.join(t for t in tracks if t) or '-'})")


def _exclusion(other_key: dict, primary_key: dict) -> dict:
    diffs = [f for f in COMPATIBILITY_FIELDS
             if _lc(other_key.get(f)) != _lc(primary_key.get(f))]
    reason = ("differs in " + ", ".join(f"{f} ({other_key.get(f) or '-'} vs "
              f"{primary_key.get(f) or '-'})" for f in diffs)) if diffs \
        else "same compatibility key (kept separate only if unmatched)"
    return {"compatibility_key": dict(other_key), "reason": reason, "differing_fields": diffs}


def _sorted_unique(items) -> List[str]:
    return sorted({_norm(x) for x in items if _norm(x)})


def rollup_versions() -> dict:
    return {"multi_event_rollup": MULTI_EVENT_ROLLUP_VERSION}
