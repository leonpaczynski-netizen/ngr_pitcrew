"""Phase 14 — candidate comparison (pure, Qt-free).

Lays the setup options the brain reasoned over side-by-side, per field, so the
driver can see WHY the recommended value sits where it does: current vs the proven
historical value vs the from-scratch baseline vs the rule-engine recommendation
(and race/quali columns when those are supplied).

It collates candidate value-maps that were computed elsewhere — it never generates
a setup, never fabricates a column, and marks any candidate that wasn't produced as
unavailable rather than inventing values. Rows are emitted only for fields at least
one available candidate carries a numeric value for.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field


@dataclass(frozen=True)
class CandidateColumn:
    name: str            # stable key, e.g. "current" / "historical" / "recommended"
    label: str           # human label, e.g. "Proven (history)"
    source: str          # provenance / confidence note
    available: bool
    values: dict = _dc_field(default_factory=dict)


@dataclass(frozen=True)
class FieldRow:
    field: str
    values: dict         # column name -> value (only available columns w/ a value)
    differs: bool        # True when available candidates disagree on this field


@dataclass(frozen=True)
class CandidateComparison:
    columns: list        # list[CandidateColumn] (available only, display order)
    rows: list           # list[FieldRow]

    def is_empty(self) -> bool:
        return not self.rows


def make_candidate(name: str, label: str, values, *, source: str = "",
                   available: "bool | None" = None) -> CandidateColumn:
    """Build a candidate column from a values dict. ``available`` defaults to
    'has at least one numeric value' when not stated explicitly."""
    vals = {}
    for k, v in (values or {}).items():
        n = _num(v)
        if n is not None:
            vals[k] = n
    avail = bool(vals) if available is None else bool(available)
    return CandidateColumn(name=name, label=label, source=source,
                           available=avail, values=vals)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _close(a, b) -> bool:
    return abs(a - b) <= 1e-9


def build_candidate_comparison(candidates: "list[CandidateColumn]",
                               fields: "list[str] | None" = None) -> CandidateComparison:
    """Assemble a per-field comparison across the available candidate columns.

    Only available candidates are shown. A field row is emitted when ≥1 available
    candidate has a numeric value for it (union of fields, or the given ``fields``
    order). ``differs`` is True when the available candidates disagree."""
    avail = [c for c in (candidates or []) if c.available and c.values]
    if not avail:
        return CandidateComparison([], [])

    if fields:
        field_order = [f for f in fields]
        seen = set(field_order)
        for c in avail:
            for f in c.values:
                if f not in seen:
                    seen.add(f)
                    field_order.append(f)
    else:
        field_order = []
        seen = set()
        for c in avail:
            for f in c.values:
                if f not in seen:
                    seen.add(f)
                    field_order.append(f)

    rows = []
    for f in field_order:
        row_vals = {c.name: c.values[f] for c in avail if f in c.values}
        if not row_vals:
            continue
        present = list(row_vals.values())
        differs = any(not _close(present[0], v) for v in present[1:])
        rows.append(FieldRow(field=f, values=row_vals, differs=differs))

    return CandidateComparison(columns=avail, rows=rows)


def candidate_comparison_to_json(cmp: CandidateComparison) -> dict:
    """Serialise a CandidateComparison to the response dict shape."""
    return {
        "columns": [
            {"name": c.name, "label": c.label, "source": c.source}
            for c in cmp.columns
        ],
        "rows": [
            {"field": r.field, "values": dict(r.values), "differs": r.differs}
            for r in cmp.rows
        ],
    }
